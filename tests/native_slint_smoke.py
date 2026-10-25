"""Run against the real Slint Concat, no physical X11 input."""
import base64
import os
import secrets
import stat
import sys
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch
from ccer.inapp_protocol import InAppComputerUse
from ccer.isolated_session import terminate, viewer


class WatchingClient(InAppComputerUse):
    """Publish already-verified Slint frames without a second UI connection."""
    frame_sink = None

    def _publish(self, result):
        if self.frame_sink is not None:
            self.frame_sink(base64.b64decode(result["imageBase64"]))
        return result

    def observe(self):
        return self._publish(super().observe())

    def act(self, *args, **kwargs):
        return self._publish(super().act(*args, **kwargs))


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
    with tempfile.TemporaryDirectory(prefix="ccer-native-") as tmp:
        scratch=Path(tmp)
        private_root=scratch/".local/state/ccer-inapp"
        private_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(private_root,0o700)
        sock=private_root/("smoke-"+secrets.token_hex(8)+".sock")
        credential=secrets.token_hex(32)
        (scratch / "Desktop").mkdir()
        env=os.environ.copy()
        env.update({"HOME":str(scratch),
                    "XDG_DESKTOP_DIR":str(scratch / "Desktop"),
                    "CCER_INAPP_SOCKET":str(sock),
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
                                   stdin=subprocess.DEVNULL,stdout=logs,stderr=logs,
                                   start_new_session=True)
            observer = None
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
                with patch("ccer.inapp_protocol.PRIVATE_ROOT", private_root), WatchingClient(str(sock),credential,expected_pid=child.pid,timeout=15) as ui:
                    mirrored = {"jpeg": b""}
                    if "--watch" in sys.argv:
                        ui.frame_sink = lambda pixels: mirrored.__setitem__("jpeg", pixels)
                    a=ui.observe()
                    if "--watch" in sys.argv:
                        access = secrets.token_hex(24)
                        observer = viewer(env, None, access,
                                          frame_provider=lambda: mirrored["jpeg"])
                        threading.Thread(target=observer.serve_forever, daemon=True).start()
                        from urllib import error, request
                        local = "http://127.0.0.1:" + str(observer.server_address[1])
                        with request.urlopen(local + "/image?pass=" + access, timeout=10) as response:
                            picture = response.read(2_000_000)
                            if response.status != 200 or not picture.startswith(bytes.fromhex("ffd8")):
                                raise RuntimeError("Private Slint JPEG viewer failed")
                        try:
                            request.urlopen(local + "/image?pass=invalid", timeout=5)
                            raise RuntimeError("Private viewer accepted an invalid token")
                        except error.HTTPError as rejected:
                            if rejected.code != 403:
                                raise
                        print("CCER PRIVATE WATCH VERIFIED: HTTP 200 JPEG; invalid token 403", flush=True)
                        print("CCER PRIVATE WATCH (read-only): http://127.0.0.1:"
                              + str(observer.server_address[1]) + "/?pass=" + access, flush=True)
                    evidence_dir = base / ".runtime/ccer-smoke"
                    (evidence_dir / "before.jpg").write_bytes(base64.b64decode(a["imageBase64"]))
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
                    (evidence_dir / "import_after.jpg").write_bytes(
                        base64.b64decode(result["imageBase64"]))
                    with patch.dict(os.environ, {"CCER_INAPP_EXPORT_ROOT": str(export_dir.resolve())}):
                        observed=ui.observe()
                        result=ui.act({"type": "select_export_folder"},
                                      confirm=True, expected_sha256=observed["sha256"])
                        assert result["frameNo"] > observed["frameNo"]
                    evidence = evidence_dir / "export_folder_after.jpg"
                    evidence.write_bytes(base64.b64decode(result["imageBase64"]))
                    print("PASS native Slint transport: JPEG, move, paced drag, click, scroll, Escape, approved file drop",
                          ui._width, ui._height, "evidence:", evidence_dir)
                    if "--project" in sys.argv:
                        project_root = (scratch / "Desktop" / "Concat").resolve()
                        if not project_root.is_relative_to(scratch.resolve()):
                            raise RuntimeError("Project root escaped disposable HOME")
                        observed = ui.observe()
                        created = ui.act({"type": "click", "x": 200, "y": 487},
                                         confirm=True, expected_sha256=observed["sha256"])
                        (evidence_dir / "project_create_after.jpg").write_bytes(
                            base64.b64decode(created["imageBase64"]))
                        deadline = time.monotonic() + 20
                        while not (project_root.is_dir() and any(project_root.iterdir())) and time.monotonic() < deadline:
                            time.sleep(.25)
                        if not project_root.is_dir() or not any(project_root.iterdir()):
                            raise RuntimeError("Concat did not create a disposable project")
                        time.sleep(4)
                        final_frame = ui.observe()
                        (evidence_dir / "project_import_after.jpg").write_bytes(
                            base64.b64decode(final_frame["imageBase64"]))
                        print("PASS: Concat created project inside disposable HOME:", project_root)
                        selected_before = ui.observe()
                        selected = ui.act({"type": "click", "x": 164, "y": 166},
                                          confirm=True, expected_sha256=selected_before["sha256"])
                        (evidence_dir / "project_selected_media.jpg").write_bytes(
                            base64.b64decode(selected["imageBase64"]))
                        menu_before = ui.observe()
                        menu = ui.act({"type": "click", "x": 25, "y": 13},
                                      confirm=True, expected_sha256=menu_before["sha256"])
                        (evidence_dir / "project_file_menu.jpg").write_bytes(
                            base64.b64decode(menu["imageBase64"]))
                        chosen_before = ui.observe()
                        chosen = ui.act({"type": "click", "x": 91, "y": 49},
                                        confirm=True, expected_sha256=chosen_before["sha256"])
                        (evidence_dir / "project_menu_add_after.jpg").write_bytes(
                            base64.b64decode(chosen["imageBase64"]))
                        time.sleep(2)
                        menu_result = ui.observe()
                        (evidence_dir / "project_menu_add_settled.jpg").write_bytes(
                            base64.b64decode(menu_result["imageBase64"]))
                        print("Menu Add Selected dispatched; actual clip placement and export require proof")
                    else:
                        print("Import/export-folder outcomes need visual inspection; no export is claimed")
                    if "--stay" in sys.argv:
                        if "--watch" not in sys.argv:
                            raise RuntimeError("Long-running native session requires private watch")
                        print("CCER NATIVE WATCH SESSION LIVE; stop its owning service to close", flush=True)
                        while child.poll() is None:
                            time.sleep(1.5)
                            ui.observe()
                        raise RuntimeError("Native Concat stopped during live viewing")
            except Exception:
                # Capture a bounded diagnostic before TemporaryDirectory removes it.
                # Do not print environment variables or the private session secret.
                try:
                    details = (scratch / "logs.txt").read_text(errors="replace")[-2500:]
                    print("Native Concat startup/action diagnostic:", details)
                except OSError:
                    pass
                raise
            finally:
                if observer is not None:
                    observer.shutdown()
                    observer.server_close()
                terminate(child)
                if sock.exists() or sock.is_symlink(): sock.unlink()

if __name__=="__main__": main()
