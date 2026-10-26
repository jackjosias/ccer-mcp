"""Bounded retention for *CCER-generated* visible desktop JPEG evidence only.

Never traverse parents, delete project media, source videos, exported MP4s,
unrecognized files, or active (<=60 seconds) pre-action receipts.
Image inspection via MCP remains in memory; it does not use this directory.
"""
from __future__ import annotations

import os
import re
import stat
import time
from pathlib import Path

from .controls import PolicyError

# Initial conservative defaults. Change only after measuring real workloads.
MAX_BYTES = 32 * 1024 * 1024
RETENTION_SECONDS = 30 * 60
ACTIVE_RECEIPT_SECONDS = 90
_PATTERN = re.compile(r"^(before|after)-([0-9a-f]{12})\.(jpg|json)$")
_RECEIPT = re.compile(r"^[0-9a-f]{12}$")


def _private_root(root: Path) -> Path:
    root = Path(root)
    if root.is_symlink():
        raise PolicyError("CCER evidence root cannot be a symlink")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    mode = root.stat()
    if not stat.S_ISDIR(mode.st_mode) or mode.st_uid != os.getuid():
        raise PolicyError("CCER evidence root ownership invalid")
    # Older CCER versions created this directory with default umask.
    os.chmod(root, 0o700)
    return root


def _managed_files(root: Path):
    for entry in root.iterdir():
        match = _PATTERN.fullmatch(entry.name)
        if not match:
            continue
        mode = entry.lstat()
        if not stat.S_ISREG(mode.st_mode) or mode.st_uid != os.getuid():
            raise PolicyError("Unsafe CCER evidence file: " + entry.name)
        yield entry, match, mode


def prune(root: Path, *, now: float | None = None) -> dict:
    """Delete only expired recognized evidence; never an unexpired action receipt."""
    root = _private_root(root)
    now = time.time() if now is None else now
    removed = 0
    bytes_removed = 0
    count_remaining = 0
    bytes_remaining = 0
    for entry, match, mode in _managed_files(root):
        age = now - mode.st_mtime
        # A pre-action approval is used for up to 60 seconds. A separate
        # safety margin avoids racing with an action in progress.
        expiry = max(RETENTION_SECONDS, ACTIVE_RECEIPT_SECONDS)
        if age >= expiry:
            try:
                entry.unlink()
            except FileNotFoundError:
                continue
            removed += 1
            bytes_removed += mode.st_size
        else:
            count_remaining += 1
            bytes_remaining += mode.st_size
    return {"removed": removed, "bytesRemoved": bytes_removed,
            "remaining": count_remaining, "bytesRemaining": bytes_remaining,
            "quotaBytes": MAX_BYTES}


def reserve(root: Path, size: int) -> dict:
    """Refuse growth beyond fixed evidence budget; no uncontrolled eviction."""
    if size < 0 or size > MAX_BYTES:
        raise PolicyError("CCER evidence exceeds per-file budget")
    result = prune(root)
    if result["bytesRemaining"] + size > MAX_BYTES:
        raise PolicyError("CCER evidence cache full; review and clean old evidence")
    return result


def acknowledge(root: Path, receipt: str, *, confirmed_reviewed: bool) -> dict:
    """Delete exactly one reviewed receipt's generated files, not other projects.

    Manual acknowledgement means its before/after evidence is no longer
    required. Unknown action outcomes MUST NOT be acknowledged prematurely.
    """
    if not confirmed_reviewed:
        raise PolicyError("Evidence cleanup requires explicit review confirmation")
    if not isinstance(receipt, str) or not _RECEIPT.fullmatch(receipt):
        raise PolicyError("Invalid CCER evidence receipt")
    root = _private_root(root)
    files = [(path, match, mode) for path, match, mode in _managed_files(root)
             if match.group(2) == receipt]
    # A not-yet-dispatched before receipt is still usable. Do not erase it.
    active = any(match.group(1) == "before" and match.group(3) == "json"
                 and time.time() - mode.st_mtime < ACTIVE_RECEIPT_SECONDS
                 for _, match, mode in files)
    has_after = any(match.group(1) == "after" and match.group(3) == "jpg"
                    for _, match, _ in files)
    if active and not has_after:
        raise PolicyError("Active pre-action receipt cannot be deleted")
    removed = 0
    bytes_removed = 0
    for path, _, mode in files:
        path.unlink()
        removed += 1
        bytes_removed += mode.st_size
    return {"receipt": receipt, "removed": removed, "bytesRemoved": bytes_removed}
