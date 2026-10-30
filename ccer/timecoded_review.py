"""Bounded audiovisual evidence for real editorial inspection by an image-capable agent.

Technical analyzers identify *candidates*, not meaning. Expose original,
timecoded JPEG frames to the agent through MCP image parts; never label
content semantically without examining those frames. Read-only, no Concat edits.
"""
from __future__ import annotations

import base64
import math
import shutil
import subprocess
from pathlib import Path

from .controls import PolicyError, media_probe
from .quality import visual_scan
from .shot_intelligence import scene_cuts
from .rhythm import silence_map
from .visual_edit import color_report


def _number(value, name, lo, hi):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PolicyError(f"{name} must be a finite number")
    if not math.isfinite(value) or not lo <= value <= hi:
        raise PolicyError(f"{name} must be between {lo} and {hi}")
    return float(value)


def _frame(source: Path, seconds: float) -> bytes:
    process = subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
         "-ss", f"{seconds:.6f}", "-i", str(source), "-map", "0:v:0",
         "-frames:v", "1", "-vf", "scale=480:-2",
         "-c:v", "mjpeg", "-q:v", "6", "-f", "image2pipe", "pipe:1"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=40)
    if process.returncode or not process.stdout.startswith(b"\xff\xd8"):
        raise PolicyError("Failed extracting timecoded frame: " +
                          process.stderr.decode(errors="replace")[-250:])
    if len(process.stdout) > 350_000:
        raise PolicyError("Timecoded frame exceeds safety size limit")
    return process.stdout


def plan_long_review(source, *, cursor=0, window_seconds=30, frame_count=6, page_size=12):
    """Page over full video timecodes without decoding or writing image frames.

    Each planned window reuses ccer_timecoded_review, never editing Concat.
    """
    source = Path(source)
    window = _number(window_seconds, "windowSeconds", .5, 120)
    if type(cursor) is not int or cursor < 0:
        raise PolicyError("cursor must be a nonnegative integer")
    if type(frame_count) is not int or not 1 <= frame_count <= 8:
        raise PolicyError("frameCount must be 1..8")
    if type(page_size) is not int or not 1 <= page_size <= 24:
        raise PolicyError("pageSize must be 1..24")
    info = media_probe(source)
    if not any(stream.get("codec_type") == "video" for stream in info["streams"]):
        raise PolicyError("Media has no video")
    try:
        duration = float(info["format"]["duration"])
    except (ValueError, TypeError, KeyError) as error:
        raise PolicyError("Media duration unavailable") from error
    if not math.isfinite(duration) or not 0 < duration <= 86400:
        raise PolicyError("Planning supports video durations up to 24 hours")
    total = math.ceil(duration / window)
    if cursor > total:
        raise PolicyError("cursor is beyond the final review window")
    end_cursor = min(total, cursor + page_size)
    windows = []
    for index in range(cursor, end_cursor):
        start = index * window
        end = min(duration, (index + 1) * window)
        windows.append({
            "index": index, "startSeconds": round(start, 3),
            "endSeconds": round(end, 3),
            "reviewArguments": {
                "file": str(source), "startSeconds": round(start, 3),
                "seconds": window, "frameCount": frame_count,
            },
        })
    return {
        "file": str(source), "durationSeconds": round(duration, 3),
        "windowSeconds": window, "totalWindows": total, "cursor": cursor,
        "nextCursor": end_cursor if end_cursor < total else None,
        "plannedFramesPerWindow": frame_count, "windows": windows,
        "imageFilesCreated": 0, "readOnly": True,
        "requiresEditorialJudgment": True,
        "note": ("Metadata-only plan. Call ccer_timecoded_review on each "
                 "reviewArguments to decode bounded real JPEG frames in "
                 "memory. Planning never infers video semantics."),
    }


