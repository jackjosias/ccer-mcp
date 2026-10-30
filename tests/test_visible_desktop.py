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

    def test_status_explains_memory_block_without_spawning(self):
        with (patch.object(desktop, "_file_state", return_value=None),
              patch.object(desktop, "_windows", return_value=[]),
              patch.object(desktop, "_desktop", return_value=":1"),
              patch("ccer.asr_readiness.status", return_value={
                  "memoryAvailableBytes": 500_000_000,
                  "loadPerLogicalCpu": 0.2}),
              patch.object(desktop.subprocess, "Popen") as spawn):
            state = desktop.status()
            self.assertFalse(state["nativeBridge"])
            self.assertFalse(state["launchReady"])
            self.assertIn("overloaded", state["launchBlocker"])
            self.assertIn("blocked", state["next"])
            spawn.assert_not_called()

    def test_status_allows_only_single_new_launch_if_safe(self):
        with (patch.object(desktop, "_file_state", return_value=None),
              patch.object(desktop, "_windows", return_value=[]),
              patch.object(desktop, "_desktop", return_value=":1"),
              patch("ccer.asr_readiness.status", return_value={
                  "memoryAvailableBytes": 6 * 1024**3,
                  "loadPerLogicalCpu": 0.3})):
            state = desktop.status()
            self.assertTrue(state["launchReady"])
            self.assertIsNone(state["launchBlocker"])

    def test_overloaded_launch_is_denied_before_any_spawn(self):
        with (patch.dict(os.environ, {"DISPLAY": ":1", "XDG_SESSION_TYPE": "x11"}),
              patch.object(desktop, "_windows", return_value=[]),
              patch("ccer.asr_readiness.status", return_value={
                  "memoryAvailableBytes": 1500000000,
                  "loadPerLogicalCpu": 4.5}),
              patch.object(desktop.subprocess, "Popen") as spawn):
            with self.assertRaisesRegex(PolicyError, "overloaded"):
                desktop.launch(desktop.HOME / "Videos", desktop.HOME / "Videos")
            spawn.assert_not_called()

    def test_cpu_overload_refuses_even_if_ram_sufficient(self):
        with patch("ccer.asr_readiness.status", return_value={
                "memoryAvailableBytes": 8 * 1024**3,
                "loadPerLogicalCpu": 2.25}):
            with self.assertRaisesRegex(PolicyError, "overloaded"):
                desktop._verify_launch_resources()

    def test_explicit_cpu_override_preserves_memory_gate(self):
        with patch.dict(os.environ, {"CCER_VISIBLE_CPU_OVERRIDE": "1"}):
            with patch("ccer.asr_readiness.status", return_value={
                    "memoryAvailableBytes": 4 * 1024**3,
                    "loadPerLogicalCpu": 5.0}):
                self.assertEqual(5.0, desktop._verify_launch_resources()["loadPerLogicalCpu"])
            with patch("ccer.asr_readiness.status", return_value={
                    "memoryAvailableBytes": 500_000_000,
                    "loadPerLogicalCpu": 5.0}):
                with self.assertRaisesRegex(PolicyError, "overloaded"):
                    desktop._verify_launch_resources()

    def test_owner_opt_in_accepts_resource_pressure(self):
        with (patch.dict(os.environ, {"CCER_VISIBLE_RESOURCE_OVERRIDE": "1"}),
              patch("ccer.asr_readiness.status", return_value={
                  "memoryAvailableBytes": 350_000_000,
                  "loadPerLogicalCpu": 9.5})):
            measured = desktop._verify_launch_resources()
            self.assertEqual(350_000_000, measured["memoryAvailableBytes"])
            self.assertEqual(9.5, measured["loadPerLogicalCpu"])

    def test_owner_override_still_requires_measurements(self):
        with (patch.dict(os.environ, {"CCER_VISIBLE_RESOURCE_OVERRIDE": "1"}),
              patch("ccer.asr_readiness.status", return_value={
                  "memoryAvailableBytes": None, "loadPerLogicalCpu": None})):
            with self.assertRaisesRegex(PolicyError, "cannot be verified"):
                desktop._verify_launch_resources()

    def test_missing_resource_measurement_fails_closed(self):
        with patch("ccer.asr_readiness.status", return_value={
                "memoryAvailableBytes": None, "loadPerLogicalCpu": None}):
            with self.assertRaisesRegex(PolicyError, "cannot be verified"):
                desktop._verify_launch_resources()

    def test_safe_reading_allows_continuing_to_other_guards(self):
        with patch("ccer.asr_readiness.status", return_value={
                "memoryAvailableBytes": 4 * 1024**3,
                "loadPerLogicalCpu": 0.75}):
            value = desktop._verify_launch_resources()
            self.assertEqual(0.75, value["loadPerLogicalCpu"])

    def test_delayed_window_registration_waits_without_relaunch(self):
        found = {"windowId": "0x03c00005", "pid": 105496, "title": "Concat"}
        with (patch.object(desktop, "_windows", side_effect=[[], [], [found]]) as spy,
              patch.object(desktop.time, "sleep") as pause):
            self.assertEqual(found, desktop._wait_for_native_window(105496))
            self.assertEqual(3, spy.call_count)
            self.assertEqual(2, pause.call_count)

    def test_conflicting_window_refuses_without_killing_or_relaunching(self):
        other = {"windowId": "0x03c00006", "pid": 22222, "title": "Concat"}
        with patch.object(desktop, "_windows", return_value=[other]):
            with self.assertRaisesRegex(PolicyError, "another Concat"):
                desktop._wait_for_native_window(105496)

    def test_registration_timeout_keeps_native_process_intact(self):
        with patch.object(desktop, "_windows", return_value=[]):
            with patch.object(desktop.time, "sleep") as pause:
                with self.assertRaisesRegex(RuntimeError, "left running"):
                    desktop._wait_for_native_window(105496, timeout=0)
                pause.assert_not_called()

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

    def test_visible_bounded_text_uses_existing_slint_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            receipt = "aabbccddeeff"
            (root / ("before-" + receipt + ".json")).write_text(json.dumps({
                "pid": 700, "sha256": "before", "observedAt": time.time()}))
            native = MagicMock()
            active = native.__enter__.return_value
            active.observe.return_value = {"sha256": "before"}
            active.act.return_value = {"frameNo": 2, "imageBase64": "fixture"}
            with (patch.object(desktop, "EVIDENCE", root),
                  patch.object(desktop, "_file_state", return_value={"pid": 700}),
                  patch.object(desktop, "_client", return_value=native),
                  patch.object(desktop, "_write_image", return_value="after.jpg")):
                result = desktop.act(SimpleNamespace(
                    confirm=True, receipt=receipt, type="type_text",
                    text="CCER Démonstration"))
            active.act.assert_called_once_with(
                {"type": "type_text", "text": "CCER Démonstration"},
                confirm=True, expected_sha256="before")
            self.assertEqual("type_text", result["nativeEvent"])
            self.assertFalse((root / ("before-" + receipt + ".json")).exists())

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
        with patch.dict(os.environ, {"DISPLAY": ":1"}, clear=True):
            with patch.object(desktop, "_file_state", side_effect=PolicyError("unsafe state")):
                with self.assertRaisesRegex(PolicyError, "unsafe state"):
                    native_desktop.enabled()


if __name__ == "__main__":
    unittest.main()
