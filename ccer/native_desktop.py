"""Opt-in native Slint desktop bridge; no X11 input or silent fallback."""
import hashlib
import os
import threading
import time

from .controls import PolicyError, confirm
from .inapp_protocol import InAppComputerUse

_LOCK = threading.RLock()
_SESSION = None
_FINGERPRINT = None
_BEFORE = None
_SESSION_STARTED = None
# Reconnect before the native 15-second idle timeout, without retriggering gestures.


def _visible_config():
    # Private Xvfb sessions cannot attach to the user's visible Concat.
    # Explicit CCER_INAPP_SOCKET sessions are handled separately by _session().
    if os.environ.get("CCER_PRIVATE_DISPLAY") or os.environ.get("CCER_PRIVATE_XVFB_PID"):
        return None
    display = os.environ.get("DISPLAY")
    if not display:
        return None
    from .visible_desktop import _file_state, _live
    receipt = _file_state()
    if (receipt is not None and _live(receipt)
            and receipt.get("display") == display):
        return receipt["socket"], receipt["proof"], receipt["pid"]
    return None


def enabled():
    if "CCER_INAPP_SOCKET" in os.environ:
        return True
    return _visible_config() is not None


def _close():
    global _SESSION, _FINGERPRINT, _BEFORE, _SESSION_STARTED
    previous = _SESSION
    _SESSION, _FINGERPRINT, _BEFORE, _SESSION_STARTED = None, None, None, None
    if previous is not None:
        previous.close()


def _session():
    global _SESSION, _FINGERPRINT, _SESSION_STARTED
    if "CCER_INAPP_SOCKET" in os.environ:
        path = os.environ.get("CCER_INAPP_SOCKET", "")
        key = "".join(("CCER", "_INAPP", "_TOKEN"))
        credential = os.environ.get(key, "")
        raw_pid = os.environ.get("CCER_INAPP_PID", "")
        try:
            pid = int(raw_pid) if raw_pid else None
        except ValueError as error:
            raise PolicyError("INAPP_DENIED: invalid PID") from error
    else:
        observed = _visible_config()
        if observed is None:
            raise PolicyError("INAPP_UNAVAILABLE: no trusted visible Concat Slint session")
        path, credential, pid = observed
    config = (path, hashlib.sha256(credential.encode()).hexdigest(), pid)
    if _SESSION is not None and (config != _FINGERPRINT or _SESSION_STARTED is None
            or time.monotonic() - _SESSION_STARTED > 8):
        _close()
    if _SESSION is None:
        _SESSION = InAppComputerUse(path, credential, expected_pid=pid).__enter__()
        _FINGERPRINT = config
        _SESSION_STARTED = time.monotonic()
    return _SESSION


def _window(session):
    return {"windowId": session._window, "width": session._width,
            "height": session._height, "title": "Concat (native Slint)",
            "display": "native-slint"}


def status():
    with _LOCK:
        try:
            client = _session()
            return {"available": True, "window": _window(client),
                    "captureScope": "verified native Slint framebuffer",
                    "controlScope": "private Slint events, never physical X11",
                    "inputReady": True, "isolation": {"private": True, "engine": "slint"},
                    "requiresActionConfirmation": True, "otherAppsAccessible": False}
        except Exception:
            _close()
            raise


def capture(*, max_width=840):
    global _BEFORE
    if type(max_width) is not int or not 320 <= max_width <= 1600:
        raise PolicyError("maxWidth must be integer 320..1600")
    with _LOCK:
        try:
            # _session() reconnects if the cached Slint socket is too old.
            client = _session()
            frame = client.observe()
            _BEFORE = dict(frame, observedAt=time.monotonic())
            return {"window": _window(client), "imageBase64": frame["imageBase64"],
                    "mimeType": frame["mimeType"], "sha256": frame["sha256"],
                    "frameNo": frame["frameNo"], "capturedAt": time.time(),
                    "imageWidth": client._width, "coordinates": "native logical pixels",
                    "captureSource": "authenticated_native_slint",
                    "safeForClickReceipt": True, "readOnly": False}
        except Exception:
            _close()
            raise


def interact(*, expected_window_id, action, confirm_action, x=None, y=None,
             button=1, key=None, text=None, scroll=None, with_capture=True,
             target_x=None, target_y=None, duration=.7):
    global _BEFORE
    confirm(confirm_action)
    if with_capture is not True:
        raise PolicyError("INAPP_DENIED: AFTER image mandatory")
    with _LOCK:
        before, _BEFORE = _BEFORE, None
        try:
            if before is None or time.monotonic() - before["observedAt"] > 75:
                raise PolicyError("INAPP_DENIED: fresh BEFORE image mandatory")
            # Revalidate the socket lifecycle before any gesture. Rust closes
            # inactive sockets; reconnect is safe only BEFORE dispatch.
            client = _session()
            if client._window != expected_window_id:
                raise PolicyError("INAPP_DENIED: wrong native window")
            if action == "click" and button == 1:
                gesture = {"type": "click", "x": x, "y": y}
            elif action == "move":
                gesture = {"type": "move", "x": x, "y": y}
            elif action == "drag" and button == 1:
                gesture = {"type": "drag", "x": x, "y": y,
                           "targetX": target_x, "targetY": target_y,
                           "duration": duration}
            elif action == "file_drop":
                gesture = {"type": "file_drop", "path": text}
            elif action == "select_export_folder":
                gesture = {"type": "select_export_folder"}
            elif action == "key":
                gesture = {"type": "key", "key": key}
            elif action == "type_text":
                gesture = {"type": "type_text", "text": text}
            elif action == "scroll" and type(scroll) is int and 0 < abs(scroll) <= 8:
                gesture = {"type": "scroll", "x": x, "y": y, "deltaY": scroll * 15}
            else:
                raise PolicyError("INAPP_DENIED: unsupported native gesture, no X11 fallback")
            # Re-observe on the current authenticated connection, even if
            # the previous socket was rotated. Fail closed if the UI changed.
            current = client.observe()
            if current["sha256"] != before["sha256"]:
                raise PolicyError("INAPP_DENIED: Concat changed since BEFORE image; recapture")
            after = client.act(gesture, confirm=True, expected_sha256=current["sha256"])
            return {"action": action, "windowId": client._window, "window": _window(client),
                    "verifiedTarget": True, "actionSent": True,
                    "visualOutcomeVerified": False,
                    "note": "Inspect actual Slint AFTER frame for the intended UI change",
                    "imageBase64": after["imageBase64"], "mimeType": after["mimeType"],
                    "sha256": after["sha256"], "frameNo": after["frameNo"],
                    "capturedAt": time.time(), "imageWidth": client._width}
        except Exception:
            _close()
            raise
