"""Prove native desktop routing never silently touches X11."""
import base64
import hashlib
import os
import tempfile
import time
import unittest
from pathlib import Path
from tests.test_inapp_protocol import FakeSlintServer
from unittest.mock import patch
from ccer import desktop_gui, native_desktop
from ccer.controls import PolicyError

class FakeClient:
    _window = "concat-main"
    _width = 900
    _height = 700
    def __init__(self):
        self.closed, self.actions, self.count = False, [], 0
    def __enter__(self):
        return self
    def close(self):
        self.closed = True
    def observe(self):
        self.count += 1
        data = b"\xff\xd8" + b"test-frame" * 35 + b"\xff\xd9"
        return {"windowId": self._window, "frameNo": self.count,
                "mimeType": "image/jpeg", "sha256": hashlib.sha256(data).hexdigest(),
                "imageBase64": base64.b64encode(data).decode()}
    def act(self, gesture, *, confirm, expected_sha256):
        self.actions.append((gesture, confirm, expected_sha256))
        return self.observe()

class NativeDesktopTests(unittest.TestCase):
    def setUp(self):
        native_desktop._close()
        self.env = patch.dict(os.environ, {
            "CCER_INAPP_SOCKET": "/tmp/example.sock",
            "CCER_INAPP_TOKEN": "z" * 48})
        self.env.start()
        self.client = FakeClient()
        self.backend = patch("ccer.native_desktop.InAppComputerUse", return_value=self.client)
        self.factory = self.backend.start()
        self.x11 = patch("ccer.desktop_gui._run",
                         side_effect=AssertionError("physical X11 access forbidden"))
        self.x11.start()
    def tearDown(self):
        native_desktop._close()
        self.x11.stop()
        self.backend.stop()
        self.env.stop()
    def test_before_action_after_one_connection(self):
        self.assertEqual("native-slint", desktop_gui.status()["window"]["display"])
        before = desktop_gui.capture()
        after = desktop_gui.interact(expected_window_id="concat-main",
                                     action="click", confirm_action=True, x=20, y=30)
        self.assertEqual(1, self.factory.call_count)
        self.assertGreater(after["frameNo"], before["frameNo"])
        self.assertEqual([({"type": "click", "x": 20, "y": 30},
                           True, before["sha256"])], self.client.actions)
    def test_idle_native_connection_is_refreshed_without_x11(self):
        desktop_gui.status()
        old_client = self.client
        new_client = FakeClient()
        self.factory.side_effect = [new_client]
        native_desktop._SESSION_STARTED = time.monotonic() - 20
        result = desktop_gui.capture()
        self.assertEqual("concat-main", result["window"]["windowId"])
        self.assertEqual(2, self.factory.call_count)
        self.assertTrue(old_client.closed)
        self.assertFalse(new_client.closed)

    def test_stale_socket_reconnects_and_revalidates_before_click(self):
        before = desktop_gui.capture()
        old_client = self.client
        fresh_client = FakeClient()
        self.factory.side_effect = [fresh_client]
        native_desktop._SESSION_STARTED = time.monotonic() - 20
        result = desktop_gui.interact(
            expected_window_id="concat-main", action="click",
            confirm_action=True, x=20, y=30)
        self.assertEqual(2, self.factory.call_count)
        self.assertTrue(old_client.closed)
        self.assertEqual(before["sha256"], fresh_client.actions[0][2])
        self.assertEqual("click", result["action"])
        self.assertEqual([], old_client.actions)

    def test_changed_screen_rejects_click_after_reconnect(self):
        desktop_gui.capture()
        fresh_client = FakeClient()
        original_observe = fresh_client.observe
        def changed_observe():
            frame = original_observe()
            frame["sha256"] = "f" * 64
            return frame
        fresh_client.observe = changed_observe
        self.factory.side_effect = [fresh_client]
        native_desktop._SESSION_STARTED = time.monotonic() - 20
        with self.assertRaisesRegex(PolicyError, "changed since BEFORE"):
            desktop_gui.interact(expected_window_id="concat-main",
                                 action="click", confirm_action=True, x=20, y=30)
        self.assertEqual([], fresh_client.actions)

    def test_timed_drag_routes_to_native_session(self):
        before = desktop_gui.capture()
        after = desktop_gui.interact(
            expected_window_id="concat-main", action="drag",
            confirm_action=True, x=120, y=200,
            target_x=300, target_y=240, duration=0.55)
        self.assertGreater(after["frameNo"], before["frameNo"])
        self.assertEqual(({"type": "drag", "x": 120, "y": 200,
                           "targetX": 300, "targetY": 240, "duration": 0.55},
                          True, before["sha256"]), self.client.actions[0])

    def test_pointer_move_stays_in_slint(self):
        desktop_gui.capture()
        desktop_gui.interact(expected_window_id="concat-main", action="move",
                             confirm_action=True, x=150, y=110)
        self.assertEqual("move", self.client.actions[0][0]["type"])

    def test_approved_file_drop_routes_to_existing_gui(self):
        with tempfile.TemporaryDirectory() as folder:
            media = Path(folder) / "test.mp4"
            media.write_bytes(b"sample")
            with patch.dict(os.environ, {"CCER_INAPP_MEDIA_ROOT": folder}):
                before = desktop_gui.capture()
                after = desktop_gui.interact(
                    expected_window_id="concat-main", action="file_drop",
                    text=str(media), confirm_action=True)
                self.assertGreater(after["frameNo"], before["frameNo"])
                self.assertEqual({"type": "file_drop", "path": str(media)},
                                 self.client.actions[0][0])

    def test_file_drop_rejects_outside_root_symlink_and_unsafe_type(self):
        from ccer.inapp_protocol import InAppComputerUse
        adapter = object.__new__(InAppComputerUse)
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            approved = base / "approved"
            approved.mkdir()
            inside = approved / "clip.mp4"
            inside.write_bytes(b"test")
            outside = base / "outside.mp4"
            outside.write_bytes(b"test")
            link = approved / "linked.mp4"
            link.symlink_to(outside)
            wrong = approved / "report.txt"
            wrong.write_text("not media")
            with patch.dict(os.environ, {"CCER_INAPP_MEDIA_ROOT": str(approved)}):
                self.assertEqual(
                    {"type": "file_drop", "path": str(inside)},
                    adapter._validate_gesture({"type": "file_drop", "path": str(inside)}))
                for candidate in (outside, link, wrong):
                    with self.subTest(candidate=candidate):
                        with self.assertRaises(PolicyError):
                            adapter._validate_gesture(
                                {"type": "file_drop", "path": str(candidate)})

    def test_selected_export_directory_routes_to_concat_gui(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ, {"CCER_INAPP_EXPORT_ROOT": folder}):
                before = desktop_gui.capture()
                after = desktop_gui.interact(
                    expected_window_id="concat-main",
                    action="select_export_folder", confirm_action=True)
                self.assertGreater(after["frameNo"], before["frameNo"])
                self.assertEqual({"type": "select_export_folder"},
                                 self.client.actions[0][0])

    def test_export_directory_must_be_real_approved_directory(self):
        from ccer.inapp_protocol import InAppComputerUse
        adapter = object.__new__(InAppComputerUse)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            approved = root / "exports"
            approved.mkdir()
            alias = root / "alias"
            alias.symlink_to(approved, target_is_directory=True)
            with patch.dict(os.environ, {"CCER_INAPP_EXPORT_ROOT": str(approved)}):
                self.assertEqual({"type": "select_export_folder"},
                                 adapter._validate_gesture({"type": "select_export_folder"}))
            for configured in ("", str(alias), str(root / "missing")):
                with patch.dict(os.environ, {"CCER_INAPP_EXPORT_ROOT": configured}):
                    with self.assertRaises(PolicyError):
                        adapter._validate_gesture({"type": "select_export_folder"})

    def test_action_without_observation_denied(self):
        with self.assertRaisesRegex(PolicyError, "fresh BEFORE"):
            desktop_gui.interact(expected_window_id="concat-main", action="click",
                                 confirm_action=True, x=10, y=20)
    def test_unsupported_native_gesture_never_falls_back(self):
        desktop_gui.capture()
        with self.assertRaisesRegex(PolicyError, "no X11 fallback"):
            desktop_gui.interact(expected_window_id="concat-main", action="type",
                                 text="hello", confirm_action=True)
        self.assertTrue(self.client.closed)
        self.assertEqual([], self.client.actions)
    def test_bad_native_configuration_denied_without_x11(self):
        self.backend.stop()
        with patch.dict(os.environ, {"CCER_INAPP_TOKEN": ""}):
            with self.assertRaises(PolicyError):
                desktop_gui.capture()

