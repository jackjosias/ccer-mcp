import unittest

from ccer.audio_studio import engines, voice, mix
from ccer.controls import PolicyError
from ccer.shot_intelligence import inspect_shots, scene_cuts, contact_sheet


class StudioTests(unittest.TestCase):
    def test_voice_gates(self):
        self.assertIn("ffmpeg", engines())
        with self.assertRaises(PolicyError):
            voice("", "/tmp/nothing.wav")
        with self.assertRaises(PolicyError):
            voice("hello", "/tmp/nothing.wav", rate=10)
        with self.assertRaises(PolicyError):
            mix("no-file", None, "/tmp/no.wav")

    def test_shot_guard(self):
        with self.assertRaises(PolicyError):
            inspect_shots([])
        with self.assertRaises(PolicyError):
            scene_cuts("missing.mp4", threshold=5)
        with self.assertRaises(PolicyError):
            contact_sheet("missing.mp4", "bad.mp4", interval=-1)
