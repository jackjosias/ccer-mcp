import tempfile
import unittest
from pathlib import Path

from ccer.controls import PolicyError
from ccer.production import Production
from ccer.director_render import render


class DirectorTests(unittest.TestCase):
    def test_refuse_missing_approved_scene(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = Production(None, Path(tmp))
            plan = {"video": {"width": 320, "height": 180,
                              "rateNum": 24, "rateDen": 1},
                    "scenes": [{"source": "/etc/passwd", "duration": 2}]}
            with self.assertRaises(PolicyError):
                render(engine, plan, str(Path(tmp) / "out.mp4"))

    def test_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = Production(None, Path(tmp))
            out = Path(tmp) / "saved.mp4"
            out.write_bytes(b"existing")
            with self.assertRaises(PolicyError):
                render(engine, {"scenes": [], "video": {}}, str(out))
            self.assertEqual(out.read_bytes(), b"existing")
