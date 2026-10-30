"""Deterministic Unix transport tests; NO host X11 or editing is performed."""
import base64
import hashlib
import json
import os
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from ccer.controls import PolicyError
from ccer.inapp_protocol import InAppComputerUse, PROTOCOL


class FakeSlintServer:
    def __init__(self, socket_path, *, valid_frame=True, reject_action=False, stale_after=False):
        self.socket_path = Path(socket_path)
        self.valid_frame = valid_frame
        self.reject_action = reject_action
        self.stale_after = stale_after
        self.calls = []
        self.frame_number = 0
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.bind(str(self.socket_path))
        os.chmod(self.socket_path, 0o600)
        self.listener.listen(1)
        self.worker = threading.Thread(target=self.serve, daemon=True)
        self.worker.start()

    def frame(self):
        self.frame_number += 1
        # Synthetic JPEG envelope: verifies framed bytes and hash/ordering,
        # NOT the actual Slint renderer or JPEG decoder.
        pixels = bytes.fromhex("ffd8") + b"mock-frame-" * 25 + bytes.fromhex("ffd9")
        return {"imageBase64":base64.b64encode(pixels).decode(),
                "mimeType":"image/jpeg", "sha256":hashlib.sha256(pixels).hexdigest()
                              if self.valid_frame else "0"*64,
                "windowId":"concat-window-test", "frameNo":self.frame_number}

    def serve(self):
        try:
            conn, _ = self.listener.accept()
            with conn:
                stream = conn.makefile("rwb", buffering=0)
                for line in stream:
                    msg = json.loads(line)
                    method, args = msg["method"], msg["params"]
                    self.calls.append((method,args))
                    if method == "hello":
                        result = {"protocol":PROTOCOL, "app":"Concat", "engine":"slint",
                            "capabilities":["real-frame","scene-input"],
                            "windowId":"concat-window-test",
                            "sessionId":"a"*32, "width":900, "height":700}
                    elif method == "capture":
                        result = self.frame()
                    elif method == "gesture":
                        after = self.frame()
                        if self.stale_after:
                            after["frameNo"] -= 1
                        result = {"accepted":not self.reject_action,
                                  "dispatched":not self.reject_action,
                                  "after":after}
                    else:
                        result = None
                    stream.write(json.dumps({"id":msg["id"],"result":result}).encode()+b"\n")
        except (OSError, BrokenPipeError):
            pass

    def stop(self):
        self.listener.close()
        self.worker.join(timeout=2)


class InAppProtocolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        os.chmod(self.root, 0o700)
        self.patch = patch("ccer.inapp_protocol.PRIVATE_ROOT", self.root)
        self.patch.start()
        self.sock = self.root/"app.sock"
        self.server = None

    def tearDown(self):
        if self.server is not None:
            self.server.stop()
        self.patch.stop()
        self.tmp.cleanup()

    def connect(self, **kwargs):
        self.server = FakeSlintServer(self.sock, **kwargs)
        return InAppComputerUse(str(self.sock), "c"*48)

    def test_missing_endpoint_refuses_without_x11_fallback(self):
        with self.assertRaisesRegex(PolicyError, "INAPP_UNAVAILABLE"):
            InAppComputerUse(str(self.sock), "t"*48)

    def test_weak_token_and_wrong_socket_location_are_denied(self):
        self.server = FakeSlintServer(self.sock)
        with self.assertRaisesRegex(PolicyError, "token"):
            InAppComputerUse(str(self.sock), "short")
        with self.assertRaisesRegex(PolicyError, "dedicated"):
            InAppComputerUse("/tmp/another.sock", "t"*48)

    def test_peer_pid_verification_refuses_other_process(self):
        client=self.connect()
        client.expected_pid=999999
        with self.assertRaisesRegex(PolicyError, "PID/UID"):
            with client: pass

    def test_real_frame_gate_one_complete_click_and_replay_denied(self):
        with self.connect() as control:
            with self.assertRaisesRegex(PolicyError, "BEFORE screenshot"):
                control.act({"type":"click","x":35,"y":60},confirm=True,
                            expected_sha256="0"*64)
            before=control.observe()
            done=control.act({"type":"click","x":35,"y":60},confirm=True,
                             expected_sha256=before["sha256"])
            self.assertEqual(done["frameNo"],before["frameNo"]+1)
            with self.assertRaisesRegex(PolicyError, "BEFORE screenshot"):
                control.act({"type":"click","x":35,"y":60},confirm=True,
                            expected_sha256=before["sha256"])
            self.assertEqual([m for m,_ in self.server.calls].count("gesture"),1)

    def test_drag_uses_one_native_atomic_gesture(self):
        with self.connect() as control:
            before=control.observe()
            done=control.act({"type":"drag","x":12,"y":13,
                 "targetX":400,"targetY":330,"duration":0.6},
                 confirm=True,expected_sha256=before["sha256"])
            self.assertEqual(done["frameNo"],2)
            self.assertEqual([m for m,_ in self.server.calls].count("gesture"),1)

    def test_bounded_unicode_typing_requires_visual_receipt(self):
        with self.connect() as control:
            with self.assertRaisesRegex(PolicyError, "BEFORE screenshot"):
                control.act({"type": "type_text", "text": "CCER test"},
                            confirm=True, expected_sha256="0" * 64)
            before = control.observe()
            done = control.act({"type": "type_text", "text": "CCER Démonstration"},
                               confirm=True, expected_sha256=before["sha256"])
            self.assertGreater(done["frameNo"], before["frameNo"])
            gestures = [params["gesture"] for method, params in self.server.calls
                        if method == "gesture"]
            self.assertEqual(gestures, [{"type": "type_text", "text": "CCER Démonstration"}])

    def test_select_all_is_explicit_one_gesture(self):
        with self.connect() as control:
            before = control.observe()
            done = control.act({"type": "key", "key": "SelectAll"},
                               confirm=True, expected_sha256=before["sha256"])
            self.assertGreater(done["frameNo"], before["frameNo"])
            gestures = [params["gesture"] for method, params in self.server.calls
                        if method == "gesture"]
            self.assertEqual(gestures, [{"type": "key", "key": "SelectAll"}])

    def test_reused_after_frame_is_rejected(self):
        with self.connect(stale_after=True) as control:
            before = control.observe()
            with self.assertRaisesRegex(PolicyError, "AFTER frame must advance"):
                control.act({"type": "move", "x": 12, "y": 30},
                            confirm=True, expected_sha256=before["sha256"])
            with self.assertRaisesRegex(PolicyError, "BEFORE screenshot"):
                control.act({"type": "move", "x": 12, "y": 30},
                            confirm=True, expected_sha256=before["sha256"])

    def test_invalid_coordinates_keyboard_or_extra_fields_fail_without_dispatch(self):
        with self.connect() as control:
            bad=[
                {"type":"click","x":901,"y":30},
                {"type":"click","x":-1,"y":30},
                {"type":"click","x":float("nan"),"y":30},
                {"type":"key","key":"ctrl+shift+delete"},
                {"type":"type_text","text":""},
                {"type":"type_text","text":"X" * 161},
                {"type":"type_text","text":"line\nbreak"},
                {"type":"type_text","text":"safe", "shell":"bad"},
                {"type":"click","x":35,"y":30,"shell":"rm"},
                {"type":"drag","x":10,"y":10,"targetX":20,"targetY":20,"duration":6},
                {"type":"scroll","x":40,"y":40,"deltaY":float("inf")},
            ]
            for gesture in bad:
                with self.subTest(gesture=gesture):
                    obs=control.observe()
                    with self.assertRaises(PolicyError):
                        control.act(gesture,confirm=True,expected_sha256=obs["sha256"])
            self.assertEqual([m for m,_ in self.server.calls].count("gesture"),0)

    def test_no_action_without_explicit_confirmation(self):
        with self.connect() as control:
            obs=control.observe()
            with self.assertRaisesRegex(PolicyError, "confirmation"):
                control.act({"type":"move","x":12,"y":30},
                            confirm=False,expected_sha256=obs["sha256"])
            self.assertEqual([m for m,_ in self.server.calls].count("gesture"),0)

    def test_invalid_frame_hash_blocks_gestures(self):
        with self.connect(valid_frame=False) as control:
            with self.assertRaisesRegex(PolicyError, "visual frame verification"):
                control.observe()
            self.assertEqual([m for m,_ in self.server.calls].count("gesture"),0)

    def test_native_event_rejection_does_not_replay(self):
        with self.connect(reject_action=True) as control:
            obs=control.observe()
            with self.assertRaisesRegex(PolicyError, "not accepted"):
                control.act({"type":"key","key":"Escape"},confirm=True,
                            expected_sha256=obs["sha256"])
            with self.assertRaisesRegex(PolicyError, "BEFORE screenshot"):
                control.act({"type":"key","key":"Escape"},confirm=True,
                            expected_sha256=obs["sha256"])


if __name__=="__main__":
    unittest.main()
