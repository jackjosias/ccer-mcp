"""Offline English narration via FFmpeg's optional libflite filter. No cloud or shell."""
from __future__ import annotations
import os
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from .controls import PolicyError, media_probe

_ALLOWED_VOICES = frozenset({"kal", "kal16", "awb", "rms", "slt"})


@lru_cache(maxsize=1)
def flite_available():
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    try:
        result = subprocess.run([ffmpeg, "-hide_banner", "-h", "filter=flite"],
                                capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and "Filter flite" in (result.stdout + result.stderr)


def synthesize_flite(text, output, *, language="en", speaker="kal"):
    """Render an English voice in a private folder and atomically publish new WAV."""
    if not isinstance(text, str) or not 0 < len(text.strip()) <= 4000:
        raise PolicyError("Narration text must contain 1..4000 characters")
    if language not in ("en", "en-US", "en-GB"):
        raise PolicyError("FFmpeg flite is English-only; provide separately recorded French narration")
    if speaker not in _ALLOWED_VOICES:
        raise PolicyError("Unknown flite voice")
    if not flite_available():
        raise PolicyError("FFmpeg libflite filter is unavailable")
    dest = Path(output)
    if dest.suffix.lower() != ".wav" or not dest.parent.is_dir():
        raise PolicyError("Output must be WAV in an existing directory")
    if dest.exists() or dest.is_symlink():
        raise PolicyError("Cannot replace existing narration")
    if shutil.disk_usage(dest.parent).free < 256 * 1024 * 1024:
        raise PolicyError("Insufficient free storage (256 MiB required)")
    with tempfile.TemporaryDirectory(prefix=".ccer-flite-", dir=dest.parent) as directory:
        folder = Path(directory)
        (folder / "speech.txt").write_text(text, encoding="utf-8")
        wav = folder / "narration.wav"
        result = subprocess.run([
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"flite=textfile=speech.txt:voice={speaker}",
            "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", "-f", "wav", str(wav)],
            cwd=folder, capture_output=True, text=True, timeout=180)
        if result.returncode:
            raise PolicyError("Speech generation failed: " + result.stderr[-450:])
        checked = media_probe(wav)
        if not any(s.get("codec_type") == "audio" for s in checked["streams"]):
            raise PolicyError("Generated file has no audio stream")
        try:
            seconds = float(checked["format"]["duration"])
        except (ValueError, TypeError) as exc:
            raise PolicyError("Generated speech duration unavailable") from exc
        if seconds <= 0 or wav.stat().st_size < 100:
            raise PolicyError("Generated speech is empty")
        if dest.exists():
            raise PolicyError("Speech output appeared during rendering")
        os.link(wav, dest)
        return {"file": str(dest), "engine": "ffmpeg-flite", "language": language,
                "voice": speaker, "durationSeconds": seconds,
                "bytes": dest.stat().st_size, "verified": True, "naturalSounding": False}
