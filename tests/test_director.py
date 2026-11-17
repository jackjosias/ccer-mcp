import os
import stat
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from ccer.controls import PolicyError, media_probe
from ccer.production import Production
from ccer.director_render import render
from ccer.temp_lifecycle import sweep


class DirectorTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                         "FFmpeg and FFprobe required")
    def test_real_ffmpeg_render_cleans_scratch_preserves_final(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine = Production(None, root)
            source = root / "source.mp4"
            output = root / "final.mp4"
            command = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                       "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=12",
                       "-t", "1.5", "-c:v", "mpeg4", "-q:v", "7", str(source)]
            made = subprocess.run(command, capture_output=True, timeout=40)
            self.assertEqual(0, made.returncode, made.stderr.decode(errors="replace"))
            source_size = source.stat().st_size
            plan = {"video": {"width": 320, "height": 180,
                              "rateNum": 12, "rateDen": 1},
                    "scenes": [{"source": str(source), "duration": 1.25}],
                    "captions": []}
            info = render(engine, plan, str(output), preset="ultrafast")
            self.assertTrue(info["verified"])
            self.assertGreater(output.stat().st_size, 0)
            self.assertEqual(source_size, source.stat().st_size)
            self.assertEqual(320, next(s["width"] for s in media_probe(output)["streams"]
                                       if s["codec_type"] == "video"))
            jobs = root / ".ccer" / "scratch-jobs"
            self.assertEqual([], list(jobs.iterdir()))

    def test_metadata_private_even_with_permissive_ci_umask(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_umask = os.umask(0o022)
            try:
                root = Path(tmp)
                engine = Production(None, root)
                self.assertFalse(engine.meta.exists())  # read-only init stays side-effect free
                engine._mission("fixture", {})
                self.assertEqual(stat.S_IMODE(engine.meta.stat().st_mode), 0o700)
                self.assertEqual(stat.S_IMODE((engine.meta / "missions").stat().st_mode), 0o700)
                self.assertEqual(0, sweep(root, dry_run=True)["deleted"])
            finally:
                os.umask(old_umask)

    def test_existing_insecure_metadata_refused_without_permission_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            metadata = Path(tmp) / ".ccer"
            metadata.mkdir(mode=0o700)
            metadata.chmod(0o755)
            with self.assertRaisesRegex(PolicyError, "0700"):
                Production(None, Path(tmp))._mission("fixture", {})
            self.assertEqual(stat.S_IMODE(metadata.stat().st_mode), 0o755)

    def test_direct_audit_journal_creates_private_metadata_only_when_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_umask = os.umask(0o022)
            try:
                engine = Production(None, Path(tmp))
                self.assertFalse(engine.meta.exists())
                engine.journal.append("fixture.audit", {"approved": True})
                self.assertEqual(stat.S_IMODE(engine.meta.stat().st_mode), 0o700)
            finally:
                os.umask(old_umask)

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
