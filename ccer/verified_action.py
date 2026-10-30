"""One-shot CCER native click: reuse real Slint BEFORE/AFTER guards."""
import argparse
import json
import re
import secrets
import subprocess
from pathlib import Path
from types import SimpleNamespace

from .controls import PolicyError
from . import visible_desktop as desktop


def _same_screen_except_caret(first, second, *, menu_only=False):
    """Only permit pre-dispatch retry for nearly identical verified frames."""
    images = (Path(first), Path(second))
    for p in images:
        if (p.parent.resolve() != desktop.EVIDENCE.resolve() or p.is_symlink()
                or not p.is_file()
                or re.fullmatch(r"(?:before|after)-[a-f0-9]{12}[.]jpg", p.name) is None):
            raise PolicyError("Untrusted native visual receipt")
    graph = ("[0:v]crop=250:350:0:0[a];[1:v]crop=250:350:0:0[b];[a][b]ssim"
             if menu_only else "[0:v][1:v]ssim")
    try:
        check = subprocess.run(
            ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "info",
             "-i", str(images[0]), "-i", str(images[1]),
             "-filter_complex", graph, "-frames:v", "1",
             "-f", "null", "-"], capture_output=True, text=True,
            timeout=12, check=False)
        measure = re.search(r"All:([0-9.]+)", check.stderr)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PolicyError("Visual comparison unavailable") from exc
    if check.returncode or not measure or float(measure.group(1)) < 0.9999:
        raise PolicyError("Native scene changed beyond caret animation")


def click_once(*, expected_pid, x, y, confirmed):
    if confirmed is not True:
        raise PolicyError("Explicit confirmation required")
    if type(expected_pid) is not int or expected_pid < 2:
        raise PolicyError("Expected Concat PID required")
    baseline = None
    for _ in range(4):
        observed = desktop.observe()
        if observed["pid"] != expected_pid:
            raise PolicyError("Concat PID changed before action")
        width, height = observed["nativeWidth"], observed["nativeHeight"]
        if (type(x) is not int or type(y) is not int
                or not (0 <= x < width and 0 <= y < height)):
            raise PolicyError("Target outside observed native window")
        image = Path(observed["image"])
        matched = re.fullmatch(r"before-([a-f0-9]{12})[.]jpg", image.name)
        if matched is None:
            raise PolicyError("Invalid native receipt")
        if baseline is None:
            baseline = observed
        else:
            if (observed["windowId"] != baseline["windowId"]
                    or width != baseline["nativeWidth"]
                    or height != baseline["nativeHeight"]):
                raise PolicyError("Native window changed before action")
            _same_screen_except_caret(baseline["image"], observed["image"])
        try:
            return desktop.act(SimpleNamespace(
                confirm=True, receipt=matched.group(1), type="click", x=x, y=y))
        except PolicyError as error:
            if str(error) != "CCER: desktop changed; recapture before acting":
                raise
            # Only this pre-dispatch rejection permits another observed attempt.
    raise PolicyError("Caret changed repeatedly; no click dispatched")


def click_reviewed_once(*, expected_pid, x, y, approved_image, confirmed, menu_only=False):
    """Dispatch on the same Slint session whose real frame was just reviewed."""
    if confirmed is not True:
        raise PolicyError("Explicit confirmation required")
    if type(expected_pid) is not int or expected_pid < 2:
        raise PolicyError("Expected Concat PID required")
    if (not isinstance(approved_image, str)
            or re.fullmatch(r"after-[a-f0-9]{12}[.]jpg", approved_image) is None):
        raise PolicyError("Approved AFTER image filename required")
    if menu_only and not (10 <= x <= 220 and 35 <= y <= 325):
        raise PolicyError("Reviewed file menu target outside menu bounds")
    state = desktop._file_state()
    if not state or state["pid"] != expected_pid or not desktop._live(state):
        raise PolicyError("Concat PID changed before action")
    reviewed = desktop.EVIDENCE / approved_image
    with desktop._client(state) as client:
        if (type(x) is not int or type(y) is not int
                or not 0 <= x < client._width or not 0 <= y < client._height):
            raise PolicyError("Native target outside authorized window")
        frame = client.observe()
        temporary = Path(desktop._write_image(
            "before-" + secrets.token_hex(6) + ".jpg", frame))
        try:
            _same_screen_except_caret(str(reviewed), str(temporary), menu_only=menu_only)
            try:
                after = client.act(
                    {"type": "click", "x": x, "y": y},
                    confirm=True, expected_sha256=frame["sha256"])
            except PolicyError as error:
                if ("CCER: UI timeout" in str(error)
                        or "CCER: application action timed out" in str(error)):
                    return {"state": "UNKNOWN_DISPATCH", "pid": expected_pid,
                            "warning": "Native event may have run; no retry"}
                raise
        finally:
            temporary.unlink(missing_ok=True)
    evidence = desktop._write_image(
        "after-" + secrets.token_hex(6) + ".jpg", after)
    return {"sent": True, "pid": expected_pid, "frameNo": after["frameNo"],
            "afterImage": evidence, "nativeEvent": "click",
            "visualOutcomeRequiresReview": True}


def main():
    parser = argparse.ArgumentParser(description="One-shot verified native click")
    parser.add_argument("--expected-pid", type=int, required=True)
    parser.add_argument("--x", type=int, required=True)
    parser.add_argument("--y", type=int, required=True)
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--approved-image")
    parser.add_argument("--menu-only", action="store_true")
    args = parser.parse_args()
    try:
        if args.approved_image:
            result = click_reviewed_once(
                expected_pid=args.expected_pid, x=args.x, y=args.y,
                approved_image=args.approved_image, confirmed=args.confirm,
                menu_only=args.menu_only)
        else:
            result = click_once(
                expected_pid=args.expected_pid, x=args.x, y=args.y,
                confirmed=args.confirm)
        print(json.dumps(result))
    except (OSError, ValueError, RuntimeError, PolicyError) as error:
        print(json.dumps({"error": str(error)}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
