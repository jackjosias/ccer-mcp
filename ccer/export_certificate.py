"""Read-only post-export certificate for MP4 files actually rendered by Concat.

The GUI export is performed separately: this module NEVER edits media, drives
Concat, transcodes, writes screenshots, or claims semantic/creative QA.
"""
import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
from pathlib import Path

if __package__ in (None, ""):
    import sys
    # Direct CLI from the isolated, assigned WCER test worktree.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from ccer.controls import PolicyError, media_probe
else:
    from .controls import PolicyError, media_probe


def timeline(project):
    clips = project.get("clips") if isinstance(project, dict) else None
    media = project.get("media") if isinstance(project, dict) else None
    if not isinstance(clips, list) or not 1 <= len(clips) <= 5000 or not isinstance(media, list):
        raise PolicyError("CCER: invalid native project timeline")
    media_ids = {m.get("id") for m in media if isinstance(m, dict)}
    intervals, videos = [], []
    for clip in clips:
        if not isinstance(clip, dict):
            raise PolicyError("CCER: invalid timeline clip")
        try:
            start, length = float(clip["start"]), float(clip["duration"])
        except (TypeError, ValueError, KeyError) as exc:
            raise PolicyError("CCER: invalid clip timing") from exc
        if not all(map(math.isfinite, (start, length))) or start < 0 or not 0 < length <= 3600:
            raise PolicyError("CCER: invalid clip timing")
        intervals.append((start, start + length))
        if clip.get("kind") == "video":
            if clip.get("mediaId") not in media_ids:
                raise PolicyError("CCER: video references absent source media")
            videos.append((start, start + length))
    last = 0.0
    for start, end in sorted(intervals):
        if start > last + 0.04:
            raise PolicyError("CCER: timeline contains an uncovered gap")
        last = max(last, end)
    if not videos:
        raise PolicyError("CCER: timeline contains no real video")
    return {"duration": last, "clipCount": len(clips), "videoIntervals": sorted(videos)}


def _run(args, timeout):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PolicyError("CCER: media QA subprocess did not finish") from exc
    if r.returncode:
        raise PolicyError("CCER: media decode/inspection failed: " + r.stderr[-200:])
    return r.stderr


def certify(project_path, exported_mp4, *, max_seconds=300, require_audio=True):
    project_path, exported_mp4 = Path(project_path), Path(exported_mp4)
    if (not project_path.is_file() or not exported_mp4.is_file()
            or project_path.is_symlink() or exported_mp4.is_symlink()):
        raise PolicyError("CCER: missing or untrusted project/export path")
    if exported_mp4.suffix.lower() != ".mp4" or not shutil.which("ffmpeg"):
        raise PolicyError("CCER: requires an existing MP4 and FFmpeg")
    if project_path.stat().st_size > 10_000_000:
        raise PolicyError("CCER: project manifest too large")
    try:
        project = json.loads(project_path.read_text(encoding="utf-8"))
    except (ValueError, OSError, UnicodeError) as exc:
        raise PolicyError("CCER: invalid native Concat JSON") from exc
    expected = timeline(project)
    if not isinstance(max_seconds, (float, int)) or not math.isfinite(max_seconds) or not 1 <= max_seconds <= 3600:
        raise PolicyError("CCER: invalid duration budget")
    if expected["duration"] > max_seconds:
        raise PolicyError("CCER: timeline exceeds certification budget")

    signature = (exported_mp4.stat().st_size, exported_mp4.stat().st_mtime_ns)
    meta = media_probe(exported_mp4)  # reuse existing FFprobe validation
    videos = [s for s in meta["streams"] if s.get("codec_type") == "video"]
    audios = [s for s in meta["streams"] if s.get("codec_type") == "audio"]
    if len(videos) != 1 or (require_audio and len(audios) != 1):
        raise PolicyError("CCER: missing/duplicate required AV streams")
    v = videos[0]
    if v.get("codec_name") != "h264" or (v.get("width"), v.get("height")) != (1920, 1080):
        raise PolicyError("CCER: H.264 1080p video not certified")
    try:
        n, d = v["avg_frame_rate"].split("/")
        fps, duration = int(n) / int(d), float(meta["format"]["duration"])
    except (KeyError, ValueError, TypeError, ZeroDivisionError) as exc:
        raise PolicyError("CCER: frame rate or duration unknown") from exc
    if not math.isfinite(duration) or abs(duration - expected["duration"]) > 0.12 or abs(fps - 24) > 0.05:
        raise PolicyError("CCER: export truncated or frame rate mismatch")
    if require_audio and (audios[0].get("codec_name") != "aac"
                          or int(audios[0].get("sample_rate", 0)) != 48000):
        raise PolicyError("CCER: expected native AAC 48 kHz")
    _run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
          "-i", str(exported_mp4), "-f", "null", "-"],
         timeout=max(75, min(900, int(duration * 20 + 35))))
    mean_db = None
    if require_audio:
        begin, end = expected["videoIntervals"][-1]
        output = _run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "info",
                       "-ss", str(begin), "-t", str(end - begin),
                       "-i", str(exported_mp4), "-map", "0:a:0",
                       "-af", "volumedetect", "-f", "null", "-"],
                      timeout=max(45, min(600, int((end - begin) * 12 + 30))))
        levels = re.findall(r"mean_volume:\s*(-?(?:inf|\d+(?:\.\d+)?)) dB", output)
        if not levels:
            raise PolicyError("CCER: no measurable output audio")
        mean_db = float(levels[-1])
        if not math.isfinite(mean_db) or mean_db <= -65:
            raise PolicyError("CCER: expected source segment is silent")
    if (exported_mp4.stat().st_size, exported_mp4.stat().st_mtime_ns) != signature:
        raise PolicyError("CCER: export changed during verification")
    sha = hashlib.sha256()
    with exported_mp4.open("rb") as source:
        for block in iter(lambda: source.read(1048576), b""):
            sha.update(block)
    if (exported_mp4.stat().st_size, exported_mp4.stat().st_mtime_ns) != signature:
        raise PolicyError("CCER: export changed while hashing")
    return {"contract": "CCER_NATIVE_EXPORT_CERTIFICATE_V1", "passed": True,
            "clipCount": expected["clipCount"], "videoClipCount": len(expected["videoIntervals"]),
            "timelineSeconds": expected["duration"], "exportSeconds": duration,
            "resolution": "1920x1080", "fps": round(fps, 3),
            "videoCodec": "h264", "audioCodec": "aac" if audios else None,
            "audioMeanDb": mean_db, "decode": "PASS",
            "sha256": sha.hexdigest(), "bytes": signature[0], "readOnly": True,
            "scope": "technical QA, not semantic or visual editorial approval"}


def main():
    p = argparse.ArgumentParser(description="Verify existing visible-Concat export, read-only")
    p.add_argument("--project", required=True)
    p.add_argument("--export", required=True)
    p.add_argument("--max-seconds", type=float, default=300)
    args = p.parse_args()
    print(json.dumps(certify(args.project, args.export, max_seconds=args.max_seconds)))


if __name__ == "__main__":
    main()
