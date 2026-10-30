"""Technical shot intelligence, cut detection, and visually inspectable contact sheets."""
from __future__ import annotations
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path

from .controls import PolicyError, media_probe
from .temporal_seek import start_args, absolute


def inspect_shots(sources):
    if not isinstance(sources, list) or not 1 <= len(sources) <= 200:
        raise PolicyError("Supply 1..200 media files")
    results = []
    for source in sources:
        report = media_probe(source)
        video = next((s for s in report["streams"] if s.get("codec_type") == "video"), None)
        if not video:
            results.append({"file": source, "eligible": False, "reason": "no_video"})
            continue
        w, h = int(video.get("width", 0)), int(video.get("height", 0))
        area = w * h
        try:
            duration = float(report["format"]["duration"])
        except (ValueError, TypeError):
            duration = 0.
        score = min(100, round(25 * min(1., area/(1920*1080)) +
                               30 * min(1., duration/8.) +
                               45 * (1 if video.get("codec_name") else 0), 1))
        results.append({"file": str(source), "eligible": bool(area and duration),
                        "technicalScore": score, "width": w, "height": h,
                        "duration": duration, "codec": video.get("codec_name")})
    results.sort(key=lambda item: item.get("technicalScore", -1), reverse=True)
    return {"assets": results, "scoring": "technical metadata only; no semantic/aesthetic judgment"}


def scene_cuts(source, threshold=0.32, seconds=120, *, start_seconds=0):
    if not shutil.which("ffmpeg"):
        raise PolicyError("FFmpeg unavailable")
    if not isinstance(threshold, (int, float)) or not 0.05 <= threshold <= 0.95:
        raise PolicyError("Scene threshold must be 0.05..0.95")
    if not isinstance(seconds, int) or not 1 <= seconds <= 1800:
        raise PolicyError("Analyzed time must be 1..1800 seconds")
    media_probe(source)
    seek, start = start_args(start_seconds)
    result = subprocess.run([
        "ffmpeg", "-nostdin", "-hide_banner", *seek, "-i", str(source),
        "-t", str(seconds), "-vf",
        f"setpts=PTS-STARTPTS,select=gt(scene\\,{threshold}),showinfo", "-an", "-f", "null", "-"],
        capture_output=True, text=True, timeout=max(60, seconds * 4))
    if result.returncode:
        raise PolicyError("Scene analysis failed: " + result.stderr[-350:])
    stamps = [absolute(t, start) for t in re.findall(r"pts_time:([\d.]+)", result.stderr)]
    return {"file": str(source), "threshold": threshold, "startSeconds": start,
            "cutsSeconds": stamps, "count": len(stamps)}


def contact_sheet(source, output, *, interval=2):
    if not shutil.which("ffmpeg"):
        raise PolicyError("FFmpeg unavailable")
    media_probe(source)
    if not isinstance(interval, (int, float)) or not 0.2 <= interval <= 60:
        raise PolicyError("Interval must be 0.2..60")
    out = Path(output)
    if out.exists() or out.is_symlink():
        raise PolicyError("Refuse replacing existing contact sheet")
    if out.suffix.lower() != ".png" or not out.parent.is_dir():
        raise PolicyError("Output must be PNG in existing directory")
    tmp = out.with_name(out.stem + "." + uuid.uuid4().hex + ".tmp.png")
    try:
        command = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                   "-i", str(source), "-vf",
                   f"fps=1/{float(interval)},scale=320:-1,tile=3x3:nb_frames=9:padding=4:margin=4",
                   "-frames:v", "1", "-y", str(tmp)]
        done = subprocess.run(command, capture_output=True, text=True, timeout=180)
        if done.returncode or not tmp.is_file():
            raise PolicyError("Contact sheet generation failed: " + done.stderr[-350:])
        os.link(tmp, out)
        return {"file": str(out), "bytes": out.stat().st_size}
    finally:
        tmp.unlink(missing_ok=True)
