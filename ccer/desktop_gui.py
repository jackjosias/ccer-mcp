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
from .focus_isolation import require_private_input
from . import native_desktop


_GUI_LOCK = threading.RLock()
_ALLOWED_KEYS = frozenset({
    "Escape", "Tab", "Return", "BackSpace", "Delete",
    "Left", "Right", "Up", "Down", "Home", "End",
    "space", "ctrl+s", "ctrl+z", "ctrl+shift+z",
    "ctrl+o", "ctrl+n", "ctrl+i", "ctrl+a", "ctrl+l",
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


def _visible_x11_windows():
    """Constrained discovery without EWMH (private Xvfb has no window manager).

    wmctrl is preferred on normal desktops. On a bare Xvfb, fall back to
    xdotool *read-only* discovery, then require exact X11 WM_CLASS, WM_NAME
    and PID verification in the existing _concat_window/_media_import_dialog.
    """
    try:
        return _run(["wmctrl", "-lx"], timeout=8)
    except PolicyError as exc:
        if "Cannot get client list properties" not in str(exc):
            raise
    # Xvfb without a window manager has no _NET_CLIENT_LIST; window tree
    # enumeration is still available through the X server itself. xdotool
    # search --onlyvisible is unreliable for these unmanaged top-level windows.
    tree = _run(["xwininfo", "-root", "-tree"], timeout=8)
    lines = []
    for match in re.finditer(
        r'^\s*(0x[0-9a-fA-F]+)\s+"([^"]+)":\s+\("([^"]*)"\s+"([^"]+)"\)',
        tree, flags=re.M
    ):
        raw, title, instance, cls = match.groups()
        if not ((instance == "" and cls == "concat" and title.startswith("Concat"))
                or (instance == "xdg-desktop-portal-gtk" and
                    cls == "Xdg-desktop-portal-gtk" and title == "Importer des médias")):
            continue
        props = _run(["xprop", "-id", raw, "WM_CLASS", "WM_NAME"], timeout=6)
        if (f'WM_CLASS(STRING) = "{instance}", "{cls}"' not in props or
                f'WM_NAME(STRING) = "{title}"' not in props):
            continue
        lines.append(f"{raw.lower()} 0 {instance}.{cls} private {title}")
    return "\n".join(lines)


def _concat_window():
    display = _environment()
    listing = _visible_x11_windows()
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


def _media_import_dialog(main):
    """Strictly scoped GTK file chooser spawned for Concat's visible Import UI.

    The portal does not advertise WM_TRANSIENT_FOR. We therefore require a
    unique exact media-import title, GTK portal class/process and X11 dialog
    type in addition to a verified live Concat window. Other portal dialogs
    are never controllable with this bridge.
    """
    listing = _visible_x11_windows()
    candidates = []
    for line in listing.splitlines():
        pieces = line.split(maxsplit=4)
        if len(pieces) < 5:
            continue
        raw, _, wmclass, _, title = pieces
        if title != "Importer des médias":
            continue
        if wmclass != "xdg-desktop-portal-gtk.Xdg-desktop-portal-gtk":
            raise PolicyError("Media dialog has unexpected X11 window class")
        if not re.fullmatch(r"0x[0-9a-fA-F]+", raw):
            raise PolicyError("Media dialog window ID is invalid")
        properties = _run(["xprop", "-id", raw, "WM_CLASS",
                           "WM_NAME", "_NET_WM_WINDOW_TYPE", "_NET_WM_PID"], timeout=6)
        if ('WM_CLASS(STRING) = "xdg-desktop-portal-gtk", "Xdg-desktop-portal-gtk"'
                not in properties
                or 'WM_NAME(STRING) = "Importer des médias"' not in properties
                or "_NET_WM_WINDOW_TYPE_DIALOG" not in properties):
            raise PolicyError("Media dialog identity cannot be verified")
        pid_match = re.search(r"_NET_WM_PID\(CARDINAL\)\s*=\s*(\d+)", properties)
        if not pid_match:
            raise PolicyError("Media dialog process ID is missing")
        args = _run(["ps", "-p", pid_match.group(1), "-o", "args="], timeout=6).strip()
        if not args or args.split()[0].rsplit("/", 1)[-1] != "xdg-desktop-portal-gtk":
            raise PolicyError("Media dialog executable cannot be verified")
        geometry = _run(["xwininfo", "-id", raw], timeout=6)
        width = re.search(r"^\s*Width:\s*(\d+)", geometry, re.M)
        height = re.search(r"^\s*Height:\s*(\d+)", geometry, re.M)
        if not width or not height or "Map State: IsViewable" not in geometry:
            raise PolicyError("Media dialog is not a visible X11 window")
        ww, hh = int(width.group(1)), int(height.group(1))
        if not (200 <= ww <= 7680 and 200 <= hh <= 4320):
            raise PolicyError("Media dialog dimensions out of range")
        candidates.append({"windowId": raw.lower(), "pid": int(pid_match.group(1)),
                           "title": "Importer des médias", "width": ww, "height": hh,
                           "display": main["display"], "role": "concat_media_import_dialog",
                           "parentConcatWindowId": main["windowId"]})
    if len(candidates) > 1:
        raise PolicyError("Multiple matching media import dialogs; refusing input")
    return candidates[0] if candidates else None


def _window():
    main = _concat_window()
    dialog = _media_import_dialog(main)
    return dialog if dialog else main


def status():
    """Read-only; no desktop activation."""
    if native_desktop.enabled():
        try:
            return native_desktop.status()
        except PolicyError as error:
            if ("UI timeout" not in str(error)
                    or os.environ.get("CCER_PRIVATE_DISPLAY")
                    or os.environ.get("CCER_PRIVATE_XVFB_PID")):
                raise
            # Reuse the already-attested read-only fallback; never claim
            # authenticated BEFORE evidence or enable physical X11 input.
            from .readonly_window import capture as fallback_capture
            evidence = fallback_capture(max_width=320)
            return {"available": True, "window": evidence["window"],
                    "captureScope": "attested X11 read-only observation",
                    "controlScope": "disabled until native Slint responds",
                    "inputReady": False,
                    "isolation": {"private": False, "engine": "x11_readonly"},
                    "requiresActionConfirmation": True,
                    "otherAppsAccessible": False, "readOnly": True,
                    "safeForClickReceipt": False,
                    "nativeStatus": "slint_ui_timeout"}
    with _GUI_LOCK:
        try:
            isolation = require_private_input()
            input_ready = True
        except PolicyError:
            isolation = {"private": False, "reason": "FOCUS_ISOLATION_REQUIRED"}
            input_ready = False
        return {"available": True, "window": _window(),
                "captureScope": "verified Concat X11 window or exact media-import portal dialog only",
                "controlScope": "private-Xvfb-only; no physical desktop focus or cursor access",
                "inputReady": input_ready, "isolation": isolation,
                "requiresActionConfirmation": True,
                "otherAppsAccessible": False}


def capture(*, max_width=840):
    """Capture verified Concat UI or its narrowly allowlisted Import dialog."""
    if native_desktop.enabled():
        try:
            return native_desktop.capture(max_width=max_width)
        except PolicyError as error:
            if ("UI timeout" not in str(error)
                    or os.environ.get("CCER_PRIVATE_DISPLAY")
                    or os.environ.get("CCER_PRIVATE_XVFB_PID")):
                raise  # Private Xvfb must never fall back to the human desktop.
            # Read-only observation of the *same* verified Concat window.
            # Never use fallback frames as Slint BEFORE receipts or for input.
            from .readonly_window import capture as fallback_capture
            return fallback_capture(max_width=max_width)
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
                "captureSource": "verified_x11_observation_only",
                "readOnly": True, "safeForClickReceipt": False,
                "coordinates": "Window pixels; X11 screenshot is observation only"}


def interact(*, expected_window_id, action, confirm_action, x=None, y=None,
             button=1, key=None, text=None, scroll=None, with_capture=True,
             target_x=None, target_y=None, duration=.7):
    if native_desktop.enabled():
        return native_desktop.interact(
            expected_window_id=expected_window_id, action=action,
            confirm_action=confirm_action, x=x, y=y, button=button,
            key=key, text=text, scroll=scroll, with_capture=with_capture,
            target_x=target_x, target_y=target_y, duration=duration)
    confirm(confirm_action)
    if type(with_capture) is not bool:
        raise PolicyError("withCapture must be boolean")
    with _GUI_LOCK:
        win = _window()
        if expected_window_id != win["windowId"]:
            raise PolicyError("Stale verified Concat/dialog window ID; recapture before acting")
        if action not in ("click", "key", "type", "scroll", "drag"):
            raise PolicyError("Only click/key/type/scroll/drag actions are supported")
        if action in ("click", "scroll", "drag"):
            if (type(x) is not int or type(y) is not int or
                not 0 <= x < win["width"] or not 0 <= y < win["height"]):
                raise PolicyError("Coordinates must be inside Concat window bounds")
        if action == "click" and (type(button) is not int or button not in (1, 2, 3)):
            raise PolicyError("Click button must be 1..3")
        if action == "drag":
            if type(button) is not int or button != 1:
                raise PolicyError("Only left-button dragging is supported")
            if (type(target_x) is not int or type(target_y) is not int or
                    not 0 <= target_x < win["width"] or
                    not 0 <= target_y < win["height"]):
                raise PolicyError("Drag target must remain inside Concat")
            if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not .3 <= duration <= 3:
                raise PolicyError("Drag duration must be 0.3..3.0 seconds")
        if action == "key" and key not in _ALLOWED_KEYS:
            raise PolicyError("Keyboard shortcut not in explicit safe allowlist")
        if action == "type" and (not isinstance(text, str) or
                                 not 1 <= len(text) <= 500 or
                                 any(ord(ch) < 32 for ch in text)):
            raise PolicyError("Type supports only up to 500 printable characters")
        if action == "scroll" and (type(scroll) is not int or not -8 <= scroll <= 8 or scroll == 0):
            raise PolicyError("Scroll must be an integer between -8 and +8, excluding zero")
        # This MUST precede even windowfocus/mousemove. Activating a real
        # desktop window is categorically forbidden, even if the user agrees
        # to a Concat editing mission. Only a distinct attested Xvfb pointer
        # and input focus may be manipulated.
        require_private_input()
        target_window = int(win["windowId"], 16)
        _run(["xdotool", "windowfocus", "--sync", str(target_window)])
        try:
            active = int(_run(["xdotool", "getwindowfocus"]).strip())
        except (PolicyError, ValueError) as exc:
            raise PolicyError("Concat virtual input focus could not be verified") from exc
        if active != target_window:
            raise PolicyError("Concat is not the focused window; aborting input")
        if action in ("click", "scroll", "drag"):
            _run(["xdotool", "mousemove", "--window",
                  str(active), str(x), str(y)])
            time.sleep(.2)  # Make the pointer movement visible to the human.
        if action == "click":
            _run(["xdotool", "click", str(button)])
        elif action == "drag":
            # Drag the pointer through actual GUI positions over a visible
            # duration, rather than editing the underlying timeline API.
            _run(["xdotool", "mousedown", "1"])
            try:
                steps = 9
                for step in range(1, steps + 1):
                    cx = round(x + (target_x - x) * step / steps)
                    cy = round(y + (target_y - y) * step / steps)
                    _run(["xdotool", "mousemove", "--window",
                          str(active), str(cx), str(cy)])
                    time.sleep(duration / steps)
            finally:
                _run(["xdotool", "mouseup", "1"])
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
            time.sleep(.15)  # Allow UI repaint before the post-action observation.
            result.update(capture())
        return result


def main():
    """Expose existing read-only Concat status/capture without GUI input."""
    import argparse
    import json
    parser = argparse.ArgumentParser(description="Inspect verified Concat window")
    parser.add_argument("--capture", action="store_true",
                        help="Send a read-only JPEG to stdout; never an action receipt")
    parser.add_argument("--max-width", type=int, default=640)
    args = parser.parse_args()
    result = capture(max_width=args.max_width) if args.capture else status()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
