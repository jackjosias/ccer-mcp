"""Saved Concat caption audit tests: no edit or ASR side effects."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ccer.controls import PolicyError
from ccer.project_caption_audit import inspect


class ProjectCaptionAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.projects = self.root / "projects"
        self.projects.mkdir()
        self.media_root = self.root / "media"
        self.media_root.mkdir()
        self.video = self.media_root / "speech.mp4"
        self.video.write_bytes(b"test")
        self.project_dir = self.projects / "project8"
        self.project_dir.mkdir()
        self.project_file = self.project_dir / "concat.json"
        self.data = {
            "name": "Project 8", "activeTimelineId": "TL1",
            "media": [{"id": "m1", "path": str(self.video), "kind": "video"}],
            "timelines": [{"id": "TL1", "clips": [
                {"kind": "video", "mediaId": "m1",
                 "start": .9, "duration": 5.705, "sourceStart": 0, "speed": 1},
                {"kind": "text", "start": .9, "duration": 5.6,
                 "text": {"content": "Hello friends, this is a test."}},
            ]}],
        }
        self.probe = {"streams": [{"codec_type": "video"},
                                  {"codec_type": "audio"}],
                      "format": {"duration": "5.705"}}

    def audit(self):
        self.project_file.write_text(json.dumps(self.data))
        with patch("ccer.project_caption_audit.media_probe",
                   return_value=self.probe) as probe:
            result = inspect(self.projects, self.project_file, self.media_root)
            probe.assert_called_once_with(self.video)
        return result

    def test_realistic_timing_and_provenance(self):
        result = self.audit()
        self.assertTrue(result["captionQA"]["passed"])
        self.assertEqual(.9, result["titles"][0]["startSeconds"])
        self.assertEqual(6.5, result["titles"][0]["endSeconds"])
        self.assertTrue(result["audioInSourceVideos"])
        self.assertFalse(result["whisperOriginVerified"])
        self.assertFalse(result["nativeSrtExportPerformed"])
        self.assertFalse(result["transcriptionPerformed"])

    def test_caption_outside_video_is_failed_qa(self):
        self.data["timelines"][0]["clips"][1]["duration"] = 6.5
        result = self.audit()
        self.assertFalse(result["captionQA"]["passed"])
        self.assertIn("outside_video",
                      [i["issue"] for i in result["captionQA"]["issues"]])

    def test_media_outside_root_refused_before_probe(self):
        private = self.root / "private.mp4"
        private.write_bytes(b"test")
        self.data["media"][0]["path"] = str(private)
        self.project_file.write_text(json.dumps(self.data))
        with patch("ccer.project_caption_audit.media_probe") as probe:
            with self.assertRaises(PolicyError):
                inspect(self.projects, self.project_file, self.media_root)
            probe.assert_not_called()

    def test_source_duration_exceeded(self):
        self.probe["format"]["duration"] = "2"
        with self.assertRaises(PolicyError):
            self.audit()

    def test_empty_text_refused_and_no_media_generated(self):
        self.data["timelines"][0]["clips"][1]["text"]["content"] = ""
        with self.assertRaises(PolicyError):
            self.audit()
        self.assertFalse(list(self.root.rglob("*.srt")))
        self.assertFalse(list(self.root.rglob("*.jpg")))


if __name__ == "__main__":
    unittest.main()
