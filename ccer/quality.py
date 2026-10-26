"""Media quality gates and professional multi-format delivery, using local FFmpeg."""
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path

from .controls import PolicyError, media_probe
from .temporal_seek import start_args, absolute


FORMATS = {
    "vertical": (1080, 1920),
    "square": (1080, 1080),
    "landscape": (1920, 1080),
    "vertical-preview": (360, 640),
    "square-preview": (320, 320),
    "landscape-preview": (640, 360),
}


def captions_check(cues):
    if not isinstance(cues, list) or len(cues) > 2000:
        raise PolicyError("cues must be a list of up to 2000 items")
    issues, entries = [], []
    for index, cue in enumerate(cues):
        if not isinstance(cue, dict):
            raise PolicyError("Every cue must be an object")
        text = cue.get("text")
        if not isinstance(text, str) or not text.strip():
            issues.append({"level": "error", "cue": index, "issue": "empty_text"})
            continue
        try:
            start = float(cue["start"])
            duration = float(cue["duration"])
        except (ValueError, TypeError, KeyError) as exc:
            raise PolicyError("Each cue requires numeric start/duration") from exc
        if not (0 <= start < 86400 and 0 < duration < 3600):
            issues.append({"level": "error", "cue": index, "issue": "invalid_timing"})
            continue
        entries.append((start, start + duration, index))
        lines = text.splitlines()
        if len(lines) > 2 or any(len(line) > 42 for line in lines):
            issues.append({"level": "warning", "cue": index, "issue": "caption_layout"})
        cps = len(text.replace("\n", "")) / duration
        if cps > 20:
            issues.append({"level": "warning", "cue": index, "issue": "high_reading_speed",
                           "charactersPerSecond": round(cps, 1)})
        if duration < 0.6:
            issues.append({"level": "warning", "cue": index, "issue": "brief_cue"})
    entries.sort()
    for left, right in zip(entries, entries[1:]):
        if left[1] > right[0] + 0.0001:
            issues.append({"level": "error", "cue": right[2],
                           "overlapsCue": left[2], "issue": "overlap"})
    return {"passed": not any(i["level"] == "error" for i in issues),
            "count": len(cues), "issues": issues}


def visual_scan(path, seconds=60, *, start_seconds=0):
    path = Path(path)
    if not path.is_file() or not shutil.which("ffmpeg"):
        raise PolicyError("Media file or ffmpeg missing")
    meta = media_probe(path)
    if not any(s.get("codec_type") == "video" for s in meta["streams"]):
        raise PolicyError("Media contains no video stream")
    seconds = min(300, max(1, int(seconds)))
    seek, start = start_args(start_seconds)
    p = subprocess.run([
        "ffmpeg", "-nostdin", "-hide_banner", *seek, "-i", str(path),
        "-t", str(seconds), "-vf",
        "setpts=PTS-STARTPTS,blackdetect=d=0.3:pix_th=0.1,freezedetect=n=-50dB:d=1.5",
        "-an", "-f", "null", "-",
    ], text=True, capture_output=True, timeout=seconds * 3 + 40)
    if p.returncode != 0:
        raise PolicyError("Video analysis failed: " + p.stderr[-350:])
    blacks = [{"start": absolute(a, start), "end": absolute(b, start)}
              for a,b in re.findall(r"black_start:([\d.]+)\s+black_end:([\d.]+)", p.stderr)]
    freezes = [{"start": absolute(x, start)} for x in re.findall(
        r"freeze_start:\s*([\d.]+)", p.stderr)]
    return {"analyzedSeconds": seconds, "startSeconds": start, "blackIntervals": blacks,
            "freezeStarts": freezes, "needsHumanReview": bool(blacks or freezes)}


def transcode(source, destination, profile):
    source, destination = Path(source), Path(destination)
    if profile not in FORMATS:
        raise PolicyError("Unknown delivery profile")
    if not source.is_file() or not shutil.which("ffmpeg"):
        raise PolicyError("Source media or ffmpeg unavailable")
    if source.resolve() == destination.resolve() or destination.exists() or destination.is_symlink():
        raise PolicyError("Refuse overwrite or in-place transcoding")
    width, height = FORMATS[profile]
    if shutil.disk_usage(destination.parent).free < 512 * 1024 * 1024:
        raise PolicyError("Insufficient free storage for video delivery")
    temp = destination.with_name(destination.stem + ".ccer-" + uuid.uuid4().hex + ".partial.mp4")
    filter_graph = (f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                    f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
                    "setsar=1")
    try:
        p = subprocess.run([
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
            "-i", str(source), "-vf", filter_graph,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
            "-movflags", "+faststart", "-f", "mp4", str(temp),
        ], capture_output=True, text=True, timeout=3600)
        if p.returncode:
            raise PolicyError("FFmpeg transcode failed: " + p.stderr[-400:])
        result = media_probe(temp)
        stream = next((s for s in result["streams"] if s.get("codec_type") == "video"), {})
        if stream.get("width") != width or stream.get("height") != height:
            raise PolicyError("Delivery dimensions do not match target")
        if destination.exists():
            raise PolicyError("Destination appeared during transcoding")
        os.link(temp, destination)
        return {"file": str(destination), "bytes": destination.stat().st_size,
                "width": width, "height": height, "profile": profile, "verified": True}
    finally:
        temp.unlink(missing_ok=True)
