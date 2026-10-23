"""Desktop bridge policy and MCP image-content integration tests (no physical input)."""
import tempfile
import unittest
from unittest.mock import patch

from ccer.controls import PolicyError
from ccer.desktop_gui import interact, capture
from ccer.server import Gateway


WINDOW = {"windowId": "0x3a00005", "pid": 10486, "title": "Concat",
          "width": 1400, "height": 900, "display": ":1"}


class FakeUpstream:
    def tools(self):
        return []


class DesktopGuiTests(unittest.TestCase):
    def test_action_requires_explicit_confirmation(self):
        with self.assertRaises(PolicyError):
            interact(expected_window_id="0x3a00005",
                     action="click", confirm_action=False, x=200, y=200)

    @patch("ccer.desktop_gui._window", return_value=WINDOW)
    def test_stale_window_and_coordinate_bound_fail_closed(self, window):
        with self.assertRaises(PolicyError):
            interact(expected_window_id="0x3a00006", action="click",
                     confirm_action=True, x=200, y=200)
        with self.assertRaises(PolicyError):
            interact(expected_window_id="0x3a00005", action="click",
                     confirm_action=True, x=1400, y=200)
        with self.assertRaises(PolicyError):
            interact(expected_window_id="0x3a00005", action="key",
                     confirm_action=True, key="ctrl+alt+Delete")
        with self.assertRaises(PolicyError):
            interact(expected_window_id="0x3a00005", action="type",
                     confirm_action=True, text="a\nenter")
        window.assert_called()

    @patch("ccer.desktop_gui._run", return_value=b"\xff\xd8testjpeg")
    @patch("ccer.desktop_gui._window", return_value=WINDOW)
    def test_bad_capture_is_refused(self, window, run):
        with self.assertRaises(PolicyError):
            capture(max_width=640)

    def test_gateway_returns_real_mcp_image_block_and_no_base64_in_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            gateway = Gateway(FakeUpstream(), d)
            image_result = {"window": WINDOW, "imageBase64": "aGVsbG8=",
                            "mimeType": "image/jpeg", "sha256": "abc"}
            with patch.object(gateway.production, "run", return_value=image_result):
                output = gateway.invoke("ccer_desktop_capture", {})
            self.assertEqual(output["content"][1]["type"], "image")
            self.assertEqual(output["content"][1]["data"], "aGVsbG8=")
            self.assertNotIn("imageBase64", output["structuredContent"])
