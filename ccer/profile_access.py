"""Safely change only CCER's local tunnel-client command access mode.

Preserves the real tunnel ID, key reference, other configuration and file
permissions. Does NOT edit WCER, start/kill daemons, or expose secrets.
"""
from __future__ import annotations

import argparse
import os
import re
import stat
import tempfile
from pathlib import Path

from .controls import PolicyError


def _profile_path():
    return Path.home() / ".config" / "tunnel-client" / "ccer-direct.yaml"


def switch_profile(path: Path, *, access: str = "control", apply: bool = False) -> dict:
    """Switch only the documented CCER launcher --access flag.

    A dry-run is the default; actual change must be explicitly requested.
    """
    if access not in ("control", "observe"):
        raise PolicyError("Only control and observe access modes are supported")
    if type(apply) is not bool:
        raise PolicyError("apply must be boolean")
    path = Path(path)
    if path.name != "ccer-direct.yaml" or path.is_symlink():
        raise PolicyError("Only a non-symlink ccer-direct.yaml may be changed")
    try:
        before_stat = path.lstat()
        if not stat.S_ISREG(before_stat.st_mode) or before_stat.st_uid != os.getuid():
            raise PolicyError("CCER tunnel profile must be a regular user-owned file")
        if before_stat.st_size > 64 * 1024:
            raise PolicyError("Profile unexpectedly large")
        before = path.read_bytes()
        content = before.decode("utf-8")
    except (OSError, UnicodeError) as err:
        raise PolicyError("Cannot safely read CCER profile") from err
    # Never inspect, copy to logs or change the control-plane credentials.
    match_expr = re.compile(
        r'(?m)^([ \t]*command:[ \t]*")([^"\r\n]*ccer_direct_stdio\.py --access )(observe|control)("[ \t]*)$'
    )
    matches = list(match_expr.finditer(content))
    launcher = str(Path(__file__).resolve().parents[1] / "ccer_direct_stdio.py")
    if len(matches) != 1 or launcher not in matches[0].group(2):
        raise PolicyError("Expected precisely one CCER Direct launcher command")
    current = matches[0].group(3)
    changed = current != access
    result = {"profile": str(path), "current": current, "requested": access,
              "changed": changed, "applied": False,
              "requiresRestart": changed,
              "secretFieldsReadButNeverReported": True}
    if not apply or not changed:
        return result
    replacement = (matches[0].group(1) + matches[0].group(2) +
                   access + matches[0].group(4))
    after = (content[:matches[0].start()] + replacement +
             content[matches[0].end():]).encode("utf-8")
    # Race guard before replacing a user-owned config. Avoid taking backups of
    # credential-containing profiles, and keep sensitive bytes under mode 0600.
    tmp = None
    try:
        if path.is_symlink() or path.lstat() != before_stat or path.read_bytes() != before:
            raise PolicyError("Profile changed concurrently; abort")
        fd, name = tempfile.mkstemp(prefix=".ccer-direct-", dir=str(path.parent))
        tmp = Path(name)
        os.fchmod(fd, before_stat.st_mode & 0o777)
        with os.fdopen(fd, "wb") as stream:
            stream.write(after)
            stream.flush()
            os.fsync(stream.fileno())
        if path.is_symlink() or path.lstat() != before_stat or path.read_bytes() != before:
            raise PolicyError("Profile changed during write; abort")
        os.replace(tmp, path)
        tmp = None
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if tmp:
            tmp.unlink(missing_ok=True)
    result["applied"] = True
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="CCER Direct local access mode (never touches WCER)")
    parser.add_argument("--access", choices=("observe", "control"), default="control")
    parser.add_argument("--apply", action="store_true",
                        help="Actually change the profile; default is a safe dry-run")
    args = parser.parse_args(argv)
    try:
        result = switch_profile(_profile_path(), access=args.access, apply=args.apply)
    except PolicyError as exc:
        parser.error(str(exc))
    print(f"CCER profile: {result['current']} -> {result['requested']}; "
          f"changed={result['changed']}; applied={result['applied']}")
    if result["applied"]:
        print("The existing tunnel-client process still uses its previous "
              "configuration. Restart ONLY ccer-direct in the same terminal "
              "that holds CONTROL_PLANE_API_KEY, then refresh the CCER "
              "connector/tool discovery in ChatGPT.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