def review(source, *, start_seconds=0, seconds=30, frame_count=6, focus_seconds=None):
    """Return metadata + actual JPEG frames, never an invented film description."""
    if not shutil.which("ffmpeg"):
        raise PolicyError("FFmpeg unavailable")
    source = Path(source)
    start = _number(start_seconds, "startSeconds", 0, 86400)
    requested = _number(seconds, "seconds", .5, 120)
    if isinstance(frame_count, bool) or not isinstance(frame_count, int) or not 1 <= frame_count <= 8:
        raise PolicyError("frameCount must be 1..8")
    info = media_probe(source)
    if not any(s.get("codec_type") == "video" for s in info["streams"]):
        raise PolicyError("Media has no video")
    try:
        duration = float(info["format"]["duration"])
    except (ValueError, TypeError, KeyError) as error:
        raise PolicyError("Media duration unavailable") from error
    if not math.isfinite(duration) or duration <= 0 or start >= duration:
        raise PolicyError("startSeconds outside media duration")
    end = min(duration, start + requested)
    span = end - start
    times = [round(min(duration - .001, start + span * (index + .5) / frame_count), 3)
             for index in range(frame_count)]
    if focus_seconds is not None:
        focus = _number(focus_seconds, "focusSeconds", start, end)
        anchor = round(min(duration - .001, focus), 3)
        closest = min(range(len(times)), key=lambda i: abs(times[i] - anchor))
        times[closest] = anchor
        times.sort()
    frames = [{"timeSeconds": t, "mimeType": "image/jpeg",
               "imageBase64": base64.b64encode(_frame(source, t)).decode("ascii")}
              for t in times]

    # Reuse existing analyzers; an issue emitted by an automated detector is
    # evidence for review, not a verdict about artistic intent.
    # Analyze the requested window, NOT the first N seconds of a long movie.
    # Preserve absolute source timecodes across seeked FFmpeg probes.
    coverage = min(120, max(1, math.ceil(span)))
    visual = visual_scan(source, seconds=coverage, start_seconds=start)
    cuts = scene_cuts(source, seconds=coverage, start_seconds=start)
    color = color_report(source, seconds=coverage, start_seconds=start,
                         interval=max(.2, min(10., span / max(frame_count, 1))))
    audio_present = any(s.get("codec_type") == "audio" for s in info["streams"])
    silence = (silence_map(source, seconds=coverage, start_seconds=start)
               if audio_present else None)
    findings = []
    for interval in visual["blackIntervals"]:
        if interval["end"] >= start and interval["start"] <= end:
            findings.append({"kind": "black_interval", "startSeconds": interval["start"],
                             "endSeconds": interval["end"], "reviewRequired": True})
    for frozen in visual["freezeStarts"]:
        if start <= frozen["start"] <= end:
            findings.append({"kind": "freeze_candidate", "timeSeconds": frozen["start"],
                             "reviewRequired": True})
    return {
        "file": str(source), "durationSeconds": round(duration, 3),
        "window": {"startSeconds": round(start, 3), "endSeconds": round(end, 3)},
        "frames": frames, "frameCount": len(frames),
        "sceneCutsSeconds": [t for t in cuts["cutsSeconds"] if start <= t <= end],
        "findings": findings, "colorMetrics": color["metrics"],
        "colorMethod": color["method"], "audioPresent": audio_present,
        "audioSilences": [i for i in silence["silences"]
                          if i["end"] >= start and i["start"] <= end] if silence else [],
        "requiresEditorialJudgment": True,
        "speechTranscriptionAvailable": False,
        "method": ("Original FFmpeg decoded video samples and existing technical "
                   "analyzers. Frames are delivered as MCP images for visual "
                   "inspection; no automatic semantic recognition or full-speed playback.")
    }

def review_annotation(source, *, time_seconds, note, context_seconds=8, frame_count=5):
    """Read-only evidence around a user-supplied editing note."""
    if not isinstance(note, str) or not 1 <= len(note.strip()) <= 1200:
        raise PolicyError("note must be 1..1200 characters")
    focus = _number(time_seconds, "timeSeconds", 0, 86400)
    context = _number(context_seconds, "contextSeconds", .5, 60)
    if type(frame_count) is not int or not 1 <= frame_count <= 8:
        raise PolicyError("frameCount must be 1..8")
    info = media_probe(source)
    if not any(s.get("codec_type") == "video" for s in info["streams"]):
        raise PolicyError("Media has no video")
    try:
        duration = float(info["format"]["duration"])
    except (ValueError, TypeError, KeyError) as error:
        raise PolicyError("Media duration unavailable") from error
    if not math.isfinite(duration) or duration <= 0 or focus >= duration:
        raise PolicyError("Annotation timeSeconds outside video duration")
    start = max(0., min(focus - context / 2, max(0., duration - context)))
    result = review(source, start_seconds=start, seconds=context,
                    frame_count=frame_count, focus_seconds=focus)
    result["annotation"] = {
        "note": note.strip(), "timeSeconds": focus, "verified": False,
        "provenance": "user_supplied",
        "focusFrameTimeSeconds": min(
            (frame["timeSeconds"] for frame in result["frames"]),
            key=lambda t: abs(t - focus)),
    }
    result["readOnly"] = True
    result["annotationPersisted"] = False
    return result


def main(argv=None):
    """Read-only CLI smoke test. Enforce the same media-root boundary as MCP."""
    import argparse
    import json
    from .controls import inside

    parser = argparse.ArgumentParser(description="Timecoded audiovisual evidence report")
    parser.add_argument("--file", required=True)
    parser.add_argument("--seconds", type=float, default=30)
    parser.add_argument("--start", type=float, default=0)
    parser.add_argument("--frames", type=int, default=6)
    args = parser.parse_args(argv)
    source = inside(Path.home() / "Videos" / "CCER", args.file, must_exist=True)
    result = review(source, start_seconds=args.start, seconds=args.seconds,
                    frame_count=args.frames)
    # No raw JPEG blobs in terminal logs. MCP delivers the actual image parts.
    result["frames"] = [{"timeSeconds": item["timeSeconds"],
                         "jpegBytes": len(base64.b64decode(item["imageBase64"]))}
                        for item in result["frames"]]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
