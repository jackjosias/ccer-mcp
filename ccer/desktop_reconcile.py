"""Idempotent REAL desktop Concat reconciliation; never headless.

Only owner-verified official AppImage windows may receive a graceful
WM_DELETE_WINDOW, never SIGKILL or physical pointer/keyboard input.
Replacement requires explicit confirmation; a window title is not proof
that project work has been saved. Never kill unresponsive editor processes.
"""
from __future__ import annotations

import fcntl
import os
import stat
import time
from contextlib import contextmanager
from pathlib import Path

from .controls import PolicyError
from . import visible_desktop as desktop

OFFICIAL = desktop.HOME / "WORKSPACE-LOGICIEL/concat/Concat-0.2.8-x86_64.AppImage"
LOCK_NAME = "lifecycle.lock"


@contextmanager
def _lock():
    root = desktop.ROOT
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if (root.is_symlink() or stat.S_IMODE(root.stat().st_mode) != 0o700
            or root.stat().st_uid != os.getuid()):
        raise PolicyError("CCER: unsafe lifecycle directory")
    path = root / LOCK_NAME
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if (info.st_uid != os.getuid() or not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) != 0o600):
            raise PolicyError("CCER: unsafe lifecycle lock permissions")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise PolicyError("CCER: lifecycle reconciliation already in progress") from exc
        yield
    finally:
        os.close(fd)


def _verified_official(window):
    """Pin both X11 identity and user-owned AppImage process, not title alone."""
    pid = window["pid"]
    if type(pid) is not int or pid <= 1 or window.get("title") != "Concat":
        raise PolicyError("CCER: active project or ambiguous window; not replaced")
    proc = Path("/proc") / str(pid)
    try:
        if proc.stat().st_uid != os.getuid() or not OFFICIAL.is_file():
            raise ValueError("untrusted owner/binary")
        command = (proc / "cmdline").read_bytes().split(b"\x00")[0].decode("utf-8")
        if Path(command).resolve(strict=True) != OFFICIAL.resolve(strict=True):
            raise ValueError("not the exact official AppImage")
        exe = (proc / "exe").resolve(strict=True)
        # AppImage's immutable FUSE mount; not an arbitrary executable.
        if (not str(exe).startswith("/tmp/.mount_Concat")
                or not str(exe).endswith("/usr/bin/concat")):
            raise ValueError("unexpected AppImage executable")
    except (OSError, ValueError, UnicodeError) as exc:
        raise PolicyError("CCER: cannot attest official Concat process") from exc
    if not (isinstance(window.get("windowId"), str)
            and window["windowId"].startswith("0x")):
        raise PolicyError("CCER: untrusted window identity")
    return pid


def _alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def _close_official(window):
    """Request normal window close; allow Save/Cancel dialogs to block launch."""
    pid = _verified_official(window)
    current = desktop._windows()
    if window not in current:
        raise PolicyError("CCER: Concat changed before close")
    desktop._run(["wmctrl", "-ic", window["windowId"]], timeout=6)
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        current = desktop._windows()
        if not any(w["pid"] == pid for w in current) and not _alive(pid):
            return
        time.sleep(.2)
    raise PolicyError(
        "CCER: Concat has not exited (possibly unsaved work); "
        "no force termination and no duplicate launch"
    )


def reconcile(media_root, export_root, *, replace_unpatched=False, confirmed=False):
    """Return an attached native window or safely create exactly one.

    On conflict, refuse unless a *separate explicit* replace confirmation
    was supplied. No headless process or physical X11 input is ever used.
    """
    desktop._desktop()
    with _lock():
        state = desktop._file_state()
        windows = desktop._windows()
        active = desktop._live(state)
        if active:
            native = [w for w in windows if w["pid"] == state["pid"]]
            if len(native) != 1:
                raise PolicyError("CCER: native process/window mismatch; no replacement")
            extras = [w for w in windows if w["pid"] != state["pid"]]
            if extras:
                if not (replace_unpatched and confirmed):
                    raise PolicyError("CCER: another Concat window exists; explicit replacement required")
                for extra in extras:
                    _verified_official(extra)
                for extra in extras:
                    _close_official(extra)
            with desktop._client(state) as client:
                frame = client.observe()
            return {"state": "ATTACHED", "launched": False,
                    "pid": state["pid"], "windowId": native[0]["windowId"],
                    "nativeFrame": frame["frameNo"], "display": desktop._desktop(),
                    "inputReady": True, "headless": False,
                    "physicalPointerUsed": False}
        if windows and not (replace_unpatched and confirmed):
            return {"state": "REPLACEMENT_REQUIRES_CONFIRMATION",
                    "launched": False, "inputReady": False,
                    "windows": windows, "headless": False}
        if windows:
            if len(windows) > 3:
                raise PolicyError("CCER: too many Concat windows; manual review required")
            # Verify EVERYTHING before sending a single close request.
            for win in windows:
                _verified_official(win)
            desktop._verify_launch_resources()
            if not desktop.EXE.is_file() or not desktop.LIBS.is_dir():
                raise PolicyError("CCER: native bridge executable/runtime missing")
            for win in windows:
                _close_official(win)
            if desktop._windows():
                raise PolicyError("CCER: duplicate windows remain; no launch")
        result = desktop._launch_unlocked(Path(media_root), Path(export_root))
        return {"state": "LAUNCHED_AND_ATTACHED", **result,
                "inputReady": True, "headless": False,
                "physicalPointerUsed": False}
