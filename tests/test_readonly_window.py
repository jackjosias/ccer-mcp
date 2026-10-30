"""No physical X11 input and no file artifacts in native screenshot fallback."""
import unittest
from unittest.mock import patch

from ccer import desktop_gui, readonly_window, visible_desktop
from ccer.controls import PolicyError


WIN = [{"windowId":"0x03600005", "pid":598971, "title":"Concat"}]
STATE = {"pid":598971}
JPEG = b"\xff\xd8\xff" + b"q" * 200 + b"\xff\xd9"


def fake_run(argv, **kwargs):
    if argv[0] == "xprop":
        return ('WM_CLASS(STRING) = "", "concat"\n'
                '_NET_WM_PID(CARDINAL) = 598971\n'
                'WM_NAME(STRING) = "Concat"\n')
    if argv[0] == "xwininfo":
        return "Width: 1400\nHeight: 900\nMap State: IsViewable\n"
    if argv[0] == "ffmpeg":
        return JPEG
    raise AssertionError("No other applications or X11 input accepted: " + str(argv))


class ReadOnlyNativeFallbackTests(unittest.TestCase):
    def setUp(self):
        patches = [
            patch.object(visible_desktop, "_desktop", return_value=":1"),
            patch.object(visible_desktop, "_file_state", return_value=STATE),
            patch.object(visible_desktop, "_live", return_value=True),
            patch.object(visible_desktop, "_windows", return_value=WIN),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def test_exact_window_image_no_files_and_no_pointer(self):
        with patch.object(desktop_gui, "_run", side_effect=fake_run) as commands:
            result = readonly_window.capture(max_width=840)
        self.assertTrue(result["readOnly"])
        self.assertFalse(result["safeForClickReceipt"])
        self.assertEqual("verified_x11_read_only", result["captureSource"])
        self.assertEqual(840, result["imageWidth"])
        self.assertEqual(598971, result["window"]["pid"])
        self.assertTrue(result["imageBase64"].startswith("/9j/"))
        self.assertEqual(["xprop", "xwininfo", "ffmpeg"],
                         [c.args[0][0] for c in commands.call_args_list])

    def test_other_window_and_other_process_refused_before_capture(self):
        for windows in ([], [{"windowId":"0x05","pid":2}], WIN + WIN):
            with self.subTest(windows=windows):
                with patch.object(visible_desktop, "_windows", return_value=windows):
                    with patch.object(desktop_gui, "_run") as run:
                        with self.assertRaises(PolicyError):
                            readonly_window.capture()
                        run.assert_not_called()

    def test_tampered_x11_process_identity_fails_closed(self):
        with patch.object(desktop_gui, "_run", return_value=(
                'WM_CLASS(STRING) = "", "concat"\n'
                '_NET_WM_PID(CARDINAL) = 1234\n'
                'WM_NAME(STRING) = "Concat"\n')) as run:
            with self.assertRaisesRegex(PolicyError, "identity mismatch"):
                readonly_window.capture()
            self.assertEqual(1, run.call_count)

    def test_status_exposes_readonly_after_native_timeout_without_input(self):
        with patch.object(desktop_gui.native_desktop, "enabled", return_value=True), \
             patch.object(desktop_gui.native_desktop, "status",
                          side_effect=PolicyError("CCER: UI timeout")), \
             patch.object(readonly_window, "capture",
                          return_value={"window": {"windowId": "0x03600005",
                                                   "pid": 598971}}) as fallback:
            status = desktop_gui.status()
        self.assertFalse(status["inputReady"])
        self.assertFalse(status["safeForClickReceipt"])
        self.assertEqual("slint_ui_timeout", status["nativeStatus"])
        self.assertEqual("0x03600005", status["window"]["windowId"])
        fallback.assert_called_once_with(max_width=320)

    def test_status_does_not_fallback_on_authentication_failure(self):
        with patch.object(desktop_gui.native_desktop, "enabled", return_value=True), \
             patch.object(desktop_gui.native_desktop, "status",
                          side_effect=PolicyError("bad credential")), \
             patch.object(readonly_window, "capture") as fallback:
            with self.assertRaisesRegex(PolicyError, "credential"):
                desktop_gui.status()
            fallback.assert_not_called()

    def test_only_native_timeout_falls_back_to_read_only(self):
        with patch.object(desktop_gui.native_desktop, "enabled", return_value=True):
            with patch.object(desktop_gui.native_desktop, "capture",
                              side_effect=PolicyError("CCER: UI timeout")):
                with patch.object(readonly_window, "capture",
                                  return_value={"readOnly":True}) as fallback:
                    result = desktop_gui.capture(max_width=640)
                    self.assertEqual({"readOnly":True}, result)
                    fallback.assert_called_once_with(max_width=640)
            with patch.object(desktop_gui.native_desktop, "capture",
                              side_effect=PolicyError("bad credential")):
                with patch.object(readonly_window, "capture") as fallback:
                    with self.assertRaisesRegex(PolicyError, "credential"):
                        desktop_gui.capture(max_width=640)
                    fallback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
