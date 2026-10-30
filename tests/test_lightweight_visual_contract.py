"""Keep CCER model-free: authentic FFmpeg imagery and native desktop captures."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ccer.direct_gateway import DirectGateway


class NativeStub:
    def tools(self):
        return []


class LightweightVisualTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.gateway = DirectGateway(NativeStub(), Path(self.temp.name))

    def test_image_audio_and_native_desktop_tools_retained(self):
        names = {item["name"] for item in self.gateway.catalogue}
        for name in ("ccer_timecoded_review", "ccer_av_timeline",
                     "ccer_av_replay_poll", "ccer_desktop_capture",
                     "ccer_desktop_status", "ccer_audio_window",
                     "ccer_asr_status"):
            self.assertIn(name, names)
        self.assertNotIn("ccer_vision_model_status", names)
        self.assertNotIn("ccer_vision_frame", names)

    def test_ffmpeg_frame_delivered_as_real_mcp_image_part(self):
        evidence = {"frames": [{"timeSeconds": 1.25,
                                "mimeType": "image/jpeg",
                                "imageBase64": "/9j/4AAQSkZJRgABAQ=="}],
                    "frameCount": 1, "readOnly": True}
        with patch("ccer.server.Production.run", return_value=evidence):
            result = self.gateway.invoke("ccer_timecoded_review", {"file": "fixture"})
        self.assertFalse(result["isError"])
        self.assertEqual([("image/jpeg", "/9j/4AAQSkZJRgABAQ==")],
                         [(p["mimeType"], p["data"]) for p in result["content"]
                          if p["type"] == "image"])
        self.assertEqual(1.25,
                         result["structuredContent"]["frames"][0]["timeSeconds"])
        self.assertNotIn("imageBase64", result["structuredContent"])


if __name__ == "__main__":
    unittest.main()
