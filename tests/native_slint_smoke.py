"""Run against the real Slint Concat, no physical X11 input."""
import base64
import os
import secrets
import stat
import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
from ccer.inapp_protocol import InAppComputerUse, PRIVATE_ROOT

def main():
    base=Path.cwd()
    executable=base/".upstream-concat/src/target/debug/concat"
    ffmpeg=base/".upstream-concat/.ccer-ffmpeg7/lib"
    media=base/".runtime/ccer-smoke/source.mp4"
    if not media.is_file():
        raise RuntimeError("Approved smoke fixture missing: run tests/create_native_smoke_fixture.sh")
    if not executable.is_file() or not ffmpeg.is_dir():
        raise RuntimeError("Native binary or FFmpeg unavailable")
    export_dir=base/".runtime/ccer-smoke/exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    PRIVATE_ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(PRIVATE_ROOT,0o700)
    sock=PRIVATE_ROOT/("smoke-"+secrets.token_hex(8)+".sock")
    credential=secrets.token_hex(32)
    with tempfile.TemporaryDirectory(prefix="ccer-native-") as tmp:
        scratch=Path(tmp)
        env=os.environ.copy()
        env.update({"CCER_INAPP_SOCKET":str(sock),
                    "CCER_INAPP_MEDIA_ROOT":str(media.parent.resolve()),
                    "CCER_INAPP_EXPORT_ROOT":str(export_dir.resolve()),
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
                permissions = stat.S_IMODE(sock.stat().st_mode)
                if permissions != 0o600:
                    raise RuntimeError(f"Private Slint socket has unsafe permissions: {permissions:o}")
                with InAppComputerUse(str(sock),credential,expected_pid=child.pid,timeout=15) as ui:
                    a=ui.observe()
                    x,y=ui._width//2,ui._height//2
                    b=ui.act({"type":"move","x":x,"y":y},confirm=True,expected_sha256=a["sha256"])
                    assert b["frameNo"]>a["frameNo"]
                    c=ui.observe()
                    d=ui.act({"type":"drag","x":x,"y":y,"targetX":x+10,"targetY":y+10,"duration":.25},
                             confirm=True,expected_sha256=c["sha256"])
                    assert d["frameNo"]>c["frameNo"]
                    actions = [
                        {"type": "click", "x": x, "y": y},
                        {"type": "scroll", "x": x, "y": y, "deltaY": 15},
                        {"type": "key", "key": "Escape"},
                    ]
                    for gesture in actions:
                        observed = ui.observe()
                        current = ui.act(gesture, confirm=True,
                                         expected_sha256=observed["sha256"])
                        assert current["frameNo"] > observed["frameNo"]
                    with patch.dict(os.environ, {"CCER_INAPP_MEDIA_ROOT": str(media.parent.resolve())}):
                        observed = ui.observe()
                        result = ui.act({"type": "file_drop", "path": str(media.resolve())},
                                        confirm=True, expected_sha256=observed["sha256"])
                        assert result["frameNo"] > observed["frameNo"]
                    with patch.dict(os.environ, {"CCER_INAPP_EXPORT_ROOT": str(export_dir.resolve())}):
                        observed=ui.observe()
                        result=ui.act({"type": "select_export_folder"},
                                      confirm=True, expected_sha256=observed["sha256"])
                        assert result["frameNo"] > observed["frameNo"]
                    evidence = base/".runtime/ccer-smoke/import_after.jpg"
                    evidence.write_bytes(base64.b64decode(result["imageBase64"]))
                    print("PASS native Slint transport: JPEG, move, paced drag, click, scroll, Escape, approved file drop",
                          ui._width, ui._height, "evidence:", evidence)
                    print("Import/export-folder outcomes need visual inspection; no export is claimed")
            finally:
                if child.poll() is None:
                    child.terminate()
                    try: child.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait(timeout=8)
                if sock.exists() or sock.is_symlink(): sock.unlink()

if __name__=="__main__": main()
