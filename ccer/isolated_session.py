"""Private Concat desktop: isolated Xvfb, Lavapipe and voluntary read-only viewer."""
import argparse
import http.server
import json
import os
import re
import signal
import stat
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from .controls import PolicyError
from .focus_isolation import require_private_input

ROOT = Path.home() / ".local/state/ccer-isolated"
STATE = ROOT / "active.json"
APP = Path.home() / "WORKSPACE-LOGICIEL/concat/Concat-0.2.8-x86_64.AppImage"
ICD = Path("/usr/share/vulkan/icd.d/lvp_icd.json")


def command(argv, env=None, *, binary=False, timeout=12):
    p = subprocess.run(argv, env=env, capture_output=True, text=not binary, timeout=timeout)
    if p.returncode:
        raise RuntimeError(f"{argv[0]} failed: {str(p.stderr)[-200:]}")
    return p.stdout


def read_session():
    if not STATE.exists() and not STATE.is_symlink():
        return None
    st = STATE.lstat()
    if (STATE.is_symlink() or not stat.S_ISREG(st.st_mode) or
            st.st_uid != os.getuid() or st.st_mode & 0o077 or st.st_size > 16000):
        raise PolicyError("Invalid private session manifest permissions")
    try:
        info = json.loads(STATE.read_text())
        if info["version"] != 1 or info["uid"] != os.getuid():
            raise PolicyError("Private session identity mismatch")
        if not re.fullmatch(r":[0-9]{1,3}", info["display"]):
            raise PolicyError("Invalid private DISPLAY")
        if (info["display"] == info["humanDisplay"] or
                b"ccer.isolated_session" not in
                (Path("/proc") / str(info["ownerPid"]) / "cmdline").read_bytes()):
            raise PolicyError("Private supervisor identity could not be verified")
        env = {
            "DISPLAY": info["display"], "XAUTHORITY": info["authority"],
            "CCER_PRIVATE_DISPLAY": info["display"],
            "CCER_HUMAN_DISPLAY": info["humanDisplay"],
            "CCER_PRIVATE_XAUTHORITY": info["authority"],
            "CCER_PRIVATE_XVFB_PID": str(info["xvfbPid"]),
            "XDG_CONFIG_HOME": info["config"], "XDG_DATA_HOME": info["data"],
            "XDG_CACHE_HOME": info["cache"], "XDG_SESSION_TYPE": "x11",
            "WINIT_UNIX_BACKEND": "x11", "GDK_BACKEND": "x11",
            "LIBGL_ALWAYS_SOFTWARE": "1", "LP_NUM_THREADS": "2",
            "VK_DRIVER_FILES": str(ICD), "VK_ICD_FILENAMES": str(ICD),
        }
        require_private_input(env=env)
        return info, env
    except (OSError, TypeError, KeyError, ValueError) as exc:
        raise PolicyError("Private session malformed or no longer active") from exc


def bind_direct_process():
    result = read_session()
    if result is None:
        return False
    info, env = result
    if os.environ.get("DISPLAY") != info["humanDisplay"]:
        raise PolicyError("Tunnel must attach from the original human DISPLAY")
    os.environ.update(env)
    return True


def concat_window(env):
    tree = command(["xwininfo", "-root", "-tree"], env)
    matches = re.findall(r'^\s*(0x[0-9a-fA-F]+)\s+"Concat":\s+\(""\s+"concat"\)', tree, re.M)
    if len(matches) != 1:
        return None
    props = command(["xprop", "-id", matches[0], "WM_CLASS", "WM_NAME", "_NET_WM_PID"], env)
    if ('WM_CLASS(STRING) = "", "concat"' not in props or
            'WM_NAME(STRING) = "Concat"' not in props or
            not re.search(r"_NET_WM_PID\(CARDINAL\)\s*=\s*\d+", props)):
        raise PolicyError("Private Concat window identity mismatch")
    return matches[0]


