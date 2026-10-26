"""Regression tests for authentic timecoded MCP images and read-only policy."""
import base64
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ccer.controls import PolicyError
from ccer.direct_gateway import DirectGateway
from ccer.server import Gateway
from ccer.timecoded_review import review


class _NoBackend:
    def tools(self):
        return []


class TimecodedReviewTests(unittest.TestCase):
    def test_direct_mcp_surfaces_actual_frames_without_base64_in_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "sample.mp4"
            source.write_bytes(b"dummy")
            frame = {"timeSeconds": 0.5, "mimeType": "image/jpeg",
                     "imageBase64": base64.b64encode(b"\xff\xd8test\xff\xd9").decode()}
            data = {"file": str(source), "durationSeconds": 1.,
                    "frameCount": 1, "frames": [frame],
                    "requiresEditorialJudgment": True}
            with patch("ccer.timecoded_review.review", return_value=data):
                g = DirectGateway(_NoBackend(), folder, access="observe")
                result = g.invoke("ccer_timecoded_review", {"file": str(source)})
            self.assertFalse(result["isError"])
            self.assertEqual("image", result["content"][2]["type"])
            self.assertEqual(frame["imageBase64"], result["content"][2]["data"])
            self.assertEqual([{"timeSeconds": .5, "mimeType": "image/jpeg"}],
                             result["structuredContent"]["frames"])
            self.assertNotIn("imageBase64", str(result["structuredContent"]))

    def test_root_policy_never_opens_unapproved_media(self):
        with tempfile.TemporaryDirectory() as base:
            approved = Path(base) / "approved"
            approved.mkdir()
            outside = Path(base) / "private.mp4"
            outside.write_bytes(b"unapproved")
            gateway = Gateway(_NoBackend(), approved)
            with self.assertRaises(PolicyError):
                gateway.invoke("ccer_timecoded_review", {"file": str(outside)})

    def test_input_bounds_before_expensive_analysis(self):
        with self.assertRaises(PolicyError):
            review("/not-present.mp4", frame_count=9)
        with self.assertRaises(PolicyError):
            review("/not-present.mp4", seconds=float("nan"))
        with self.assertRaises(PolicyError):
            review("/not-present.mp4", frame_count=True)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                         "FFmpeg and FFprobe are required")
    def test_real_decoded_video_frames_have_matching_timecodes(self):
        with tempfile.TemporaryDirectory() as base:
            path = Path(base) / "fixture.mp4"
            proc = subprocess.run(
                ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                 "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=12",
                 "-t", "2", "-c:v", "mpeg4", "-q:v", "6", str(path)],
                capture_output=True, timeout=40)
            self.assertEqual(0, proc.returncode, proc.stderr.decode(errors="replace"))
            result = review(path, start_seconds=.25, seconds=1.5, frame_count=3)
            self.assertEqual(3, result["frameCount"])
            self.assertFalse(result["audioPresent"])
            self.assertFalse(result["speechTranscriptionAvailable"])
            self.assertTrue(result["requiresEditorialJudgment"])
            self.assertEqual(3, len(result["frames"]))
            for row in result["frames"]:
                image = base64.b64decode(row["imageBase64"], validate=True)
                self.assertTrue(image.startswith(b"\xff\xd8"))
                self.assertTrue(.25 <= row["timeSeconds"] <= 1.75)
            self.assertTrue(result["colorMetrics"]["YAVG"]["mean"] >= 0)


if __name__ == "__main__":
    unittest.main()
