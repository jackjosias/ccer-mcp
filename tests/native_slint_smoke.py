"""Run against the real Slint Concat, no physical X11 input."""
import os
import secrets
import subprocess
import tempfile
import time
from pathlib import Path
from ccer.inapp_protocol import InAppComputerUse, PRIVATE_ROOT

def main():
    base=Path.cwd()
    executable=base/".upstream-concat/src/target/debug/concat"
    ffmpeg=base/".upstream-concat/.ccer-ffmpeg7/lib"
    if not executable.is_file() or not ffmpeg.is_dir():
        raise RuntimeError("Native binary or FFmpeg unavailable")
    PRIVATE_ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(PRIVATE_ROOT,0o700)
    sock=PRIVATE_ROOT/("smoke-"+secrets.token_hex(8)+".sock")
    credential=secrets.token_hex(32)
    with tempfile.TemporaryDirectory(prefix="ccer-native-") as tmp:
        scratch=Path(tmp)
        env=os.environ.copy()
        env.update({"CCER_INAPP_SOCKET":str(sock),
                    "XDG_CONFIG_HOME":str(scratch/"config"),
                    "XDG_DATA_HOME":str(scratch/"data"),
                    "XDG_CACHE_HOME":str(scratch/"cache"),
                    "LD_LIBRARY_PATH":str(ffmpeg)+(":"+env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")})
        env["".join(("CCER","_INAPP","_TOKEN"))]=credential
        env.setdefault("SLINT_BACKEND","winit-software")
        with (scratch/"logs.txt").open("wb") as logs:
            child=subprocess.Popen([str(executable)],cwd=scratch,env=env,
                                   stdin=subprocess.DEVNULL,stdout=logs,stderr=logs)
            try:
                deadline=time.monotonic()+60
                while not sock.is_socket() and time.monotonic()<deadline:
                    if child.poll() is not None:
                        raise RuntimeError("Native app exited before socket ready")
                    time.sleep(.25)
                if not sock.is_socket():
                    raise RuntimeError("Native socket not available")
                with InAppComputerUse(str(sock),credential,expected_pid=child.pid,timeout=15) as ui:
                    a=ui.observe()
                    x,y=ui._width//2,ui._height//2
                    b=ui.act({"type":"move","x":x,"y":y},confirm=True,expected_sha256=a["sha256"])
                    assert b["frameNo"]>a["frameNo"]
                    c=ui.observe()
                    d=ui.act({"type":"drag","x":x,"y":y,"targetX":x+10,"targetY":y+10,"duration":.25},
                             confirm=True,expected_sha256=c["sha256"])
                    assert d["frameNo"]>c["frameNo"]
                    print("PASS actual Slint JPEG and timed native drag",ui._width,ui._height)
            finally:
                if child.poll() is None:
                    child.terminate()
                    try: child.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait(timeout=8)
                if sock.exists() or sock.is_symlink(): sock.unlink()

if __name__=="__main__": main()