def frame(env, win):
    metadata = command(["xwininfo", "-id", win], env)
    bounds = re.findall(r"^\s*(?:Width|Height):\s*(\d+)", metadata, re.M)
    if len(bounds) != 2 or "Map State: IsViewable" not in metadata:
        raise RuntimeError("Private window not viewable")
    w, h = map(int, bounds)
    if not (200 <= w <= 2500 and 200 <= h <= 2000):
        raise RuntimeError("Private window size invalid")
    result = command(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                      "-f", "x11grab", "-window_id", str(int(win, 16)),
                      "-video_size", f"{w}x{h}", "-i", env["DISPLAY"],
                      "-frames:v", "1", "-vf", "scale=840:-2",
                      "-c:v", "mjpeg", "-q:v", "12", "-f", "image2pipe", "-"],
                     env, binary=True, timeout=22)
    if len(result) < 400 or not result.startswith(bytes.fromhex("ffd8")):
        raise RuntimeError("Private screenshot invalid")
    return result


def viewer(env, win, access, *, frame_provider=None, on_view=None):
    cache = {"when": 0, "data": b""}
    lock = threading.Lock()

    class ReadOnly(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            uri = urlsplit(self.path)
            if parse_qs(uri.query).get("pass", [""])[0] != access:
                self.send_response(403)
                self.end_headers()
                return
            if uri.path == "/":
                if on_view is not None:
                    on_view()
                body = ("""<!doctype html><meta charset="utf-8"><title>CCER | Concat isolé</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{background:#111;color:white;margin:0;text-align:center;font:15px system-ui}
header{padding:14px}img{width:100%;height:auto;max-width:1400px}</style>
<header>Concat isolé · lecture seule · aucune prise de focus</header>
<img id="v" alt="Fenêtre Concat privée">
<script>const p=new URL(location.href).searchParams.get('pass');
const img=document.getElementById('v');
function paint(){img.src='/image?pass='+encodeURIComponent(p)+'&r='+Date.now()}
paint();setInterval(paint,650);</script>""").encode("utf-8")
                mime = "text/html; charset=utf-8"
            elif uri.path == "/image":
                try:
                    with lock:
                        if time.monotonic() - cache["when"] >= 0.35 or not cache["data"]:
                            pixels = (frame_provider() if frame_provider is not None
                                      else frame(env, win))
                            if (not isinstance(pixels, bytes) or len(pixels) < 400
                                    or not pixels.startswith(bytes.fromhex("ffd8"))):
                                raise RuntimeError("Private screenshot invalid")
                            cache.update(when=time.monotonic(), data=pixels)
                        body = cache["data"]
                except (OSError, RuntimeError, subprocess.TimeoutExpired):
                    self.send_response(503)
                    self.end_headers()
                    return
                mime = "image/jpeg"
            else:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy",
                             "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self'")
            self.end_headers()
            self.wfile.write(body)

    result = http.server.ThreadingHTTPServer(("127.0.0.1", 0), ReadOnly)
    result.daemon_threads = True
    return result


def terminate(proc):
    if proc is None or proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=5)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait(timeout=5)


