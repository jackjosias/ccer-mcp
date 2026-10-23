"""Disposable real Concat GUI on Xvfb: prove foreground and pointer non-interference.

Does NOT open existing projects. Uses isolated XDG state and Xauth. Closes
every child process it starts. This is a qualifying trial, not production.
"""
import os
import secrets
import signal
import subprocess
import tempfile
import time
from pathlib import Path

from tests.live_isolation_probe import run

def main():
    display = ":96"
    app = Path.home() / "WORKSPACE-LOGICIEL/concat/Concat-0.2.8-x86_64.AppImage"
    if not app.is_file() or Path("/tmp/.X11-unix/X96").exists():
        raise RuntimeError("Concat binary missing or isolated X display is occupied")
    host_focus = run(["xdotool", "getwindowfocus"])
    host_mouse = run(["xdotool", "getmouselocation", "--shell"])
    with tempfile.TemporaryDirectory(prefix="ccer-concat-isolated-") as tmp:
        base = Path(tmp)
        auth = base / "Xauthority"
        auth.touch(mode=0o600)
        run(["xauth", "-f", str(auth), "add", display, "MIT-MAGIC-COOKIE-1", secrets.token_hex(16)])
        env = dict(os.environ, DISPLAY=display, XAUTHORITY=str(auth),
                   XDG_CONFIG_HOME=str(base / "config"),
                   XDG_DATA_HOME=str(base / "data"),
                   XDG_CACHE_HOME=str(base / "cache"),
                   LIBGL_ALWAYS_SOFTWARE="1", CONCAT_GPU="software",
                   WINIT_UNIX_BACKEND="x11", GDK_BACKEND="x11")
        x = subprocess.Popen(["Xvfb", display, "-screen", "0", "1400x900x24",
                              "-nolisten", "tcp", "-auth", str(auth)],
                             start_new_session=True,
                             stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ui = None
        try:
            for _ in range(60):
                if x.poll() is not None:
                    raise RuntimeError("Xvfb exited")
                try:
                    run(["xwininfo", "-root"], env=env, timeout=2)
                    break
                except (RuntimeError, subprocess.TimeoutExpired):
                    time.sleep(.1)
            else:
                raise RuntimeError("Xvfb did not start")
            logpath = base / "concat-startup.log"
            log = logpath.open("wb")
            ui = subprocess.Popen([str(app)], env=env,
                                  start_new_session=True,
                                  stdin=subprocess.DEVNULL,
                                  stdout=log,
                                  stderr=subprocess.STDOUT)
            log.close()
            detected = None
            for _ in range(80):
                if ui.poll() is not None:
                    print({"exitCode": ui.returncode,
                           "applicationOutput": logpath.read_text(errors="replace")[-2600:]}, flush=True)
                    raise RuntimeError("Concat GUI process exited immediately")
                try:
                    listing = run(["xdotool", "search", "--onlyvisible",
                                   "--class", "concat"], env=env, timeout=3)
                    if listing:
                        detected = listing.splitlines()[0]
                        break
                except (RuntimeError, subprocess.TimeoutExpired):
                    pass
                time.sleep(.2)
            if not detected:
                print({"virtualTree": run(["xwininfo", "-root", "-tree"], env=env, timeout=5)[-1400:],
                       "applicationOutput": logpath.read_text(errors="replace")[-2500:],
                       "appPid": ui.pid, "appRunning": ui.poll() is None}, flush=True)
                raise RuntimeError("Concat did not open a visible window on virtual Xvfb")
            # No physical input. Verify exact X display and a real image frame.
            shot = base / "concat.jpg"
            run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                 "-f", "x11grab", "-video_size", "1400x900", "-i", display,
                 "-frames:v", "1", "-q:v", "10", "-y", str(shot)],
                env=env, timeout=20)
            if not shot.exists() or shot.stat().st_size < 3000:
                raise RuntimeError("Virtual Concat GUI screenshot invalid")
            if run(["xdotool", "getwindowfocus"]) != host_focus:
                raise RuntimeError("Human foreground focus changed")
            if run(["xdotool", "getmouselocation", "--shell"]) != host_mouse:
                raise RuntimeError("Human pointer moved while testing isolated Concat")
            print({"concatGuiInPrivateDisplay": True, "virtualDisplay": display,
                   "virtualWindowId": detected, "screenshotBytes": shot.stat().st_size,
                   "humanFocusUnchanged": True, "humanPointerUnchanged": True}, flush=True)
        finally:
            for p in (ui, x):
                if p is None or p.poll() is not None:
                    continue
                try:
                    os.killpg(p.pid, signal.SIGTERM)
                    p.wait(timeout=4)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    try: os.killpg(p.pid, signal.SIGKILL)
                    except ProcessLookupError: pass

if __name__ == "__main__":
    main()
