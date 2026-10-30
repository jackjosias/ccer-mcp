"""Read-only bounded image capture of the *existing* attested native Concat window.

Used only when the authenticated Slint screenshot has timed out. It cannot
supply an action receipt and NEVER injects X11 input or stores a JPEG.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import time

from .controls import PolicyError


def capture(*, max_width: int = 840):
    from . import desktop_gui, visible_desktop

    if type(max_width) is not int or not 320 <= max_width <= 1600:
        raise PolicyError("maxWidth must be integer 320..1600")
    display = visible_desktop._desktop()
    state = visible_desktop._file_state()
    if not visible_desktop._live(state):
        raise PolicyError("No attested running native Concat for read-only capture")
    windows = visible_desktop._windows()
    if len(windows) != 1 or windows[0]["pid"] != state["pid"]:
        raise PolicyError("Expected exactly one native Concat window with attested PID")
    win = windows[0]
    window_id = win["windowId"]
    props = desktop_gui._run(
        ["xprop", "-id", window_id, "WM_CLASS", "_NET_WM_PID", "WM_NAME"],
        timeout=8)
    if (not re.search(r'WM_CLASS\(STRING\)\s*=\s*""\s*,\s*"concat"', props)
            or not re.search(r"_NET_WM_PID\(CARDINAL\)\s*=\s*" +
                             str(state["pid"]) + r"(?:\s|$)", props)
            or not re.search(r'WM_NAME\(STRING\)\s*=\s*"Concat"', props)):
        raise PolicyError("Native window X11 identity mismatch; no screenshot")
    geometry = desktop_gui._run(["xwininfo", "-id", window_id], timeout=8)
    ww = re.search(r"^\s*Width:\s*(\d+)", geometry, flags=re.M)
    hh = re.search(r"^\s*Height:\s*(\d+)", geometry, flags=re.M)
    if not ww or not hh or "Map State: IsViewable" not in geometry:
        raise PolicyError("Native window not visible or dimensions unavailable")
    width, height = int(ww.group(1)), int(hh.group(1))
    if not 320 <= width <= 7680 or not 200 <= height <= 4320:
        raise PolicyError("Native window dimensions out of bounds")
    target = min(width, max_width)
    jpeg = desktop_gui._run([
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-f", "x11grab", "-window_id", str(int(window_id, 16)),
        "-video_size", f"{width}x{height}", "-i", display,
        "-frames:v", "1", "-vf", f"scale={target}:-2",
        "-c:v", "mjpeg", "-q:v", "8", "-f", "image2pipe", "-"
    ], timeout=25, binary=True)
    if not 128 < len(jpeg) < 2_000_000 or not jpeg.startswith(b"\xff\xd8"):
        raise PolicyError("Read-only Concat capture invalid or oversized")
    return {
        "window": {"windowId":window_id, "pid":state["pid"],
                   "title":"Concat", "width":width, "height":height,
                   "display":display},
        "imageBase64":base64.b64encode(jpeg).decode("ascii"),
        "mimeType":"image/jpeg", "imageWidth":target,
        "sha256":hashlib.sha256(jpeg).hexdigest(),
        "capturedAt":time.time(), "captureSource":"verified_x11_read_only",
        "readOnly":True, "safeForClickReceipt":False,
        "coordinates":"Native window pixels; thumbnail is for viewing only",
        "warning":"Do not dispatch actions from this fallback; obtain fresh authenticated Slint BEFORE evidence."
    }


def main():
    print(json.dumps(capture()), flush=True)


if __name__ == "__main__":
    main()
