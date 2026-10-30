"""User-approved installer for official Concat Linux AppImage releases."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sys
import tempfile
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

API = "https://api.github.com/repos/jub0t/Concat/releases/latest"
UPSTREAM = "https://github.com/jub0t/Concat"
ARCH = {"x86_64": "x86_64", "amd64": "x86_64", "aarch64": "aarch64", "arm64": "aarch64"}
MAX_SIZE = 512 * 1024 * 1024


class SetupError(RuntimeError):
    pass


def install_directory(home=None):
    return Path(home or Path.home()) / ".local/share/ccer/concat"


def managed_binary(home=None):
    return install_directory(home) / "current.AppImage"


def default_binary(home=None):
    """Discover a Concat executable without network, launch or mutation."""
    explicit = os.environ.get("CCER_CONCAT_BIN")
    if explicit:
        return Path(explicit).expanduser()
    managed = managed_binary(home)
    if managed.is_file():
        return managed
    on_path = shutil.which("concat")
    return Path(on_path) if on_path else managed


def select_release(payload, arch):
    tag = payload.get("tag_name")
    if not isinstance(tag, str) or not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag):
        raise SetupError("Invalid upstream release version")
    filename = f"Concat-{tag[1:]}-{arch}.AppImage"
    assets = payload.get("assets")
    if not isinstance(assets, list):
        raise SetupError("Missing upstream assets")
    choices = [a for a in assets if isinstance(a, dict) and a.get("name") == filename]
    if len(choices) != 1:
        raise SetupError(f"No official AppImage for {arch}")
    asset = choices[0]
    url = asset.get("browser_download_url", "")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "github.com" or parsed.path != f"/jub0t/Concat/releases/download/{tag}/{filename}" or parsed.query or parsed.fragment:
        raise SetupError("Unexpected release asset URL")
    checksum = asset.get("digest")
    if not isinstance(checksum, str) or not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", checksum):
        raise SetupError("Official asset has no SHA-256; refusing unverified download")
    size = asset.get("size")
    if not isinstance(size, int) or not 1_000_000 <= size <= MAX_SIZE:
        raise SetupError("Invalid download size")
    return {"tag": tag, "name": filename, "url": url, "sha256": checksum[7:].lower(), "size": size}


def latest_release(machine=None):
    if sys.platform != "linux":
        raise SetupError("Automatic AppImage installation is Linux-only")
    arch = ARCH.get((machine or platform.machine()).lower())
    if not arch:
        raise SetupError("Unsupported machine architecture")
    try:
        request = Request(API, headers={"Accept": "application/vnd.github+json", "User-Agent": "CCER"})
        with urlopen(request, timeout=25) as result:
            raw = result.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise SetupError("Oversized GitHub response")
        payload = json.loads(raw)
    except (OSError, ValueError) as exc:
        raise SetupError(f"Cannot obtain official GitHub release metadata: {exc}") from exc
    return select_release(payload, arch)


def download_asset(url, dest, maximum):
    """Stream checksum evidence into a temporary file, without executing content."""
    size, digest = 0, hashlib.sha256()
    req = Request(url, headers={"User-Agent": "CCER"})
    with urlopen(req, timeout=45) as response, dest.open("xb") as out:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > maximum:
                raise SetupError("Download exceeds official size")
            out.write(chunk)
            digest.update(chunk)
        out.flush()
        os.fsync(out.fileno())
    return size, digest.hexdigest()


def install_release(release, home=None, downloader=download_asset):
    """Explicit, owner-local and atomic; never modifies or restarts running Concat."""
    directory = install_directory(home)
    if directory.is_symlink():
        raise SetupError("Managed directory must not be a symlink")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    target, current = directory / release["name"], directory / "current.AppImage"
    import fcntl
    with (directory / ".install.lock").open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if target.is_symlink() or (current.exists() and not current.is_symlink()):
            raise SetupError("Refusing to replace a non-managed executable")
        if target.exists():
            with target.open("rb") as stream:
                digest = hashlib.sha256()
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            if target.stat().st_size != release["size"] or digest.hexdigest() != release["sha256"]:
                raise SetupError("Existing release differs from official SHA-256: not overwritten")
        else:
            fd, tmp = tempfile.mkstemp(prefix=".pending-", suffix=".part", dir=directory)
            os.close(fd)
            pending = Path(tmp)
            pending.unlink()
            try:
                size, sha = downloader(release["url"], pending, release["size"])
                if size != release["size"] or sha.lower() != release["sha256"]:
                    raise SetupError("Downloaded AppImage checksum/size mismatch")
                pending.chmod(0o700)
                os.replace(pending, target)
            finally:
                pending.unlink(missing_ok=True)
        new_link = directory / f".current-{os.getpid()}"
        if new_link.exists() or new_link.is_symlink():
            raise SetupError("Temporary activation path already exists")
        try:
            new_link.symlink_to(target.name)
            os.replace(new_link, current)
        finally:
            new_link.unlink(missing_ok=True)
    return current


def main(argv=None):
    parser = argparse.ArgumentParser(description="Install or check official Concat Linux AppImage")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--status", action="store_true", help="Offline Concat discovery")
    action.add_argument("--check", action="store_true", help="Query latest upstream release, without installing")
    action.add_argument("--install", action="store_true", help="Install latest SHA-verified Linux AppImage")
    args = parser.parse_args(argv)
    try:
        if args.status:
            found = default_binary()
            print(f"Concat executable: {found} ({'found' if found.is_file() else 'missing'})")
            return 0 if found.is_file() else 1
        release = latest_release()
        print(f"Official latest: {release['tag']}")
        if args.install:
            print(f"Installed: {install_release(release)}")
            print("The CCER native Slint bridge requires a separately patched Concat build.")
            print("No running Concat process was touched.")
        return 0
    except SetupError as exc:
        print(f"Concat setup: {exc}. See {UPSTREAM}/releases", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
