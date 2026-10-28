"""Replay cursor semantics and in-memory backpressure, no GUI mutation."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ccer.controls import PolicyError
from ccer.av_replay_poll import replay_poll


class AVReplayPollTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.media = self.root / "test.mp4"
        self.media.write_bytes(b"nondecoded fixture")
        self.meta = {"streams": [{"codec_type": "video"}],
                     "format": {"duration": "8.0"}}

    def test_pause_with_backpressure_never_decodes_or_skips_cursor(self):
        with patch("ccer.av_replay_poll.media_probe", return_value=self.meta), \
             patch("ccer.av_replay_poll.inspect_event_window") as decode:
            result = replay_poll(self.root, self.media, consumer_ready=False)
        decode.assert_not_called()
        self.assertTrue(result["paused"])
        self.assertEqual(0, result["nextCursor"])
        self.assertEqual([], result["events"])

    def test_critical_pressure_adapts_to_one_frame(self):
        fake = {"tier": "critical", "loadPerCpu": 7,
                "memAvailableBytes": 1700000000}
        response = {"events": [{"kind": "frame_sample", "timeSeconds": 1}],
                    "nextCursor": None, "totalEvents": 1,
                    "transcriptSource": "none", "timelineOffsetSeconds": 0}
        with patch("ccer.av_replay_poll.media_probe", return_value=self.meta), \
             patch("ccer.av_replay_poll._pressure", return_value=fake), \
             patch("ccer.av_replay_poll.inspect_event_window",
                   return_value=response) as reviewer:
            a = replay_poll(self.root, self.media, cursor=0, frame_count=4)
            b = replay_poll(self.root, self.media, cursor=a["nextCursor"],
                            frame_count=4)
        self.assertEqual(1, a["decodedFrames"])
        self.assertEqual(1, reviewer.call_args.kwargs["frame_count"])
        self.assertEqual(1, a["nextCursor"])
        self.assertIsNone(b["nextCursor"])
        self.assertTrue(b["complete"])
        self.assertFalse(a["liveStreamActive"])

    def test_replay_latency_is_measured_not_claimed_live(self):
        report = {"events": [], "nextCursor": None, "totalEvents": 0,
                  "transcriptSource": "none", "timelineOffsetSeconds": 0}
        with patch("ccer.av_replay_poll.media_probe", return_value=self.meta), \
             patch("ccer.av_replay_poll._pressure",
                   return_value={"tier": "normal"}), \
             patch("ccer.av_replay_poll.inspect_event_window", return_value=report), \
             patch("ccer.av_replay_poll.time.perf_counter", side_effect=[20.0, 20.25]):
            measured = replay_poll(self.root, self.media, window_seconds=2)
        self.assertEqual(250, measured["observationLatencyMs"])
        self.assertEqual(8, measured["processingRealTimeFactor"])
        self.assertEqual("local_steady_clock_elapsed_per_poll_not_end_to_end_stream",
                         measured["latencyMeasurement"])
        self.assertFalse(measured["liveStreamActive"])

    def test_no_silent_truncation_or_unsafe_root(self):
        response = {"events": [], "nextCursor": 2, "totalEvents": 101}
        with patch("ccer.av_replay_poll.media_probe", return_value=self.meta), \
             patch("ccer.av_replay_poll.inspect_event_window",
                   return_value=response):
            with self.assertRaisesRegex(PolicyError, "overflow"):
                replay_poll(self.root, self.media)
        with tempfile.TemporaryDirectory() as private:
            foreign = Path(private) / "private.mp4"
            foreign.write_bytes(b"test")
            with self.assertRaises(PolicyError):
                replay_poll(self.root, foreign)

    def test_type_and_cursor_limits_fail_closed(self):
        for kwargs in ({"cursor": -1}, {"cursor": True},
                       {"cursor": 4}, {"window_seconds": 0.1},
                       {"frame_count": 9}, {"max_events": 101},
                       {"consumer_ready": 1},
                       {"timeline_offset_seconds": float("nan")},
                       {"include_frames": 1}):
            with self.subTest(kwargs=kwargs), \
                 patch("ccer.av_replay_poll.media_probe", return_value=self.meta):
                with self.assertRaises(PolicyError):
                    replay_poll(self.root, self.media, **kwargs)

    def test_completed_cursor_never_decodes_again(self):
        with patch("ccer.av_replay_poll.media_probe", return_value=self.meta), \
             patch("ccer.av_replay_poll.inspect_event_window") as reviewer:
            result = replay_poll(self.root, self.media, cursor=2)
        reviewer.assert_not_called()
        self.assertTrue(result["complete"])
        self.assertIsNone(result["nextCursor"])


    def test_real_ffmpeg_pull_through_readonly_mcp(self):
        import shutil
        import subprocess
        from ccer.direct_gateway import DirectGateway
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            self.skipTest("FFmpeg binaries unavailable")
        class Backend:
            def tools(self):
                return []
        video = self.root / "real-replay.mp4"
        command = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                   "-f", "lavfi", "-i", "testsrc2=size=120x68:rate=10",
                   "-f", "lavfi", "-i", "sine=frequency=300:sample_rate=16000",
                   "-t", "3", "-c:v", "mpeg4", "-q:v", "10",
                   "-c:a", "aac", str(video)]
        made = subprocess.run(command, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=50)
        self.assertEqual(0, made.returncode, made.stderr.decode(errors="replace"))
        gateway = DirectGateway(Backend(), self.root)
        self.assertIn("ccer_av_replay_poll",
                      {tool["name"] for tool in gateway.catalogue})
        first = gateway.invoke("ccer_av_replay_poll",
                               {"file": str(video), "windowSeconds": 2,
                                "frameCount": 2})
        self.assertFalse(first["isError"])
        item = first["structuredContent"]
        self.assertEqual("recorded_pull_replay", item["mode"])
        self.assertEqual(1, item["nextCursor"])
        self.assertTrue(item["processed"])
        self.assertTrue(item["events"])
        self.assertGreaterEqual(item["observationLatencyMs"], 0)
        self.assertEqual("local_steady_clock_elapsed_per_poll_not_end_to_end_stream",
                         item["latencyMeasurement"])
        self.assertFalse(any(part["type"] == "image"
                             for part in first["content"]))
        # Same FFmpeg decode as the events, now exposed as real MCP JPEG parts.
        with_frames = gateway.invoke("ccer_av_replay_poll",
                                     {"file": str(video), "windowSeconds": 2,
                                      "frameCount": 2, "includeFrames": True})
        import base64
        image_parts = [part for part in with_frames["content"]
                       if part["type"] == "image"]
        self.assertTrue(image_parts)
        self.assertLessEqual(len(image_parts), 2)
        self.assertTrue(all(base64.b64decode(part["data"]).startswith(bytes((0xFF, 0xD8)))
                            for part in image_parts))
        self.assertNotIn("imageBase64", str(with_frames["structuredContent"]))
        self.assertEqual(len(image_parts), len(with_frames["structuredContent"]["frames"]))
        paused = gateway.invoke("ccer_av_replay_poll",
                                {"file": str(video), "windowSeconds": 2,
                                 "cursor": 1, "consumerReady": False,
                                 "includeFrames": True})
        self.assertEqual(1, paused["structuredContent"]["nextCursor"])
        self.assertFalse(paused["structuredContent"]["processed"])
        self.assertFalse(any(part["type"] == "image" for part in paused["content"]))
        self.assertEqual([], list(self.root.glob("*.jpg")))

if __name__ == "__main__":
    unittest.main()
