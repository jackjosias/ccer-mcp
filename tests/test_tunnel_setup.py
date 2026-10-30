import tempfile
import unittest

from ccer.controls import PolicyError
from ccer.tunnel_setup import init_command


SYNTHETIC_ID = "tunnel_" + "a" * 32


class TunnelSetupTests(unittest.TestCase):
    def test_valid_command_contains_independent_stdio_and_no_credentials(self):
        with tempfile.TemporaryDirectory() as path:
            args = init_command(tunnel_id=SYNTHETIC_ID, access="control",
                                profile="ccer-direct", profile_dir=path)
        self.assertEqual(args[0:3], ["tunnel-client", "init", "--sample"])
        self.assertIn("--mcp-command", args)
        entry = args[args.index("--mcp-command") + 1]
        self.assertIn("ccer_direct_stdio.py", entry)
        self.assertIn("--access control", entry)
        self.assertNotIn("wcer", entry.lower())
        self.assertIn("env:CONTROL_PLANE_API_KEY", args)
        self.assertNotIn("--force", args)
        self.assertIn("127.0.0.1:0", args)

    def test_observe_is_default(self):
        args = init_command(tunnel_id=SYNTHETIC_ID)
        self.assertIn("--access observe", args[args.index("--mcp-command") + 1])

    def test_refuses_invalid_ids_and_profile_injection(self):
        with self.assertRaises(PolicyError):
            init_command(tunnel_id="tunnel_fake")
        with self.assertRaises(PolicyError):
            init_command(tunnel_id=SYNTHETIC_ID, profile="ccer;rm -rf")
        with self.assertRaises(PolicyError):
            init_command(tunnel_id=SYNTHETIC_ID, access="all")
        with self.assertRaises(PolicyError):
            init_command(tunnel_id=SYNTHETIC_ID, profile_dir="/missing/not-real-directory")
