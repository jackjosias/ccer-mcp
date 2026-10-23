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

    @patch("ccer.desktop_gui._window", return_value=WINDOW)
    def test_drag_coordinates_are_bounded_before_input(self, win):
        with self.assertRaises(PolicyError):
            interact(expected_window_id="0x3a00005", action="drag",
                     confirm_action=True, x=50, y=60,
                     target_x=1500, target_y=100, duration=.7)
        with self.assertRaises(PolicyError):
            interact(expected_window_id="0x3a00005", action="drag",
                     confirm_action=True, x=50, y=60,
                     target_x=70, target_y=100, duration=20)
        win.assert_called()

    @patch("ccer.desktop_gui.time.sleep")
    @patch("ccer.desktop_gui._run")
    @patch("ccer.desktop_gui._window", return_value=WINDOW)
    def test_drag_produces_actual_stepwise_pointer_motion(self, win, run, sleep):
        def reply(argv, **kwargs):
            return "60817413" if argv[:2] == ["xdotool", "getactivewindow"] else ""
        run.side_effect = reply
        result = interact(expected_window_id="0x3a00005", action="drag",
                          confirm_action=True, x=25, y=50,
                          target_x=125, target_y=150, duration=.6,
                          with_capture=False)
        calls = [c.args[0] for c in run.call_args_list]
        self.assertTrue(any(x[:2] == ["xdotool", "mousedown"] for x in calls))
        self.assertTrue(any(x[:2] == ["xdotool", "mouseup"] for x in calls))
        self.assertGreaterEqual(sum(x[:2] == ["xdotool", "mousemove"] for x in calls), 10)
        self.assertTrue(result["actionSent"])

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
