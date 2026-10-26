"""Read-only health probe of Concat's preinstalled multilingual Whisper model.

Does not load model, run transcription, download assets, modify media or GUI.
Pinned model metadata from Concat concat-speech/src/transcribe.rs.
"""
from __future__ import annotations
import hashlib
import json
import os
import stat
from pathlib import Path
from .controls import PolicyError

MODEL_ID = "small"
MODEL_BYTES = 487601967
MODEL_SHA256 = "1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b"


def _model_path():
    value = os.getenv("XDG_DATA_HOME", "")
    base = Path(value) if value and Path(value).is_absolute() else Path.home() / ".local/share"
    return base / "app.concat.editor" / "whisper-models" / "ggml-small.bin"


def _available_memory():
    try:
        for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
            if line.startswith("MemAvailable:"):
                number, unit = line.split(":")[1].split()
                if unit == "kB":
                    return int(number) * 1024
    except (OSError, ValueError, UnicodeError):
        pass
    return None


def status(*, verify_sha256=False):
    if type(verify_sha256) is not bool:
        raise PolicyError("verifySha256 must be boolean")
    path = _model_path()
    installed, size, invalid = False, None, None
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            invalid = "not_owner_regular_file"
        else:
            size = info.st_size
            installed = size == MODEL_BYTES
            if not installed:
                invalid = "size_mismatch"
    except FileNotFoundError:
        pass
    except OSError:
        invalid = "not_readable"

    integrity = "not_verified"
    if verify_sha256:
        if not installed:
            integrity = "unavailable"
        else:
            digest = hashlib.sha256()
            try:
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                integrity = "verified" if digest.hexdigest() == MODEL_SHA256 else "mismatch"
            except OSError:
                integrity = "unavailable"
    mem = _available_memory()
    try:
        load_per_core = round(os.getloadavg()[0] / (os.cpu_count() or 1), 2)
    except OSError:
        load_per_core = None
    under_pressure = ((mem is not None and mem < 3 * 1024**3)
                      or (load_per_core is not None and load_per_core > 2.0))
    return {
        "engine": "Concat embedded whisper.cpp",
        "modelId": MODEL_ID, "modelPath": str(path),
        "installed": installed, "sizeBytes": size, "expectedBytes": MODEL_BYTES,
        "invalidReason": invalid, "integrity": integrity,
        "digestVerified": integrity == "verified",
        "verifySha256Requested": verify_sha256,
        "memoryAvailableBytes": mem, "loadPerLogicalCpu": load_per_core,
        "resourceAdvisory": "defer_heavy_transcription" if under_pressure
                            else "no_obvious_pressure_from_these_metrics",
        "transcriptionPerformed": False, "modelLoaded": False, "downloadPerformed": False,
        "next": "Use actual Concat captions/transcriber GUI on authorized speech footage; model integrity is not transcription quality.",
    }


def main():
    print(json.dumps(status(verify_sha256="--verify-sha256" in os.sys.argv)))


if __name__ == "__main__":
    main()
