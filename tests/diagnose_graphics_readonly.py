"""Bounded, read-only GPU diagnosis. No Concat launch or config mutation."""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path


def probe(argv, timeout=12):
    if not shutil.which(argv[0]):
        return {"status": "MISSING"}
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "ERROR", "reason": type(exc).__name__}
    data = re.sub(re.escape(str(Path.home())), "~",
                  (p.stdout + "\n" + p.stderr).strip())
    return {"status": "OK" if p.returncode == 0 else "FAIL",
            "exit": p.returncode, "output": data[-2600:]}


def main():
    roots = (Path("/usr/share/vulkan/icd.d"), Path("/etc/vulkan/icd.d"))
    app = Path.home() / "WORKSPACE-LOGICIEL/concat/Concat-0.2.8-x86_64.AppImage"
    report = {
        "host": {"display": os.environ.get("DISPLAY"), "sessionType": os.environ.get("XDG_SESSION_TYPE"),
                 "concatBinaryExists": app.is_file()},
        "vulkanICDs": sorted(str(f) for root in roots if root.is_dir() for f in root.glob("*.json")),
        "renderNodes": sorted(str(p) for p in Path("/dev/dri").glob("renderD*")),
        "packages": {p: probe(["dpkg-query", "-W", p]) for p in
                     ("mesa-vulkan-drivers", "vulkan-tools", "mesa-utils", "libvulkan1")},
        "vulkanSummary": probe(["vulkaninfo", "--summary"], timeout=15),
        "coredumps": probe(["coredumpctl", "list", "--no-pager"], timeout=12),
        "binariesAvailable": {n: bool(shutil.which(n)) for n in
                 ("vulkaninfo", "vkcube", "glxinfo", "eglinfo", "Xvfb", "openbox", "weston", "Xwayland", "x11vnc")},
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
