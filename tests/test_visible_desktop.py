"""Visible Concat integration: real desktop detection and non-intrusive gating."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ccer import visible_desktop as desktop
from ccer import native_desktop
from ccer.controls import PolicyError


class VisibleDesktopTests(unittest.TestCase):
    SAMPLE = ("0x05200005  0 635319 .concat jack-josias-lnx Concat\n"
              "0x0400000b  0 15482 antigravity.Antigravity jack-josias-lnx ccer-mcp - Antigravity\n")

    def test_real_open_appimage_is_identified(self):
        with patch.object(desktop, "_run", return_value=self.SAMPLE):
            self.assertEqual(
                [{"windowId": "0x05200005", "pid": 635319, "title": "Concat"}],
                desktop._windows())

    def test_concat_class_remains_detected_with_project_title(self):
        title = "0x05200005  0 635319 .concat host My project - Concat\n"
        with patch.object(desktop, "_run", return_value=title):
            self.assertEqual(1, len(desktop._windows()))

    def test_non_concat_windows_not_targeted(self):
        text = "0x05200005 0 635319 browser.Browser host Concat\n"
        with patch.object(desktop, "_run", return_value=text):
            self.assertEqual([], desktop._windows())

    def test_official_open_refuses_parallel_launch(self):
        with patch.dict(os.environ, {"DISPLAY": ":1", "XDG_SESSION_TYPE": "x11"}, clear=False):
            with patch.object(desktop, "_windows", return_value=[
                    {"windowId": "0x05200005", "pid": 635319, "title": "Concat"}]):
                with patch.object(desktop.subprocess, "Popen") as spawn:
                    with self.assertRaisesRegex(PolicyError, "Concat already open"):
                        desktop.launch(desktop.HOME / "Videos", desktop.HOME / "Videos")
                    spawn.assert_not_called()

    def test_non_x11_fails_closed(self):
        with patch.dict(os.environ, {"DISPLAY": ":0", "XDG_SESSION_TYPE": "wayland"}):
            with self.assertRaisesRegex(PolicyError, "not X11"):
                desktop._desktop()

    def test_act_without_explicit_approval_fails_before_io(self):
        with patch.object(desktop, "_file_state", side_effect=AssertionError("should not read")):
            with self.assertRaisesRegex(PolicyError, "requires --confirm"):
                desktop.act(SimpleNamespace(confirm=False))

    def test_native_route_attaches_to_existing_patched_visible_app(self):
        native_desktop._close()
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(native_desktop, "_visible_config",
                              return_value=("/private/desktop.sock", "proof-value", 635319)):
                with patch.object(native_desktop, "InAppComputerUse") as factory:
                    self.assertTrue(native_desktop.enabled())
                    native_desktop._session()
                    factory.assert_called_once_with("/private/desktop.sock", "proof-value",
                                                    expected_pid=635319)
        native_desktop._close()

    def test_native_route_rejects_tampered_visible_state(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(desktop, "_file_state", side_effect=PolicyError("unsafe state")):
                with self.assertRaisesRegex(PolicyError, "unsafe state"):
                    native_desktop.enabled()


if __name__ == "__main__":
    unittest.main()
