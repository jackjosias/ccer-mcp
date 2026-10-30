"""Idempotent single-visible-Concat reconciliation and no-data-loss guards."""
from contextlib import nullcontext
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from ccer import desktop_reconcile as subject
from ccer import visible_desktop as desktop
from ccer.controls import PolicyError


class DesktopReconcileTests(unittest.TestCase):
    WINDOW = {"windowId": "0x03a00005", "pid": 10485, "title": "Concat"}
    NATIVE = {"windowId": "0x04400005", "pid": 101086, "title": "Concat"}

    def test_existing_authenticated_native_is_reused_without_spawning(self):
        live = {"pid": 101086, "version": 1}
        client = MagicMock()
        client.__enter__.return_value.observe.return_value = {"frameNo": 7}
        with patch.object(subject, "_lock", return_value=nullcontext()), \
             patch.object(desktop, "_desktop", return_value=":1"), \
             patch.object(desktop, "_file_state", return_value=live), \
             patch.object(desktop, "_live", return_value=True), \
             patch.object(desktop, "_windows", return_value=[self.NATIVE]), \
             patch.object(desktop, "_client", return_value=client), \
             patch.object(desktop, "_launch_unlocked") as spawn, \
             patch.object(subject, "_close_official") as closer:
            first = subject.reconcile(Path("/fake"), Path("/fake"))
            again = subject.reconcile(Path("/fake"), Path("/fake"))
        self.assertEqual("ATTACHED", first["state"])
        self.assertEqual(first, again)
        self.assertEqual(7, first["nativeFrame"])
        self.assertTrue(first["inputReady"])
        self.assertFalse(first["headless"])
        spawn.assert_not_called()
        closer.assert_not_called()

    def test_official_unpatched_without_confirmation_is_untouched(self):
        with patch.object(subject, "_lock", return_value=nullcontext()), \
             patch.object(desktop, "_desktop", return_value=":1"), \
             patch.object(desktop, "_file_state", return_value={"pid": 1}), \
             patch.object(desktop, "_live", return_value=False), \
             patch.object(desktop, "_windows", return_value=[self.WINDOW]), \
             patch.object(subject, "_close_official") as closer, \
             patch.object(desktop, "_launch_unlocked") as spawn:
            result = subject.reconcile(Path("/fake"), Path("/fake"))
        self.assertEqual("REPLACEMENT_REQUIRES_CONFIRMATION", result["state"])
        self.assertFalse(result["inputReady"])
        closer.assert_not_called()
        spawn.assert_not_called()

    def test_confirmed_official_closes_once_then_launches_visible_native(self):
        launched = {"launched": True, "pid": 20202, "nativeFrame": 1}
        with patch.object(subject, "_lock", return_value=nullcontext()), \
             patch.object(desktop, "_desktop", return_value=":1"), \
             patch.object(desktop, "_file_state", return_value=None), \
             patch.object(desktop, "_live", return_value=False), \
             patch.object(desktop, "_windows", side_effect=[[self.WINDOW], []]), \
             patch.object(subject, "_verified_official", return_value=10485) as validate, \
             patch.object(desktop, "_verify_launch_resources", return_value={}) as ready, \
             patch.object(subject, "_close_official") as close, \
             patch.object(desktop, "_launch_unlocked", return_value=launched) as spawn:
            result = subject.reconcile(Path("/Videos"), Path("/Videos"),
                                       confirmed=True, replace_unpatched=True)
        self.assertEqual("LAUNCHED_AND_ATTACHED", result["state"])
        self.assertFalse(result["headless"])
        self.assertFalse(result["physicalPointerUsed"])
        validate.assert_called_once_with(self.WINDOW)
        ready.assert_called_once_with()
        close.assert_called_once_with(self.WINDOW)
        spawn.assert_called_once_with(Path("/Videos"), Path("/Videos"))

    def test_insufficient_resources_refuse_before_closing_existing_app(self):
        with patch.object(subject, "_lock", return_value=nullcontext()), \
             patch.object(desktop, "_desktop", return_value=":1"), \
             patch.object(desktop, "_file_state", return_value=None), \
             patch.object(desktop, "_live", return_value=False), \
             patch.object(desktop, "_windows", return_value=[self.WINDOW]), \
             patch.object(subject, "_verified_official", return_value=10485), \
             patch.object(desktop, "_verify_launch_resources",
                          side_effect=PolicyError("resources insufficient")), \
             patch.object(subject, "_close_official") as close:
            with self.assertRaisesRegex(PolicyError, "insufficient"):
                subject.reconcile(Path("/x"), Path("/x"),
                                  confirmed=True, replace_unpatched=True)
        close.assert_not_called()

    def test_multiple_verified_standard_windows_closed_before_single_launch(self):
        second = {"windowId": "0x03a00006", "pid": 10486, "title": "Concat"}
        windows = [self.WINDOW, second]
        with patch.object(subject, "_lock", return_value=nullcontext()), \
             patch.object(desktop, "_desktop", return_value=":1"), \
             patch.object(desktop, "_file_state", return_value=None), \
             patch.object(desktop, "_live", return_value=False), \
             patch.object(desktop, "_windows", side_effect=[windows, []]), \
             patch.object(subject, "_verified_official") as attest, \
             patch.object(desktop, "_verify_launch_resources", return_value={}), \
             patch.object(subject, "_close_official") as close, \
             patch.object(desktop, "_launch_unlocked",
                          return_value={"launched": True}) as launch:
            result = subject.reconcile(Path("/x"), Path("/x"),
                                       confirmed=True, replace_unpatched=True)
        self.assertEqual("LAUNCHED_AND_ATTACHED", result["state"])
        self.assertEqual(2, attest.call_count)
        self.assertEqual([self.WINDOW, second], [c.args[0] for c in close.call_args_list])
        launch.assert_called_once_with(Path("/x"), Path("/x"))

    def test_ambiguous_window_aborts_without_close_or_launch(self):
        with patch.object(subject, "_lock", return_value=nullcontext()), \
             patch.object(desktop, "_desktop", return_value=":1"), \
             patch.object(desktop, "_file_state", return_value=None), \
             patch.object(desktop, "_live", return_value=False), \
             patch.object(desktop, "_windows", return_value=[self.WINDOW]), \
             patch.object(subject, "_verified_official",
                          side_effect=PolicyError("not official")), \
             patch.object(subject, "_close_official") as close, \
             patch.object(desktop, "_launch_unlocked") as launch:
            with self.assertRaisesRegex(PolicyError, "official"):
                subject.reconcile(Path("/x"), Path("/x"),
                                  confirmed=True, replace_unpatched=True)
        close.assert_not_called()
        launch.assert_not_called()

    def test_native_window_mismatch_fails_without_removal(self):
        with patch.object(subject, "_lock", return_value=nullcontext()), \
             patch.object(desktop, "_desktop", return_value=":1"), \
             patch.object(desktop, "_file_state", return_value={"pid": 101086}), \
             patch.object(desktop, "_live", return_value=True), \
             patch.object(desktop, "_windows", return_value=[self.WINDOW]), \
             patch.object(subject, "_close_official") as close:
            with self.assertRaisesRegex(PolicyError, "mismatch"):
                subject.reconcile(Path("/x"), Path("/x"),
                                  confirmed=True, replace_unpatched=True)
        close.assert_not_called()

    def test_nonempty_project_title_must_never_be_force_replaced(self):
        with self.assertRaisesRegex(PolicyError, "active project"):
            subject._verified_official(dict(self.WINDOW, title="My project - Concat"))

    def test_closing_a_window_never_sends_kill_and_refuses_stuck_dialog(self):
        with patch.object(subject, "_verified_official", return_value=10485), \
             patch.object(desktop, "_windows", return_value=[self.WINDOW]), \
             patch.object(desktop, "_run", return_value="") as command, \
             patch.object(subject.time, "monotonic", side_effect=[0, 12.1]), \
             patch.object(subject.time, "sleep") as sleeper:
            with self.assertRaisesRegex(PolicyError, "no force termination"):
                subject._close_official(self.WINDOW)
        command.assert_called_once_with(["wmctrl", "-ic", "0x03a00005"], timeout=6)
        sleeper.assert_not_called()

    def test_cross_process_lock_rejects_reentry(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            directory.chmod(0o700)
            with patch.object(desktop, "ROOT", directory):
                with subject._lock():
                    with self.assertRaisesRegex(PolicyError, "already in progress"):
                        with subject._lock():
                            pass
                with subject._lock():
                    pass


if __name__ == "__main__":
    unittest.main()
