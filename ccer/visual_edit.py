"""Local FFmpeg visual tools: measured color, safe reframing, two-shot transitions."""
from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .controls import PolicyError, media_probe
from .quality import FORMATS, transcode
from .temporal_seek import start_args


def _finite(value, label, lo, hi):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not lo <= value <= hi:
        raise PolicyError(f"{label} outside [{lo}, {hi}] or not finite")
    return float(value)


def _video(path):
    p = Path(path)
    report = media_probe(p)
    if not any(s.get("codec_type") == "video" for s in report["streams"]):
        raise PolicyError("Media has no video stream")
    return p, report


def _new_output(path):
    p = Path(path)
    if p.suffix.lower() != ".mp4" or not p.parent.is_dir():
        raise PolicyError("Output must be .mp4 in existing directory")
    if p.exists() or p.is_symlink():
        raise PolicyError("Refuse output overwrite")
    if shutil.disk_usage(p.parent).free < 512*1024*1024:
        raise PolicyError("At least 512 MiB free space required")
    return p


def _render(arguments, output, expected, *, timeout=240):
    dest = _new_output(output)
    with tempfile.TemporaryDirectory(prefix=".ccer-visual-", dir=dest.parent) as tmpdir:
        temp = Path(tmpdir) / "movie.mp4"
        task = subprocess.run(
            ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
             "-filter_complex_threads", "1", *arguments, str(temp)],
            capture_output=True, text=True, timeout=timeout)
        if task.returncode:
            raise PolicyError("FFmpeg visual rendering failed: " + task.stderr[-500:])
        info = media_probe(temp)
        vid = next((s for s in info["streams"] if s.get("codec_type") == "video"), {})
        try:
            duration = float(info["format"]["duration"])
        except (ValueError, TypeError) as exc:
            raise PolicyError("Rendered duration unavailable") from exc
        if (vid.get("width"), vid.get("height")) != expected[:2]:
            raise PolicyError("Output dimensions do not match request")
        if abs(duration - expected[2]) > .45:
            raise PolicyError("Rendered duration does not match request")
        if dest.exists():
            raise PolicyError("Output appeared during render")
        os.link(temp, dest)
        return {"file": str(dest), "bytes": dest.stat().st_size,
                "duration": duration, "width": expected[0], "height": expected[1],
                "verified": True}


def color_report(source, *, seconds=30, interval=1, start_seconds=0):
    seconds = _finite(seconds, "seconds", 1, 300)
    interval = _finite(interval, "interval", .2, 10)
    path, metadata = _video(source)
    seek, start = start_args(start_seconds)
    try:
        length = min(seconds, float(metadata["format"]["duration"]) - start)
    except (ValueError, TypeError) as exc:
        raise PolicyError("Unknown source duration") from exc
    if length <= 0:
        raise PolicyError("Requested color window starts beyond media duration")
    sample = max(interval, length / 35)
    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "info",
         *seek, "-i", str(path), "-t", str(length),
         "-vf", f"fps=1/{sample:.6f},signalstats,metadata=mode=print",
         "-frames:v", "35", "-an", "-f", "null", "-"],
        text=True, capture_output=True, timeout=max(40, int(length * 4)))
    if proc.returncode:
        raise PolicyError("FFmpeg color sampling failed: " + proc.stderr[-350:])
    fields = ("YAVG", "YMIN", "YMAX", "SATAVG", "UAVG", "VAVG")
    metrics = {}
    for field in fields:
        values = [float(t) for t in re.findall(
            rf"lavfi\.signalstats\.{field}=([0-9]+(?:\.[0-9]+)?)", proc.stderr)]
        if values:
            metrics[field] = {"mean": round(sum(values)/len(values), 2),
                              "min": round(min(values), 2),
                              "max": round(max(values), 2)}
    if not metrics.get("YAVG"):
        raise PolicyError("No FFmpeg signalstats frames available")
    y = metrics["YAVG"]["mean"]
    return {"file": str(path), "startSeconds": start, "sampledFrames": len(re.findall(r"lavfi\.signalstats\.YAVG=", proc.stderr)),
            "metrics": metrics, "lumaFlag": "dark" if y < 40 else "bright" if y > 215 else "normal_range",
            "colorGradingCertified": False, "requiresEditorialReview": True,
            "method": "8-bit YUV signalstats, not a perceptual quality score"}


