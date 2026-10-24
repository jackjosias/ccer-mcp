"""Prove native desktop routing never silently touches X11."""
import base64
import hashlib
import os
import tempfile
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
                        self.assertEqual(["hello", "capture", "gesture"],
                                         [method for method, _ in server.calls])
                finally:
                    native_desktop._close()
                    server.stop()

if __name__ == "__main__":
    unittest.main()
