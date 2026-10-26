"""Visible Concat integration: real desktop detection and non-intrusive gating."""
import base64
import json
import os
import tempfile
import time
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import MagicMock, patch

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

    def test_delayed_slint_action_is_observed_but_never_repeated(self):
        with tempfile.TemporaryDirectory() as folder:
            where = Path(folder)
            (where / "before-abcdef012345.json").write_text(json.dumps({
                "pid": 733454, "sha256": "before", "observedAt": time.time()}))
            first = MagicMock()
            first.__enter__.return_value.observe.return_value = {"sha256": "before"}
            first.__enter__.return_value.act.side_effect = PolicyError(
                "INAPP_DENIED: native adapter rejected: CCER: UI timeout")
            second = MagicMock()
            second.__enter__.return_value.observe.return_value = {
                "sha256": "after", "imageBase64": base64.b64encode(b"jpeg evidence").decode()}
            with (patch.object(desktop, "EVIDENCE", where),
                  patch.object(desktop, "_file_state", return_value={"pid": 733454}),
                  patch.object(desktop, "_client", side_effect=[first, second]) as factory):
                result = desktop.act(SimpleNamespace(
                    confirm=True, receipt="abcdef012345", type="click", x=200, y=250))
            self.assertEqual("UNKNOWN_DISPATCH", result["state"])
            self.assertTrue(result["uiChanged"])
            self.assertFalse((where / "before-abcdef012345.json").exists())
            self.assertTrue((where / "after-abcdef012345.jpg").exists())
            first.__enter__.return_value.act.assert_called_once()
            second.__enter__.return_value.act.assert_not_called()
            self.assertEqual(2, factory.call_count)



    def test_observe_reports_native_window_size_not_resized_preview(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            client = MagicMock()
            active = client.__enter__.return_value
            active._width, active._height = 1400, 900
            active.observe.return_value = {
                "windowId": "concat-main", "frameNo": 1, "sha256": "a" * 64,
                "imageBase64": "unused",
            }
            with (patch.object(desktop, "EVIDENCE", root),
                  patch.object(desktop, "_file_state", return_value={"pid": 700}),
                  patch.object(desktop, "_client", return_value=client),
                  patch.object(desktop, "_write_image", return_value="evidence.jpg"),
                  patch.object(desktop.secrets, "token_hex", return_value="abcdef012345")):
                receipt = desktop.observe()
            self.assertEqual(1400, receipt["nativeWidth"])
            self.assertEqual(900, receipt["nativeHeight"])
            disk = json.loads((root / "before-abcdef012345.json").read_text())
            self.assertEqual(1400, disk["nativeWidth"])
            self.assertEqual(900, disk["nativeHeight"])

    def test_native_launch_scope_restores_verified_media_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            allowed = root / "Videos"
            allowed.mkdir()
            data = (b"UNRELATED_SECRET=[REDACTED]" +
                    ("CCER_INAPP_MEDIA_ROOT=" + str(allowed)).encode() + b"\x00")
            with (patch.object(desktop, "HOME", root),
                  patch.object(desktop, "_live", return_value=True),
                  patch.object(desktop.Path, "read_bytes", return_value=(
                      ("CCER_INAPP_MEDIA_ROOT=" + str(allowed)).encode() + bytes([0]))),
                  patch.dict(os.environ, {}, clear=True)):
                with desktop._native_launch_scope({"pid": 12345}, "file_drop"):
                    self.assertEqual(str(allowed), os.environ["CCER_INAPP_MEDIA_ROOT"])
                    self.assertNotIn("UNRELATED_SECRET", os.environ)
                self.assertNotIn("CCER_INAPP_MEDIA_ROOT", os.environ)

    def test_native_launch_scope_rejects_missing_or_different_permission(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            allowed = root / "Videos"
            allowed.mkdir()
            data = ("CCER_INAPP_MEDIA_ROOT=" + str(allowed)).encode() + b"\x00"
            with (patch.object(desktop, "HOME", root),
                  patch.object(desktop, "_live", return_value=True),
                  patch.object(desktop.Path, "read_bytes", return_value=data)):
                with patch.dict(os.environ, {"CCER_INAPP_MEDIA_ROOT": str(root)}):
                    with self.assertRaisesRegex(PolicyError, "differs"):
                        with desktop._native_launch_scope({"pid": 12345}, "file_drop"):
                            pass
                with patch.object(desktop.Path, "read_bytes", return_value=b""):
                    with self.assertRaisesRegex(PolicyError, "permission unavailable"):
                        with desktop._native_launch_scope({"pid": 12345}, "file_drop"):
                            pass

    def test_native_route_rejects_tampered_visible_state(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(desktop, "_file_state", side_effect=PolicyError("unsafe state")):
                with self.assertRaisesRegex(PolicyError, "unsafe state"):
                    native_desktop.enabled()


if __name__ == "__main__":
    unittest.main()
