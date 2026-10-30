"""Local voice recording/TTS adapters and broadcast-aware audio mixing with FFmpeg.

No undeclared cloud calls, model downloads, API keys, or overwrite of source media.
"""
from __future__ import annotations
import math
import os
import shutil
import subprocess
import uuid
from pathlib import Path

from .controls import PolicyError, audio_analyze, media_probe


def engines():
    return {"espeak-ng": bool(shutil.which("espeak-ng")),
            "espeak": bool(shutil.which("espeak")),
            "piper": bool(shutil.which("piper")),
            "ffmpeg": bool(shutil.which("ffmpeg"))}


def _output(destination):
    dest = Path(destination)
    if dest.exists() or dest.is_symlink():
        raise PolicyError("Refuse overwrite or symlink output")
    if not dest.parent.is_dir():
        raise PolicyError("Create output parent first")
    if shutil.disk_usage(dest.parent).free < 256*1024*1024:
        raise PolicyError("Less than 256MiB available")
    return dest


def voice(text, output, *, language="fr", rate=150, engine="auto"):
    """Local eSpeak voice generation. Piper needs a model and is deliberately not implicit."""
    if not isinstance(text, str) or not 0 < len(text.strip()) <= 12000:
        raise PolicyError("Voice text must be 1..12000 characters")
    if not isinstance(language, str) or not language.isalpha() or len(language) > 8:
        raise PolicyError("Invalid language")
    if not isinstance(rate, int) or not 80 <= rate <= 300:
        raise PolicyError("Voice rate must be 80..300 WPM")
    chosen = next((cmd for cmd in (("espeak-ng", "espeak") if engine == "auto" else (engine,))
                   if cmd in ("espeak-ng", "espeak") and shutil.which(cmd)), None)
    if not chosen:
        raise PolicyError("No supported local TTS engine installed: install espeak-ng or espeak; Piper adapter pending")
    dest = _output(output)
    if dest.suffix.lower() != ".wav":
        raise PolicyError("Speech output must be WAV")
    temp = dest.with_name(dest.stem + "." + uuid.uuid4().hex + ".tmp.wav")
    try:
        proc = subprocess.run([chosen, "-v", language, "-s", str(rate), "-w", str(temp), text],
                              capture_output=True, text=True, timeout=90)
        if proc.returncode:
            raise PolicyError("Voice synthesis failed: " + proc.stderr[-300:])
        meta = media_probe(temp)
        if not any(s.get("codec_type") == "audio" for s in meta["streams"]):
            raise PolicyError("No audio generated")
        os.link(temp, dest)
        return {"file": str(dest), "engine": chosen, "duration": meta["format"]["duration"],
                "verified": True}
    finally:
        temp.unlink(missing_ok=True)


def mix(voice_file, music_file, output, *, music_gain=0.18, target_lufs=-16.0):
    """Normalize narration, duck background with sidechain compression, limit peaks."""
    if not shutil.which("ffmpeg"):
        raise PolicyError("FFmpeg unavailable")
    narr = Path(voice_file)
    music = Path(music_file) if music_file else None
    if not narr.is_file() or (music and not music.is_file()):
        raise PolicyError("Voice/music source not found")
    if not isinstance(music_gain, (int, float)) or not math.isfinite(music_gain) or not 0 <= music_gain <= 1:
        raise PolicyError("musicGain must be 0..1")
    if not isinstance(target_lufs, (int, float)) or not math.isfinite(target_lufs) or not -24 <= target_lufs <= -9:
        raise PolicyError("targetLufs must be -24..-9")
    dest = _output(output)
    if dest.suffix.lower() not in (".wav", ".m4a"):
        raise PolicyError("Mix output must be .wav or .m4a")
    temp = dest.with_name(dest.stem + "." + uuid.uuid4().hex + dest.suffix)
    mastered = temp.with_name(temp.stem + ".master" + dest.suffix)
    if music:
        # Sidechain key is narration. The mix ends when the narration ends.
        graph = ("[0:a]aresample=48000,asplit=2[side][voiceraw];"
                 "[1:a]aresample=48000[music];"
                 "[music][side]sidechaincompress=threshold=0.035:ratio=9:attack=10:release=350[duck];"
                 "[duck]volume=" + str(float(music_gain)) + "[quiet];"
                 "[voiceraw]dynaudnorm=f=50:g=5:p=0.9[voice];"
                 "[voice][quiet]amix=inputs=2:duration=first:dropout_transition=0,"
                 "alimiter=limit=0.92[out]")
        args = ["-i", str(narr), "-stream_loop", "-1", "-i", str(music),
                "-filter_complex", graph, "-map", "[out]"]
    else:
        args = ["-i", str(narr), "-af",
                "aresample=48000,dynaudnorm=f=50:g=5:p=0.9,alimiter=limit=0.92"]
    codec = ["-c:a", "pcm_s16le"] if dest.suffix == ".wav" else ["-c:a", "aac", "-b:a", "192k"]
    try:
        result = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                                 *args, *codec, str(temp)], capture_output=True,
                                text=True, timeout=1800)
        if result.returncode:
            raise PolicyError("Audio mix failed: " + result.stderr[-350:])
        metadata = media_probe(temp)
        if not any(s.get("codec_type") == "audio" for s in metadata["streams"]):
            raise PolicyError("Mix rendered without audio: " + repr(metadata)[:900])
        analysis = audio_analyze(temp, seconds=40)
        original_lufs = analysis.get("integratedLufs")
        if original_lufs is None or not math.isfinite(original_lufs):
            raise PolicyError("Cannot determine integrated loudness for mastering")
        gain = max(-18.0, min(18.0, float(target_lufs) - original_lufs))
        result = subprocess.run([
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
            "-i", str(temp), "-af", f"volume={gain:.3f}dB,alimiter=limit=0.92",
            *codec, str(mastered)], capture_output=True, text=True, timeout=1800)
        if result.returncode:
            raise PolicyError("Final audio mastering failed: " + result.stderr[-350:])
        mastered_meta = media_probe(mastered)
        if not any(s.get("codec_type") == "audio" for s in mastered_meta["streams"]):
            raise PolicyError("Mastered file has no audio stream")
        final_analysis = audio_analyze(mastered, seconds=40)
        final_lufs = final_analysis.get("integratedLufs")
        if dest.exists():
            raise PolicyError("Destination appeared while mixing")
        os.link(mastered, dest)
        return {"file": str(dest), "duration": mastered_meta["format"]["duration"],
                "musicDuck": bool(music), "verified": True,
                "targetLufs": float(target_lufs), "integratedLufs": final_lufs,
                "loudnessWithin3Lufs": bool(final_lufs is not None and
                                         abs(final_lufs - target_lufs) <= 3.0)}
    finally:
        temp.unlink(missing_ok=True)
        mastered.unlink(missing_ok=True)
