import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
from ccer.controls import PolicyError, inside
from ccer.studio_pipeline import produce_studio

class FakeEngine:
    def __init__(self, root):
        self.root = Path(root)
        self.missions = []
    def path(self, raw, must_exist=False):
        return inside(self.root, raw, must_exist=must_exist)
    def _mission(self, kind, data):
        mission = {"id": uuid.uuid4().hex, "kind": kind, "data": data}
        self.missions.append(mission)
        return mission
    def _finish(self, mission, state, **fields):
        mission.update(state=state, **fields)
    def _dispatch(self, method, args):
        if method != "ccer_export_verify":
            raise AssertionError("Unexpected QA call")
        return {"passed": True}

class StudioPipelineTests(unittest.TestCase):
    def test_production_orchestration_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            engine = FakeEngine(d)
            media = Path(d) / "input.mp4"
            media.write_bytes(b"fake; renderer is mocked")
            spec = {"name": "PipelineTest", "brief": {
                "topic": "A project", "script": "Welcome. This is our video.",
                "durationSeconds": 8, "profile": "shorts", "language": "en",
                "assets": [str(media), str(media)]},
                "video": {"width": 320, "height": 180, "rateNum": 24, "rateDen": 1}}
            def fake_render(_, plan, output, **kwargs):
                Path(output).write_bytes(b"test fixture, not an actual video")
                return {"file": output, "width": 320, "height": 180,
                        "verified": True, "subtitles": None}
            with patch("ccer.studio_pipeline.directed_render", side_effect=fake_render) as render, patch(
                "ccer.studio_pipeline.visual_scan", return_value={"needsHumanReview": False}):
                result = produce_studio(engine, spec)
                self.assertTrue(result["passed"])
                self.assertEqual(render.call_count, 1)
                self.assertEqual(engine.missions[-1]["state"], "completed")
                with self.assertRaises(PolicyError):
                    produce_studio(engine, spec)

    def test_path_policy_prevents_unauthorized_files(self):
        with tempfile.TemporaryDirectory() as d:
            engine = FakeEngine(d)
            spec = {"name": "Demo", "brief": {"topic": "A",
                "script": "Welcome to CCER.", "profile": "shorts",
                "durationSeconds": 8, "assets": ["/etc/passwd"]}}
            with self.assertRaises(PolicyError):
                produce_studio(engine, spec)
            self.assertFalse((Path(d) / "Demo").exists())
