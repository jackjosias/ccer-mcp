"""Event pages preserve source times, provenance, safety and bounded memory."""
import unittest
from ccer.av_event_cursor import event_page
from ccer.controls import PolicyError

class EventCursorTests(unittest.TestCase):
    def setUp(self):
        self.report = {
            "window": {"startSeconds": 1, "endSeconds": 5},
            "frames": [{"timeSeconds": 2, "mimeType": "image/jpeg",
                        "imageBase64": "SECRET_JPEG"}],
            "sceneCutsSeconds": [3], "audioSilences": [{"start": 2.5, "end": 2.8}],
            "findings": [{"kind": "black_interval", "startSeconds": .7,
                          "endSeconds": 1.4},
                         {"kind": "freeze_candidate", "timeSeconds": 3.5}],
            "transcriptCues": [{"index": 0, "startSeconds": .8,
                                "endSeconds": 2.2, "text": "Bitcoin",
                                "provenance": "external_srt_unverified"}]}
    def test_source_times_and_no_jpeg_leak(self):
        result = event_page(self.report)
        self.assertEqual(6, result["totalEvents"])
        self.assertEqual(sorted(e["timeSeconds"] for e in result["events"]),
                         [e["timeSeconds"] for e in result["events"]])
        cue = next(e for e in result["events"] if e["kind"] == "supplied_caption")
        self.assertEqual(.8, cue["sourceStartSeconds"])
        self.assertEqual(1, cue["timeSeconds"])
        self.assertNotIn("SECRET_JPEG", str(result))
        self.assertFalse(result["transcriptionPerformed"])
    def test_pagination_and_cursor_stability(self):
        a = event_page(self.report, page_size=2)
        b = event_page(self.report, cursor=a["nextCursor"], page_size=2)
        c = event_page(self.report, cursor=b["nextCursor"], page_size=2)
        self.assertEqual([f"event-{i}" for i in range(6)],
                         [e["id"] for e in a["events"]+b["events"]+c["events"]])
        self.assertIsNone(c["nextCursor"])
        self.assertEqual([], event_page(self.report, cursor=6)["events"])
    def test_invalid_cursor_and_page(self):
        for params in ({"cursor": -1}, {"cursor": 9}, {"cursor": True},
                       {"page_size": 0}, {"page_size": 101}, {"page_size": 1.5}):
            with self.subTest(params=params), self.assertRaises(PolicyError):
                event_page(self.report, **params)
    def test_no_fabricated_speech(self):
        self.report["transcriptCues"][0]["provenance"] = "whisper_verified"
        with self.assertRaises(PolicyError):
            event_page(self.report)
    def test_no_nan_or_unbounded_events(self):
        self.report["sceneCutsSeconds"] = [float("nan")]
        with self.assertRaises(PolicyError):
            event_page(self.report)
        self.report["sceneCutsSeconds"] = [1 + i / 500 for i in range(1001)]
        with self.assertRaises(PolicyError):
            event_page(self.report)
    def test_out_of_window_candidates_excluded(self):
        self.report["sceneCutsSeconds"] = [-3, 8]
        self.report["audioSilences"] = [{"start": 9, "end": 10}]
        kinds = [e["kind"] for e in event_page(self.report)["events"]]
        self.assertNotIn("scene_cut_candidate", kinds)
        self.assertNotIn("audio_silence_candidate", kinds)

    def test_cross_modal_candidates_link_existing_proofs_without_claiming_semantics(self):
        report = {
            "window": {"startSeconds": 2, "endSeconds": 6},
            "frames": [{"timeSeconds": 2.5, "mimeType": "image/jpeg",
                        "imageBase64": "SECRET_JPEG"}],
            "audioSilences": [{"start": 1.5, "end": 3.6}],
            "findings": [
                {"kind": "black_interval", "startSeconds": 2.8, "endSeconds": 3.4},
                {"kind": "freeze_candidate", "timeSeconds": 4.1}],
            "transcriptCues": [{"index": 0, "startSeconds": 2.2,
                                "endSeconds": 4.5, "text": "unverified speech",
                                "provenance": "external_srt_unverified"}],
        }
        first = event_page(report, page_size=2)
        second = event_page(report, cursor=2, page_size=100)
        review = first["editorialCandidates"]
        self.assertEqual(3, first["editorialCandidateCount"])
        self.assertEqual(review, second["editorialCandidates"])
        self.assertFalse(first["editorialCandidatesTruncated"])
        self.assertEqual(
            ["caption_silence_overlap", "black_silence_overlap",
             "freeze_under_caption"],
            [item["kind"] for item in review])
        self.assertEqual((2.2, 3.6),
                         (review[0]["startSeconds"], review[0]["endSeconds"]))
        self.assertEqual((2.8, 3.4),
                         (review[1]["startSeconds"], review[1]["endSeconds"]))
        event_ids = {event["id"] for event in first["events"] + second["events"]}
        for item in review:
            self.assertTrue(set(item["evidenceIds"]).issubset(event_ids))
            self.assertTrue(item["reviewRequired"])
            self.assertFalse(item["correctionVerified"])
            self.assertIn("check", item["suggestedCheck"])
        self.assertNotIn("SECRET_JPEG", str(first))
        self.assertNotIn("unverified speech", str(review))
        self.assertFalse(first["semanticUnderstandingPerformed"])

    def test_cross_modal_only_real_overlaps_and_bounded_preview(self):
        source = {
            "window": {"startSeconds": 0, "endSeconds": 10},
            "audioSilences": [{"start": 0, "end": 4} for _ in range(12)],
            "findings": [{"kind": "black_interval", "startSeconds": 1,
                          "endSeconds": 3} for _ in range(12)],
        }
        result = event_page(source, page_size=1)
        self.assertEqual(144, result["editorialCandidateCount"])
        self.assertEqual(40, len(result["editorialCandidates"]))
        self.assertTrue(result["editorialCandidatesTruncated"])
        self.assertTrue(all(v["endSeconds"] > v["startSeconds"]
                            for v in result["editorialCandidates"]))
        source["audioSilences"] = [{"start": 5, "end": 6}]
        self.assertEqual([], event_page(source)["editorialCandidates"])

    def test_real_detector_correlation_via_mcp_without_media_artifacts(self):
        import shutil
        import subprocess
        import tempfile
        from pathlib import Path
        from ccer.direct_gateway import DirectGateway
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            self.skipTest("FFmpeg and FFprobe required")
        class Backend:
            def tools(self):
                return []
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            video = root / "silent_black.mp4"
            srt = root / "supplied.srt"
            srt.write_text(
                "1\n00:00:00,500 --> 00:00:01,500\nBonjour\n",
                encoding="utf-8")
            made = subprocess.run(
                ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                 "-f", "lavfi", "-i", "color=c=black:s=160x90:r=12",
                 "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
                 "-t", "3", "-c:v", "mpeg4", "-q:v", "9",
                 "-c:a", "aac", "-shortest", str(video)],
                capture_output=True, timeout=70)
            self.assertEqual(0, made.returncode, made.stderr.decode(errors="replace"))
            original = {p.name for p in root.iterdir()}
            result = DirectGateway(Backend(), root).invoke(
                "ccer_av_events", {"file": str(video), "transcriptFile": str(srt),
                                    "seconds": 2, "frameCount": 2, "pageSize": 80})
            self.assertFalse(result["isError"])
            data = result["structuredContent"]
            kinds = {item["kind"] for item in data["editorialCandidates"]}
            self.assertIn("caption_silence_overlap", kinds)
            self.assertIn("black_silence_overlap", kinds)
            self.assertTrue(all(item["reviewRequired"]
                                and not item["correctionVerified"]
                                for item in data["editorialCandidates"]))
            self.assertFalse(data["semanticUnderstandingPerformed"])
            self.assertNotIn("imageBase64", str(data))
            self.assertEqual(original, {p.name for p in root.iterdir()})

    def test_readonly_adapter_uses_existing_review_and_strips_jpeg(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from ccer.av_event_cursor import inspect_event_window
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            video = root / "clip.mp4"
            video.write_bytes(b"fixture")
            with patch("ccer.timecoded_review.review", return_value=self.report) as spy:
                result = inspect_event_window(root, video, seconds=4)
            spy.assert_called_once()
            self.assertEqual("none", result["transcriptSource"])
            self.assertNotIn("SECRET_JPEG", str(result))

    def test_readonly_adapter_checks_media_root_for_video_and_srt(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from ccer.av_event_cursor import inspect_event_window
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "approved"
            root.mkdir()
            video = root / "clip.mp4"
            video.write_bytes(b"fixture")
            srt = root / "speech.srt"
            srt.write_text("00:00:00,000 --> 00:00:01,000\nHello\n")
            with patch("ccer.av_timeline.audiovisual_review",
                       return_value=self.report) as spy:
                result = inspect_event_window(root, video, transcript=srt)
            spy.assert_called_once()
            self.assertEqual("external_srt_unverified", result["transcriptSource"])
            private = Path(folder) / "private.mp4"
            private.write_bytes(b"private fixture")
            with patch("ccer.timecoded_review.review") as blocked:
                with self.assertRaises(PolicyError):
                    inspect_event_window(root, private)
                blocked.assert_not_called()

    def test_mcp_direct_gateway_exposes_readonly_event_page(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from ccer.direct_gateway import DirectGateway
        class Backend:
            def tools(self):
                return []
        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder) / "clip.mp4"
            video.write_bytes(b"fixture")
            gateway = DirectGateway(Backend(), folder)
            self.assertIn("ccer_av_events", {entry["name"] for entry in gateway.catalogue})
            expected = {"events": [{"kind": "frame_sample", "timeSeconds": 1}],
                        "transcriptionPerformed": False}
            with patch("ccer.av_event_cursor.inspect_event_window",
                       return_value=expected) as inspect:
                result = gateway.invoke("ccer_av_events", {"file": str(video)})
            inspect.assert_called_once()
            self.assertFalse(result["isError"])
            self.assertEqual(expected, result["structuredContent"])
            self.assertFalse(any(part["type"] == "image" for part in result["content"]))

    def test_real_ffmpeg_video_to_mcp_event_page_without_jpeg_files(self):
        import shutil
        import subprocess
        import tempfile
        from pathlib import Path
        from ccer.direct_gateway import DirectGateway
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            self.skipTest("FFmpeg and FFprobe required")
        class Backend:
            def tools(self):
                return []
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            video = root / "real.mp4"
            made = subprocess.run([
                "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=12",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000",
                "-t", "3", "-c:v", "mpeg4", "-q:v", "8",
                "-c:a", "aac", str(video),
            ], capture_output=True, timeout=75)
            self.assertEqual(0, made.returncode, made.stderr.decode(errors="replace"))
            result = DirectGateway(Backend(), root).invoke(
                "ccer_av_events", {"file": str(video), "startSeconds": 0,
                                   "seconds": 2, "frameCount": 2, "pageSize": 3})
            self.assertFalse(result["isError"])
            data = result["structuredContent"]
            self.assertTrue(data["totalEvents"] >= 2)
            self.assertEqual(2, data["sampledFrames"])
            self.assertTrue(all(0 <= e["timeSeconds"] < 2 for e in data["events"]))
            self.assertFalse(data["transcriptionPerformed"])
            self.assertFalse(data["continuousPlaybackPerformed"])
            self.assertFalse(data["mediaArtifactsCreated"])
            self.assertFalse(any(part["type"] == "image" for part in result["content"]))
            self.assertEqual([], list(root.glob("*.jpg")))

if __name__ == "__main__":
    unittest.main()
