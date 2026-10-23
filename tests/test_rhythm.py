import unittest

from ccer.controls import PolicyError
from ccer.rhythm import cut_plan, subtitle_timing_hint, silence_map, beat_candidates


class RhythmTests(unittest.TestCase):
    def test_cut_points_observe_bounds_and_do_not_mutate(self):
        report = cut_plan(duration=8, onsets=[.5, 2, 4, 6, 8], target_shot=2)
        self.assertEqual(report["cutPointsSeconds"], [2.,4.,6.])
        self.assertEqual(len(report["shots"]), 4)
        self.assertFalse(report["mutated"])
        self.assertTrue(all(.5 <= shot["duration"] <= 4 for shot in report["shots"]))
        with self.assertRaises(PolicyError):
            cut_plan(duration=8, onsets=[float("nan")])
        with self.assertRaises(PolicyError):
            cut_plan(duration=8, min_shot=3, target_shot=2)
        with self.assertRaises(PolicyError):
            cut_plan(duration=1800, target_shot=.5, max_shot=.5, max_cuts=1)

    def test_subtitles_estimate_not_forced_alignment(self):
        report = {"activeRegions": [{"start": .2, "end": 1.4}, {"start": 2, "end": 3.6}]}
        estimates = subtitle_timing_hint(
            [{"text": "Hello world"}, {"text": "This is the second phrase"}],report)
        self.assertFalse(estimates["forcedAligned"])
        self.assertEqual(len(estimates["cues"]), 2)
        self.assertTrue(estimates["captionQA"]["passed"])
        self.assertAlmostEqual(estimates["cues"][0]["start"],.2,places=2)
        self.assertAlmostEqual(sum(1 for _ in estimates["cues"]),2)

    def test_refuse_invalid_and_missing_media(self):
        with self.assertRaises(PolicyError):
            subtitle_timing_hint([{"text":"Hello"}], {"activeRegions":[]})
        with self.assertRaises(PolicyError):
            subtitle_timing_hint([{"text":"Hello"}], {"activeRegions":[{"start":1,"end":0}]})
        with self.assertRaises(PolicyError):
            silence_map("/tmp/missing_ccer_media.wav")
        with self.assertRaises(PolicyError):
            beat_candidates("/tmp/missing_ccer_media.wav")
