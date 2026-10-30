"""Test the production chain with an in-memory Concat stub."""
import tempfile
import unittest
from pathlib import Path

from ccer.production import Production
from ccer.controls import PolicyError


class FakeConcat:
    def __init__(self):
        self.calls = []
        self.assets = 0
        self.clips = []

    def tool(self, name, args=None, timeout=None):
        self.calls.append(name)
        if name == "project_create":
            dest = Path(args["location"]) / args["name"]
            dest.mkdir()
            (dest / "concat.json").write_text("{}")
        if name == "media_import":
            self.assets += 1
            return {"structuredContent": {"createdId": f"m{self.assets}"}}
        if name == "clips_add_sequence":
            for key in args["mediaIds"]:
                self.clips.append({"id": key, "trackId": "video",
                                   "start": len(self.clips), "duration": 1})
        if name == "title_add":
            self.clips.append({"id": "title", "trackId": "titles",
                               "start": args["start"], "duration": args["duration"]})
        if name == "timeline_read":
            return {"structuredContent": {"timeline": {"clips": self.clips}}}
        return {"structuredContent": {"ok": True}}


class RecipeTests(unittest.TestCase):
    def test_prepare_project_with_deduplicated_sources_and_caption(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            media = root / "source.mp4"
            media.write_bytes(b"fake media stub")
            engine = Production(FakeConcat(), root)
            result = engine.run("ccer_produce", {
                "name": "Demo One", "profile": "shorts",
                "shots": [str(media), str(media)],
                "captions": [{"start": 0, "duration": 1.0, "text": "Bonjour"}],
                "export": False})
            self.assertEqual(result["shots"], 2)
            self.assertFalse(result["exported"])
            self.assertEqual(engine.upstream.assets, 1)
            self.assertEqual(result["timelineQA"]["clipCount"], 3)
            self.assertTrue(engine.journal.verify()["valid"])

    def test_invalid_name_and_escape_fail_before_project_creation(self):
        with tempfile.TemporaryDirectory() as td:
            engine = Production(FakeConcat(), Path(td))
            with self.assertRaises(PolicyError):
                engine.run("ccer_produce", {"name": "../bad", "shots": ["x"]})
            with self.assertRaises(PolicyError):
                engine.run("ccer_produce", {"name": "okay", "shots": ["/etc/passwd"]})
            self.assertNotIn("project_create", engine.upstream.calls)
