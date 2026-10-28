import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ccer.controls import PolicyError
from ccer.native_srt_acceptance import verify


class NativeSrtAcceptanceTests(unittest.TestCase):
    def test_reuses_both_existing_analyzers_and_hides_jpegs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "clip.mp4"
            srt = root / "speech.srt"
            video.write_bytes(b"fixture")
            srt.write_text("dummy")
            row = {"durationSeconds": 5.705, "timebase": "source_relative",
                   "timelineOffsetSeconds": .9,
                   "cues": [{"start": 0., "duration": 5.6, "text": "speech"}],
                   "captionQA": {"passed": True}, "audioPresent": True}
            frame = {"frameCount": 2, "frameSpeechAssociations": [
                {"timeSeconds": .5, "cueIndices": [0]},
                {"timeSeconds": 1.5, "cueIndices": [0]}],
                "frames": [{"imageBase64": "NO_JPEG_LEAK"}]}
            with patch("ccer.native_srt_acceptance.read_srt", return_value=row) as reader, \
                 patch("ccer.native_srt_acceptance.audiovisual_review",
                       return_value=frame) as reviewer:
                result = verify(root, root, video, srt, timeline_offset_seconds=.9)
            reader.assert_called_once()
            reviewer.assert_called_once()
            self.assertNotIn("NO_JPEG_LEAK", str(result))
            self.assertFalse(result["transcriptionPerformed"])
            self.assertFalse(result["mediaArtifactsCreated"])

    def test_denies_unapproved_srt_before_decoding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            approved = root / "approved"
            approved.mkdir()
            media = approved / "clip.mp4"
            media.write_bytes(b"dummy")
            foreign = root / "private.srt"
            foreign.write_text("dummy")
            with patch("ccer.native_srt_acceptance.read_srt") as spy:
                with self.assertRaises(PolicyError):
                    verify(approved, approved, media, foreign)
                spy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
