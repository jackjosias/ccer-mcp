"""Disposable real Concat GUI on Xvfb: prove foreground and pointer non-interference.

Does NOT open existing projects. Uses isolated XDG state and Xauth. Closes
every child process it starts. This is a qualifying trial, not production.
"""
import os
import argparse
import shutil
from unittest.mock import patch
import secrets
import signal
import subprocess
import tempfile
import time
from pathlib import Path

from tests.live_isolation_probe import run

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gpu-mode", choices=("system", "lavapipe", "lavapipe-software"),
                        default="lavapipe")
    args = parser.parse_args()
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
                   LIBGL_ALWAYS_SOFTWARE="1", LP_NUM_THREADS="2",
                   WINIT_UNIX_BACKEND="x11", GDK_BACKEND="x11")
        if args.gpu_mode != "system":
            driver = "/usr/share/vulkan/icd.d/lvp_icd.json"
            if not Path(driver).is_file():
                raise RuntimeError("Lavapipe ICD unavailable")
            env.update(VK_DRIVER_FILES=driver, VK_ICD_FILENAMES=driver,
                       VK_LOADER_DEBUG="error")
        if args.gpu_mode == "lavapipe-software":
            env["CONCAT_GPU"] = "software"
        else:
            env.pop("CONCAT_GPU", None)
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
            print({"gpuMode": args.gpu_mode,
                   "XvfbGLX": run(["glxinfo", "-B"], env=env, timeout=12)[-600:]
                                if shutil.which("glxinfo") else "missing"}, flush=True)
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
                    # Bare Xvfb has no EWMH window manager: ask the raw X11
                    # tree rather than xdotool --onlyvisible search.
                    listing = run(["xwininfo", "-root", "-tree"], env=env, timeout=3)
                    found = __import__("re").search(
                        r'^\s*(0x[0-9a-fA-F]+)\s+"Concat":\s+\(""\s+"concat"\)',
                        listing, __import__("re").M)
                    if found:
                        detected = found.group(1)
                        break
                except (RuntimeError, subprocess.TimeoutExpired):
                    pass
                time.sleep(.2)
            if not detected:
                print({"virtualTree": run(["xwininfo", "-root", "-tree"], env=env, timeout=5)[-1400:],
                       "applicationOutput": logpath.read_text(errors="replace")[-2500:],
                       "appPid": ui.pid, "appRunning": ui.poll() is None}, flush=True)
                raise RuntimeError("Concat did not open a visible window on virtual Xvfb")
            # This display is private, with a verified Xvfb process and
            # dedicated Xauthority. A bare Xvfb has no WM to honor the app's
            # mapping request: map ONLY the matched Concat window inside :96.
            from ccer.focus_isolation import require_private_input
            private_env = dict(env, CCER_PRIVATE_DISPLAY=display,
                               CCER_HUMAN_DISPLAY=os.environ["DISPLAY"],
                               CCER_PRIVATE_XAUTHORITY=str(auth),
                               CCER_PRIVATE_XVFB_PID=str(x.pid),
                               XDG_SESSION_TYPE="x11")
            require_private_input(env=private_env)
            props = run(["xprop", "-id", detected, "WM_CLASS", "_NET_WM_PID"], env=env)
            if 'WM_CLASS(STRING) = "", "concat"' not in props:
                raise RuntimeError("Private window is not Concat")
            run(["xdotool", "windowmap", "--sync", str(int(detected, 16))],
                env=env, timeout=10)
            map_state = run(["xwininfo", "-id", detected], env=env)
            if "Map State: IsViewable" not in map_state:
                raise RuntimeError("Concat window still not viewable in private Xvfb")
            # No physical input. Verify exact X display and a real image frame.
            shot = base / "concat.jpg"
            run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                 "-f", "x11grab", "-video_size", "1400x900", "-i", display,
                 "-frames:v", "1", "-q:v", "10", "-y", str(shot)],
                env=env, timeout=20)
            if not shot.exists() or shot.stat().st_size < 3000:
                raise RuntimeError("Virtual Concat GUI screenshot invalid")
            from ccer.desktop_gui import status, capture, interact
            private_env = dict(env, CCER_PRIVATE_DISPLAY=display,
                               CCER_HUMAN_DISPLAY=os.environ["DISPLAY"],
                               CCER_PRIVATE_XAUTHORITY=str(auth),
                               CCER_PRIVATE_XVFB_PID=str(x.pid),
                               XDG_SESSION_TYPE="x11")
            with patch.dict(os.environ, private_env):
                try:
                    state = status()
                    frame = capture(max_width=700)
                    acted = interact(expected_window_id=state["window"]["windowId"],
                                     action="key", key="Escape", confirm_action=True)
                    if not acted.get("actionSent"):
                        raise RuntimeError("Isolated GUI key not accepted")
                    print({"isolatedInputReady": state["inputReady"],
                           "screenshotSha256": frame["sha256"],
                           "postActionSha256": acted["sha256"]}, flush=True)
                except Exception as error:
                    from ccer.desktop_gui import _visible_x11_windows
                    print({"virtualTree": run(["xwininfo", "-root", "-tree"], env=env)[-1300:],
                           "x11Listing": _visible_x11_windows(),
                           "properties": run(["xprop", "-id", detected,
                                               "WM_NAME", "WM_CLASS", "_NET_WM_PID"], env=env)[-1600:],
                           "geometry": run(["xwininfo", "-id", detected], env=env)[-1200:],
                           "isolatedGuiError": repr(error)}, flush=True)
                    raise
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
