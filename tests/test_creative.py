import tempfile
import unittest
from pathlib import Path

from ccer.controls import PolicyError
from ccer.creative import plan, storyboard, to_srt, save


class CreativeTests(unittest.TestCase):
    def setUp(self):
        self.brief = {"topic": "Innovation", "script": "Bienvenue dans le futur. Voici la technologie.",
                      "profile": "shorts", "durationSeconds": 12, "assets": ["a.mp4", "b.mp4"]}

    def test_storyboard_plan_deterministic(self):
        x = plan(self.brief)
        self.assertEqual(x, plan(self.brief))
        self.assertEqual(len(x["scenes"]), 2)
        self.assertTrue(x["productionReady"])
        self.assertTrue(x["captionQA"]["passed"])
        self.assertEqual(len(storyboard(x)["panels"]), 2)

    def test_guard_and_srt(self):
        with self.assertRaises(PolicyError):
            plan({"topic": "No script"})
        with self.assertRaises(PolicyError):
            plan({**self.brief, "durationSeconds": 2})
        srt = to_srt(plan(self.brief)["captions"])
        self.assertIn("-->", srt)
        with tempfile.TemporaryDirectory() as root:
            file = str(Path(root) / "captions.srt")
            self.assertTrue(save(root, file, srt)["bytes"] > 0)
            with self.assertRaises(PolicyError):
                save(root, file, srt)
            with self.assertRaises(PolicyError):
                save(root, "/etc/captions.srt", srt)
