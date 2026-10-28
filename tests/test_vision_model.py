import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ccer.controls import PolicyError
from ccer.vision_model import vision_status, describe_frame


class VisionModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.video = self.root / "test.mp4"
        self.video.write_bytes(b"fixture")
        self.meta = {"streams": [{"codec_type": "video"}],
                     "format": {"duration": "3.0"}}

    def test_offline_refuses_before_any_video_decode(self):
        with patch("ccer.vision_model.vision_status",
                   return_value={"ready": False}), \
             patch("ccer.vision_model._frame") as decoder:
            with self.assertRaisesRegex(PolicyError, "unavailable"):
                describe_frame(self.root, self.video)
            decoder.assert_not_called()

    def test_local_model_response_binds_to_exact_frame_sha(self):
        class Reply(io.BytesIO):
            status = 200
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.close()
        class Client:
            def __init__(self):
                self.body = None
            def add_handler(self, *args):
                pass
            def open(self, request, timeout):
                self.body = json.loads(request.data)
                return Reply(b'{"response":"A test pattern is visible."}')
        client = Client()
        with patch("ccer.vision_model.vision_status", return_value={"ready": True}), \
             patch("ccer.vision_model.media_probe", return_value=self.meta), \
             patch("ccer.vision_model._frame", return_value=b"\xff\xd8sample\xff\xd9"), \
             patch("ccer.vision_model.urllib.request.build_opener",
                   return_value=client):
            got = describe_frame(self.root, self.video, time_seconds=1.0)
        import hashlib
        self.assertEqual(hashlib.sha256(b"\xff\xd8sample\xff\xd9").hexdigest(),
                         got["frameSha256"])
        self.assertTrue(got["visionInferencePerformed"])
        self.assertFalse(got["semanticAccuracyIndependentlyVerified"])
        self.assertFalse(got["audioUnderstood"])
        self.assertEqual("qwen3.5:0.8b", client.body["model"])
        self.assertEqual(False, client.body["stream"])
        self.assertEqual("0s", client.body["keep_alive"])
        self.assertEqual([], list(self.root.glob("*.jpg")))

    def test_outside_root_and_invalid_timestamp_refused(self):
        with patch("ccer.vision_model.vision_status", return_value={"ready": True}), \
             patch("ccer.vision_model.media_probe", return_value=self.meta):
            for bad in (-1, True, float("nan"), 3):
                with self.assertRaises(PolicyError):
                    describe_frame(self.root, self.video, time_seconds=bad)
            with tempfile.TemporaryDirectory() as private:
                other = Path(private) / "private.mp4"
                other.write_bytes(b"secret")
                with self.assertRaises(PolicyError):
                    describe_frame(self.root, other)

    def test_bogus_model_manifest_refused(self):
        manifest = self.root / "0.8b"
        manifest.write_text('{"layers":[{"mediaType":"application/vnd.ollama.image.model","digest":"invalid","size":12}]}')
        with patch("ccer.vision_model.MANIFEST", manifest), \
             patch("ccer.vision_model.socket.create_connection",
                   side_effect=OSError("offline")):
            result = vision_status()
        self.assertFalse(result["ready"])
        self.assertFalse(result["installed"])
        self.assertFalse(result["ollamaLoopbackOnline"])


    def test_gateway_exposes_local_vision_and_refuses_offline_inference(self):
        from ccer.direct_gateway import DirectGateway
        class Backend:
            def tools(self):
                return []
        gateway = DirectGateway(Backend(), self.root)
        names = {item["name"] for item in gateway.catalogue}
        self.assertIn("ccer_vision_model_status", names)
        self.assertIn("ccer_vision_frame", names)
        with patch("ccer.vision_model.vision_status",
                   return_value={"ready": False, "installed": True,
                                 "ollamaLoopbackOnline": False}):
            status = gateway.invoke("ccer_vision_model_status", {})
            self.assertFalse(status["structuredContent"]["ready"])
            with self.assertRaises(PolicyError):
                gateway.invoke("ccer_vision_frame",
                               {"file": str(self.video), "timeSeconds": 0})

if __name__ == "__main__":
    unittest.main()