def run():
    if not APP.is_file() or not ICD.is_file():
        raise RuntimeError("Concat AppImage or Lavapipe ICD absent")
    human = os.environ.get("DISPLAY", "")
    if not re.fullmatch(r":[0-9]{1,3}(?:\.[0-9]{1,2})?", human):
        raise PolicyError("Missing human X11 DISPLAY")
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    if ROOT.is_symlink() or ROOT.stat().st_mode & 0o077:
        raise PolicyError("State directory must be mode 0700")
    if STATE.exists() or STATE.is_symlink():
        raise PolicyError("An isolated desktop state already exists")
    with tempfile.TemporaryDirectory(prefix="gui-", dir=ROOT) as base:
        home = Path(base)
        auth = home / "Xauthority"
        auth.touch(mode=0o600)
        display = next((f":{i}" for i in range(96,120) if f":{i}" != human
                        and not Path(f"/tmp/.X11-unix/X{i}").exists()
                        and not Path(f"/tmp/.X{i}-lock").exists()), None)
        if not display:
            raise RuntimeError("No free private X11 display")
        command(["xauth", "-f", str(auth), "add", display,
                 "MIT-MAGIC-COOKIE-1", os.urandom(16).hex()])
        env = dict(os.environ, DISPLAY=display, XAUTHORITY=str(auth),
                   XDG_CONFIG_HOME=str(home / "config"), XDG_DATA_HOME=str(home / "data"),
                   XDG_CACHE_HOME=str(home / "cache"), XDG_SESSION_TYPE="x11",
                   WINIT_UNIX_BACKEND="x11", GDK_BACKEND="x11",
                   LIBGL_ALWAYS_SOFTWARE="1", LP_NUM_THREADS="2",
                   VK_DRIVER_FILES=str(ICD), VK_ICD_FILENAMES=str(ICD))
        env.pop("CONCAT_GPU", None)
        xvfb = app = http = None
        saved = False
        try:
            xvfb = subprocess.Popen(["Xvfb", display, "-screen", "0", "1400x900x24",
                                     "-nolisten", "tcp", "-auth", str(auth)],
                                    start_new_session=True, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(60):
                if xvfb.poll() is not None:
                    raise RuntimeError("Private Xvfb stopped")
                try:
                    command(["xwininfo", "-root"], env, timeout=2)
                    break
                except (RuntimeError, subprocess.TimeoutExpired):
                    time.sleep(.15)
            else:
                raise RuntimeError("Private Xvfb failed to initialize")
            guard = dict(env, CCER_PRIVATE_DISPLAY=display, CCER_HUMAN_DISPLAY=human,
                         CCER_PRIVATE_XAUTHORITY=str(auth),
                         CCER_PRIVATE_XVFB_PID=str(xvfb.pid))
            require_private_input(env=guard)
            log = (home / "concat.log").open("wb")
            app = subprocess.Popen([str(APP)], env=env, start_new_session=True,
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
            log.close()
            win = None
            for _ in range(110):
                if app.poll() is not None:
                    raise RuntimeError("Isolated Concat exited during launch")
                if xvfb.poll() is not None:
                    raise RuntimeError("Private Xvfb exited during Concat startup")
                try:
                    win = concat_window(env)
                    if win:
                        command(["xdotool", "windowmap", "--sync", str(int(win,16))], env)
                        if "Map State: IsViewable" in command(["xwininfo", "-id", win], env):
                            break
                except RuntimeError:
                    if xvfb.poll() is not None:
                        raise RuntimeError("Private Xvfb exited unexpectedly")
                time.sleep(.15)
            else:
                raise RuntimeError("No viewable isolated Concat window")
            frame(env, win)
            access = os.urandom(20).hex()
            http = viewer(env, win, access)
            info = {
                "version":1, "uid":os.getuid(), "display":display, "humanDisplay":human,
                "authority":str(auth), "xvfbPid":xvfb.pid, "ownerPid":os.getpid(),
                "concatPid":app.pid, "windowId":win,
                "config":env["XDG_CONFIG_HOME"], "data":env["XDG_DATA_HOME"],
                "cache":env["XDG_CACHE_HOME"],
                "viewerPort":http.server_address[1], "viewerPass":access,
            }
            fd = os.open(STATE, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd,"w") as f:
                json.dump(info, f)
                f.flush()
                os.fsync(f.fileno())
            saved = True
            threading.Thread(target=http.serve_forever, daemon=True).start()
            print("CCER PRIVATE READY "+display+" "+win, flush=True)
            print("VIEWER (open manually): http://127.0.0.1:"+str(info["viewerPort"])+
                  "/?pass="+access, flush=True)
            while xvfb.poll() is None and app.poll() is None:
                time.sleep(.5)
            raise RuntimeError("Private Concat / Xvfb stopped")
        finally:
            if saved:
                try:
                    if json.loads(STATE.read_text()).get("ownerPid") == os.getpid():
                        STATE.unlink()
                except (OSError, ValueError):
                    pass
            if http is not None:
                http.shutdown()
                http.server_close()
            terminate(app)
            terminate(xvfb)


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("run","status","stop"))
    action=parser.parse_args(argv).action
    if action=="run":
        def stop_private(_signal, _frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, stop_private)
        try:
            run()
        except KeyboardInterrupt:
            return 0
        except (PolicyError,OSError,RuntimeError) as exc:
            print("CCER isolated: "+str(exc))
            return 1
    else:
        try:
            active=read_session()
        except PolicyError as exc:
            print("CCER isolated: invalid "+str(exc))
            return 2
        if action=="status":
            if active is None:
                print("CCER isolated: stopped")
                return 1
            data,_=active
            print("CCER isolated: READY "+data["display"])
            print("Viewer: http://127.0.0.1:"+str(data["viewerPort"])+
                  "/?pass="+data["viewerPass"])
            return 0
        if active is None:
            print("CCER isolated: already stopped")
            return 0
        os.kill(active[0]["ownerPid"],signal.SIGTERM)
        print("CCER isolated: stop requested")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
