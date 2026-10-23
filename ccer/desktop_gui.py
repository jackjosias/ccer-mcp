"""Scoped Concat Desktop X11 GUI bridge, no shell and no other-window control.

Expose screenshots as MCP image content through Gateway, and allow explicit,
window-ID-guarded user-authorized keyboard/mouse actions.
"""
from __future__ import annotations

import base64
import hashlib
import os
import re
import shutil
import subprocess
import threading
import time

from .controls import PolicyError, confirm


_GUI_LOCK = threading.RLock()
_ALLOWED_KEYS = frozenset({
    "Escape", "Tab", "Return", "BackSpace", "Delete",
    "Left", "Right", "Up", "Down", "Home", "End",
    "space", "ctrl+s", "ctrl+z", "ctrl+shift+z",
})


def _run(argv, *, timeout=12, binary=False):
    try:
        p = subprocess.run(argv, capture_output=True, text=not binary, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PolicyError("Desktop tool unavailable or timed out: " + argv[0]) from error
    if p.returncode:
        message = p.stderr if not binary else p.stderr.decode("utf-8", errors="replace")
        raise PolicyError("Desktop operation failed: " + message[-300:])
    return p.stdout


def _environment():
    if os.environ.get("XDG_SESSION_TYPE", "").lower() != "x11":
        raise PolicyError("This desktop bridge requires a local X11 session")
    display = os.environ.get("DISPLAY", "")
    if not re.fullmatch(r":[0-9]{1,3}(?:\.[0-9]{1,2})?", display):
        raise PolicyError("Refuse nonlocal or missing X11 DISPLAY")
    for exe in ("wmctrl", "xwininfo", "xprop", "xdotool", "ffmpeg"):
        if not shutil.which(exe):
            raise PolicyError("Missing required local GUI tool: " + exe)
    return display


def _window():
    display = _environment()
    listing = _run(["wmctrl", "-lx"], timeout=8)
    matches = []
    for line in listing.splitlines():
        pieces = line.split(maxsplit=4)
        if len(pieces) < 5:
            continue
        raw, desktop, wmclass, host, title = pieces
        if wmclass.lower() != ".concat" or not title.startswith("Concat"):
            continue
        if not re.fullmatch(r"0x[0-9a-fA-F]+", raw):
            continue
        win_id = int(raw, 16)
        props = _run(["xprop", "-id", raw, "WM_CLASS", "_NET_WM_PID"], timeout=6)
        if not re.search(r'WM_CLASS\(STRING\)\s*=\s*""\s*,\s*"concat"', props):
            continue
        pid = re.search(r"_NET_WM_PID\(CARDINAL\)\s*=\s*(\d+)", props)
        if pid is None:
            continue
        command = _run(["ps", "-p", pid.group(1), "-o", "comm="], timeout=6).strip()
        if command not in ("AppRun", "Concat"):
            continue
        geometry = _run(["xwininfo", "-id", raw], timeout=6)
        width = re.search(r"^\s*Width:\s*(\d+)", geometry, flags=re.M)
        height = re.search(r"^\s*Height:\s*(\d+)", geometry, flags=re.M)
        if not width or not height or "Map State: IsViewable" not in geometry:
            continue
        w, h = int(width.group(1)), int(height.group(1))
        if not (200 <= w <= 7680 and 200 <= h <= 4320):
            continue
        matches.append({"windowId": raw.lower(), "pid": int(pid.group(1)),
                        "title": title, "width": w, "height": h, "display": display})
    if len(matches) != 1:
        raise PolicyError(f"Expected one verified Concat window, detected {len(matches)}")
    return matches[0]


def status():
    """Read-only; no desktop activation."""
    with _GUI_LOCK:
        return {"available": True, "window": _window(),
                "captureScope": "Concat X11 window_id, not whole desktop",
                "controlScope": "window-ID-guarded xdotool, activation verified",
                "requiresActionConfirmation": True,
                "otherAppsAccessible": False}


def capture(*, max_width=840):
    """Capture only the currently verified Concat window, for the AI reviewer."""
    if type(max_width) is not int or not 320 <= max_width <= 1600:
        raise PolicyError("maxWidth must be integer 320..1600")
    with _GUI_LOCK:
        window = _window()
        target = min(max_width, window["width"])
        vf = f"scale={target}:-2"
        jpeg = _run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                     "-f", "x11grab", "-window_id", str(int(window["windowId"],16)),
                     "-video_size", f"{window['width']}x{window['height']}",
                     "-i", window["display"], "-frames:v", "1",
                     "-vf", vf, "-c:v", "mjpeg", "-q:v", "8",
                     "-f", "image2pipe", "-"], timeout=25, binary=True)
        if not 128 < len(jpeg) < 2_000_000 or not jpeg.startswith(b"\xff\xd8"):
            raise PolicyError("Concat screenshot invalid or too large")
        return {"window": window, "imageBase64": base64.b64encode(jpeg).decode("ascii"),
                "mimeType": "image/jpeg",
                "sha256": hashlib.sha256(jpeg).hexdigest(),
                "capturedAt": time.time(), "imageWidth": target,
                "coordinates": "Interaction x/y are full window pixels, not thumbnail pixels"}


