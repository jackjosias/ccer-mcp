"""Bounded, read-only audiovisual chronology over existing CCER evidence.

No second decoder, transcription, VLM, media cache, or Concat mutation.
"""
import heapq
import math
from .controls import PolicyError

def _sec(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise PolicyError("Event time must be finite")
    return round(float(value), 3)

def _editorial_candidates(events):
    """Correlate existing evidence only; candidate != verified editing defect.

    Keep the earliest 40 timecoded suggestions even for dense detector output.
    Count all associations without retaining an unbounded candidate list.
    """
    by_kind = {}
    for item in events:
        by_kind.setdefault(item["kind"], []).append(item)
    retained, count = [], 0
    limit = 40

    def add(kind, start, end, first, second, check):
        nonlocal count
        count += 1
        candidate = {
            "kind": kind, "startSeconds": round(start, 3),
            "evidenceIds": [first["id"], second["id"]],
            "evidenceOrigins": [first["origin"], second["origin"]],
            "reviewRequired": True, "correctionVerified": False,
            "semanticUnderstandingPerformed": False,
            "suggestedCheck": check,
        }
        if end is not None:
            candidate["endSeconds"] = round(end, 3)
        key = (-start, -count, candidate)
        if len(retained) < limit:
            heapq.heappush(retained, key)
        elif key[:2] > retained[0][:2]:
            heapq.heapreplace(retained, key)

    for kind, a, b, check in (
        ("caption_silence_overlap", "supplied_caption", "audio_silence_candidate",
         "check_caption_audio_alignment"),
        ("black_silence_overlap", "black_interval", "audio_silence_candidate",
         "check_audiovisual_transition"),
    ):
        for left in by_kind.get(a, ()):
            for right in by_kind.get(b, ()):
                start = max(left["timeSeconds"], right["timeSeconds"])
                end = min(left["endSeconds"], right["endSeconds"])
                if end - start > .001:
                    add(kind, start, end, left, right, check)
    for freeze in by_kind.get("freeze_candidate", ()):
        for cue in by_kind.get("supplied_caption", ()):
            t = freeze["timeSeconds"]
            if cue["timeSeconds"] <= t < cue["endSeconds"]:
                add("freeze_under_caption", t, None, freeze, cue,
                    "check_freeze_during_caption")
    preview = [row[2] for row in sorted(retained, key=lambda x: (-x[0], -x[1]))]
    return preview, count


def event_page(report, *, cursor=0, page_size=40):
    """Page absolute-time evidence; never mistake samples for continuous playback."""
    if type(cursor) is not int or cursor < 0:
        raise PolicyError("cursor must be nonnegative")
    if type(page_size) is not int or not 1 <= page_size <= 100:
        raise PolicyError("page_size must be 1..100")
    if not isinstance(report, dict) or not isinstance(report.get("window"), dict):
        raise PolicyError("An existing timecoded_review report is required")
    lo, hi = (_sec(report["window"].get(k)) for k in ("startSeconds", "endSeconds"))
    if not 0 <= lo < hi <= 86400:
        raise PolicyError("Invalid reviewed window")
    items = []

    def at(kind, t, origin, payload=None):
        t = _sec(t)
        if lo <= t < hi:
            items.append(dict(kind=kind, timeSeconds=t, origin=origin,
                              reviewRequired=True, payload=payload or {}))

    def span(kind, a, b, origin, payload=None):
        a, b = _sec(a), _sec(b)
        if b <= a:
            raise PolicyError("Invalid evidence interval")
        if a < hi and b > lo:
            items.append(dict(kind=kind, timeSeconds=max(a, lo),
                              endSeconds=min(b, hi), sourceStartSeconds=a,
                              sourceEndSeconds=b, origin=origin,
                              reviewRequired=True, payload=payload or {}))

    for i, f in enumerate(report.get("frames", [])):
        if not isinstance(f, dict) or f.get("mimeType") != "image/jpeg":
            raise PolicyError("Expected real JPEG frame metadata")
        at("frame_sample", f.get("timeSeconds"), "ffmpeg_sample", {"frameIndex": i})
    for cut in report.get("sceneCutsSeconds", []):
        at("scene_cut_candidate", cut, "ffmpeg_scene_detection")
    for silence in report.get("audioSilences", []):
        span("audio_silence_candidate", silence.get("start"),
             silence.get("end"), "ffmpeg_silence_detection")
    for finding in report.get("findings", []):
        if finding.get("kind") == "black_interval":
            span("black_interval", finding.get("startSeconds"),
                 finding.get("endSeconds"), "ffmpeg_black_detection")
        elif finding.get("kind") == "freeze_candidate":
            at("freeze_candidate", finding.get("timeSeconds"), "ffmpeg_freeze_detection")
    for cue in report.get("transcriptCues", []):
        if cue.get("provenance") != "external_srt_unverified":
            raise PolicyError("Speech provenance is unverified SRT only")
        phrase = cue.get("text")
        if not isinstance(phrase, str) or not 0 < len(phrase) <= 800:
            raise PolicyError("Invalid subtitle text")
        span("supplied_caption", cue.get("startSeconds"), cue.get("endSeconds"),
             "external_srt_unverified", {"cueIndex": cue.get("index"), "text": phrase})
    if len(items) > 1000:
        raise PolicyError("Event window exceeds safe limit; use shorter window")
    items.sort(key=lambda e: (e["timeSeconds"], e["kind"],
                              e.get("endSeconds", e["timeSeconds"])))
    if cursor > len(items):
        raise PolicyError("cursor exceeds event count")
    for i, item in enumerate(items):
        item["id"] = f"event-{i}"
    stop = min(cursor + page_size, len(items))
    editorial, count = _editorial_candidates(items)
    return {"window": {"startSeconds": lo, "endSeconds": hi},
            "events": items[cursor:stop], "cursor": cursor,
            "nextCursor": stop if stop < len(items) else None,
            "totalEvents": len(items), "sampledFrames": len(report.get("frames", [])),
            "editorialCandidates": editorial, "editorialCandidateCount": count,
            "editorialCandidatesTruncated": count > len(editorial),
            "editorialCandidateScope": "full_review_window_not_event_page",
            "readOnly": True, "transcriptionPerformed": False,
            "semanticUnderstandingPerformed": False,
            "continuousPlaybackPerformed": False, "mediaArtifactsCreated": False}


def inspect_event_window(root, video, *, transcript=None, start_seconds=0,
                         seconds=30, frame_count=4, cursor=0, page_size=40,
                         timeline_offset_seconds=0, include_frames=False):
    """Reuse one authorized reviewer; optionally forward existing JPEGs."""
    from .controls import inside
    if type(cursor) is not int or cursor < 0:
        raise PolicyError("cursor must be nonnegative")
    if type(page_size) is not int or not 1 <= page_size <= 100:
        raise PolicyError("page_size must be 1..100")
    if type(frame_count) is not int or not 1 <= frame_count <= 8:
        raise PolicyError("frame_count must be 1..8")
    if type(include_frames) is not bool:
        raise PolicyError("includeFrames must be boolean")
    source = inside(root, video, must_exist=True)
    if transcript is None:
        from .timecoded_review import review
        report = review(source, start_seconds=start_seconds,
                        seconds=seconds, frame_count=frame_count)
    else:
        from .av_timeline import audiovisual_review
        captions = inside(root, transcript, must_exist=True)
        report = audiovisual_review(source, captions,
                                    start_seconds=start_seconds,
                                    seconds=seconds, frame_count=frame_count,
                                    timeline_offset_seconds=timeline_offset_seconds)
    result = event_page(report, cursor=cursor, page_size=page_size)
    if include_frames:
        # Forward the same JPEGs already decoded; no extra FFmpeg invocation.
        result["frames"] = report["frames"]
    result["file"] = str(source)
    result["timelineOffsetSeconds"] = timeline_offset_seconds if transcript is not None else 0
    result["transcriptSource"] = ("external_srt_unverified"
                                   if transcript is not None else "none")
    return result
