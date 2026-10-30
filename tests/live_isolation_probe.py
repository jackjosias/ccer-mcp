"""Non-invasive live probe: dedicated Xvfb and two independent X pointers.

Never opens Concat or touches a project. A temporary X server is started and
cleaned up; the human desktop's mouse/focus are observed, never modified.
"""
import os
import secrets
import subprocess
import tempfile
import time
from pathlib import Path

from ccer.focus_isolation import require_private_input

def run(argv, env=None, timeout=10):
    r = subprocess.run(argv, env=env, text=True, capture_output=True, timeout=timeout)
    if r.returncode:
        raise RuntimeError(f"{argv[0]} failure: {r.stderr[-400:]}")
    return r.stdout.strip()

def main():
    display = ":96"
    existing_socket = Path("/tmp/.X11-unix/X96")
    if existing_socket.exists():
        raise RuntimeError("Refuse already occupied virtual X display :96")
    human_pointer = run(["xdotool", "getmouselocation", "--shell"])
    human_focus = run(["xdotool", "getwindowfocus"])
    with tempfile.TemporaryDirectory(prefix="ccer-xvfb-probe-") as root:
        authority = Path(root) / "Xauthority"
        authority.touch(mode=0o600)
        run(["xauth", "-f", str(authority), "add", display, "MIT-MAGIC-COOKIE-1", secrets.token_hex(16)])
        proc = subprocess.Popen(["Xvfb", display, "-screen", "0", "1400x900x24",
                                 "-nolisten", "tcp", "-auth", str(authority)],
                                stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            isolated = dict(os.environ, DISPLAY=display, XAUTHORITY=str(authority))
            for retry in range(30):
                if proc.poll() is not None:
                    raise RuntimeError("Xvfb stopped unexpectedly")
                try:
                    rootinfo = run(["xwininfo", "-root"], env=isolated, timeout=3)
                    if "1400" in rootinfo:
                        break
                except (OSError, RuntimeError, subprocess.TimeoutExpired):
                    time.sleep(.12)
            else:
                raise RuntimeError("Xvfb did not become ready")
            # A forged DISPLAY is not sufficient; attest the live Xvfb PID,
            # Unix socket and private Xauthority before ANY input is allowed.
            private_input_env = dict(isolated, CCER_PRIVATE_DISPLAY=display,
                                     CCER_HUMAN_DISPLAY=os.environ["DISPLAY"],
                                     CCER_PRIVATE_XAUTHORITY=str(authority),
                                     CCER_PRIVATE_XVFB_PID=str(proc.pid))
            attestation = require_private_input(env=private_input_env)
            if not attestation["private"]:
                raise RuntimeError("Isolated input attestation failed")
            # Xvfb pointer motion cannot cross into the human X server.
            before_virtual = run(["xdotool", "getmouselocation", "--shell"], env=isolated)
            # A disposable Xvfb without a window manager can reset the pointer
            # when the last client disconnects. Move and observe in ONE X client.
            after_virtual = run(["xdotool", "mousemove", "453", "219",
                                 "getmouselocation", "--shell"], env=isolated)
            human_pointer_after = run(["xdotool", "getmouselocation", "--shell"])
            human_focus_after = run(["xdotool", "getwindowfocus"])
            if before_virtual == after_virtual or human_pointer != human_pointer_after:
                print({"virtualBefore": before_virtual, "virtualAfter": after_virtual,
                       "humanBefore": human_pointer, "humanAfter": human_pointer_after}, flush=True)
                raise RuntimeError("Pointer isolation invariant failed")
            if human_focus != human_focus_after:
                print({"humanFocusChanged": True}, flush=True)
                raise RuntimeError("Human window focus changed!")
            print({"virtualPointerMoves": True,
                   "humanPointerPreserved": True,
                   "humanFocusPreserved": True,
                   "isolatedDisplay": display})
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

if __name__ == "__main__":
    main()
