import tempfile
import unittest
from pathlib import Path
from ccer.controls import PolicyError
from ccer.quality import captions_check, visual_scan, FORMATS


class QualityTests(unittest.TestCase):
    def test_captions_warn_and_detect_overlap(self):
        report = captions_check([
            {"start": 0, "duration": 1, "text": "A" * 70},
            {"start": 0.8, "duration": 1, "text": "Bienvenue"}])
        self.assertFalse(report["passed"])
        self.assertTrue(any(i["issue"] == "overlap" for i in report["issues"]))
        self.assertTrue(any(i["issue"] == "high_reading_speed" for i in report["issues"]))

    def test_valid_captions(self):
        report = captions_check([{"start": 0, "duration": 2.0, "text": "Bonjour"},
                                 {"start": 2.1, "duration": 2.0, "text": "Bienvenue"}])
        self.assertTrue(report["passed"])
        self.assertFalse(report["issues"])

    def test_invalid_inputs(self):
        invalid = captions_check([{"start": -3, "duration": 1, "text": "bad"},
                                  {"start": 0, "duration": 0, "text": "bad"}])
        self.assertFalse(invalid["passed"])
        self.assertEqual(len(invalid["issues"]), 2)
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(PolicyError):
                visual_scan(Path(td) / "missing.mp4")
        self.assertEqual(FORMATS["square-preview"], (320, 320))
