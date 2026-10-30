import io
import json
import tempfile
import unittest
from pathlib import Path

from ccer.controls import Journal, PolicyError, inside
from ccer.production import Production, TOOLS
from ccer.server import Gateway


class FakeConcat:
    def __init__(self):
        self.clips = []
        self.calls = []

    def tools(self):
        return [{"name": "concat_version", "inputSchema": {"type": "object"}},
                {"name": "project_create", "inputSchema": {"type": "object"}},
                {"name": "timeline_read", "inputSchema": {"type": "object"}},
                {"name": "edit_apply", "inputSchema": {"type": "object"}},
                {"name": "project_get", "inputSchema": {"type": "object"}},
                {"name": "project_save", "inputSchema": {"type": "object"}}]

    def tool(self, name, args=None, timeout=None):
        self.calls.append((name, args))
        if name == "concat_version":
            data = {"concat": "0.2.8", "mcp": {"mode": "window"}}
        elif name == "timeline_read":
            data = {"timeline": {"clips": list(self.clips)}}
        elif name == "project_get":
            data = {"project": {"name": "demo"}}
        elif name == "edit_apply":
            commands = args["command"]["commands"]
            for item in commands:
                if item["op"] == "fakeAdd":
                    self.clips.append({"id": "c" + str(len(self.clips)),
                        "trackId": "v1", "start": len(self.clips),
                        "duration": 1})
            data = {"applied": True}
        else:
            data = {"ok": True}
        return {"structuredContent": data, "isError": False}


class ControlsTests(unittest.TestCase):
    def test_root_policy_blocks_escape(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.assertEqual(inside(root, str(root / "good")), root / "good")
            with self.assertRaises(PolicyError):
                inside(root, str(root / "../outside"))

    def test_audit_chain_detects_tampering(self):
        with tempfile.TemporaryDirectory() as td:
            j = Journal(td)
            j.append("first", {"x": 1})
            j.append("second", {"x": 2})
            self.assertTrue(j.verify()["valid"])
            lines = j.path.read_text().splitlines()
            value = json.loads(lines[0])
            value["data"]["x"] = 123
            lines[0] = json.dumps(value)
            j.path.write_text("\n".join(lines) + "\n")
            self.assertFalse(j.verify()["valid"])

    def test_tools_and_preflight(self):
        with tempfile.TemporaryDirectory() as td:
            g = Gateway(FakeConcat(), td)
            self.assertTrue({"ccer_transcript_read", "ccer_av_timeline"}.issubset(TOOLS))
            self.assertEqual(len(g.catalogue), len(TOOLS) + len(g.native))
            answer = g.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-06-18"}})
            self.assertEqual(answer["result"]["serverInfo"]["name"], "ccer-mcp")
            preflight = g.invoke("ccer_preflight", {})["structuredContent"]
            self.assertEqual(preflight["concat"]["concat"], "0.2.8")
            self.assertEqual(preflight["asr"]["engine"], "Concat embedded whisper.cpp")
            self.assertFalse(preflight["asr"]["transcriptionPerformed"])
            output = io.StringIO()
            g.serve(io.StringIO('{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n'), output)
            self.assertEqual(len(json.loads(output.getvalue())["result"]["tools"]), len(g.catalogue))

    def test_batch_and_timeline(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "Demo"
            p.mkdir()
            g = Gateway(FakeConcat(), td)
            result = g.invoke("ccer_batch_edit", {"path": str(p),
                "commands": [{"op": "fakeAdd"}, {"op": "fakeAdd"}],
                "expectedClipDelta": 2, "save": True})["structuredContent"]
            self.assertTrue(result["verified"])
            self.assertTrue(result["saved"])
            self.assertEqual(result["clipDelta"], 2)
            timeline = g.invoke("ccer_timeline_validate", {"path": str(p)})["structuredContent"]
            self.assertEqual(timeline["clipCount"], 2)
            self.assertTrue(timeline["valid"])
            self.assertEqual(len(list((Path(td) / ".ccer/missions").glob("*.json"))), 1)

    def test_restore_requires_confirmation(self):
        with tempfile.TemporaryDirectory() as td:
            g = Gateway(FakeConcat(), td)
            with self.assertRaises(PolicyError):
                g.production.run("ccer_checkpoint_restore", {
                    "checkpointId": "a" * 32, "confirm": False})

    def test_checkpoint_protects_existing_project(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            project = root / "project"
            project.mkdir()
            (project / "concat.json").write_text('{"cut":1}')
            engine = Production(FakeConcat(), root)
            snap = engine.run("ccer_checkpoint_create", {"path": str(project)})
            (project / "concat.json").write_text('{"cut":2}')
            (project / "concat.lock").write_text("busy")
            with self.assertRaises(PolicyError):
                engine.run("ccer_checkpoint_restore", {"checkpointId": snap["id"], "confirm": True})
            (project / "concat.lock").unlink()
            result = engine.run("ccer_checkpoint_restore", {
                "checkpointId": snap["id"], "confirm": True})
            self.assertEqual((project / "concat.json").read_text(), '{"cut":1}')
            self.assertTrue(Path(result["backup"]).exists())


if __name__ == "__main__":
    unittest.main()