def reframe(engine, source, output, *, profile="vertical-preview", mode="cover",
            focus_x=.5, focus_y=.5):
    a = engine.path(source, must_exist=True)
    b = engine.path(output)
    _, metadata = _video(a)
    if profile not in FORMATS or mode not in ("cover", "contain"):
        raise PolicyError("Unknown format or reframing mode")
    x = _finite(focus_x, "focusX", 0, 1)
    y = _finite(focus_y, "focusY", 0, 1)
    if a.resolve() == b.resolve():
        raise PolicyError("In-place modifications refused")
    if mode == "contain":
        return {**transcode(a, b, profile), "mode": mode}
    width, height = FORMATS[profile]
    try:
        duration = float(metadata["format"]["duration"])
    except (ValueError, TypeError) as exc:
        raise PolicyError("Duration unavailable") from exc
    if not 0 < duration <= 3600:
        raise PolicyError("Source duration out of range")
    vf = (f"scale={width}:{height}:force_original_aspect_ratio=increase:force_divisible_by=2,"
          f"crop={width}:{height}:(iw-ow)*{x:.6f}:(ih-oh)*{y:.6f},setsar=1")
    out = _render(["-i", str(a), "-vf", vf, "-map", "0:v:0", "-map", "0:a:0?",
                   "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                   "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
                   "-movflags", "+faststart", "-t", f"{duration:.5f}"],
                  b, (width, height, duration), timeout=1800)
    return {**out, "mode": mode, "profile": profile, "focus": {"x": x, "y": y}}


def transition(engine, first, second, output, *, profile="landscape-preview",
               scene_seconds=2., overlap_seconds=.5, kind="fade", music=None):
    a = engine.path(first, must_exist=True)
    b = engine.path(second, must_exist=True)
    _video(a)
    _video(b)
    dest = engine.path(output)
    if profile not in FORMATS:
        raise PolicyError("Unknown profile")
    if kind not in ("fade", "wipeleft", "wiperight", "slideleft", "slideright"):
        raise PolicyError("Unsupported transition kind")
    seconds = _finite(scene_seconds, "sceneSeconds", .6, 20)
    overlap = _finite(overlap_seconds, "overlapSeconds", .1, 2.5)
    if overlap >= seconds:
        raise PolicyError("Transition must be shorter than a scene")
    width, height = FORMATS[profile]
    duration = 2*seconds - overlap
    fps = 24
    graph = []
    for i in (0, 1):
        graph.append(
            f"[{i}:v]fps={fps},scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,"
            f"trim=duration={seconds:.4f},setpts=PTS-STARTPTS,format=yuv420p[v{i}]")
    graph.append(f"[v0][v1]xfade=transition={kind}:duration={overlap:.4f}:offset={seconds-overlap:.4f}[v]")
    command = ["-stream_loop", "-1", "-i", str(a),
               "-stream_loop", "-1", "-i", str(b)]
    if music:
        soundtrack = engine.path(music, must_exist=True)
        meta = media_probe(soundtrack)
        if not any(s.get("codec_type") == "audio" for s in meta["streams"]):
            raise PolicyError("Selected external soundtrack has no audio")
        command.extend(["-i", str(soundtrack)])
    command.extend(["-filter_complex", ";".join(graph), "-map", "[v]"])
    if music:
        command.extend(["-map", "2:a:0", "-c:a", "aac", "-b:a", "160k"])
    else:
        command.append("-an")
    command.extend(["-t", f"{duration:.5f}", "-r", "24", "-c:v", "libx264",
                    "-preset", "ultrafast", "-crf", "23", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart"])
    result = _render(command, dest, (width, height, duration), timeout=300)
    return {**result, "transition": kind, "overlapSeconds": overlap,
            "originalAudioPreserved": False, "externalSoundtrack": bool(music)}
