"""CCER's human desktop isolation must be fail-closed."""
import os
import tempfile
import unittest
from pathlib import Path

from ccer.controls import PolicyError
from ccer.focus_isolation import require_private_input


class FocusIsolationTests(unittest.TestCase):
    def test_unconfigured_human_display_is_refused(self):
        for env in ({}, {"DISPLAY": ":1"}, {"DISPLAY": ":1",
                    "CCER_PRIVATE_DISPLAY": ":1", "CCER_HUMAN_DISPLAY": ":1"}):
            with self.subTest(env=env):
                with self.assertRaisesRegex(PolicyError, "FOCUS_ISOLATION_REQUIRED"):
                    require_private_input(env=env)

    def test_invalid_virtual_server_identity_is_refused(self):
        with tempfile.TemporaryDirectory() as root:
            auth = Path(root) / "Xauthority"
            auth.write_bytes(b"test-cookie")
            os.chmod(auth, 0o600)
            env = {"DISPLAY": ":96", "CCER_PRIVATE_DISPLAY": ":96",
                   "CCER_HUMAN_DISPLAY": ":1",
                   "CCER_PRIVATE_XAUTHORITY": str(auth),
                   "CCER_PRIVATE_XVFB_PID": "99999"}
            with self.assertRaisesRegex(PolicyError, "attested Xvfb"):
                require_private_input(env=env, cmdline=b"/usr/bin/Xorg\0:96\0-auth\0" +
                                      str(auth).encode() + b"\0-nolisten\0tcp\0")
            with self.assertRaisesRegex(PolicyError, "attested Xvfb"):
                require_private_input(env=env, cmdline=b"/usr/bin/Xvfb\0:95\0-auth\0" +
                                      str(auth).encode() + b"\0-nolisten\0tcp\0")
            auth.chmod(0o644)
            with self.assertRaisesRegex(PolicyError, "not safely owned"):
                require_private_input(env=env, cmdline=b"/usr/bin/Xvfb\0:96\0")

    def test_missing_pid_or_xauthority_fails_closed(self):
        env = {"DISPLAY": ":96", "CCER_PRIVATE_DISPLAY": ":96",
               "CCER_HUMAN_DISPLAY": ":1"}
        with self.assertRaisesRegex(PolicyError, "identity and authority"):
            require_private_input(env=env)
