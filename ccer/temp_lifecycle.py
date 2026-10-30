"""Crash-recoverable, project-labelled scratch folders owned exclusively by CCER.

Only directories created by this module are eligible for deletion. Original
media, Concat project folders, exported MP4s and user-selected paths are never
accepted as scratch targets. This complements (not replaces) evidence_retention.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .controls import PolicyError, atomic_json

MARKER = "CCER_MANAGED_SCRATCH_V1"
PREFIX = "job-"
NAME = re.compile(r"^[A-Za-z0-9_-]{1,61}$")
AGE_SECONDS = 24 * 3600  # crash-only recovery, not active-job eviction
MAX_JOBS = 128
MIN_FREE_BYTES = 2 * 1024 * 1024 * 1024  # refuse new renders on low disk
MARKER_FILE = ".ccer-scratch.json"


def _user_dir(path: Path, *, create: bool = False) -> Path:
    path = Path(path).expanduser()
    if path.is_symlink():
        raise PolicyError("CCER scratch symlink directory refused")
    if create:
        path.mkdir(mode=0o700, parents=False, exist_ok=True)
    if not path.is_dir():
        raise PolicyError("CCER scratch directory missing")
    st = path.stat()
    if st.st_uid != os.getuid() or not stat.S_ISDIR(st.st_mode):
        raise PolicyError("CCER scratch directory ownership invalid")
    if stat.S_IMODE(st.st_mode) & 0o077:
        raise PolicyError("CCER scratch directory must be private 0700")
    return path


def _base(project_root: Path, *, create: bool) -> Path:
    project_root = Path(project_root).expanduser().resolve(strict=True)
    if not project_root.is_dir():
        raise PolicyError("Invalid project root")
    parent = project_root / ".ccer"
    if not parent.exists():
        if not create:
            return parent / "scratch-jobs"
        parent.mkdir(mode=0o700)
    _user_dir(parent)
    root = parent / "scratch-jobs"
    if not root.exists():
        if not create:
            return root
        root.mkdir(mode=0o700)
    return _user_dir(root)


def _start_tick(pid: int) -> int | None:
    try:
        data = Path(f"/proc/{pid}/stat").read_text()
        return int(data.rsplit(") ", 1)[-1].split()[19])
    except (FileNotFoundError, PermissionError, IndexError, ValueError):
        return None


def _process_active(info: dict) -> bool:
    tick = _start_tick(info["pid"])
    expected = info.get("startTick")
    if tick is not None and expected is not None:
        return tick == expected
    # If process visibility is restricted, protect its files instead of
    # assuming it has stopped. Only ENOENT/ESRCH qualifies as dead.
    try:
        os.kill(info["pid"], 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _manifest(folder: Path) -> dict:
    marker = folder / MARKER_FILE
    st = marker.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid():
        raise PolicyError("Untrusted scratch manifest")
    data = json.loads(marker.read_text(encoding="utf-8"))
    if (data.get("contract") != MARKER or data.get("jobId") != folder.name or
            not isinstance(data.get("createdAt"), (int, float)) or
            not isinstance(data.get("pid"), int)):
        raise PolicyError("Scratch marker missing or invalid")
    return data


def _remove_files(folder: Path) -> tuple[int, int]:
    """No shutil.rmtree and no symlink traversal; preflight whole tree first."""
    directories = [folder]
    files = []
    for directory in directories:
        for entry in directory.iterdir():
            st = entry.lstat()
            if st.st_uid != os.getuid() or stat.S_ISLNK(st.st_mode):
                raise PolicyError("Unsafe scratch entry; refusing deletion: " + entry.name)
            if stat.S_ISDIR(st.st_mode):
                directories.append(entry)
            elif stat.S_ISREG(st.st_mode):
                files.append((entry, st.st_size))
            else:
                raise PolicyError("Special scratch entry; refusing deletion")
    total = sum(size for _, size in files)
    for entry, _ in files:
        entry.unlink()
    for directory in reversed(directories):
        directory.rmdir()
    return len(files), total


def sweep(project_root: Path, *, now: float | None = None, dry_run: bool = True) -> dict:
    """Recover *only* crashed/dead older jobs, never an active process."""
    now = time.time() if now is None else now
    base = _base(project_root, create=False)
    if not base.exists():
        return {"dryRun": dry_run, "eligible": 0, "deleted": 0, "bytesReclaimed": 0,
                "protectedActive": 0}
    _user_dir(base)
    candidates = []
    protected = 0
    for folder in base.iterdir():
        if not folder.name.startswith(PREFIX):
            continue
        if folder.is_symlink():
            raise PolicyError("Symlinked scratch job refused")
        _user_dir(folder)
        info = _manifest(folder)
        same_process = _process_active(info)
        age = now - info["createdAt"]
        if same_process or age < AGE_SECONDS:
            protected += 1
            continue
        candidates.append(folder)
    removed = 0
    bytes_removed = 0
    for folder in candidates:
        # verify at deletion time as well, fail closed if PID reappeared
        info = _manifest(folder)
        if _process_active(info):
            protected += 1
            continue
        if not dry_run:
            _, total = _remove_files(folder)
            removed += 1
            bytes_removed += total
    return {"dryRun": dry_run, "eligible": len(candidates),
            "deleted": removed, "bytesReclaimed": bytes_removed,
            "protectedActive": protected}


@contextmanager
def managed_scratch(project_root: Path, *, project: str, purpose: str):
    """Scratch files are removed when the producer exits, even on errors.

    On power loss/crash an old directory remains until a later sweep; neither
    it nor its media ever belongs to Concat's permanent project or export.
    """
    if not isinstance(project, str) or not NAME.fullmatch(project):
        raise PolicyError("Invalid CCER scratch project label")
    if not isinstance(purpose, str) or not NAME.fullmatch(purpose):
        raise PolicyError("Invalid CCER scratch purpose")
    # A new job also recovers crashed scratch folders older than 24h.
    # Live PID/start-tick matches are never evicted.
    sweep(project_root, dry_run=False)
    if shutil.disk_usage(project_root).free < MIN_FREE_BYTES:
        raise PolicyError("CCER scratch denied: less than 2 GiB free on target disk")
    base = _base(project_root, create=True)
    if sum(1 for p in base.iterdir() if p.name.startswith(PREFIX)) >= MAX_JOBS:
        raise PolicyError("Too many scratch jobs; inspect abandoned jobs")
    name = PREFIX + uuid.uuid4().hex
    folder = base / name
    folder.mkdir(mode=0o700)
    info = {"contract": MARKER, "jobId": name, "project": project,
            "purpose": purpose, "pid": os.getpid(),
            "startTick": _start_tick(os.getpid()), "createdAt": time.time()}
    atomic_json(folder / MARKER_FILE, info)
    try:
        yield folder
    finally:
        # Failed removal remains inspectable and recoverable, without deleting
        # user media or suppressing a producer's original error.
        _remove_files(folder)


MAX_RENDER_SCRATCH_BYTES = 2 * 1024 * 1024 * 1024
MIN_RUNTIME_FREE_BYTES = 1024 * 1024 * 1024


def run_bounded_encoder(command, *, scratch: Path, timeout: float,
                        max_bytes: int = MAX_RENDER_SCRATCH_BYTES,
                        min_free_bytes: int = MIN_RUNTIME_FREE_BYTES,
                        poll_seconds: float = 0.25):
    """Run a single FFmpeg process with active disk limits and no RAM log buildup.

    The managed scratch context owns cleanup. No output is moved or written
    outside its private folder by this helper.
    """
    import signal
    import subprocess

    scratch = _user_dir(scratch)
    _manifest(scratch)
    if (isinstance(max_bytes, bool) or not isinstance(max_bytes, int)
            or not 1 <= max_bytes <= 64 * 1024**3):
        raise PolicyError("Invalid scratch budget")
    if (isinstance(min_free_bytes, bool) or not isinstance(min_free_bytes, int)
            or min_free_bytes < 1 or not .05 <= poll_seconds <= 5
            or not 0 < timeout <= 86400):
        raise PolicyError("Invalid encoder monitor settings")
    if shutil.disk_usage(scratch).free < min_free_bytes:
        raise PolicyError("Not enough free disk for CCER encoder")

    log = scratch / "ffmpeg-stderr.log"
    proc = None
    reason = None
    exit_code = None
    try:
        with log.open("xb") as error_log:
            proc = subprocess.Popen(command, cwd=scratch,
                                    stdout=subprocess.DEVNULL, stderr=error_log,
                                    start_new_session=True)
            started = time.monotonic()
            while True:
                try:
                    exit_code = proc.wait(timeout=poll_seconds)
                except subprocess.TimeoutExpired:
                    pass

                if time.monotonic() - started > timeout:
                    reason = "CCER FFmpeg stopped: duration limit exceeded"
                elif shutil.disk_usage(scratch).free < min_free_bytes:
                    reason = "CCER FFmpeg stopped: low free disk space"
                else:
                    total_bytes = 0
                    for entry in scratch.iterdir():
                        st = entry.lstat()
                        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid():
                            raise PolicyError("Unsafe encoder scratch entry")
                        total_bytes += st.st_size
                    if total_bytes > max_bytes:
                        reason = "CCER FFmpeg stopped: scratch budget exceeded"
                if reason or exit_code is not None:
                    break
    finally:
        if proc is not None and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
    if reason:
        raise PolicyError(reason)
    with log.open("rb") as stream:
        stream.seek(0, os.SEEK_END)
        stream.seek(max(0, stream.tell() - 1024))
        error_text = stream.read().decode(errors="replace")
    if exit_code != 0:
        raise PolicyError("Directed FFmpeg render failed: " + error_text[-650:])
    return {"exitCode": exit_code, "elapsedSeconds": round(time.monotonic() - started, 3)}

def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="List/recover CCER-owned scratch only")
    parser.add_argument("action", choices=("status", "sweep"))
    parser.add_argument("--root", default=str(Path.home() / "Videos" / "CCER"))
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args(argv)
    # Nothing is deleted by default, even when the subcommand is sweep.
    result = sweep(Path(args.root), dry_run=not (args.action == "sweep" and args.confirm))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
