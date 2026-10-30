"""Real timecoded WAV evidence, decoded in memory from an approved source.

No Whisper execution or semantic audio understanding is claimed.
"""
from __future__ import annotations
import base64
import math
import shutil
import subprocess
from pathlib import Path
from .controls import PolicyError, media_probe

MAX_WAV_BYTES = 400_000
SAMPLE_RATE = 16_000
MAX_WINDOW_SECONDS = 10

def _bounded(value, name, lower, upper):
    if type(value) not in (int, float) or not math.isfinite(value) or not lower <= value <= upper:
        raise PolicyError(f"{name} must be finite and in [{lower}, {upper}]")
    return float(value)

def audio_window(source, *, start_seconds=0, seconds=4):
    """Decode authentic PCM audio into a bounded WAV with no temporary files."""
    start = _bounded(start_seconds, "startSeconds", 0, 86400)
    length = _bounded(seconds, "seconds", .25, MAX_WINDOW_SECONDS)
    source = Path(source)
    info = media_probe(source)
    if not any(row.get("codec_type") == "audio" for row in info["streams"]):
        raise PolicyError("Media has no audio stream")
    try:
        duration = float(info["format"]["duration"])
    except (TypeError, ValueError, KeyError) as exc:
        raise PolicyError("Audio duration unavailable") from exc
    if not math.isfinite(duration) or not 0 < duration <= 86400 or start >= duration:
        raise PolicyError("Audio window outside media duration")
    length = min(length, duration - start)
    if length < .01 or not shutil.which("ffmpeg"):
        raise PolicyError("Audio window too short or FFmpeg unavailable")
    command = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
               "-ss", f"{start:.6f}", "-i", str(source), "-t", f"{length:.6f}",
               "-map", "0:a:0", "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE),
               "-c:a", "pcm_s16le", "-f", "wav", "pipe:1"]
    try:
        process = subprocess.run(command, capture_output=True, timeout=45)
    except subprocess.TimeoutExpired as exc:
        raise PolicyError("Audio decoding timed out") from exc
    wav = process.stdout
    if (process.returncode or len(wav) < 44 or len(wav) > MAX_WAV_BYTES
            or not wav.startswith(b"RIFF") or wav[8:12] != b"WAVE"):
        raise PolicyError("Invalid or oversized audio window: " +
                          process.stderr.decode(errors="replace")[-180:])
    return {
        "file": str(source), "startSeconds": round(start, 3),
        "endSeconds": round(start + length, 3),
        "durationSeconds": round(length, 3),
        "sampleRate": SAMPLE_RATE, "channels": 1, "audioBytes": len(wav),
        "mimeType": "audio/wav",
        "audioBase64": base64.b64encode(wav).decode("ascii"),
        "audioSource": "original_media_ffmpeg_mono_pcm",
        "transcriptionPerformed": False, "semanticUnderstandingPerformed": False,
        "readOnly": True, "noLocalMediaArtifacts": True,
    }
