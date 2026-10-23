"""Path policy, durable journal, atomic state, FFmpeg probing."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path


class PolicyError(ValueError):
    pass


def inside(root, raw, must_exist=False):
    root = Path(root).expanduser().resolve()
    target = Path(raw).expanduser().resolve(strict=must_exist)
    if target != root and root not in target.parents:
        raise PolicyError("Path outside allowed project root: " + str(target))
    return target


def confirm(value):
    if value is not True:
        raise PolicyError("Explicit confirm=true required")


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with tmp.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


class Journal:
    def __init__(self, root):
        self.path = Path(root) / ".ccer" / "audit.jsonl"
        self.lock = threading.RLock()

    def append(self, event, data):
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            prev = "0" * 64
            if self.path.exists():
                for line in self.path.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        prev = json.loads(line)["sha256"]
            record = {"time": time.time(), "event": event,
                      "data": data, "previous": prev}
            record["sha256"] = hashlib.sha256(json.dumps(record,
                sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            with self.path.open("a", encoding="utf-8") as out:
                out.write(json.dumps(record, sort_keys=True) + "\n")
                out.flush()
                os.fsync(out.fileno())
            return record

    def verify(self):
        prev, count = "0" * 64, 0
        if not self.path.exists():
            return {"valid": True, "events": 0, "head": prev}
        for line in self.path.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            sha = rec.pop("sha256")
            found = hashlib.sha256(json.dumps(rec, sort_keys=True,
                     separators=(",", ":")).encode()).hexdigest()
            if sha != found or rec["previous"] != prev:
                return {"valid": False, "errorAt": count + 1}
            prev, count = sha, count + 1
        return {"valid": True, "events": count, "head": prev}


def media_probe(path):
    path = Path(path)
    if not path.is_file():
        raise PolicyError("Media not found")
    if not shutil.which("ffprobe"):
        raise PolicyError("ffprobe unavailable")
    p = subprocess.run(["ffprobe", "-v", "error", "-show_format",
                        "-show_streams", "-of", "json", str(path)],
                       capture_output=True, text=True, timeout=30)
    if p.returncode:
        raise PolicyError("ffprobe failed: " + p.stderr[-250:])
    value = json.loads(p.stdout)
    return {"file": str(path), "bytes": path.stat().st_size,
        "format": {k: value.get("format", {}).get(k) for k in
                   ("format_name", "duration", "bit_rate")},
        "streams": [{k: v for k, v in s.items() if k in (
            "codec_type", "codec_name", "width", "height", "sample_rate",
            "channels", "avg_frame_rate")} for s in value.get("streams", [])]}


def audio_analyze(path, seconds=40):
    path = Path(path)
    if not path.is_file() or not shutil.which("ffmpeg"):
        raise PolicyError("Media missing or ffmpeg unavailable")
    seconds = min(300, max(1, int(seconds)))
    p = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-i",
                        str(path), "-t", str(seconds), "-af",
                        "silencedetect=noise=-40dB:d=0.5,ebur128=peak=true",
                        "-f", "null", "-"], capture_output=True,
                       text=True, timeout=seconds * 3 + 40)
    loudness = re.findall(r"\bI:\s*(-?[\d.]+)\s+LUFS", p.stderr)
    peaks = re.findall(r"\bPeak:\s*(-?[\d.]+)\s+dBFS", p.stderr)
    silences = re.findall(r"silence_(start|end):\s*([\d.]+)", p.stderr)
    return {"success": p.returncode == 0,
        "integratedLufs": float(loudness[-1]) if loudness else None,
        "truePeakDbfs": float(peaks[-1]) if peaks else None,
        "silences": [{"kind": k, "seconds": float(v)} for k,v in silences],
        "secondsAnalyzed": seconds}
