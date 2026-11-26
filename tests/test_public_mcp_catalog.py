"""Verify the public catalogue and the actual offline discovery policy."""
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PublicMcpCatalogueTests(unittest.TestCase):
    def test_catalogue_is_current(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "docs/render_mcp_catalog.py"), "--check"],
            cwd=ROOT, capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_profiles_and_schemas(self):
        data = json.loads((ROOT / "docs/mcp-tools.json").read_text(encoding="utf-8"))
        profiles = {key: set(value) for key, value in data["profiles"].items()}
        tools = data["tools"]
        names = [tool["name"] for tool in tools]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(set(names), profiles["standard"])
        self.assertEqual(profiles["directControl"] - profiles["directObserve"],
                         {"ccer_desktop_act"})
        self.assertTrue(profiles["directObserve"] < profiles["directControl"])
        self.assertTrue(profiles["directControl"] <= profiles["standard"])
        for name in ("ccer_checkpoint_restore", "ccer_batch_edit", "ccer_produce"):
            self.assertNotIn(name, profiles["directControl"])
        for profile, names_in_profile in profiles.items():
            self.assertEqual(data["counts"][profile], len(names_in_profile))
        for tool in tools:
            with self.subTest(tool=tool["name"]):
                self.assertTrue(tool["description"])
                self.assertEqual(tool["inputSchema"]["type"], "object")
                self.assertTrue(set(tool["inputSchema"].get("required", []))
                                <= set(tool["inputSchema"].get("properties", {})))


if __name__ == "__main__":
    unittest.main()