class VisibleRoutingTests(unittest.TestCase):
    def test_xvfb_cannot_attach_visible_bridge(self):
        with patch.dict(os.environ, {"CCER_PRIVATE_DISPLAY": ":98", "DISPLAY": ":98"}, clear=True):
            self.assertIsNone(native_desktop._visible_config())
            self.assertFalse(native_desktop.enabled())

    def test_visible_bridge_requires_same_display(self):
        state = {"socket": "/tmp/example.sock", "proof": "dummy", "pid": 9001,
                 "display": ":1"}
        with patch("ccer.visible_desktop._file_state", return_value=state), \
             patch("ccer.visible_desktop._live", return_value=True):
            for display in ("", ":97"):
                with patch.dict(os.environ, {"DISPLAY": display}, clear=True):
                    self.assertIsNone(native_desktop._visible_config())
            with patch.dict(os.environ, {"DISPLAY": ":1"}, clear=True):
                self.assertEqual(9001, native_desktop._visible_config()[2])

class NativeUnixWireTests(unittest.TestCase):
    def test_real_unix_transport_and_router(self):
        native_desktop._close()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            os.chmod(root, 0o700)
            socket_path = root / "concat.sock"
            with patch("ccer.inapp_protocol.PRIVATE_ROOT", root):
                server = FakeSlintServer(socket_path)
                try:
                    with patch.dict(os.environ, {
                        "CCER_INAPP_SOCKET": str(socket_path),
                        "CCER_INAPP_TOKEN": "v" * 48,
                    }, clear=True):
                        status = desktop_gui.status()
                        before = desktop_gui.capture()
                        after = desktop_gui.interact(
                            expected_window_id=status["window"]["windowId"],
                            action="click", confirm_action=True, x=25, y=70)
                        self.assertGreater(after["frameNo"], before["frameNo"])
                        self.assertEqual(["hello", "capture", "capture", "gesture"],
                                         [method for method, _ in server.calls])
                finally:
                    native_desktop._close()
                    server.stop()

if __name__ == "__main__":
    unittest.main()
