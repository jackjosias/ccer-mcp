"""Rough-cut invariants and actual all-silent audio safety fixtures."""
import tempfile
import unittest
import wave
from pathlib import Path

from ccer.rhythm import cut_plan, beat_candidates, silence_map
from ccer.controls import PolicyError


class RhythmBoundsTests(unittest.TestCase):
    def test_shot_durations_cover_exact_runtime_without_overlaps(self):
        configurations = [
            (8.0, 2.0, .5, 4.0),
            (5.0, 3.0, 2.0, 4.0),
            (2.5, .5, .25, 1.2),
            (3.0, .75, .2, 2.0),
            (9.0, 2.0, 1.0, 4.0),
            (2.0, 2.0, .5, 4.0),
        ]
        for duration, target, minimum, maximum in configurations:
            with self.subTest(duration=duration, target=target):
                result = cut_plan(duration=duration, target_shot=target,
                                  min_shot=minimum, max_shot=maximum)
                self.assertAlmostEqual(sum(s["duration"] for s in result["shots"]),
                                       duration, delta=.005)
                self.assertTrue(all(minimum - .003 <= s["duration"] <= maximum + .003
                                    for s in result["shots"]))
                self.assertEqual(result["shots"][-1]["end"], duration)

    def test_all_silent_audio_is_not_mislabeled_as_music(self):
        with tempfile.TemporaryDirectory() as folder:
            wav_file = Path(folder) / "silence.wav"
            with wave.open(str(wav_file), "wb") as f:
                f.setnchannels(1)
                f.setsampwidth(2)
                f.setframerate(8000)
                f.writeframes(b"\x00\x00" * 16000)
            silence = silence_map(wav_file, seconds=2, min_silence=.2)
            beat = beat_candidates(wav_file, seconds=2)
            self.assertFalse(silence["activeRegions"])
            self.assertEqual(beat["onsetsSeconds"], [])
            self.assertIsNone(beat["estimatedBpm"])

    def test_reject_unbounded_audio_analysis(self):
        with self.assertRaises(PolicyError):
            cut_plan(duration=1801)
        with self.assertRaises(PolicyError):
            cut_plan(duration=4, onsets=[float("inf")])
