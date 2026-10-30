"""Read-only, timecoded audiovisual inspection. SRT is externally supplied.

No second Whisper installation and no claim of speech recognition: text
comes from supplied subtitle file, frames from existing timecoded_review.
"""
from __future__ import annotations
import math
import re
from pathlib import Path
from .controls import PolicyError, media_probe
from .quality import captions_check
from .timecoded_review import review

STAMP = re.compile(
    r"^(\d\d):(\d\d):(\d\d)[,.](\d{3})\s*-->\s*"
    r"(\d\d):(\d\d):(\d\d)[,.](\d{3})(?:\s+.*)?$")


def _seconds(parts):
    h, m, s, ms = map(int, parts)
    if m >= 60 or s >= 60:
        raise PolicyError("Invalid SRT timecode")
    return h * 3600 + m * 60 + s + ms / 1000


def read_srt(video, transcript, *, timeline_offset_seconds=0):
    """Read supplied SRT and optionally map project time into source time."""
    offset = timeline_offset_seconds
    if type(offset) not in (int, float) or not math.isfinite(offset) or not 0 <= offset <= 86400:
        raise PolicyError("timelineOffsetSeconds must be finite and nonnegative")
    info = media_probe(video)
    if not any(s.get("codec_type") == "video" for s in info["streams"]):
        raise PolicyError("SRT review requires video")
    try:
        duration = float(info["format"]["duration"])
    except (ValueError, KeyError, TypeError) as exc:
        raise PolicyError("Media duration unavailable") from exc
    if not math.isfinite(duration) or not 0 < duration <= 86400:
        raise PolicyError("Unsupported media duration")
    path = Path(transcript)
    if path.is_symlink() or not path.is_file() or path.suffix.lower() != ".srt":
        raise PolicyError("Expected a safe existing SRT")
    if path.stat().st_size > 2_000_000:
        raise PolicyError("SRT exceeds 2 MB")
    try:
        contents = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise PolicyError("SRT must be readable UTF-8") from exc
    cues = []
    for block in re.split(r"\r?\n\s*\r?\n", contents.strip()):
        lines = [s.strip() for s in block.splitlines() if s.strip()]
        if not lines:
            continue
        if lines[0].isdigit():
            lines.pop(0)
        match = STAMP.fullmatch(lines[0]) if lines else None
        if match is None or len(lines) < 2:
            raise PolicyError("Malformed SRT cue")
        timeline_start = _seconds(match.groups()[:4])
        timeline_end = _seconds(match.groups()[4:])
        if timeline_start < offset - .001:
            raise PolicyError("SRT begins before mapped clip")
        start, end = max(0.0, timeline_start - offset), timeline_end - offset
        text = "\n".join(lines[1:])
        if not text or len(text) > 800 or start < 0 or end <= start or end > duration + .05:
            raise PolicyError("Invalid SRT cue")
        cues.append({"start": start, "duration": end - start, "text": text,
                     "timelineStartSeconds": timeline_start,
                     "timelineEndSeconds": timeline_end})
        if len(cues) > 2000:
            raise PolicyError("Too many SRT cues")
    if not cues:
        raise PolicyError("SRT contains no cues")
    qa = captions_check(cues)
    if not qa["passed"]:
        raise PolicyError("SRT subtitle timing failed QA")
    return {"file": str(video), "transcriptFile": str(path),
            "durationSeconds": round(duration, 3),
            "cues": cues, "cueCount": len(cues), "captionQA": qa,
            "audioPresent": any(s.get("codec_type") == "audio" for s in info["streams"]),
            "provenance": "external_srt_unverified",
            "timebase": "source_relative",
            "timelineOffsetSeconds": round(float(offset), 3),
            "asrPerformed": False, "readOnly": True}


def audiovisual_review(video, transcript, *, start_seconds=0, seconds=30,
                       frame_count=4, max_cues=100, include_audio=False,
                        timeline_offset_seconds=0):
    """Time-align real JPEG evidence, speech captions and existing audio metrics."""
    if type(max_cues) is not int or not 1 <= max_cues <= 200:
        raise PolicyError("maxCues must be 1..200")
    if type(include_audio) is not bool:
        raise PolicyError("includeAudio must be boolean")
    if include_audio and (type(seconds) not in (int, float) or not math.isfinite(seconds)
                          or not .25 <= seconds <= 10):
        raise PolicyError("includeAudio requires a 0.25..10 second window")
    subtitles = read_srt(video, transcript, timeline_offset_seconds=timeline_offset_seconds)
    report = review(video, start_seconds=start_seconds, seconds=seconds,
                    frame_count=frame_count)
    start = report["window"]["startSeconds"]
    end = report["window"]["endSeconds"]
    matched = [{"index": i, "startSeconds": round(cue["start"], 3),
                "endSeconds": round(cue["start"] + cue["duration"], 3),
                "text": cue["text"], "provenance": subtitles["provenance"]}
               for i, cue in enumerate(subtitles["cues"])
               if cue["start"] < end and cue["start"] + cue["duration"] > start]
    if len(matched) > max_cues:
        raise PolicyError("Too many captions in window; reduce seconds")
    associations = [
        {"timeSeconds": row["timeSeconds"],
         "cueIndices": [cue["index"] for cue in matched
                        if cue["startSeconds"] <= row["timeSeconds"] < cue["endSeconds"]]}
        for row in report["frames"]]
    report.update({"transcriptFile": str(transcript),
                   "transcriptSource": subtitles["provenance"],
                    "timelineOffsetSeconds": subtitles["timelineOffsetSeconds"],
                   "transcriptCues": matched,
                   "totalTranscriptCues": subtitles["cueCount"],
                   "frameSpeechAssociations": associations,
                   "captionQA": subtitles["captionQA"],
                   "speechTranscriptionAvailable": bool(matched),
                   "transcriptionPerformed": False,
                   "semanticUnderstandingPerformed": False,
                   "readOnly": True, "noLocalMediaArtifacts": True,
                   "method": "Existing timecoded_review frames and audio metrics + unverified supplied SRT"})
    if include_audio:
        from .audio_evidence import audio_window
        report["audioEvidence"] = audio_window(
            video, start_seconds=start, seconds=end - start)
    return report
