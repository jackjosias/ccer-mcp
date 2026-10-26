"""Checks user-annotated, read-only, timecoded evidence returned by CCER."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ccer.controls import PolicyError
from ccer.direct_gateway import DirectGateway
from ccer.timecoded_review import review_annotation
from tests.test_timecoded_review import _NoBackend


class EditorialNoteTests(unittest.TestCase):
    def test_real_video_at_exact_requested_timecode_without_jpeg_cache(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "sample.mp4"
            generation = subprocess.run(
                ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                 "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=10",
                 "-t", "3", "-c:v", "mpeg4", "-q:v", "8", str(source)],
                capture_output=True, timeout=35)
            self.assertEqual(0, generation.returncode,
                             generation.stderr.decode(errors="replace"))
            reply = DirectGateway(_NoBackend(), root).invoke(
                "ccer_editorial_note_review", {
                    "file": str(source), "timeSeconds": 1.25,
                    "note": "Cadrage insuffisant à 00:01.25",
                    "contextSeconds": 2, "frameCount": 3})
            summary = reply["structuredContent"]
            self.assertFalse(reply["isError"])
            self.assertEqual(1.25, summary["annotation"]["focusFrameTimeSeconds"])
            self.assertEqual("user_supplied", summary["annotation"]["provenance"])
            self.assertFalse(summary["annotation"]["verified"])
            self.assertFalse(summary["annotationPersisted"])
            self.assertTrue(summary["readOnly"])
            self.assertEqual(3, summary["frameCount"])
            self.assertEqual(3, sum(c["type"] == "image" for c in reply["content"]))
            self.assertNotIn("imageBase64", str(summary))
            self.assertEqual([], list(Path(root).rglob("*.jpg")))

    def test_invalid_note_and_timecode_fail_closed(self):
        for options in ({"note": " "}, {"note": "x" * 1201},
                        {"note": "review", "time_seconds": float("nan")},
                        {"note": "review", "frame_count": True}):
            with self.subTest(options=options), self.assertRaises(PolicyError):
                review_annotation("/no/media", **{"time_seconds": 1, **options})
        with patch("ccer.timecoded_review.media_probe", return_value={
            "format": {"duration": "4"},
            "streams": [{"codec_type": "video"}]}):
            with self.assertRaises(PolicyError):
                review_annotation("/no/media", time_seconds=4, note="End")

    def test_does_not_read_files_outside_approved_root(self):
        with tempfile.TemporaryDirectory() as root:
            approved = Path(root) / "allowed"
            approved.mkdir()
            external = Path(root) / "outside.mp4"
            external.write_bytes(b"fixture")
            with self.assertRaises(PolicyError):
                DirectGateway(_NoBackend(), approved).invoke(
                    "ccer_editorial_note_review", {
                        "file": str(external), "timeSeconds": 1,
                        "note": "Needs review"})


if __name__ == "__main__":
    unittest.main()
