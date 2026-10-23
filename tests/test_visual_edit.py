import tempfile
import unittest
from pathlib import Path
from ccer.controls import inside, PolicyError
from ccer.visual_edit import reframe, transition, color_report, _finite


class Engine:
    def __init__(self, root):
        self.root = Path(root)
    def path(self, raw, must_exist=False):
        return inside(self.root, raw, must_exist=must_exist)


class VisualTests(unittest.TestCase):
    def test_refuse_nonfinite_and_unsafe_source(self):
        with self.assertRaises(PolicyError):
            _finite(float("nan"), "test", 0, 1)
        with self.assertRaises(PolicyError):
            _finite(True, "test", 0, 1)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with self.assertRaises(PolicyError):
                reframe(Engine(root), "/etc/passwd", str(root / "movie.mp4"))
            with self.assertRaises(PolicyError):
                color_report(root / "absent.mp4")
            self.assertFalse((root / "movie.mp4").exists())

    def test_invalid_transition_media_never_creates_output(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with self.assertRaises(PolicyError):
                transition(Engine(root), "/etc/passwd", "/etc/passwd",
                           str(root / "output.mp4"), kind="fade")
            self.assertFalse((root / "output.mp4").exists())
