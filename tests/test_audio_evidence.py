"""Read-only authentic WAV audio MCP payloads, boundaries and retention."""
import base64
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ccer.audio_evidence import MAX_WAV_BYTES, audio_window
from ccer.controls import PolicyError
from ccer.direct_gateway import DirectGateway

class Backend:
    def tools(self):
        return []

class AudioEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.file = self.root / "sample.mp4"
        self.file.write_bytes(b"dummy")
        self.meta = {"format": {"duration": "10"},
                     "streams": [{"codec_type": "audio"}]}

    def test_bad_windows_rejected(self):
        with patch("ccer.audio_evidence.media_probe", return_value=self.meta):
            for options in ({"seconds": 11}, {"seconds": .1}, {"seconds": True},
                            {"seconds": float("nan")}, {"start_seconds": 10},
                            {"start_seconds": -1}):
                with self.subTest(options=options), self.assertRaises(PolicyError):
                    audio_window(self.file, **options)

    def test_audio_stream_required(self):
        with patch("ccer.audio_evidence.media_probe", return_value={
                "format": {"duration": "3"}, "streams": [{"codec_type": "video"}]}):
            with self.assertRaisesRegex(PolicyError, "no audio stream"):
                audio_window(self.file)

    def test_unapproved_file_rejected_by_mcp(self):
        approved = self.root / "approved"
        approved.mkdir()
        with self.assertRaises(PolicyError):
            DirectGateway(Backend(), approved).invoke(
                "ccer_audio_window", {"file": str(self.file)})

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                         "FFmpeg unavailable")
    def test_real_audio_without_scratch_files_and_mcp_audio_part(self):
        wavfile = self.root / "speech.wav"
        made = subprocess.run(
            ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
             "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000",
             "-t", "1.5", "-c:a", "pcm_s16le", str(wavfile)],
            capture_output=True, timeout=35)
        self.assertEqual(0, made.returncode, made.stderr.decode(errors="replace"))
        before = {p.name for p in self.root.iterdir()}
        report = audio_window(wavfile, start_seconds=.25, seconds=.75)
        raw = base64.b64decode(report["audioBase64"], validate=True)
        self.assertTrue(raw.startswith(b"RIFF"))
        self.assertEqual(b"WAVE", raw[8:12])
        self.assertLess(len(raw), MAX_WAV_BYTES)
        self.assertEqual(16000, report["sampleRate"])
        self.assertFalse(report["transcriptionPerformed"])
        self.assertTrue(report["noLocalMediaArtifacts"])
        self.assertEqual(before, {p.name for p in self.root.iterdir()})
        result = DirectGateway(Backend(), self.root).invoke(
            "ccer_audio_window",
            {"file": str(wavfile), "startSeconds": .25, "seconds": .75})
        self.assertFalse(result["isError"])
        self.assertEqual("audio", result["content"][1]["type"])
        self.assertEqual("audio/wav", result["content"][1]["mimeType"])
        self.assertNotIn("audioBase64", str(result["structuredContent"]))
        self.assertTrue(base64.b64decode(result["content"][1]["data"]).startswith(b"RIFF"))
        self.assertEqual(before, {p.name for p in self.root.iterdir()})

if __name__ == "__main__":
    unittest.main()
