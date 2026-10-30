"""Regression tests for CCER SRT and audiovisual frame alignment."""
import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ccer.av_timeline import read_srt, audiovisual_review
from ccer.controls import PolicyError
from ccer.direct_gateway import DirectGateway

class Backend:
    def tools(self):
        return []

class AVTimelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.video = self.root / "video.mp4"
        self.video.write_bytes(b"test")
        self.srt = self.root / "speech.srt"
        self.srt.write_text("1\n00:00:00,000 --> 00:00:01,200\nBonjour\n\n"
                            "2\n00:00:01,200 --> 00:00:02,400\nMon gars\n", encoding="utf-8")
        self.meta = {"format": {"duration": "3"}, "streams": [
            {"codec_type": "video"}, {"codec_type": "audio"}]}

    def test_import_is_readonly_not_claiming_asr(self):
        with patch("ccer.av_timeline.media_probe", return_value=self.meta):
            result = read_srt(self.video, self.srt)
        self.assertEqual(2, result["cueCount"])
        self.assertFalse(result["asrPerformed"])
        self.assertEqual("external_srt_unverified", result["provenance"])

    def test_concat_timeline_offset_maps_to_media_and_frame(self):
        self.srt.write_text("1\n00:00:00,900 --> 00:00:02,900\nHello friends\n",
                            encoding="utf-8")
        frame = {"timeSeconds": 1., "mimeType": "image/jpeg",
                 "imageBase64": base64.b64encode(b"\xff\xd8test\xff\xd9").decode()}
        report = {"frames": [frame], "window": {"startSeconds": 0., "endSeconds": 2.},
                  "frameCount": 1}
        with patch("ccer.av_timeline.media_probe", return_value=self.meta), \
             patch("ccer.av_timeline.review", return_value=report):
            result = audiovisual_review(
                self.video, self.srt, start_seconds=0, seconds=2, frame_count=1,
                timeline_offset_seconds=.9)
        self.assertEqual(0, result["transcriptCues"][0]["startSeconds"])
        self.assertEqual(2, result["transcriptCues"][0]["endSeconds"])
        self.assertEqual([0], result["frameSpeechAssociations"][0]["cueIndices"])
        self.assertEqual(.9, result["timelineOffsetSeconds"])
        self.assertFalse(result["transcriptionPerformed"])

    def test_untrusted_offset_fails_closed(self):
        for bad in (-.1, True, float("nan"), 86401):
            with self.subTest(value=bad), self.assertRaises(PolicyError):
                read_srt(self.video, self.srt, timeline_offset_seconds=bad)

    def test_srt_overlap_rejected(self):
        self.srt.write_text("00:00:00,000 --> 00:00:01,400\nA\n\n"
                            "00:00:01,000 --> 00:00:02,000\nB\n")
        with patch("ccer.av_timeline.media_probe", return_value=self.meta):
            with self.assertRaises(PolicyError):
                read_srt(self.video, self.srt)

    def test_real_frame_matches_speech_time(self):
        frame = {"timeSeconds": 1.5, "mimeType": "image/jpeg",
                 "imageBase64": base64.b64encode(b"\xff\xd8img\xff\xd9").decode()}
        observations = {"frames": [frame], "frameCount": 1,
                        "window": {"startSeconds": 1., "endSeconds": 2.}}
        with patch("ccer.av_timeline.media_probe", return_value=self.meta), \
             patch("ccer.av_timeline.review", return_value=observations):
            result = audiovisual_review(self.video, self.srt, start_seconds=1, seconds=1,
                                        frame_count=1)
        self.assertEqual([1], result["frameSpeechAssociations"][0]["cueIndices"])
        self.assertFalse(result["transcriptionPerformed"])
        self.assertTrue(result["noLocalMediaArtifacts"])

    def test_direct_gateway_rejects_unapproved_subtitles(self):
        allowed = self.root / "approved"
        allowed.mkdir()
        video = allowed / "video.mp4"
        video.write_bytes(b"test")
        with self.assertRaises(PolicyError):
            DirectGateway(Backend(), allowed).invoke(
                "ccer_av_timeline", {"file": str(video), "transcriptFile": str(self.srt)})

    def test_mcp_outputs_real_image_parts_without_base64_metadata(self):
        image = base64.b64encode(b"\xff\xd8sample\xff\xd9").decode()
        report = {"file": str(self.video),
                  "frames": [{"timeSeconds": 1., "mimeType": "image/jpeg",
                              "imageBase64": image}],
                  "transcriptCues": [{"text": "Bonjour"}]}
        with patch("ccer.av_timeline.audiovisual_review", return_value=report):
            response = DirectGateway(Backend(), self.root).invoke(
                "ccer_av_timeline", {"file": str(self.video),
                                      "transcriptFile": str(self.srt)})
        self.assertFalse(response["isError"])
        self.assertEqual("image", response["content"][2]["type"])
        self.assertEqual(image, response["content"][2]["data"])
        self.assertNotIn("imageBase64", str(response["structuredContent"]))
        self.assertEqual("Bonjour", response["structuredContent"]["transcriptCues"][0]["text"])

    def test_gateway_reads_srt_without_claiming_asr(self):
        with patch("ccer.av_timeline.media_probe", return_value=self.meta):
            response = DirectGateway(Backend(), self.root).invoke(
                "ccer_transcript_read", {"file": str(self.video),
                                         "transcriptFile": str(self.srt)})
        self.assertEqual(2, response["structuredContent"]["cueCount"])
        self.assertFalse(response["structuredContent"]["asrPerformed"])

    def test_real_ffmpeg_audio_video_and_caption_time_alignment(self):
        import shutil
        import subprocess
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            self.skipTest("FFmpeg unavailable")
        media = self.root / "real.mp4"
        generated = subprocess.run(
            ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
             "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=12",
             "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000",
             "-t", "3", "-c:v", "mpeg4", "-q:v", "8",
             "-c:a", "aac", str(media)], capture_output=True, timeout=45)
        self.assertEqual(0, generated.returncode, generated.stderr.decode(errors="replace"))
        result = audiovisual_review(media, self.srt, start_seconds=1.,
                                    seconds=1., frame_count=2, include_audio=True)
        self.assertTrue(result["audioPresent"])
        self.assertEqual(2, result["frameCount"])
        self.assertEqual(2, len(result["transcriptCues"]))
        self.assertEqual(["Bonjour", "Mon gars"],
                         [cue["text"] for cue in result["transcriptCues"]])
        self.assertTrue(all(row["imageBase64"] for row in result["frames"]))
        self.assertFalse(result["transcriptionPerformed"])
        wav = base64.b64decode(result["audioEvidence"]["audioBase64"], validate=True)
        self.assertTrue(wav.startswith(b"RIFF"))
        self.assertEqual(b"WAVE", wav[8:12])
        reply = DirectGateway(Backend(), self.root).invoke(
            "ccer_av_timeline", {"file": str(media), "transcriptFile": str(self.srt),
                                 "startSeconds": 1., "seconds": 1.,
                                 "frameCount": 1, "includeAudio": True})
        self.assertFalse(reply["isError"])
        self.assertEqual("audio", reply["content"][-1]["type"])
        self.assertEqual("image", reply["content"][2]["type"])
        self.assertNotIn("audioBase64", str(reply["structuredContent"]))
        self.assertNotIn("imageBase64", str(reply["structuredContent"]))

if __name__ == "__main__":
    unittest.main()
