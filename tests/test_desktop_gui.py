"""Desktop bridge policy and MCP image-content integration tests (no physical input)."""
import tempfile
import unittest
from unittest.mock import patch

from ccer.controls import PolicyError
from ccer.desktop_gui import interact, capture, _media_import_dialog
from ccer.server import Gateway


WINDOW = {"windowId": "0x3a00005", "pid": 10486, "title": "Concat",
          "width": 1400, "height": 900, "display": ":1"}


class FakeUpstream:
    def tools(self):
        return []


class DesktopGuiTests(unittest.TestCase):
    def setUp(self):
        # These mock the legacy private-Xvfb transport. An actual visible Concat
        # must never be selected by the test runner just because it is running.
        isolated = patch("ccer.desktop_gui.native_desktop.enabled", return_value=False)
        isolated.start()
        self.addCleanup(isolated.stop)

    def test_private_native_timeout_does_not_capture_human_desktop(self):
        with patch("ccer.desktop_gui.native_desktop.enabled", return_value=True), \
             patch("ccer.desktop_gui.native_desktop.capture", side_effect=PolicyError("CCER: UI timeout")), \
             patch.dict("os.environ", {"CCER_PRIVATE_DISPLAY": ":94"}), \
             patch("ccer.readonly_window.capture") as human_capture:
            with self.assertRaisesRegex(PolicyError, "UI timeout"):
                capture(max_width=640)
            human_capture.assert_not_called()

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

    @patch("ccer.desktop_gui._run", return_value=bytes((255, 216)) + b"x" * 260 + bytes((255, 217)))
    @patch("ccer.desktop_gui._window", return_value=WINDOW)
    def test_real_desktop_screenshot_is_observation_only(self, window, run):
        result = capture(max_width=640)
        self.assertTrue(result["readOnly"])
        self.assertFalse(result["safeForClickReceipt"])
        self.assertEqual("verified_x11_observation_only", result["captureSource"])
        self.assertEqual(WINDOW["windowId"], result["window"]["windowId"])
        self.assertEqual(["ffmpeg"], [c.args[0][0] for c in run.call_args_list])

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

    @patch("ccer.desktop_gui.require_private_input")
    @patch("ccer.desktop_gui.time.sleep")
    @patch("ccer.desktop_gui._run")
    @patch("ccer.desktop_gui._window", return_value=WINDOW)
    def test_drag_produces_actual_stepwise_pointer_motion(self, win, run, sleep, isolated):
        def reply(argv, **kwargs):
            return "60817413" if argv[:2] == ["xdotool", "getwindowfocus"] else ""
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

    @patch("ccer.desktop_gui.require_private_input")
    @patch("ccer.desktop_gui._run")
    @patch("ccer.desktop_gui._window", return_value=WINDOW)
    def test_private_display_uses_only_scoped_focus(self, win, run, isolated):
        def reply(argv, **kwargs):
            if argv[:2] == ["xdotool", "getwindowfocus"]:
                return "60817413"
            return ""
        run.side_effect = reply
        result = interact(expected_window_id="0x3a00005", action="key",
                          confirm_action=True, key="Escape", with_capture=False)
        self.assertTrue(result["actionSent"])
        self.assertTrue(any(x.args[0][:2] == ["xdotool", "windowfocus"]
                            for x in run.call_args_list))
        self.assertFalse(any(x.args[0][:2] == ["xdotool", "windowactivate"]
                             for x in run.call_args_list))

    @patch("ccer.desktop_gui.require_private_input")
    @patch("ccer.desktop_gui._run")
    @patch("ccer.desktop_gui._window", return_value=WINDOW)
    def test_private_focus_refuses_other_window(self, win, run, isolated):
        def reply(argv, **kwargs):
            if argv[:2] == ["xdotool", "getwindowfocus"]:
                return "2000"   # Different window
            return ""
        run.side_effect = reply
        with self.assertRaisesRegex(PolicyError, "not the focused window"):
            interact(expected_window_id="0x3a00005", action="click",
                     confirm_action=True, x=100, y=100, with_capture=False)
        self.assertFalse(any(x.args[0][:2] == ["xdotool", "click"]
                             for x in run.call_args_list))

    @patch("ccer.desktop_gui._run")
    @patch("ccer.desktop_gui._window", return_value=WINDOW)
    def test_human_desktop_gui_input_denied_before_any_xdotool(self, window, commands):
        with self.assertRaisesRegex(PolicyError, "FOCUS_ISOLATION_REQUIRED"):
            interact(expected_window_id="0x3a00005", action="key",
                     confirm_action=True, key="Escape", with_capture=False)
        commands.assert_not_called()

    @patch("ccer.desktop_gui._run")
    def test_verified_media_import_dialog_can_be_selected(self, run):
        def reply(argv, **kwargs):
            if argv[:2] == ["wmctrl", "-lx"]:
                return ("0x0320160b 0 "
                        "xdg-desktop-portal-gtk.Xdg-desktop-portal-gtk "
                        "host Importer des médias")
            if argv[:2] == ["xprop", "-id"]:
                return ('WM_CLASS(STRING) = "xdg-desktop-portal-gtk", '
                        '"Xdg-desktop-portal-gtk"\\n'
                        'WM_NAME(STRING) = "Importer des médias"\\n'
                        '_NET_WM_WINDOW_TYPE(ATOM) = _NET_WM_WINDOW_TYPE_DIALOG\\n'
                        '_NET_WM_PID(CARDINAL) = 7545')
            if argv[:3] == ["ps", "-p", "7545"]:
                return "/usr/libexec/xdg-desktop-portal-gtk"
            if argv[:2] == ["xwininfo", "-id"]:
                return "  Width: 1460" + chr(10) + "  Height: 765" + chr(10) + "  Map State: IsViewable"
            raise AssertionError(f"Unexpected command: {argv}")
        run.side_effect = reply
        dialog = _media_import_dialog(WINDOW)
        self.assertEqual(dialog["windowId"], "0x0320160b")
        self.assertEqual(dialog["role"], "concat_media_import_dialog")
        self.assertEqual(dialog["parentConcatWindowId"], WINDOW["windowId"])

    @patch("ccer.desktop_gui._run")
    def test_unrelated_gtk_dialog_is_not_controllable(self, run):
        run.return_value = ("0x0320160b 0 "
                            "xdg-desktop-portal-gtk.Xdg-desktop-portal-gtk "
                            "host Ouvrir les secrets")
        self.assertIsNone(_media_import_dialog(WINDOW))

    @patch("ccer.desktop_gui._run")
    def test_mismatched_media_dialog_identity_fails_closed(self, run):
        run.return_value = ("0x0320160b 0 firefox.Firefox "
                            "host Importer des médias")
        with self.assertRaises(PolicyError):
            _media_import_dialog(WINDOW)

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
