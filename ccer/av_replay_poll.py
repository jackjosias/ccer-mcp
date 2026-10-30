"""Bounded pull-based A/V replay over existing FFmpeg event review.

One poll processes at most one small window. No resident daemon, GUI input,
model download, unbounded queue, implicit continuous playback, or JPEG cache.
The consumer owns acknowledgement/backpressure through consumer_ready.
"""
from __future__ import annotations

import math
import os
import time
from pathlib import Path

from .controls import PolicyError, inside, media_probe
from .av_event_cursor import inspect_event_window


def _positive(value, name, minimum, maximum):
    if type(value) not in (float, int) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise PolicyError(f"{name} must be finite in [{minimum}, {maximum}]")
    return float(value)


def _pressure():
    """Advisory local envelope; do not falsely claim certified GPU inference."""
    try:
        load = os.getloadavg()[0] / max(1, os.cpu_count() or 1)
    except (OSError, ValueError):
        load = 0.0
    available = None
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                available = int(line.split()[1]) * 1024
                break
    except (OSError, ValueError, IndexError):
        pass
    if load >= 2.5 or available is not None and available < 2 * 1024**3:
        tier = "critical"
    elif load >= 1.0 or available is not None and available < 4 * 1024**3:
        tier = "constrained"
    else:
        tier = "normal"
    return {"tier": tier, "loadPerCpu": round(load, 2),
            "memAvailableBytes": available,
            "source": "local_readonly_runtime_observation"}


def replay_poll(root, file, *, transcript=None, cursor=0, window_seconds=4,
                frame_count=2, max_events=80, consumer_ready=True,
                timeline_offset_seconds=0, include_frames=False):
    """Return the next bounded media window, or pause without decoding.

    NOT a true live camera/audio stream: the file is a previously recorded
    source and every call is explicitly initiated by the consumer.
    """
    if type(cursor) is not int or cursor < 0:
        raise PolicyError("cursor must be a nonnegative window index")
    window = _positive(window_seconds, "windowSeconds", .5, 10)
    if type(frame_count) is not int or not 1 <= frame_count <= 4:
        raise PolicyError("frameCount must be 1..4")
    if type(max_events) is not int or not 1 <= max_events <= 100:
        raise PolicyError("maxEvents must be 1..100")
    if type(consumer_ready) is not bool:
        raise PolicyError("consumerReady must be boolean")
    if type(include_frames) is not bool:
        raise PolicyError("includeFrames must be boolean")
    _positive(timeline_offset_seconds, "timelineOffsetSeconds", 0, 86400)
    source = inside(root, file, must_exist=True)
    srt = inside(root, transcript, must_exist=True) if transcript is not None else None
    metadata = media_probe(source)
    if not any(stream.get("codec_type") == "video" for stream in metadata["streams"]):
        raise PolicyError("Video stream required")
    try:
        duration = float(metadata["format"]["duration"])
    except (KeyError, ValueError, TypeError) as exc:
        raise PolicyError("Media duration unavailable") from exc
    if not math.isfinite(duration) or not 0 < duration <= 86400:
        raise PolicyError("Unsupported media duration")
    total = math.ceil(duration / window)
    if cursor > total:
        raise PolicyError("cursor is past the final media window")
    base = {"file": str(source), "cursor": cursor,
            "totalWindows": total, "durationSeconds": round(duration, 3),
            "windowSeconds": window, "readOnly": True,
            "mode": "recorded_pull_replay", "liveStreamActive": False,
            "continuousPlaybackPerformed": False,
            "semanticUnderstandingPerformed": False,
            "transcriptionPerformed": False, "mediaArtifactsCreated": False}
    if cursor == total:
        return {**base, "events": [], "complete": True,
                "paused": False, "nextCursor": None, "processed": False}
    start = round(cursor * window, 6)
    end = min(duration, (cursor + 1) * window)
    base["window"] = {"startSeconds": round(start, 3),
                      "endSeconds": round(end, 3)}
    if not consumer_ready:
        return {**base, "events": [], "paused": True, "complete": False,
                "pauseReason": "consumer_backpressure",
                "nextCursor": cursor, "processed": False,
                "decodedFrames": 0}
    pressure = _pressure()
    budget = {"normal": 4, "constrained": 2, "critical": 1}[pressure["tier"]]
    sampled = min(frame_count, budget)
    started = time.perf_counter()
    page = inspect_event_window(root, source, transcript=srt,
                                start_seconds=start, seconds=window,
                                frame_count=sampled, page_size=max_events,
                                timeline_offset_seconds=timeline_offset_seconds,
                                 include_frames=include_frames)
    elapsed_ms = max(0.0, (time.perf_counter() - started) * 1000)
    # Never advance a window if any events would be silently dropped.
    if page["nextCursor"] is not None:
        raise PolicyError("Event overflow; reduce windowSeconds or increase maxEvents")
    frames = {"frames": page["frames"]} if include_frames else {}
    return {**base, **frames, "events": page["events"], "processed": True,
            "decodedFrames": sampled, "pressure": pressure,
            "paused": False, "complete": cursor + 1 == total,
            "nextCursor": cursor + 1 if cursor + 1 < total else None,
            "eventCount": page["totalEvents"],
            "observationLatencyMs": round(elapsed_ms, 3),
            "windowDurationSeconds": round(end - start, 3),
            "processingRealTimeFactor": round((end - start) * 1000 / elapsed_ms, 3)
            if elapsed_ms > 0 else None,
            "latencyMeasurement": "local_steady_clock_elapsed_per_poll_not_end_to_end_stream",
            "transcriptSource": page["transcriptSource"],
            "timelineOffsetSeconds": page["timelineOffsetSeconds"]}
