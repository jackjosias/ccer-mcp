"""Optional on-device vision via an ALREADY installed Ollama Qwen3.5 model.

Only 127.0.0.1; no model pulls, cloud upload, daemon management, media
persistence or automatic background inference. Verified frame bytes from
existing CCER FFmpeg decoder; model descriptions remain unverified opinions.
"""
from __future__ import annotations
import base64
import hashlib
import json
import math
import socket
import urllib.request
from pathlib import Path

from .controls import PolicyError, inside, media_probe
from .timecoded_review import _frame
from .av_replay_poll import _pressure

MODEL = "qwen3.5:0.8b"
MANIFEST = (Path.home() / ".ollama/models/manifests/registry.ollama.ai"
            / "library/qwen3.5/0.8b")
BLOBS = Path.home() / ".ollama/models/blobs"
LOOPBACK = "http://127.0.0.1:11434/api/generate"
SYSTEM_PROMPT = (
    "Describe objectively the visible scene in this single video frame in "
    "one or two short sentences. Do not infer a person's identity, speech, "
    "audio, unseen actions, or events outside this image. State uncertainty "
    "when the scene is unclear. Reply using plain text only."
)


def vision_status():
    """Read-only local readiness, no subprocess and no auto-download."""
    installed = False
    model_bytes = 0
    try:
        if MANIFEST.is_file() and not MANIFEST.is_symlink():
            data = json.loads(MANIFEST.read_text(encoding="utf-8"))
            models = [layer for layer in data.get("layers", [])
                      if layer.get("mediaType") == "application/vnd.ollama.image.model"]
            if len(models) == 1:
                layer = models[0]
                digest = layer.get("digest", "")
                if (digest.startswith("sha256:") and len(digest) == 71
                        and all(c in "0123456789abcdef" for c in digest[7:])):
                    blob = BLOBS / ("sha256-" + digest[7:])
                    model_bytes = int(layer.get("size", 0))
                    installed = (blob.is_file() and not blob.is_symlink()
                                 and 0 < model_bytes <= 2_000_000_000
                                 and blob.stat().st_size == model_bytes)
    except (OSError, ValueError, TypeError, KeyError):
        installed = False
    try:
        with socket.create_connection(("127.0.0.1", 11434), timeout=.2):
            server_online = True
    except OSError:
        server_online = False
    pressure = _pressure()
    safe_to_load = pressure["tier"] != "critical"
    return {"model": MODEL, "installed": installed,
            "modelBytes": model_bytes if installed else 0,
            "ollamaLoopbackOnline": server_online,
            "ready": installed and server_online and safe_to_load,
            "resourceAdvisory": pressure,
            "modelServerReady": installed and server_online,
            "heavyInferenceAllowed": safe_to_load,
            "inferencePerformed": False, "mediaUploadedToCloud": False,
            "requiresExplicitToolCall": True, "modelDownloadPerformed": False,
            "audioUnderstandingAvailable": False}


def describe_frame(root, file, *, time_seconds=0):
    """Describe ONE authentic image; do not falsely certify semantic truth."""
    if type(time_seconds) not in (float, int) or not math.isfinite(time_seconds):
        raise PolicyError("timeSeconds must be finite")
    status = vision_status()
    if not status["ready"]:
        raise PolicyError("Local Qwen3.5 vision unavailable; no inference attempted")
    source = inside(root, file, must_exist=True)
    meta = media_probe(source)
    if not any(s.get("codec_type") == "video" for s in meta["streams"]):
        raise PolicyError("Vision inference requires video")
    try:
        duration = float(meta["format"]["duration"])
    except (KeyError, ValueError, TypeError) as error:
        raise PolicyError("Media duration unavailable") from error
    if not math.isfinite(duration) or not 0 < duration <= 86400:
        raise PolicyError("Unsupported media duration")
    if not 0 <= time_seconds < duration:
        raise PolicyError("Frame timestamp outside video duration")
    # Decode the existing FFmpeg 480-pixel JPEG directly in memory, no temp file.
    stamp = round(float(time_seconds), 3)
    frame = _frame(source, stamp)
    if not frame.startswith(b"\xff\xd8") or not frame.endswith(b"\xff\xd9"):
        raise PolicyError("Invalid decoded JPEG")
    image_sha = hashlib.sha256(frame).hexdigest()
    payload = json.dumps({
        "model": MODEL, "prompt": SYSTEM_PROMPT,
        "images": [base64.b64encode(frame).decode("ascii")],
        "stream": False, "keep_alive": "0s",
        "options": {"num_ctx": 1024, "num_predict": 100, "num_thread": 2},
    }, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(LOOPBACK, data=payload, method="POST",
                                     headers={"Content-Type": "application/json"})
    # No environment-defined HTTP proxy or URL redirection to an outside host.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise PolicyError("Vision HTTP redirects forbidden")
    # Explicitly replace the default redirect handler (not append after it).
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=80) as response:
            if response.status != 200:
                raise PolicyError("Local vision HTTP response rejected")
            answer = response.read(16385)
    except (OSError, TimeoutError, ValueError) as error:
        raise PolicyError("Local vision endpoint unavailable or failed") from error
    if len(answer) > 16384:
        raise PolicyError("Vision response exceeds bounded size")
    try:
        data = json.loads(answer)
        text = data["response"]
    except (ValueError, KeyError, TypeError) as error:
        raise PolicyError("Invalid local vision response") from error
    if not isinstance(text, str) or not 0 < len(text.strip()) <= 2000:
        raise PolicyError("Empty or oversized vision description")
    return {"file": str(source), "timeSeconds": stamp, "frameSha256": image_sha,
            "model": MODEL, "description": text.strip(),
            "modelResponseReceived": True, "visionInferencePerformed": True,
            "semanticAccuracyIndependentlyVerified": False,
            "audioUnderstood": False, "audioTranscribed": False,
            "imageUploadedToCloud": False, "readOnly": True,
            "temporaryImageFilesCreated": False}


if __name__ == "__main__":
    # Deliberately only a read-only status CLI. Inference stays explicit via MCP.
    print(json.dumps(vision_status(), ensure_ascii=False))
