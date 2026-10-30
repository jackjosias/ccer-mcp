"""Bounded cross-check of timed subtitles with audio/video evidence."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from ccer.controls import PolicyError
from ccer.direct_gateway import DirectGateway
from ccer.timed_caption_context import timed_caption_context
from tests.test_timecoded_review import _NoBackend


class TimedCaptionContextTests(unittest.TestCase):
    def test_real_audio_window_preserves_absolute_cue_times(self):
        with tempfile.TemporaryDirectory() as root:
            video = Path(root) / "media.mp4"
            made = subprocess.run(
                ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                 "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=10",
                 "-f", "lavfi", "-i", "sine=frequency=500:sample_rate=8000",
                 "-t", "4", "-c:v", "mpeg4", "-c:a", "aac",
                 "-y", str(video)], capture_output=True, timeout=45)
            self.assertEqual(0, made.returncode, made.stderr.decode(errors="replace"))
            cues = [
                {"start": .25, "duration": 1., "text": "Intro"},
                {"start": 2.1, "duration": .9, "text": "Bonjour"},
                {"start": 3.2, "duration": .6, "text": "Fin"},
            ]
            gateway = DirectGateway(_NoBackend(), root)
            response = gateway.invoke("ccer_timed_caption_context", {
                "file": str(video), "cues": cues, "startSeconds": 1.8,
                "seconds": 1.5, "maxCues": 4})
            result = response["structuredContent"]
            self.assertFalse(response["isError"])
            self.assertEqual(["Bonjour", "Fin"], [c["text"] for c in result["windowCues"]])
            self.assertEqual([2.1, 3.2], [c["start"] for c in result["windowCues"]])
            self.assertEqual(1.8, result["window"]["startSeconds"])
            self.assertEqual(3.3, result["window"]["endSeconds"])
            self.assertTrue(result["audioPresent"])
            self.assertTrue(result["audioAnalyzed"])
            self.assertFalse(result["transcriptionPerformed"])
            self.assertFalse(result["wordForcedAlignmentPerformed"])
            self.assertEqual("user_supplied", result["cueProvenance"])
            self.assertTrue(result["readOnly"])
            self.assertEqual([], list(Path(root).rglob("*.jpg")))

    def test_bad_caption_bounds_and_overlap_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            video = Path(root) / "video.mp4"
            video.write_bytes(b"test")
            from unittest.mock import patch
            info = {"format": {"duration": "12"}, "streams": [{"codec_type": "video"}]}
            with patch("ccer.timed_caption_context.media_probe", return_value=info):
                base = [{"start": 2, "duration": 2, "text": "Hello"}]
                for kwargs in (
                    {"start_seconds": float("nan")}, {"seconds": 200},
                    {"max_cues": True}, {"include_audio_silence": 1},
                ):
                    with self.subTest(kwargs=kwargs), self.assertRaises(PolicyError):
                        timed_caption_context(video, base, **kwargs)
                for cues in (
                    [{"start": 11, "duration": 2, "text": "late"}],
                    [{"start": 2, "duration": 1, "text": " "}],
                    [{"start": 2, "duration": float("nan"), "text": "bad"}],
                    [{"start": 2, "duration": True, "text": "bad"}],
                    [{"start": 2, "duration": 2, "text": "x"},
                     {"start": 3, "duration": 2, "text": "y"}],
                ):
                    with self.subTest(cues=cues), self.assertRaises(PolicyError):
                        timed_caption_context(video, cues)
                fine = timed_caption_context(video, base)
                self.assertFalse(fine["audioPresent"])
                self.assertFalse(fine["audioAnalyzed"])

    def test_outside_media_is_rejected_before_any_probe(self):
        with tempfile.TemporaryDirectory() as root:
            allowed = Path(root) / "allowed"
            allowed.mkdir()
            private = Path(root) / "outside.mp4"
            private.write_bytes(b"secret")
            with self.assertRaises(PolicyError):
                DirectGateway(_NoBackend(), allowed).invoke(
                    "ccer_timed_caption_context", {
                        "file": str(private), "cues": [
                            {"start": 0, "duration": 1, "text": "Private"}]})
