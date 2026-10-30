"""End-to-end stdio protocol qualification without starting or touching Concat GUI."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class DirectStdioOfflineTests(unittest.TestCase):
    def test_mcp_stays_online_offline_and_rejects_headless_writes(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            absent = root / "nonexistent-Concat.AppImage"
            requests = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                 "params": {"protocolVersion": "2025-06-18"}},
                {"jsonrpc": "2.0", "id": 2, "method": "ping"},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
                {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                 "params": {"name": "edit_apply", "arguments": {}}},
                {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                 "params": {"name": "ccer_editorial_note_review",
                            "arguments": {"file": str(root / "absent.mp4"),
                                          "timeSeconds": 2, "note": "Review"}}}
            ]
            completed = subprocess.run(
                [sys.executable, str(repo / "ccer_direct_stdio.py"),
                 "--concat-bin", str(absent), "--root", temp,
                 "--mode", "window", "--access", "observe"],
                input="".join(json.dumps(item) + "\n" for item in requests),
                text=True, capture_output=True, timeout=20, cwd=repo)
            self.assertEqual(0, completed.returncode, completed.stderr[-450:])
            replies = [json.loads(line) for line in completed.stdout.splitlines()]
            self.assertEqual([1, 2, 3, 4, 5], [item["id"] for item in replies])
            self.assertEqual("ccer-mcp", replies[0]["result"]["serverInfo"]["name"])
            self.assertEqual("2025-06-18", replies[0]["result"]["protocolVersion"])
            self.assertEqual({}, replies[1]["result"])
            names = {item["name"] for item in replies[2]["result"]["tools"]}
            self.assertIn("ccer_editorial_note_review", names)
            self.assertIn("ccer_long_review_plan", names)
            self.assertIn("ccer_desktop_status", names)
            self.assertNotIn("edit_apply", names)
            self.assertNotIn("ccer_desktop_act", names)
            for response in replies[3:]:
                self.assertTrue(response["result"]["isError"])
            self.assertIn("VISUAL-ONLY", replies[3]["result"]["content"][0]["text"])
            self.assertFalse(absent.exists())
            self.assertFalse(list(root.rglob("*.jpg")))


if __name__ == "__main__":
    unittest.main()
