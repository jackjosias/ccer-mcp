"""One-hour video validation with real FFmpeg seeks and bounded RAM frames.

The generated fixture lives in TemporaryDirectory and is never user's source media.
It certifies transport/timecode mechanics, not semantic film comprehension.
"""
import base64
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from ccer.direct_gateway import DirectGateway
from tests.test_timecoded_review import _NoBackend


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                     "Real FFmpeg and FFprobe are required")
class LongFormActualSeekTests(unittest.TestCase):
    def test_one_hour_sparse_fixture_reaches_last_window_and_decodes(self):
        with tempfile.TemporaryDirectory(prefix="ccer-long-qa-") as folder:
            video = Path(folder) / "one-hour-sparse-test.mp4"
            built = subprocess.run(
                ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                 "-f", "lavfi", "-i", "testsrc2=size=120x68:rate=1",
                 "-frames:v", "3600", "-threads", "1", "-c:v", "mpeg4",
                 "-q:v", "8", "-movflags", "+faststart", str(video)],
                capture_output=True, timeout=85)
            self.assertEqual(0, built.returncode,
                             built.stderr.decode(errors="replace")[-400:])
            self.assertLess(video.stat().st_size, 20_000_000)
            gateway = DirectGateway(_NoBackend(), folder, access="observe")
            initial = gateway.invoke("ccer_long_review_plan", {
                "file": str(video), "windowSeconds": 60,
                "frameCount": 2, "cursor": 0, "pageSize": 3})
            self.assertFalse(initial["isError"])
            begin = initial["structuredContent"]
            self.assertEqual(60, begin["totalWindows"])
            self.assertEqual(3, begin["nextCursor"])
            self.assertEqual([0, 60, 120],
                             [item["startSeconds"] for item in begin["windows"]])
            final = gateway.invoke("ccer_long_review_plan", {
                "file": str(video), "windowSeconds": 60,
                "frameCount": 2, "cursor": 59, "pageSize": 2})
            self.assertFalse(final["isError"])
            finish = final["structuredContent"]
            self.assertIsNone(finish["nextCursor"])
            self.assertEqual(59, finish["windows"][0]["index"])
            self.assertEqual(3540, finish["windows"][0]["startSeconds"])
            self.assertAlmostEqual(3600, finish["windows"][0]["endSeconds"], delta=.15)
            self.assertEqual(0, finish["imageFilesCreated"])

            actual = gateway.invoke("ccer_timecoded_review", {
                "file": str(video), "startSeconds": 3594,
                "seconds": 5, "frameCount": 1})
            self.assertFalse(actual["isError"])
            summary = actual["structuredContent"]
            self.assertGreaterEqual(summary["window"]["startSeconds"], 3594)
            self.assertLessEqual(summary["window"]["endSeconds"], 3600)
            self.assertEqual(1, summary["frameCount"])
            images = [part for part in actual["content"] if part["type"] == "image"]
            self.assertEqual(1, len(images))
            self.assertTrue(base64.b64decode(images[0]["data"]).startswith(b"\xff\xd8"))
            self.assertNotIn("imageBase64", str(summary))
            self.assertFalse(list(Path(folder).rglob("*.jpg")))
            self.assertTrue(summary["requiresEditorialJudgment"])
            self.assertFalse(summary["speechTranscriptionAvailable"])


if __name__ == "__main__":
    unittest.main()
