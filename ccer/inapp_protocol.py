"""Versioned, fail-closed CCER <-> in-process Slint Computer Use contract.

Experimental until a separately built Concat binary implements this protocol.
NEVER inject X11/xdotool input or silently use the native project-edit API.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
import socket
import stat
import struct
import threading
import time
from pathlib import Path

from .controls import PolicyError

PROTOCOL = "ccer-slint-input/v1"
MAX_MESSAGE = 8_000_000
MAX_AGE = 75.0
PRIVATE_ROOT = Path.home() / ".local" / "state" / "ccer-inapp"


def _secure_socket_path(raw: str) -> Path:
    if not raw:
        raise PolicyError("INAPP_UNAVAILABLE: no socket configured")
    path = Path(raw)
    if not path.is_absolute() or path.is_symlink() or path.parent != PRIVATE_ROOT:
        raise PolicyError("INAPP_DENIED: socket must belong to the dedicated CCER in-app directory")
    for entry in (PRIVATE_ROOT, path):
        try:
            info = entry.lstat()
        except OSError as exc:
            raise PolicyError("INAPP_UNAVAILABLE: private socket is not present") from exc
        if info.st_uid != os.getuid() or (info.st_mode & 0o077):
            raise PolicyError("INAPP_DENIED: socket/directory permissions are unsafe")
    if not stat.S_ISDIR(PRIVATE_ROOT.lstat().st_mode):
        raise PolicyError("INAPP_DENIED: socket root is not a directory")
    if not stat.S_ISSOCK(path.lstat().st_mode):
        raise PolicyError("INAPP_DENIED: endpoint is not a Unix-domain socket")
    return path


def _valid_hash(raw: object) -> bool:
    return isinstance(raw, str) and re.fullmatch("[0-9a-f]{64}", raw) is not None


class InAppComputerUse:
    """One-shot observed GUI actions on the exact in-app Slint session.

    This transport is NOT X11 control. It cannot operate until Concat itself
    exposes a compatible, authorized, real-image Unix-domain endpoint.
    """
    def __init__(self, socket_path: str, token: str, *, expected_pid: int | None = None,
                 timeout: float = 8.0):
        if not isinstance(token, str) or len(token) < 32:
            raise PolicyError("INAPP_DENIED: private authorization token missing")
        if expected_pid is not None and (not isinstance(expected_pid, int) or expected_pid < 2):
            raise PolicyError("INAPP_DENIED: expected PID invalid")
        self.path = _secure_socket_path(socket_path)
        self._proof_digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        self.expected_pid = expected_pid
        self.timeout = min(15.0, max(1.0, float(timeout)))
        self._connection = None
        self._stream = None
        self._counter = 0
        self._window = None
        self._session = None
        self._width = 0
        self._height = 0
        self._observation = None
        self._lock = threading.RLock()

    def __enter__(self):
        _secure_socket_path(str(self.path))
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            conn.settimeout(self.timeout)
            conn.connect(str(self.path))
            if not hasattr(socket, "SO_PEERCRED"):
                raise PolicyError("INAPP_DENIED: Linux peer credentials unavailable")
            pid, uid, gid = struct.unpack("3i", conn.getsockopt(
                socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))
            if uid != os.getuid() or (self.expected_pid is not None and pid != self.expected_pid):
                raise PolicyError("INAPP_DENIED: server PID/UID attestation failed")
            self._connection = conn
            self._stream = conn.makefile("rwb", buffering=0)
            hello = self._rpc("hello", {"protocol": PROTOCOL, "proof": self._proof_digest})
            if (hello.get("protocol") != PROTOCOL or hello.get("app") != "Concat"
                    or hello.get("engine") != "slint"
                    or hello.get("capabilities") != ["real-frame", "scene-input"]):
                raise PolicyError("INAPP_DENIED: incompatible or nonvisual adapter")
            window = hello.get("windowId")
            session = hello.get("sessionId")
            width, height = hello.get("width"), hello.get("height")
            if (not isinstance(window, str) or not window
                    or not isinstance(session, str) or not re.fullmatch("[0-9a-f]{32}", session)
                    or type(width) is not int or type(height) is not int
                    or not (200 <= width <= 8192 and 200 <= height <= 8192)):
                raise PolicyError("INAPP_DENIED: invalid window identity or dimensions")
            self._session, self._window = session, window
            self._width, self._height = width, height
            return self
        except BaseException:
            self.close()
            conn.close()
            raise

    def _rpc(self, method: str, parameters: dict) -> dict:
        self._counter += 1
        query = {"v": 1, "id": self._counter, "method": method, "params": parameters}
        wire = json.dumps(query, separators=(",", ":")).encode("utf-8")
        if len(wire) > MAX_MESSAGE:
            raise PolicyError("INAPP_DENIED: request too large")
        self._stream.write(wire + bytes([10]))
        answer = self._stream.readline(MAX_MESSAGE + 1)
        if not answer or len(answer) > MAX_MESSAGE or not answer.endswith(bytes([10])):
            raise PolicyError("INAPP_UNAVAILABLE: truncated/oversized response")
        try:
            obj = json.loads(answer)
        except (ValueError, UnicodeError) as exc:
            raise PolicyError("INAPP_DENIED: malformed response") from exc
        if not isinstance(obj, dict) or obj.get("id") != self._counter:
            raise PolicyError("INAPP_DENIED: mismatched native response")
        if obj.get("error"):
            reason = obj["error"].get("message") if isinstance(obj["error"], dict) else None
            safe_reason = reason[:180] if isinstance(reason, str) else "unspecified"
            raise PolicyError("INAPP_DENIED: native adapter rejected: " + safe_reason)
        result = obj.get("result")
        if not isinstance(result, dict):
            raise PolicyError("INAPP_DENIED: invalid result")
        return result

    def _check_frame(self, frame: object) -> dict:
        if not isinstance(frame, dict):
            raise PolicyError("INAPP_DENIED: actual frame required")
        try:
            encoded = frame["imageBase64"]
            if not isinstance(encoded, str) or len(encoded) > MAX_MESSAGE:
                raise ValueError("size")
            data = base64.b64decode(encoded, validate=True)
        except (KeyError, ValueError, base64.binascii.Error) as exc:
            raise PolicyError("INAPP_DENIED: invalid visual frame bytes") from exc
        if (frame.get("mimeType") != "image/jpeg" or len(data) < 100
                or not data.startswith(bytes.fromhex("ffd8"))
                or not data.endswith(bytes.fromhex("ffd9"))
                or not _valid_hash(frame.get("sha256"))
                or hashlib.sha256(data).hexdigest() != frame["sha256"]
                or frame.get("windowId") != self._window
                or type(frame.get("frameNo")) is not int
                or frame["frameNo"] < 0):
            raise PolicyError("INAPP_DENIED: visual frame verification failed")
        return {"windowId": self._window, "sha256": frame["sha256"],
                "frameNo": frame["frameNo"], "imageBase64": encoded,
                "mimeType": "image/jpeg"}

    def observe(self) -> dict:
        with self._lock:
            self._observation = None
            frame = self._check_frame(self._rpc("capture", {"sessionId": self._session}))
            self._observation = dict(frame, observedAt=time.monotonic())
            return frame

    def act(self, gesture: dict, *, confirm: bool, expected_sha256: str) -> dict:
        with self._lock:
            observation = self._observation
            self._observation = None  # even on failure, another capture is mandatory
            if confirm is not True:
                raise PolicyError("INAPP_DENIED: explicit user confirmation required")
            if (observation is None or time.monotonic() - observation["observedAt"] > MAX_AGE
                    or expected_sha256 != observation["sha256"]):
                raise PolicyError("INAPP_DENIED: fresh matching BEFORE screenshot required")
            safe = self._validate_gesture(gesture)
            response = self._rpc("gesture", {
                "sessionId": self._session, "windowId": self._window,
                "expectedFrameNo": observation["frameNo"],
                "expectedSha256": observation["sha256"], "gesture": safe,
            })
            if response.get("accepted") is not True or response.get("dispatched") is not True:
                raise PolicyError("INAPP_DENIED: native Slint event was not accepted")
            result = self._check_frame(response.get("after"))
            if result["frameNo"] <= observation["frameNo"]:
                raise PolicyError("INAPP_DENIED: AFTER frame must advance beyond BEFORE")
            return result

    def _validate_gesture(self, raw: object) -> dict:
        if not isinstance(raw, dict):
            raise PolicyError("INAPP_DENIED: malformed gesture")
        kind = raw.get("type")
        if kind not in ("click", "move", "drag", "scroll", "key", "type_text", "file_drop", "select_export_folder"):
            raise PolicyError("INAPP_DENIED: unsupported gesture")
        allowed = {
            "click": {"type", "x", "y"},
            "move": {"type", "x", "y"},
            "drag": {"type", "x", "y", "targetX", "targetY", "duration"},
            "scroll": {"type", "x", "y", "deltaY"},
            "key": {"type", "key"},
            "type_text": {"type", "text"},
            "file_drop": {"type", "path"},
            "select_export_folder": {"type"},
        }[kind]
        if set(raw) != allowed:
            raise PolicyError("INAPP_DENIED: unexpected or missing gesture field")
        if kind == "select_export_folder":
            configured = os.environ.get("CCER_INAPP_EXPORT_ROOT", "")
            folder = Path(configured)
            if (not configured or not folder.is_absolute()
                    or folder.is_symlink() or not folder.is_dir()):
                raise PolicyError("INAPP_DENIED: approved export directory required")
        elif kind == "file_drop":
            supplied = raw["path"]
            configured = os.environ.get("CCER_INAPP_MEDIA_ROOT", "")
            if not isinstance(supplied, str) or not 0 < len(supplied) <= 4096 or not configured:
                raise PolicyError("INAPP_DENIED: approved media file required")
            path, root = Path(supplied), Path(configured)
            if (not path.is_absolute() or not root.is_absolute()
                    or path.is_symlink() or root.is_symlink()
                    or not path.is_file() or not root.is_dir()
                    or not path.resolve().is_relative_to(root.resolve())):
                raise PolicyError("INAPP_DENIED: media outside approved directory")
            if path.suffix.lower() not in {
                ".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v",
                ".mp3", ".wav", ".aac", ".m4a", ".flac", ".ogg",
                ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff",
            }:
                raise PolicyError("INAPP_DENIED: unsupported media extension")
        elif kind == "key":
            if raw["key"] not in ("Escape", "Left", "Right", "Up", "Down", "SelectAll"):
                raise PolicyError("INAPP_DENIED: keyboard whitelist violated")
        elif kind == "type_text":
            value = raw["text"]
            if (not isinstance(value, str) or not 0 < len(value) <= 160
                    or len(value.encode("utf-8")) > 1024 or not value.isprintable()):
                raise PolicyError("INAPP_DENIED: text input must be 1..160 printable characters")
        else:
            for prop, bound in (("x", self._width), ("y", self._height)):
                value = raw[prop]
                if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value < bound:
                    raise PolicyError("INAPP_DENIED: coordinate outside private window")
            if kind == "drag":
                for prop, bound in (("targetX", self._width), ("targetY", self._height)):
                    val = raw[prop]
                    if type(val) not in (int, float) or not math.isfinite(val) or not 0 <= val < bound:
                        raise PolicyError("INAPP_DENIED: drag target outside private window")
                if type(raw["duration"]) not in (float, int) or not 0.15 <= raw["duration"] <= 4:
                    raise PolicyError("INAPP_DENIED: invalid drag duration")
            if kind == "scroll" and (type(raw["deltaY"]) not in (int,float)
                    or not math.isfinite(raw["deltaY"]) or abs(raw["deltaY"]) > 120):
                raise PolicyError("INAPP_DENIED: invalid scroll delta")
        return raw.copy()

    def close(self):
        self._observation = None
        if self._stream:
            self._stream.close()
            self._stream = None
        if self._connection:
            self._connection.close()
            self._connection = None

    def __exit__(self, *_):
        self.close()
