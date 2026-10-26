"""Safety and crash tests for CCER-only scratch lifecycle."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from ccer.controls import PolicyError
from ccer.temp_lifecycle import MARKER_FILE, managed_scratch, sweep


class ManagedScratchTests(unittest.TestCase):
    def test_normal_exit_cleans_only_generated_files(self):
        with tempfile.TemporaryDirectory() as base:
            root = Path(base)
            source = root / "original.mp4"
            final = root / "final.mp4"
            source.write_bytes(b"source")
            final.write_bytes(b"final")
            with managed_scratch(root, project="work-001", purpose="render") as scratch:
                self.assertTrue((scratch / MARKER_FILE).exists())
                self.assertTrue(str(scratch).startswith(str(root / ".ccer" / "scratch-jobs")))
                (scratch / "segment.mp4").write_bytes(b"temporary")
                nested = scratch / "sub"; nested.mkdir()
                (nested / "frame.jpg").write_bytes(b"jpeg")
            self.assertFalse(scratch.exists())
            self.assertEqual(b"source", source.read_bytes())
            self.assertEqual(b"final", final.read_bytes())

    def test_exception_cleans_without_deleting_project(self):
        with tempfile.TemporaryDirectory() as base:
            root = Path(base)
            with self.assertRaisesRegex(RuntimeError, "fake failure"):
                with managed_scratch(root, project="work", purpose="encode") as scratch:
                    (scratch / "intermediate.mp4").write_bytes(b"data")
                    raise RuntimeError("fake failure")
            self.assertFalse(scratch.exists())
            self.assertTrue(root.exists())

    def test_dry_run_and_live_recovery_of_old_crash(self):
        with tempfile.TemporaryDirectory() as base:
            root = Path(base)
            with patch("ccer.temp_lifecycle._remove_files"):
                with managed_scratch(root, project="work", purpose="encode") as scratch:
                    (scratch / "partial.mp4").write_bytes(b"partial")
            marker = scratch / MARKER_FILE
            info = json.loads(marker.read_text())
            info["pid"] = 999999999
            info["startTick"] = -1
            info["createdAt"] = time.time() - 2*86400
            marker.write_text(json.dumps(info))
            check = sweep(root, dry_run=True)
            self.assertEqual(1, check["eligible"])
            self.assertTrue(scratch.exists())
            done = sweep(root, dry_run=False)
            self.assertEqual(1, done["deleted"])
            self.assertGreater(done["bytesReclaimed"], 0)
            self.assertFalse(scratch.exists())

    def test_live_job_remains_protected_even_if_very_old(self):
        with tempfile.TemporaryDirectory() as base:
            root = Path(base)
            with managed_scratch(root, project="x", purpose="r") as scratch:
                info = json.loads((scratch / MARKER_FILE).read_text())
                info["createdAt"] = time.time() - 30*86400
                (scratch / MARKER_FILE).write_text(json.dumps(info))
                result = sweep(root, dry_run=False)
                self.assertEqual(0, result["deleted"])
                self.assertEqual(1, result["protectedActive"])
                self.assertTrue(scratch.is_dir())

    def test_symlink_in_job_refuses_cleanup_and_preserves_target(self):
        with tempfile.TemporaryDirectory() as base:
            root = Path(base)
            permanent = root / "important.mp4"
            permanent.write_bytes(b"do not delete")
            with self.assertRaises(PolicyError):
                with managed_scratch(root, project="x", purpose="r") as scratch:
                    (scratch / "danger.mp4").symlink_to(permanent)
            self.assertEqual(b"do not delete", permanent.read_bytes())

    def test_malicious_or_unregistered_dir_does_not_get_swept(self):
        with tempfile.TemporaryDirectory() as base:
            root = Path(base)
            jobs = root / ".ccer" / "scratch-jobs"
            jobs.mkdir(parents=True, mode=0o700)
            stranger = jobs / "personal-media"
            stranger.mkdir()
            (stranger / "original.mp4").write_bytes(b"my video")
            result = sweep(root, dry_run=False)
            self.assertEqual(0, result["deleted"])
            self.assertTrue((stranger / "original.mp4").exists())

    def test_low_disk_rejects_new_job_without_touching_media(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as base:
            root = Path(base)
            original = root / "original.mp4"
            original.write_bytes(b"private")
            with patch("ccer.temp_lifecycle.shutil.disk_usage",
                       return_value=SimpleNamespace(free=512 * 1024 * 1024)):
                with self.assertRaisesRegex(PolicyError, "less than 2 GiB"):
                    with managed_scratch(root, project="x", purpose="render"):
                        pass
            self.assertEqual(b"private", original.read_bytes())

    def test_reject_user_controlled_symlink_and_invalid_labels(self):
        with tempfile.TemporaryDirectory() as base:
            root = Path(base)
            with self.assertRaises(PolicyError):
                with managed_scratch(root, project="../../Videos", purpose="render"):
                    pass
            other = root / "elsewhere"; other.mkdir()
            (root / ".ccer").symlink_to(other, target_is_directory=True)
            with self.assertRaisesRegex(PolicyError, "symlink"):
                with managed_scratch(root, project="x", purpose="r"):
                    pass


if __name__ == "__main__":
    unittest.main()
