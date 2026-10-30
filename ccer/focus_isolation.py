"""Fail-closed attestation of an independent Xvfb GUI input target.

The human desktop must never receive xdotool mouse, keyboard or activation
commands from CCER. The X server process and authority are independently
verified, not inferred from a user-controlled DISPLAY string alone.
"""
from __future__ import annotations

import os
import re
import stat
from pathlib import Path

from .controls import PolicyError

_DISPLAY = re.compile(r":[0-9]{1,3}(?:\.0)?\Z")


def require_private_input(env=None, cmdline=None):
    env = env if env is not None else os.environ
    display = env.get("DISPLAY", "")
    private = env.get("CCER_PRIVATE_DISPLAY", "")
    home_display = env.get("CCER_HUMAN_DISPLAY", "")
    auth_raw = env.get("CCER_PRIVATE_XAUTHORITY", "")
    pid_raw = env.get("CCER_PRIVATE_XVFB_PID", "")
    if (not _DISPLAY.fullmatch(display) or not private or
            display != private or not home_display or display == home_display):
        raise PolicyError(
            "FOCUS_ISOLATION_REQUIRED: CCER refuses mouse/keyboard on the human "
            "desktop; attach a verified private Xvfb display instead")
    if not auth_raw or not pid_raw or not pid_raw.isdecimal():
        raise PolicyError("Private Xvfb identity and authority are required")
    pid = int(pid_raw)
    if pid < 2:
        raise PolicyError("Invalid private Xvfb PID")
    auth = Path(auth_raw).expanduser()
    try:
        st = auth.lstat()
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or (st.st_mode & 0o077):
            raise PolicyError("Private Xauthority file is not safely owned")
        actual = (Path("/proc") / str(pid) / "cmdline").read_bytes() if cmdline is None else cmdline
    except OSError as exc:
        raise PolicyError("Private Xvfb process/authority unavailable") from exc
    arguments = [v.decode("utf-8", "replace") for v in actual.split(b"\0") if v]
    if (len(arguments) < 5 or Path(arguments[0]).name != "Xvfb" or
            display not in arguments or "-auth" not in arguments or
            arguments[arguments.index("-auth") + 1:][:1] != [str(auth)] or
            "-nolisten" not in arguments or
            arguments[arguments.index("-nolisten") + 1:][:1] != ["tcp"]):
        raise PolicyError("Private GUI process is not the attested Xvfb server")
    socket = Path("/tmp/.X11-unix/X" + display.split(":")[1].split(".")[0])
    if not socket.is_socket():
        raise PolicyError("Private Xvfb display socket is not ready")
    return {"private": True, "display": display, "serverPid": pid}
