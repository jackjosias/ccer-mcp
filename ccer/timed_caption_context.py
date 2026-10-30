"""Read-only alignment of human-supplied caption timecodes with real audio windows.

This module does not perform speech recognition or word-level alignment.
"""
import math
from pathlib import Path

from .controls import PolicyError, media_probe
from .quality import captions_check
from .rhythm import silence_map


def timed_caption_context(source, cues, *, start_seconds=0, seconds=30,
                          max_cues=30, include_audio_silence=True):
    if not isinstance(cues, list) or not 1 <= len(cues) <= 2000:
        raise PolicyError("Supply 1..2000 user-provided timed subtitle cues")
    if type(max_cues) is not int or not 1 <= max_cues <= 100:
        raise PolicyError("maxCues must be 1..100")
    if type(include_audio_silence) is not bool:
        raise PolicyError("includeAudioSilence must be boolean")
    for value, name, lower, upper in (
        (start_seconds, "startSeconds", 0, 86400),
        (seconds, "seconds", .5, 120),
    ):
        if type(value) not in (int, float) or not math.isfinite(value) or not lower <= value <= upper:
            raise PolicyError(name + " outside safe finite bounds")
    source = Path(source)
    info = media_probe(source)
    try:
        duration = float(info["format"]["duration"])
    except (ValueError, TypeError, KeyError) as error:
        raise PolicyError("Media duration unavailable") from error
    if not math.isfinite(duration) or not 0 < duration <= 86400:
        raise PolicyError("Unsupported media duration")
    if start_seconds >= duration:
        raise PolicyError("startSeconds outside media duration")
    end = min(duration, start_seconds + seconds)
    normalized = []
    for index, cue in enumerate(cues):
        if not isinstance(cue, dict):
            raise PolicyError("Every subtitle cue must be an object")
        text = cue.get("text")
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 800:
            raise PolicyError("Subtitle text must be 1..800 characters")
        a, length = cue.get("start"), cue.get("duration")
        if type(a) not in (float, int) or type(length) not in (float, int):
            raise PolicyError("Subtitle timing must be numeric, not boolean")
        if not all(math.isfinite(item) for item in (a, length)):
            raise PolicyError("Subtitle timing must be finite")
        if a < 0 or length <= 0 or a + length > duration + 0.05:
            raise PolicyError("Subtitle extends outside media")
        normalized.append({"start": float(a), "duration": float(length), "text": text.strip(), "sourceIndex": index})
    qa = captions_check(normalized)
    if not qa["passed"]:
        raise PolicyError("User-supplied subtitle timing failed QA")
    selected = [cue for cue in normalized if cue["start"] < end and
                cue["start"] + cue["duration"] > start_seconds]
    if len(selected) > max_cues:
        raise PolicyError("Window has more than maxCues; narrow the review window")
    audio_present = any(s.get("codec_type") == "audio" for s in info["streams"])
    silence = (silence_map(source, seconds=max(1, end - start_seconds),
                           start_seconds=start_seconds)
               if include_audio_silence and audio_present else None)
    return {
        "file": str(source), "window": {"startSeconds": round(start_seconds, 3),
                                      "endSeconds": round(end, 3)},
        "totalCues": len(cues), "windowCues": selected, "captionQA": qa,
        "audioPresent": audio_present, "audioSilenceCandidates": (
            silence["silences"] if silence else []),
        "audioAnalyzed": bool(silence), "transcriptionPerformed": False,
        "wordForcedAlignmentPerformed": False, "cueProvenance": "user_supplied",
        "speechPresenceVerified": False, "readOnly": True,
        "noLocalMediaArtifacts": True, "requiresHumanReview": True,
        "method": ("Existing caption QA + FFmpeg silence detection over the "
                   "requested absolute time window. Silence does not identify speech."),
    }
