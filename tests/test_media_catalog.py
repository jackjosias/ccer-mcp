import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ccer.controls import PolicyError
from ccer.media_catalog import build, load, query, match_storyboard


def fake_probe(path):
    return {"format": {"duration": "3.0"}, "streams": [
        {"codec_type": "video", "width": 320, "height": 180, "codec_name": "h264"}]}


class MediaCatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.red = self.root / "red.mp4"
        self.blue = self.root / "blue.mp4"
        self.red.write_bytes(b"test red")
        self.blue.write_bytes(b"test blue")
        self.catalog = str(self.root / "catalog.json")
        self.items = [
            {"file": str(self.red), "description": "Rouge eclatant", "tags": ["rouge", "eclatant"]},
            {"file": str(self.blue), "description": "Bleu profond", "tags": ["bleu", "profond"]},
        ]

    @patch("ccer.media_catalog.media_probe", side_effect=fake_probe)
    def test_catalog_query_provenance_and_no_overwrite(self, _):
        report = build(self.root, self.items, self.catalog)
        self.assertEqual(report["indexedCount"], 2)
        self.assertIsNone(report["semanticModel"])
        found = query(self.root, self.catalog, "rouge éclatant")
        self.assertEqual(found["totalMatches"], 1)
        self.assertEqual(found["matches"][0]["file"], str(self.red))
        self.assertEqual(found["matches"][0]["provenance"]["semantics"], "user_annotation")
        self.assertEqual(query(self.root, self.catalog, "avion")["totalMatches"], 0)
        with self.assertRaises(PolicyError):
            build(self.root, self.items, self.catalog)
        self.red.write_bytes(b"changed red")
        with self.assertRaises(PolicyError):
            query(self.root, self.catalog, "rouge")

    @patch("ccer.media_catalog.media_probe", side_effect=fake_probe)
    def test_match_plan_and_missing_evidence(self, _):
        build(self.root, self.items, self.catalog)
        plan = {"scenes": [{"visualIntent": "Rouge éclatant", "duration": 2},
                           {"visualIntent": "Bleu profond", "duration": 2}]}
        match = match_storyboard(self.root, self.catalog, plan, allow_reuse=False)
        self.assertTrue(match["ready"])
        self.assertEqual([p["source"] for p in match["plan"]["scenes"]],
                         [str(self.red), str(self.blue)])
        self.assertNotIn("source", plan["scenes"][0])
        plan["scenes"][1]["visualIntent"] = "avion"
        rejected = match_storyboard(self.root, self.catalog, plan)
        self.assertFalse(rejected["ready"])
        self.assertEqual(len(rejected["missing"]), 1)

    @patch("ccer.media_catalog.media_probe", side_effect=fake_probe)
    @patch("ccer.media_catalog.scene_cuts", return_value={"cutsSeconds": [1.0, 2.0]})
    def test_scene_segments_and_root_sandbox(self, scenes, probe):
        result = build(self.root, self.items[:1], self.catalog, detect_scenes=True)
        self.assertEqual(result["indexedCount"], 3)
        self.assertEqual([s["mediaStart"] for s in load(self.root, self.catalog)["items"]],
                         [0.0, 1.0, 2.0])
        with self.assertRaises(PolicyError):
            query(self.root, "/etc/passwd", "rouge")
        with self.assertRaises(PolicyError):
            build(self.root, [{"file": "/etc/passwd"}], str(self.root / "no.json"))
