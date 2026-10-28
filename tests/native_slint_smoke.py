"""Run against the real Slint Concat, no physical X11 input."""
import base64
import json
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
from ccer.controls import PolicyError
from ccer.focus_isolation import require_private_input
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
    # Never make short-lived native smoke windows appear on the human DISPLAY.
    # Only an independently attested Xvfb session may run this disposable test.
    require_private_input()
    base=Path.cwd()
    executable=base/".upstream-concat/src/target/debug/concat"
    ffmpeg=base/".upstream-concat/.ccer-ffmpeg7/lib"
    media=base/".runtime/ccer-smoke/source.mp4"
    if not media.is_file():
        raise RuntimeError("Approved smoke fixture missing: run tests/create_native_smoke_fixture.sh")
    if not executable.is_file() or not ffmpeg.is_dir():
        raise RuntimeError("Native binary or FFmpeg unavailable")
    export_dir=base/".runtime/ccer-smoke/exports"/("native-"+secrets.token_hex(6))
    export_dir.mkdir(parents=True, exist_ok=False)
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
                        viewing_started = threading.Event()
                        observer = viewer(env, None, access,
                                          frame_provider=lambda: mirrored["jpeg"],
                                          on_view=viewing_started.set)
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
                    if "--live-demo" in sys.argv:
                        if "--watch" not in sys.argv or "--project" not in sys.argv:
                            raise RuntimeError("Live demo requires --watch --project")
                        print("CCER LIVE DEMO READY: waiting for observer", flush=True)
                        deadline = time.monotonic() + 150
                        while not viewing_started.is_set():
                            if time.monotonic() >= deadline:
                                raise RuntimeError("No authenticated visual observer connected")
                            ui.observe()  # Keep Rust's 15-second idle timeout satisfied.
                            viewing_started.wait(1)
                        print("CCER LIVE DEMO: viewer connected", flush=True)
                        for _ in range(4):
                            ui.observe()
                            time.sleep(1)
                    evidence_dir = base / ".runtime/ccer-smoke"
                    (evidence_dir / "before.jpg").write_bytes(base64.b64decode(a["imageBase64"]))
                    if "--project" not in sys.argv:
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
                    else:
                        actions = []
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
                        try:
                            created = ui.act({"type": "click", "x": 265, "y": 250},
                                             confirm=True, expected_sha256=observed["sha256"])
                        except PolicyError as exc:
                            if "native adapter rejected: CCER: UI timeout" not in str(exc):
                                raise
                            # The first click opens a compose dialog, not a project.
                            # Never repeat an input merely because the RPC timed out.
                            print("CCER: project-dialog click timed out; observing once", flush=True)
                            created = ui.observe()
                        (evidence_dir / "project_create_after.jpg").write_bytes(
                            base64.b64decode(created["imageBase64"]))
                        time.sleep(2)
                        dialog = ui.observe()
                        (evidence_dir / "project_dialog_after.jpg").write_bytes(
                            base64.b64decode(dialog["imageBase64"]))
                        if "--dialog-only" in sys.argv:
                            print("CCER: modal capture saved; no unverified Create click", flush=True)
                            return
                        # New project opens a modal. Confirm Create exactly once;
                        # a timed-out RPC is ambiguous and must not be retried.
                        target_x = round(ui._width * 0.367)
                        target_y = round(ui._height * 0.686)
                        try:
                            committed = ui.act(
                                {"type": "click", "x": target_x, "y": target_y},
                                confirm=True, expected_sha256=dialog["sha256"])
                            (evidence_dir / "project_confirm_after.jpg").write_bytes(
                                base64.b64decode(committed["imageBase64"]))
                        except PolicyError as exc:
                            if "native adapter rejected: CCER: UI timeout" not in str(exc):
                                raise
                            print("CCER: create-click outcome ambiguous; inspecting disk only", flush=True)
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
                        # Reuse the verified MediaCard-to-timeline drag path.
                        # The File menu has no "Add selected" action in Concat.
                        source_x, source_y = 164, 166
                        target_x = round(ui._width * 0.188)
                        target_y = round(ui._height * 0.707)
                        timeline_before = ui.observe()
                        dragged = ui.act(
                            {"type": "drag", "x": source_x, "y": source_y,
                             "targetX": target_x, "targetY": target_y,
                             "duration": 0.3},
                            confirm=True, expected_sha256=timeline_before["sha256"])
                        (evidence_dir / "project_timeline_drag_after.jpg").write_bytes(
                            base64.b64decode(dragged["imageBase64"]))
                        time.sleep(3)
                        settled = ui.observe()
                        (evidence_dir / "project_timeline_drag_settled.jpg").write_bytes(
                            base64.b64decode(settled["imageBase64"]))
                        print("Media-to-timeline drag dispatched; inspect timeline evidence",
                              flush=True)
                        if "--export" in sys.argv:
                            export_before = ui.observe()
                            opened = ui.act({"type": "click", "x": 710, "y": 17},
                                            confirm=True, expected_sha256=export_before["sha256"])
                            (evidence_dir / "project_export_open_after.jpg").write_bytes(
                                base64.b64decode(opened["imageBase64"]))
                            time.sleep(2)
                            export_opened = ui.observe()
                            (evidence_dir / "project_export_dialog.jpg").write_bytes(
                                base64.b64decode(export_opened["imageBase64"]))
                            print("Native Concat export UI opened; rendering into:", export_dir, flush=True)
                            render_before = ui.observe()
                            dispatched = ui.act({"type": "click", "x": 710, "y": 529},
                                                confirm=True, expected_sha256=render_before["sha256"])
                            (evidence_dir / "project_export_dispatch_after.jpg").write_bytes(
                                base64.b64decode(dispatched["imageBase64"]))
                            deadline = time.monotonic() + 120
                            confirmed = None
                            while time.monotonic() < deadline and confirmed is None:
                                for candidate in export_dir.glob("*.mp4"):
                                    if not candidate.is_file() or candidate.stat().st_size < 1000:
                                        continue
                                    probe = subprocess.run(
                                        ["ffprobe", "-v", "error", "-show_streams", "-show_format",
                                         "-of", "json", str(candidate)], capture_output=True,
                                        text=True, timeout=25, check=False)
                                    if probe.returncode:
                                        continue
                                    report = json.loads(probe.stdout)
                                    video_streams = [stream for stream in report.get("streams", [])
                                                     if stream.get("codec_type") == "video"]
                                    duration = float(report.get("format", {}).get("duration", 0))
                                    if (video_streams and video_streams[0].get("codec_name") == "h264"
                                            and video_streams[0].get("width") == 1920
                                            and video_streams[0].get("height") == 1080
                                            and 1.5 <= duration <= 3.0):
                                        confirmed = (candidate, duration)
                                        break
                                if confirmed is None:
                                    time.sleep(2)
                            final_export = ui.observe()
                            (evidence_dir / "project_export_result.jpg").write_bytes(
                                base64.b64decode(final_export["imageBase64"]))
                            if confirmed is None:
                                raise RuntimeError("Concat did not produce a verified MP4 within 120s")
                            print("PASS Concat native MP4 H.264 verified by ffprobe:",
                                  confirmed[0], "duration:", confirmed[1], flush=True)
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
