"""Attach CCER to the visible, locally installed Concat UI via opt-in Slint.

The official, unpatched AppImage cannot be hot-attached. A patched Concat
must be started as the user's real desktop app (same DISPLAY and HOME).
Never inject X11 input, steal pointer focus, or open a second app silently.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import secrets
import stat
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

from .controls import PolicyError
from .inapp_protocol import InAppComputerUse

HOME = Path.home()
PROJECT = Path(__file__).resolve().parent.parent
EXE = PROJECT / ".upstream-concat/src/target/debug/concat"
LIBS = PROJECT / ".upstream-concat/.ccer-ffmpeg7/lib"
ROOT = HOME / ".local/state/ccer-inapp"
STATE = ROOT / "desktop.json"
EVIDENCE = PROJECT / ".runtime/ccer-desktop-evidence"


def _run(argv: list[str], *, timeout=10):
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                          check=True).stdout


def _desktop():
    display = os.environ.get("DISPLAY", "")
    if not re.fullmatch(r":[0-9]{1,3}(?:\.\d{1,2})?", display):
        raise PolicyError("CCER: a local real X11 desktop is required")
    if os.environ.get("CCER_PRIVATE_DISPLAY") or os.environ.get("CCER_PRIVATE_XVFB_PID"):
        raise PolicyError("CCER: private Xvfb cannot be the visible desktop")
    if os.environ.get("XDG_SESSION_TYPE", "").lower() not in ("", "x11"):
        raise PolicyError("CCER: desktop is not X11")
    return display


def _windows():
    """Read-only inspection; this method never raises, focuses or clicks a window."""
    try:
        lines = _run(["wmctrl", "-lxp"]).splitlines()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise PolicyError("CCER: cannot verify live Concat windows") from exc
    matches = []
    for line in lines:
        fields = line.split(maxsplit=5)
        if (len(fields) == 6 and re.fullmatch(r"0x[0-9a-fA-F]+", fields[0])
                and fields[2].isdecimal()
                and fields[3].lower() in (".concat", "concat.concat")):
            matches.append({"windowId": fields[0].lower(), "pid": int(fields[2]),
                            "title": fields[5]})
    return matches


def _file_state():
    if STATE.is_symlink() or not STATE.is_file():
        return None
    m = STATE.stat()
    if (m.st_uid != os.getuid() or stat.S_IMODE(m.st_mode) != 0o600
            or m.st_size > 8192):
        raise PolicyError("CCER: desktop identity file permissions refused")
    value = json.loads(STATE.read_text())
    if (value.get("version") != 1 or value.get("uid") != os.getuid()
            or not isinstance(value.get("pid"), int)
            or not isinstance(value.get("socket"), str)
            or not isinstance(value.get("proof"), str)):
        raise PolicyError("CCER: desktop identity malformed")
    return value


def _live(value):
    if not value:
        return False
    try:
        exe = (Path("/proc") / str(value["pid"]) / "exe").resolve(strict=True)
        return exe == EXE.resolve(strict=True)
    except (OSError, ValueError):
        return False


def _client(value):
    if not _live(value):
        raise PolicyError("CCER: attached native desktop is not alive")
    return InAppComputerUse(value["socket"], value["proof"],
                            expected_pid=value["pid"], timeout=15)


def status():
    state = _file_state()
    active = _live(state)
    return {"nativeBridge": active,
            "pid": state["pid"] if active else None,
            "officialConcatWindows": _windows(),
            "display": _desktop(),
            "next": "Connect to the patched visible Concat" if active else
                    "Close official Concat, then launch CCER-patched Concat"}


def _wait_for_native_window(pid: int, *, timeout: float = 20.0):
    """Wait for X11 registration, never respawn or terminate Concat."""
    deadline = time.monotonic() + timeout
    while True:
        windows = _windows()
        if len(windows) == 1 and windows[0]["pid"] == pid:
            return windows[0]
        if any(win["pid"] != pid for win in windows):
            raise PolicyError("CCER: another Concat window appeared; keep both untouched")
        if time.monotonic() >= deadline:
            raise RuntimeError(
                "CCER: native window registration pending; Concat left running. "
                "Check visible_desktop status; do not relaunch.")
        time.sleep(.25)


def launch(media_root: Path, export_root: Path):
    _desktop()
    if _windows():
        raise PolicyError("CCER: Concat already open; do not replace or close its user's window")
    if not EXE.is_file() or not LIBS.is_dir():
        raise PolicyError("CCER: opt-in compiled Rust binary or FFmpeg runtime is missing")
    for path in (media_root, export_root):
        if (not path.is_absolute() or path.is_symlink() or not path.is_dir()
                or not path.resolve().is_relative_to(HOME.resolve())):
            raise PolicyError("CCER: approved media/export directories must exist under HOME")
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    if ROOT.is_symlink() or stat.S_IMODE(ROOT.stat().st_mode) != 0o700:
        raise PolicyError("CCER: private socket directory is not 0700")
    old = _file_state()
    if _live(old):
        raise PolicyError("CCER: a patched desktop session is already active")
    if old is not None:
        STATE.unlink()
    sock = ROOT / ("desktop-" + secrets.token_hex(8) + ".sock")
    credential = secrets.token_hex(32)
    env = dict(os.environ, CCER_INAPP_SOCKET=str(sock),
               CCER_INAPP_MEDIA_ROOT=str(media_root.resolve()),
               CCER_INAPP_EXPORT_ROOT=str(export_root.resolve()))
    env["".join(("CCER", "_INAPP", "_TOKEN"))] = credential
    env["LD_LIBRARY_PATH"] = str(LIBS) + (":" + env["LD_LIBRARY_PATH"]
                                         if env.get("LD_LIBRARY_PATH") else "")
    logs = ROOT / ("run-" + secrets.token_hex(5) + ".log")
    with logs.open("xb") as output:
        proc = subprocess.Popen([str(EXE)], env=env, cwd=HOME,
                                stdin=subprocess.DEVNULL, stdout=output,
                                stderr=output, start_new_session=True)
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("CCER: patched Concat exited; check private startup log")
        if sock.is_socket():
            break
        time.sleep(.2)
    else:
        raise RuntimeError("CCER: patched Concat launched, but bridge socket was not ready")
    value = {"version": 1, "uid": os.getuid(), "pid": proc.pid,
             "socket": str(sock), "proof": credential,
             "log": str(logs), "display": os.environ["DISPLAY"]}
    fd = os.open(STATE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as out:
        json.dump(value, out)
        out.flush()
        os.fsync(out.fileno())
    try:
        with _client(value) as client:
            first = client.observe()
        window = _wait_for_native_window(proc.pid)
        return {"launched": True, "pid": proc.pid,
                "windowId": window["windowId"],
                "nativeFrame": first["frameNo"], "display": os.environ["DISPLAY"],
                "noPhysicalX11Input": True}
    except Exception:
        # Do not kill a successfully launched visible editor with possible work.
        raise


def _write_image(name: str, frame: dict):
    from .evidence_retention import reserve
    if not re.fullmatch(r"(?:before|after)-[0-9a-f]{12}\.jpg", name):
        raise PolicyError("CCER: unsafe generated evidence filename")
    image = base64.b64decode(frame["imageBase64"], validate=True)
    reserve(EVIDENCE, len(image))  # bounded storage and TTL cleanup
    output = EVIDENCE / name
    # Create owner-only from the first byte, never world-readable temporarily.
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(image)
            out.flush()
            os.fsync(out.fileno())
    except Exception:
        output.unlink(missing_ok=True)
        raise
    return str(output)


def observe():
    value = _file_state()
    with _client(value) as client:
        frame = client.observe()
        native_width, native_height = client._width, client._height
    stamp = secrets.token_hex(6)
    image_path = _write_image("before-" + stamp + ".jpg", frame)
    proof = {"pid": value["pid"], "windowId": frame["windowId"],
             "nativeWidth": native_width, "nativeHeight": native_height,
             "frameNo": frame["frameNo"], "sha256": frame["sha256"],
             "observedAt": time.time(), "image": image_path}
    proof_path = EVIDENCE / ("before-" + stamp + ".json")
    # Do not expose pre-action receipts even briefly under the caller\u0027s umask.
    fd = os.open(proof_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        json.dump(proof, out)
        out.flush()
        os.fsync(out.fileno())
    return proof



@contextmanager
def _native_launch_scope(value: dict, gesture_type: str):
    """Restore only the media/export scope from the attested running Concat.

    Every CLI action runs in a fresh Python process; no broadened root is
    permitted and no unrelated app environment (including secrets) is logged.
    """
    variable = {"file_drop": "CCER_INAPP_MEDIA_ROOT",
                "select_export_folder": "CCER_INAPP_EXPORT_ROOT"}.get(gesture_type)
    if variable is None:
        yield
        return
    if not _live(value):
        raise PolicyError("CCER: authorized native editor is not running")
    try:
        data = (Path("/proc") / str(value["pid"]) / "environ").read_bytes()
        prefix = variable.encode() + b"="
        matches = [entry[len(prefix):] for entry in data.split(b"\x00")
                   if entry.startswith(prefix)]
        if len(matches) != 1 or len(matches[0]) > 4096:
            raise ValueError("missing or ambiguous root")
        root = Path(matches[0].decode("utf-8"))
        if (not root.is_absolute() or root.is_symlink() or not root.is_dir()
                or not root.resolve().is_relative_to(HOME.resolve())):
            raise ValueError("root outside the owner's home")
        approved = str(root.resolve())
    except (OSError, ValueError, UnicodeError) as exc:
        raise PolicyError("CCER: native launch media/export permission unavailable") from exc
    old = os.environ.get(variable)
    if old is not None and old != approved:
        raise PolicyError("CCER: caller media/export root differs from native launch")
    os.environ[variable] = approved
    try:
        yield
    finally:
        if old is None:
            os.environ.pop(variable, None)
        else:
            os.environ[variable] = old

def act(args):
    if args.confirm is not True:
        raise PolicyError("CCER: action requires --confirm")
    before = EVIDENCE / ("before-" + args.receipt + ".json")
    if not before.is_file() or before.is_symlink():
        raise PolicyError("CCER: unknown observation receipt")
    state = json.loads(before.read_text())
    if time.time() - state["observedAt"] > 60:
        raise PolicyError("CCER: observation expired")
    value = _file_state()
    if state["pid"] != value["pid"]:
        raise PolicyError("CCER: desktop process changed since observation")
    if args.type == "click":
        gesture = {"type": "click", "x": args.x, "y": args.y}
    elif args.type == "move":
        gesture = {"type": "move", "x": args.x, "y": args.y}
    elif args.type == "drag":
        gesture = {"type": "drag", "x": args.x, "y": args.y,
                   "targetX": args.to_x, "targetY": args.to_y, "duration": args.duration}
    elif args.type == "scroll":
        gesture = {"type": "scroll", "x": args.x, "y": args.y, "deltaY": args.delta_y}
    elif args.type == "key":
        gesture = {"type": "key", "key": args.key}
    elif args.type == "file_drop":
        gesture = {"type": "file_drop", "path": args.path}
    elif args.type == "select_export_folder":
        gesture = {"type": "select_export_folder"}
    else:
        raise PolicyError("CCER: unknown gesture")
    uncertain = None
    with _native_launch_scope(value, args.type), _client(value) as client:
        before_frame = client.observe()
        if before_frame["sha256"] != state["sha256"]:
            raise PolicyError("CCER: desktop changed; recapture before acting")
        try:
            after = client.act(gesture, confirm=True, expected_sha256=state["sha256"])
        except PolicyError as exc:
            if not any(s in str(exc) for s in ("CCER: UI timeout", "CCER: application action timed out")):
                raise
            # The Slint event may execute *after* its RPC acknowledgement times out.
            # NEVER send a second gesture on this ambiguous outcome.
            uncertain = str(exc)
            after = None
    before.unlink()  # A gesture was attempted; never reuse its receipt.
    if uncertain is not None:
        try:
            with _client(value) as checker:
                observed = checker.observe()
            output = _write_image("after-" + args.receipt + ".jpg", observed)
            return {"state": "UNKNOWN_DISPATCH", "pid": value["pid"],
                    "uiChanged": observed["sha256"] != state["sha256"],
                    "afterImage": output, "nativeEvent": args.type,
                    "warning": "Slint RPC timed out; no automatic retry", "visualOutcomeRequiresReview": True}
        except (OSError, RuntimeError, PolicyError) as exc:
            return {"state": "UNKNOWN_DISPATCH", "pid": value["pid"],
                    "warning": "Slint RPC timed out; no automatic retry",
                    "verificationFailure": type(exc).__name__}
    output = _write_image("after-" + args.receipt + ".jpg", after)
    return {"sent": True, "pid": value["pid"], "frameNo": after["frameNo"],
            "afterImage": output, "nativeEvent": args.type,
            "visualOutcomeRequiresReview": True}


def main():
    p = argparse.ArgumentParser(description="Control visible Concat Slint without X11 injection")
    p.add_argument("command", choices=("status", "launch", "observe", "act", "cleanup"))
    p.add_argument("--media-root", default=str(HOME / "Videos"))
    p.add_argument("--export-root", default=str(HOME / "Videos"))
    p.add_argument("--receipt")
    p.add_argument("--confirmed-reviewed", action="store_true")
    p.add_argument("--type", choices=("click","move","drag","scroll","key",
                                      "file_drop","select_export_folder"))
    p.add_argument("--x", type=int)
    p.add_argument("--y", type=int)
    p.add_argument("--to-x", type=int)
    p.add_argument("--to-y", type=int)
    p.add_argument("--duration", type=float, default=.5)
    p.add_argument("--delta-y", type=int)
    p.add_argument("--key")
    p.add_argument("--path")
    p.add_argument("--confirm", action="store_true")
    args = p.parse_args()
    try:
        if args.command == "status":
            result = status()
        elif args.command == "launch":
            result = launch(Path(args.media_root), Path(args.export_root))
        elif args.command == "observe":
            result = observe()
        elif args.command == "cleanup":
            from .evidence_retention import acknowledge, prune
            result = (acknowledge(EVIDENCE, args.receipt,
                                  confirmed_reviewed=args.confirmed_reviewed)
                      if args.receipt else prune(EVIDENCE))
        else:
            result = act(args)
        print(json.dumps(result, ensure_ascii=False))
    except (OSError, ValueError, RuntimeError, PolicyError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
