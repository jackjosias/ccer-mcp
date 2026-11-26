"""MCP-level functional QA on synthetic media; no live desktop edits."""
import hashlib
import json
import math
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from ccer.direct_gateway import DirectGateway
from ccer.server import Gateway
from ccer.controls import atomic_json, private_dir


class FakeReadBackend:
    def tools(self):
        return [{"name": "project_get", "inputSchema": {"type": "object"}}]

    def tool(self, name, args=None, timeout=None):
        if name != "project_get":
            raise AssertionError("Unexpected upstream invocation")
        return {"structuredContent": {"project": {"name": "synthetic", "path": args["path"]}},
                "isError": False}


class OfflineReadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ccer-functional-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.gateway = DirectGateway(FakeReadBackend(), self.root, access="observe")

    def call(self, name, args):
        result = self.gateway.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                     "params": {"name": name, "arguments": args}})["result"]
        self.assertFalse(result.get("isError"), result)
        return result["structuredContent"]

    def test_project_inspection_returns_fake_backend_project(self):
        project = self.root / "project"
        project.mkdir()
        report = self.call("ccer_project_inspect", {"path": str(project)})
        self.assertEqual(report["project"]["name"], "synthetic")
        self.assertEqual(report["project"]["path"], str(project))

    def test_mission_status_is_read_only(self):
        ident = "a" * 32
        directory = self.root / ".ccer" / "missions"
        private_dir(self.root / ".ccer", create=True)
        private_dir(directory, create=True)
        path = directory / (ident + ".json")
        record = {"id": ident, "state": "running", "kind": "synthetic"}
        atomic_json(path, record)
        before = path.read_bytes()
        self.assertEqual(self.call("ccer_mission_status", {"missionId": ident}), record)
        self.assertEqual(path.read_bytes(), before)

    def test_creative_plan_storyboard_and_editorial_files(self):
        plan = self.call("ccer_creative_plan", {"brief": {
            "topic": "Synthetic", "script": "Black frame. Test tone.",
            "durationSeconds": 6, "profile": "shorts"}})
        self.assertEqual(len(plan["scenes"]), 2)
        self.assertAlmostEqual(sum(s["duration"] for s in plan["scenes"]), 6)
        self.assertFalse(plan["productionReady"])
        self.assertFalse(plan["factsExternallyVerified"])
        board = self.call("ccer_storyboard", {"plan": plan})
        self.assertEqual([p["narration"] for p in board["panels"]],
                         ["Black frame.", "Test tone."])
        # Local test-only gateway, not the restricted Direct runtime.
        self.gateway = Gateway(FakeReadBackend(), self.root)
        target = self.root / "plan.json"
        args = {"file": str(target), "plan": plan}
        result = self.call("ccer_plan_save", args)
        self.assertEqual(result["bytes"], target.stat().st_size)
        self.assertEqual(json.loads(target.read_text()), plan)
        before = target.read_bytes()
        denied = self.gateway.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                      "params": {"name": "ccer_plan_save", "arguments": args}})["result"]
        self.assertTrue(denied["isError"])
        self.assertEqual(target.read_bytes(), before)
        captions = self.root / "captions.srt"
        self.call("ccer_subtitles_write", {"file": str(captions), "cues": plan["captions"]})
        self.assertIn("00:00:00,000 --> 00:00:03,000", captions.read_text())
        self.assertIn("Test tone.", captions.read_text())

    def test_recovery_does_not_replay_edits(self):
        ident = "b" * 32
        directory = self.root / ".ccer" / "missions"
        private_dir(self.root / ".ccer", create=True)
        private_dir(directory, create=True)
        path = directory / (ident + ".json")
        record = {"id": ident, "state": "running", "kind": "synthetic"}
        atomic_json(path, record)
        before = path.read_bytes()
        self.gateway = Gateway(FakeReadBackend(), self.root)
        report = self.call("ccer_mission_recover", {"missionId": ident})
        self.assertIn("Do not automatically replay", report["recovery"])
        self.assertEqual(path.read_bytes(), before)

    def test_tts_capability_report(self):
        report = self.call("ccer_tts_status", {})
        for name in ("espeak-ng", "espeak", "piper", "ffmpeg"):
            self.assertIs(report[name], bool(shutil.which(name)))
        self.assertIn("ffmpeg-flite", report)

    def test_caption_quality_and_cut_plan(self):
        cues = [{"start": 0, "duration": 2, "text": "First"},
                {"start": 2, "duration": 2, "text": "Second"}]
        self.assertTrue(self.call("ccer_caption_validate", {"cues": cues})["passed"])
        cues[1]["start"] = 1
        report = self.call("ccer_caption_validate", {"cues": cues})
        self.assertFalse(report["passed"])
        self.assertIn("overlap", {i["issue"] for i in report["issues"]})
        plan = self.call("ccer_cut_plan", {"duration": 8, "onsets": [2, 4, 6]})
        self.assertEqual(plan["cutPointsSeconds"], [2., 4., 6.])
        self.assertFalse(plan["mutated"])
        self.assertTrue(plan["requiresEditorialApproval"])

    def test_caption_timing_is_not_transcription(self):
        result = self.call("ccer_caption_timing_hint", {
            "cues": [{"text": "First phrase"}, {"text": "Second phrase"}],
            "silenceReport": {"activeRegions": [{"start": .2, "end": 1.8},
                                               {"start": 2.2, "end": 4.0}]}})
        self.assertEqual(len(result["cues"]), 2)
        self.assertFalse(result["forcedAligned"])
        self.assertFalse(result["transcribed"])
        self.assertAlmostEqual(result["cues"][0]["start"], .2, places=2)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                     "FFmpeg and FFprobe required for synthetic media")
class SyntheticMediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="ccer-media-qa-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.media = cls.root / "black-tone.mp4"
        subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                        "-f", "lavfi", "-i", "color=c=black:s=160x90:r=10:d=4",
                        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000:duration=4",
                        "-c:v", "libx264", "-threads", "1", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-shortest", str(cls.media)], check=True, timeout=30)
        cls.before = hashlib.sha256(cls.media.read_bytes()).hexdigest()

    def setUp(self):
        self.gateway = DirectGateway(FakeReadBackend(), self.root, access="observe")

    def tearDown(self):
        self.assertEqual(hashlib.sha256(self.media.read_bytes()).hexdigest(), self.before)

    def call(self, name, args=None):
        payload = {"file": str(self.media)} if args is None else args
        result = self.gateway.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                     "params": {"name": name, "arguments": payload}})["result"]
        self.assertFalse(result.get("isError"), result)
        return result["structuredContent"]

    def test_asset_probe_and_export_verification(self):
        probe = self.call("ccer_asset_analyze")
        video = next(s for s in probe["streams"] if s["codec_type"] == "video")
        self.assertEqual((video["width"], video["height"]), (160, 90))
        self.assertIn("audio", {s["codec_type"] for s in probe["streams"]})
        args = {"file": str(self.media), "width": 160, "height": 90,
                "minDuration": 3.8, "maxDuration": 4.2}
        self.assertTrue(self.call("ccer_export_verify", args)["passed"])
        args["width"] = 999
        bad = self.call("ccer_export_verify", args)
        self.assertFalse(bad["passed"])
        self.assertTrue(any("width" in error for error in bad["errors"]))

    def test_audio_measurement_and_silence(self):
        args = {"file": str(self.media), "seconds": 4}
        audio = self.call("ccer_audio_validate", args)
        self.assertTrue(audio["success"])
        self.assertTrue(math.isfinite(audio["integratedLufs"]))
        silence = self.call("ccer_silence_map", args)
        self.assertTrue(silence["activeRegions"])
        self.assertAlmostEqual(silence["analyzedSeconds"], 4, delta=.2)
        beat = self.call("ccer_beat_candidates", args)
        self.assertIsInstance(beat["onsetsSeconds"], list)
        self.assertTrue(all(0 <= t <= 4.2 for t in beat["onsetsSeconds"]))

    def test_black_frames_color_and_scene_analysis(self):
        args = {"file": str(self.media), "seconds": 4}
        visual = self.call("ccer_visual_scan", args)
        self.assertTrue(visual["blackIntervals"])
        self.assertTrue(visual["needsHumanReview"])
        color = self.call("ccer_color_report", args)
        self.assertGreater(color["sampledFrames"], 0)
        self.assertEqual(color["lumaFlag"], "dark")
        self.assertFalse(color["colorGradingCertified"])
        scene = self.call("ccer_scene_detect", args)
        self.assertEqual(scene["cutsSeconds"], [])
        self.assertEqual(scene["count"], 0)

    def test_catalog_search_and_storyboard_matching(self):
        self.gateway = Gateway(FakeReadBackend(), self.root)
        catalog = self.root / "catalog.json"
        indexed = self.call("ccer_media_index", {
            "items": [{"file": str(self.media), "description": "Black frame",
                       "tags": ["synthetic", "black"], "licenseNote": "test fixture"}],
            "output": str(catalog)})
        self.assertEqual(indexed["indexedCount"], 1)
        self.assertIsNone(indexed["semanticModel"])
        before = catalog.read_bytes()
        self.gateway = DirectGateway(FakeReadBackend(), self.root, access="observe")
        hit = self.call("ccer_media_search", {"catalog": str(catalog), "text": "black"})
        self.assertEqual(hit["totalMatches"], 1)
        self.assertEqual(hit["matches"][0]["provenance"]["semantics"], "user_annotation")
        miss = self.call("ccer_media_search", {"catalog": str(catalog), "text": "elephant"})
        self.assertEqual(miss["totalMatches"], 0)
        plan = {"scenes": [{"visualIntent": "black", "duration": 2},
                           {"visualIntent": "elephant", "duration": 2}]}
        result = self.call("ccer_media_match", {"catalog": str(catalog), "plan": plan})
        self.assertFalse(result["ready"])
        self.assertEqual(len(result["matched"]), 1)
        self.assertEqual(len(result["missing"]), 1)
        self.assertIsNone(result["plan"]["scenes"][1]["source"])
        self.assertEqual(result["plan"]["mediaMatchProvenance"], "user_annotations_not_model_inference")
        self.assertEqual(catalog.read_bytes(), before)

    def test_contact_sheet_real_png(self):
        self.gateway = Gateway(FakeReadBackend(), self.root)
        target = self.root / "contact.png"
        result = self.call("ccer_contact_sheet", {
            "file": str(self.media), "output": str(target), "interval": 1})
        image = target.read_bytes()
        self.assertEqual(result["bytes"], len(image))
        self.assertTrue(image.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(image[12:16], b"IHDR")
        self.assertEqual(image[-8:-4], b"IEND")

    def verify_video(self, report, width, height, duration):
        self.assertTrue(report["verified"])
        path = Path(report["file"])
        self.assertGreater(path.stat().st_size, 100)
        qa = self.call("ccer_export_verify", {"file": str(path), "width": width,
                       "height": height, "minDuration": duration - .5,
                       "maxDuration": duration + .5})
        self.assertTrue(qa["passed"], qa)

    def test_mix_real_audio(self):
        self.gateway = Gateway(FakeReadBackend(), self.root)
        output = self.root / "mix.wav"
        result = self.call("ccer_audio_mix", {"voice": str(self.media),
                           "file": str(output)})
        self.assertTrue(result["verified"])
        self.assertFalse(result["musicDuck"])
        self.assertAlmostEqual(float(result["duration"]), 4, delta=.2)
        self.assertTrue(math.isfinite(result["integratedLufs"]))
        self.assertTrue(output.read_bytes().startswith(b"RIFF"))

    def test_delivery_and_reframe(self):
        self.gateway = Gateway(FakeReadBackend(), self.root)
        source = str(self.media)
        result = self.call("ccer_delivery_transcode", {"file": source,
                           "output": str(self.root / "delivery.mp4"),
                           "profile": "square-preview"})
        self.verify_video(result, 320, 320, 4)
        result = self.call("ccer_reframe_export", {"file": source,
                           "output": str(self.root / "reframe.mp4"),
                           "profile": "vertical-preview", "focusX": .25})
        self.verify_video(result, 360, 640, 4)
        self.assertEqual(result["focus"]["x"], .25)

    def test_transition_render(self):
        self.gateway = Gateway(FakeReadBackend(), self.root)
        # Use a different synthetic scene so a transition can be distinguished.
        second = self.root / "white.mp4"
        subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                        "-f", "lavfi", "-i", "color=c=white:s=160x90:r=24:d=2",
                        "-c:v", "libx264", "-threads", "1", "-pix_fmt", "yuv420p",
                        str(second)], check=True, timeout=30)
        digest = hashlib.sha256(second.read_bytes()).hexdigest()
        result = self.call("ccer_transition_export", {"first": str(self.media),
                           "second": str(second), "output": str(self.root / "fade.mp4"),
                           "profile": "landscape-preview", "sceneSeconds": 1,
                           "overlapSeconds": .25, "kind": "fade"})
        self.verify_video(result, 640, 360, 1.75)
        self.assertEqual(result["transition"], "fade")
        self.assertFalse(result["originalAudioPreserved"])
        self.assertEqual(hashlib.sha256(second.read_bytes()).hexdigest(), digest)

    def test_directed_and_matched_render(self):
        self.gateway = Gateway(FakeReadBackend(), self.root)
        plan = {"video": {"width": 160, "height": 90, "rateNum": 10, "rateDen": 1},
                "scenes": [{"duration": 2, "source": str(self.media),
                            "visualIntent": "black"}],
                "captions": [{"start": 0, "duration": 2, "text": "Synthetic"}]}
        result = self.call("ccer_directed_render", {"plan": plan,
                           "file": str(self.root / "directed.mp4"),
                           "burnCaptions": False, "preset": "ultrafast"})
        self.verify_video(result, 160, 90, 2)
        self.assertEqual(result["sceneCount"], 1)
        self.assertIn("Synthetic", Path(result["subtitles"]).read_text())
        catalog = self.root / "render-catalog.json"
        self.call("ccer_media_index", {"items": [{"file": str(self.media),
                   "tags": ["black"]}], "output": str(catalog)})
        match = self.call("ccer_media_match_render", {"catalog": str(catalog),
                          "plan": plan, "output": str(self.root / "matched.mp4"),
                          "confirm": True, "burnCaptions": False,
                          "preset": "ultrafast"})
        self.verify_video(match["render"], 160, 90, 2)
        self.assertTrue(match["technicalQA"])
        self.assertTrue(match["editorialReviewRequired"])
        self.assertEqual(match["provenance"], "user_annotations_not_model_inference")

    def test_studio_real_production(self):
        self.gateway = Gateway(FakeReadBackend(), self.root)
        result = self.call("ccer_studio_produce", {"name": "SyntheticStudio",
                           "brief": {"topic": "Synthetic", "script": "Black frame.",
                                     "durationSeconds": 3, "assets": [str(self.media)]},
                           "video": {"width": 160, "height": 90, "rateNum": 10, "rateDen": 1},
                           "burnCaptions": False, "preset": "ultrafast"})
        self.assertTrue(result["passed"])
        self.verify_video(result["render"], 160, 90, 3)
        self.assertTrue(result["technicalQA"])
        self.assertFalse(result["researchVerified"])
        self.assertTrue(result["needsVisualReview"])
        self.assertTrue(Path(result["storyboard"]).is_file())

    def test_voice_flite_real_wav(self):
        from ccer.voice_extensions import flite_available
        if not flite_available():
            self.skipTest("Optional FFmpeg libflite unavailable")
        self.gateway = Gateway(FakeReadBackend(), self.root)
        output = self.root / "flite.wav"
        result = self.call("ccer_voice_flite", {"text": "Synthetic test.",
                           "file": str(output), "language": "en"})
        self.assertTrue(result["verified"])
        self.assertGreater(result["durationSeconds"], 0)
        self.assertFalse(result["naturalSounding"])
        self.assertTrue(output.read_bytes().startswith(b"RIFF"))

    def test_voice_espeak_real_wav(self):
        if not (shutil.which("espeak-ng") or shutil.which("espeak")):
            self.skipTest("Optional eSpeak unavailable")
        self.gateway = Gateway(FakeReadBackend(), self.root)
        output = self.root / "espeak.wav"
        result = self.call("ccer_voice_synthesize", {"text": "Test de synthèse.",
                           "file": str(output), "language": "fr"})
        self.assertTrue(result["verified"])
        self.assertIn(result["engine"], ("espeak", "espeak-ng"))
        self.assertGreater(float(result["duration"]), 0)
        self.assertTrue(output.read_bytes().startswith(b"RIFF"))

    def test_technical_shot_inspection(self):
        result = self.call("ccer_shot_inspect", {"files": [str(self.media)]})
        self.assertEqual(len(result["assets"]), 1)
        shot = result["assets"][0]
        self.assertEqual((shot["width"], shot["height"]), (160, 90))
        self.assertAlmostEqual(shot["duration"], 4, delta=.2)


if __name__ == "__main__":
    unittest.main()
