"""Explicit reproducible CCER Slint preparation; no GUI/process replacement."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
BASE = "79116bd0f9a103c633d888603ad27890e929dbdc"
UPSTREAM = "https://github.com/jub0t/Concat.git"
PATCH_DIR = ROOT / "docs/native-patches"
PATCHES = (
    ("0001-feat-concat-stage-opt-in-Slint-computer-use-events-a.patch", "5a602eddd4a159af6dc173bc4839a261562877e2f678767cf5e4ad321cc31381"),
    ("0001-feat-ccer-add-opt-in-authenticated-Slint-Unix-bridge.patch", "1ce943fd65e5f9fa1372c25c2ab4e74b573be2d203588062b9c27ecc0fa2b9f8"),
    ("0001-feat-ccer-paced-native-Slint-drag-and-controlled-bui.patch", "a7c3e0e35f6dfd27e0d3238de0fa37098786721a77905c4774e779891f226f5d"),
    ("0001-build-ccer-use-two-Cargo-jobs-for-native-desktop-bin.patch", "083bd74a92ad737095bf783bd6686d4f10185f74b1c41dfb778c61cf66ceb38f"),
    ("0001-feat-ccer-guarded-scene-media-drop-and-export-folder.patch", "b485d16705b7cd10329ef32d98cba4b8ad4c544e00da952aa41f48f4593f3c28"),
    ("0002-ccer-native-runtime-fixes.patch", "baef718c5bd0557b2ff4f2882251bed46d3ca6282ab01b263667d2b2a05d2827"),
)
EXPECTED_FILES = {
    ".ccer-cargo-check.sh": "87c843a65d43fea0da7fb7662a8a01f2fee7578984d3a19dd237b45cbce9ba54",
    ".ccer-fetch-build-deps.sh": "29ec56f90c37bf3e370325e7411758bf340648fb388fc4dd6f211d8ce27505bb",
    ".gitignore": "191a91307711e0fa9b052d7cc795148ea779ea30be9f65f78fb9aae20f97e2bd",
    "src/Cargo.lock": "739dfaa159ba1e3aa6c87f420310d1ffb4a58533fc2453f70e7108ff67e0d183",
    "src/crates/concat/Cargo.toml": "93dcf5144b31ee78fcb0f650386a919466cda26ee667a4ba80ca2aa2351b88ba",
    "src/crates/concat/src/ccer_input.rs": "d9052f27613fcf626f0d5fdfd304e5a34d0d7c251b9e76882795413a1dda0c45",
    "src/crates/concat/src/ccer_server.rs": "829382d099069b324e2f24c1c2032da0c910786d247bd7f66ffd0e2455b141b6",
    "src/crates/concat/src/lib.rs": "2e3af1c2f6590be1e05c2b3404a38c5a7f3e359ec6ba9ac9b08d2c0e13bdff84",
    "src/crates/concat/src/panes/monitor.rs": "89f9487cc4dcfd43566308da49c50ba808db40448b6ae327392994534394a302",
}

DEST = ROOT / ".runtime/concat-native-prepared"
SOURCE = ROOT / ".upstream-concat"
CACHE = ROOT / ".runtime/concat-official-cache"


class SetupError(RuntimeError):
    pass


def git(*args, cwd=None, timeout=180):
    try:
        p = subprocess.run(["git", *map(str, args)], cwd=cwd, check=True,
                           capture_output=True, text=True, timeout=timeout)
        return p.stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise SetupError("Git failed: " + str(getattr(exc, "stderr", "") or exc)[-700:]) from exc


def patches_verified(directory=PATCH_DIR, patches=PATCHES):
    paths = []
    for name, digest in patches:
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise SetupError("Missing or symlink patch: " + name)
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise SetupError("Changed native patch SHA-256: " + name)
        paths.append(path)
    return paths


def safe_destination(target):
    target = Path(target).absolute()
    if (target == ROOT or not target.is_relative_to(ROOT) or target.is_symlink()
            or not target.parent.resolve().is_relative_to(ROOT.resolve())):
        raise SetupError("Native worktree must be a non-symlink location inside CCER")
    return target


def verify_source(source):
    source = Path(source).absolute()
    if source.is_symlink() or not (source / ".git").exists():
        raise SetupError("Missing or unsafe Concat source Git checkout")
    if git("remote", "get-url", "origin", cwd=source) != UPSTREAM:
        raise SetupError("Source must have the official Concat GitHub remote")
    if git("rev-parse", BASE + "^{commit}", cwd=source) != BASE:
        raise SetupError("Pinned Concat source commit is missing")
    if git("status", "--porcelain", cwd=source):
        raise SetupError("Concat source Git checkout has local edits")
    return source


def manifest(patches=PATCHES):
    return {"base": BASE, "patches": [{"name": n, "sha256": h} for n, h in patches]}


def verify(target=DEST, *, patches=PATCHES):
    target = safe_destination(target)
    path = target / ".ccer-native-manifest.json"
    if path.is_symlink() or not path.is_file():
        raise SetupError("Native manifest missing")
    if json.loads(path.read_text(encoding="utf-8")) != manifest(patches):
        raise SetupError("Native manifest does not match patchset")
    if git("rev-parse", "HEAD", cwd=target) != BASE:
        raise SetupError("Native worktree has unexpected Git revision")
    git("diff", "--check", cwd=target)
    if not (target / "src/crates/concat/src/ccer_server.rs").is_file():
        raise SetupError("Missing Slint native server")
    for relative, expected in EXPECTED_FILES.items():
        file = target / relative
        if file.is_symlink() or not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != expected:
            raise SetupError("Prepared Concat file differs from certified native fork: " + relative)
    return target


def prepare(source=SOURCE, target=DEST, *, patch_dir=PATCH_DIR, patches=PATCHES):
    """Idempotent, local-only, never overwrites a project or a running editor."""
    target = safe_destination(target)
    approved = patches_verified(patch_dir, patches)
    if target.exists() or target.is_symlink():
        return verify(target, patches=patches)
    source = verify_source(source)
    if target == source or target.is_relative_to(source):
        raise SetupError("Cannot prepare inside the original Concat source")
    target.parent.mkdir(parents=True, exist_ok=True)
    git("worktree", "add", "--detach", str(target), BASE, cwd=source)
    try:
        for patch in approved:
            git("apply", "--check", str(patch), cwd=target)
            git("apply", str(patch), cwd=target)
        git("diff", "--check", cwd=target)
        (target / ".ccer-native-manifest.json").write_text(
            json.dumps(manifest(patches), indent=2) + "\n", encoding="utf-8")
        return verify(target, patches=patches)
    except Exception:
        try:
            git("worktree", "remove", "--force", str(target), cwd=source)
        except SetupError:
            pass
        raise


def fetch_source():
    """Internet access occurs only with explicit --fetch."""
    target = safe_destination(CACHE)
    if target.exists() or target.is_symlink():
        raise SetupError("Official source cache already exists: use --source")
    target.parent.mkdir(parents=True, exist_ok=True)
    git("clone", "--filter=blob:none", "--branch", "v0.2.8",
        "--single-branch", UPSTREAM, str(target), timeout=600)
    return verify_source(target)


def build(target=DEST, target_cache=None):
    """Explicit Cargo build; no launch, kill, switch or system package install."""
    target = verify(target)
    cargo = shutil.which("cargo")
    if not cargo:
        raise SetupError("Cargo missing; install the Rust toolchain first")
    args = [cargo, "build", "--manifest-path", str(target / "src/Cargo.toml"),
            "--locked", "--offline", "-p", "concat", "--bin", "concat",
            "--features", "ccer-inapp", "-j", "2"]
    env = dict(os.environ)
    vendor = SOURCE / ".ccer-ffmpeg7"
    sysroot = SOURCE / ".ccer-build-deps/root"
    if sysroot.is_dir():
        env["CCER_DEV_SYSROOT"] = str(sysroot)
        env["PKG_CONFIG_SYSROOT_DIR"] = str(sysroot)
        env["PKG_CONFIG_PATH"] = str(sysroot / "usr/lib/x86_64-linux-gnu/pkgconfig")
        flags = "-I" + str(sysroot / "usr/include") + " -I" + str(sysroot / "usr/include/x86_64-linux-gnu")
        env["CFLAGS"] = flags
        env["BINDGEN_EXTRA_CLANG_ARGS"] = flags
    shared_target = target_cache or os.environ.get("CCER_NATIVE_CARGO_TARGET_DIR")
    if shared_target:
        cache = Path(shared_target).expanduser().absolute()
        if cache.is_symlink() or not cache.is_dir() or not cache.resolve().is_relative_to(ROOT.resolve()):
            raise SetupError("Cargo target cache must be an existing directory inside CCER")
        env["CARGO_TARGET_DIR"] = str(cache)
    if (vendor / "lib").is_dir():
        env["FFMPEG_DIR"] = str(vendor)
        env["LD_LIBRARY_PATH"] = str(vendor / "lib") + (
            ":" + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")
    try:
        subprocess.run(args, cwd=target, env=env, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SetupError("Cargo build failed: check local libraries/toolchain") from exc
    binary = Path(env["CARGO_TARGET_DIR"]) / "debug/concat" if env.get("CARGO_TARGET_DIR") else target / "src/target/debug/concat"
    if not binary.is_file():
        raise SetupError("Cargo succeeded without Concat executable")
    return binary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    for name in ("check", "prepare", "verify", "build"):
        modes.add_argument("--" + name, action="store_true")
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--dest", type=Path, default=DEST)
    parser.add_argument("--target-cache", type=Path, help="Existing Cargo target directory inside CCER; only for --build")
    parser.add_argument("--fetch", action="store_true",
                        help="Network opt-in: clone pinned official Concat v0.2.8")
    args = parser.parse_args(argv)
    try:
        if args.fetch and not args.prepare:
            raise SetupError("--fetch only allowed with --prepare")
        if args.target_cache and not args.build:
            raise SetupError("--target-cache only allowed with --build")
        files = patches_verified()
        if args.check:
            print(f"CCER native: {len(files)} verified patches; base {BASE[:12]}")
            print("Cargo:", shutil.which("cargo") or "not installed")
        elif args.prepare:
            src = args.source
            if not src.exists():
                if not args.fetch:
                    raise SetupError("Source missing: pass --fetch or provide --source")
                src = fetch_source()
            print("PREPARED", prepare(src, args.dest))
        elif args.verify:
            print("VERIFIED", verify(args.dest))
        else:
            print("BUILT", build(args.dest, args.target_cache))
        return 0
    except (SetupError, OSError, ValueError) as exc:
        print("CCER native setup refused:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
