"""Long-video offset regression: samples and findings must refer to one window."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from ccer.controls import PolicyError
from ccer.temporal_seek import start_args, absolute
from ccer.timecoded_review import review
from ccer.quality import visual_scan
from ccer.rhythm import silence_map
from ccer.visual_edit import color_report


class TemporalWindowTests(unittest.TestCase):
    def test_invalid_offsets_fail_closed(self):
        for bad in (True, -1, float("nan"), float("inf"), 86401, "20"):
            with self.subTest(bad=bad):
                with self.assertRaises(PolicyError):
                    start_args(bad)
        self.assertEqual((["-ss", "4.250000"], 4.25), start_args(4.25))
        self.assertEqual(4.375, absolute(.125, 4.25))

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                         "FFmpeg/FFprobe unavailable")
    def test_later_window_does_not_report_early_black_and_silence(self):
        with tempfile.TemporaryDirectory() as directory:
            media = Path(directory) / "two-regions.mp4"
            command = [
                "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "color=c=black:s=320x180:r=12:d=3",
                "-f", "lavfi", "-i", "testsrc2=s=320x180:r=12:d=3",
                "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono:d=3",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=3",
                "-filter_complex",
                "[0:v][1:v]concat=n=2:v=1:a=0[v];[2:a][3:a]concat=n=2:v=0:a=1[a]",
                "-map", "[v]", "-map", "[a]",
                "-c:v", "mpeg4", "-q:v", "5", "-c:a", "aac",
                "-y", str(media)]
            proc = subprocess.run(command, capture_output=True, timeout=45)
            self.assertEqual(proc.returncode, 0, proc.stderr.decode(errors="replace")[-700:])
            early = review(media, start_seconds=0, seconds=2, frame_count=2)
            late = review(media, start_seconds=4, seconds=2, frame_count=2)
            self.assertTrue(any(x["kind"] == "black_interval" for x in early["findings"]))
            self.assertFalse(any(x["kind"] == "black_interval" for x in late["findings"]))
            self.assertTrue(early["audioSilences"])
            self.assertFalse(late["audioSilences"])
            self.assertTrue(all(4 <= f["timeSeconds"] <= 6 for f in late["frames"]))
            self.assertGreater(late["colorMetrics"]["YAVG"]["mean"],
                               early["colorMetrics"]["YAVG"]["mean"] + 20)
            late_video = visual_scan(media, seconds=2, start_seconds=4)
            late_audio = silence_map(media, seconds=2, start_seconds=4)
            late_color = color_report(media, seconds=2, interval=.5, start_seconds=4)
            self.assertEqual(4.0, late_video["startSeconds"])
            self.assertEqual(4.0, late_audio["startSeconds"])
            self.assertEqual(4.0, late_color["startSeconds"])
            with self.assertRaises(PolicyError):
                color_report(media, start_seconds=300)


if __name__ == "__main__":
    unittest.main()
