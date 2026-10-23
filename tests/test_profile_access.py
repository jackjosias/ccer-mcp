import stat
import tempfile
import unittest
from pathlib import Path

from ccer.controls import PolicyError
from ccer.profile_access import switch_profile


class CcerDirectProfileAccessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "ccer-direct.yaml"
        self.launcher = str(Path(__file__).resolve().parents[1] / "ccer_direct_stdio.py")
        self.secret = '[REDACTED] "do-not-print-or-replace"'
        self.original = (
            'control_plane:\n  ' + self.secret +
            '\nmcp:\n  - name: ccer\n    command: "/usr/bin/python3 ' +
            self.launcher + ' --access observe"\n'
        )
        self.path.write_text(self.original, encoding="utf-8")
        self.path.chmod(0o600)

    def test_dry_run_does_not_write(self):
        result = switch_profile(self.path, access="control")
        self.assertTrue(result["changed"])
        self.assertFalse(result["applied"])
        self.assertEqual(self.path.read_text(), self.original)

    def test_atomic_promotion_preserves_key_permissions_and_is_idempotent(self):
        before_mode = stat.S_IMODE(self.path.stat().st_mode)
        first = switch_profile(self.path, access="control", apply=True)
        self.assertTrue(first["applied"])
        updated = self.path.read_text()
        self.assertIn("--access control", updated)
        self.assertIn(self.secret, updated)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), before_mode)
        again = switch_profile(self.path, access="control", apply=True)
        self.assertFalse(again["changed"])
        self.assertFalse(again["applied"])
        self.assertEqual(self.path.read_text(), updated)

    def test_wrong_launcher_and_symlink_are_refused(self):
        self.path.write_text('mcp:\n  command: "python3 /path/wcer_direct_stdio.py --access observe"\n')
        with self.assertRaises(PolicyError):
            switch_profile(self.path, apply=True)
        with tempfile.TemporaryDirectory() as other:
            link = Path(other) / "ccer-direct.yaml"
            link.symlink_to(self.path)
            with self.assertRaises(PolicyError):
                switch_profile(link, apply=True)

    def test_multiple_commands_and_bad_modes_are_refused(self):
        with self.assertRaises(PolicyError):
            switch_profile(self.path, access="superuser", apply=True)
        self.path.write_text(self.original + self.original)
        with self.assertRaises(PolicyError):
            switch_profile(self.path, access="control", apply=True)