def interact(*, expected_window_id, action, confirm_action, x=None, y=None,
             button=1, key=None, text=None, scroll=None, with_capture=True):
    confirm(confirm_action)
    if type(with_capture) is not bool:
        raise PolicyError("withCapture must be boolean")
    with _GUI_LOCK:
        win = _window()
        if expected_window_id != win["windowId"]:
            raise PolicyError("Stale Concat window ID; recapture before acting")
        if action not in ("click", "key", "type", "scroll"):
            raise PolicyError("Only click/key/type/scroll actions are supported")
        if action in ("click", "scroll"):
            if (type(x) is not int or type(y) is not int or
                not 0 <= x < win["width"] or not 0 <= y < win["height"]):
                raise PolicyError("Coordinates must be inside Concat window bounds")
        if action == "click" and (type(button) is not int or button not in (1,2,3)):
            raise PolicyError("Click button must be 1..3")
        if action == "key" and key not in _ALLOWED_KEYS:
            raise PolicyError("Keyboard shortcut not in explicit safe allowlist")
        if action == "type" and (not isinstance(text, str) or
                                 not 1 <= len(text) <= 500 or
                                 any(ord(ch) < 32 for ch in text)):
            raise PolicyError("Type supports only up to 500 printable characters")
        if action == "scroll" and (type(scroll) is not int or not -8 <= scroll <= 8 or scroll == 0):
            raise PolicyError("Scroll must be an integer between -8 and +8, excluding zero")
        _run(["xdotool", "windowactivate", "--sync", str(int(win["windowId"], 16))])
        active = int(_run(["xdotool", "getactivewindow"]).strip())
        if active != int(win["windowId"], 16):
            raise PolicyError("Concat is not the active window; aborting input")
        if action in ("click", "scroll"):
            _run(["xdotool", "mousemove", "--window", str(active), str(x), str(y)])
        if action == "click":
            _run(["xdotool", "click", str(button)])
        elif action == "key":
            _run(["xdotool", "key", "--clearmodifiers", key])
        elif action == "type":
            _run(["xdotool", "type", "--clearmodifiers", "--delay", "12", "--", text], timeout=30)
        else:
            direction_button = "4" if scroll > 0 else "5"
            _run(["xdotool", "click", "--repeat", str(abs(scroll)),
                  "--delay", "80", direction_button])
        result = {"action": action, "windowId": win["windowId"], "verifiedTarget": True,
                  "actionSent": True, "visualOutcomeVerified": False,
                  "note": "Inspect returned screenshot to verify intended UI change"}
        if with_capture:
            result.update(capture())
        return result
