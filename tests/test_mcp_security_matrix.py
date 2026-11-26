"""Systematic negative MCP contract tests; no live Concat or user media."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ccer.direct_gateway import DirectGateway, READ_CCER
from ccer.production import TOOLS
from ccer.server import Gateway


class NoBackend:
    def tools(self):
        return []

    def tool(self, *args, **kwargs):
        raise AssertionError("Unexpected native tool execution")


class McpSecurityMatrixTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ccer-security-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "root"
        self.root.mkdir()
        self.gateway = Gateway(NoBackend(), self.root)

    def call(self, gateway, name, args):
        response = gateway.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                   "params": {"name": name, "arguments": args}})
        self.assertEqual(response["id"], 1)
        return response["result"]

    def assert_refused(self, gateway, name, args, message):
        reply = self.call(gateway, name, args)
        self.assertTrue(reply["isError"], name)
        self.assertIn(message, reply["content"][0]["text"])

    def test_every_registered_tool_rejects_unexpected_argument(self):
        # A dispatch would be a test failure, not a simulated success.
        with patch.object(self.gateway.production, "_dispatch",
                          side_effect=AssertionError("Invalid input reached dispatch")) as dispatch:
            for name in sorted(TOOLS):
                with self.subTest(tool=name):
                    self.assert_refused(self.gateway, name, {"__unexpected_ccer_test__": True},
                                        "Unexpected argument")
            dispatch.assert_not_called()

    def test_every_required_argument_is_enforced_before_dispatch(self):
        with patch.object(self.gateway.production, "_dispatch",
                          side_effect=AssertionError("Incomplete input reached dispatch")) as dispatch:
            for name, schema in sorted(TOOLS.items()):
                for missing in schema["required"]:
                    with self.subTest(tool=name, missing=missing):
                        args = {key: None for key in schema["required"] if key != missing}
                        self.assert_refused(self.gateway, name, args,
                                            "Missing required argument: " + missing)
            dispatch.assert_not_called()

    def test_every_non_permitted_tool_is_refused_in_direct_profiles(self):
        for access in ("observe", "control"):
            gateway = DirectGateway(NoBackend(), self.root, access=access)
            expected = set(READ_CCER) | ({"ccer_desktop_act"} if access == "control" else set())
            listed = {tool["name"] for tool in gateway.handle(
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]}
            self.assertEqual(listed, expected)
            with patch.object(gateway.production, "run",
                              side_effect=AssertionError("Denied call reached production")) as run:
                for name in sorted(set(TOOLS) - expected):
                    with self.subTest(access=access, tool=name):
                        self.assert_refused(gateway, name, {}, "VISUAL-ONLY")
                run.assert_not_called()

    def test_outside_root_media_and_symlink_are_rejected(self):
        outside = self.base / "outside.mp4"
        outside.write_bytes(b"synthetic sentinel")
        link = self.root / "alias.mp4"
        link.symlink_to(outside)
        for name in ("ccer_asset_analyze", "ccer_audio_validate", "ccer_export_verify",
                     "ccer_visual_scan", "ccer_timecoded_review", "ccer_color_report",
                     "ccer_scene_detect", "ccer_silence_map", "ccer_beat_candidates"):
            for path in (outside, link, self.root / ".." / outside.name):
                with self.subTest(tool=name, path=path.name):
                    reply = self.call(self.gateway, name, {"file": str(path)})
                    self.assertTrue(reply["isError"], name)
                    reason = reply["content"][0]["text"]
                    # Newer development branches may reject unattested media
                    # reads before reaching the root boundary. Do not bypass it.
                    self.assertRegex(reason, r"outside|requires attested live Concat|refuses symlinks")
        self.assertEqual(outside.read_bytes(), b"synthetic sentinel")

    def test_outside_root_plan_write_is_rejected(self):
        outside = self.base / "outside.json"
        outside.write_bytes(b"sentinel")
        link = self.root / "alias.json"
        link.symlink_to(outside)
        for path in (outside, link, self.root / ".." / outside.name):
            with self.subTest(path=path.name):
                self.assert_refused(self.gateway, "ccer_plan_save",
                                    {"file": str(path), "plan": {}}, "outside")
        self.assertEqual(outside.read_bytes(), b"sentinel")
        self.assertTrue(link.is_symlink())

    def test_audit_tool_reports_chain_tampering(self):
        journal = self.gateway.production.journal
        journal.append("synthetic.test", {"value": 1})
        good = self.call(self.gateway, "ccer_audit_report", {})
        self.assertTrue(good["structuredContent"]["valid"])
        entry = json.loads(journal.path.read_text(encoding="utf-8"))
        entry["data"]["value"] = 2
        journal.path.write_text(json.dumps(entry) + "\n", encoding="utf-8")
        bad = self.call(self.gateway, "ccer_audit_report", {})
        self.assertFalse(bad["structuredContent"]["valid"])
        self.assertEqual(bad["structuredContent"]["errorAt"], 1)


if __name__ == "__main__":
    unittest.main()
