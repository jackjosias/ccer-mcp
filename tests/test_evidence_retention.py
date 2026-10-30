"""Retention tests: no source media touched, no active receipts lost."""
import base64
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from ccer import evidence_retention as gc
from ccer import visible_desktop
from ccer.controls import PolicyError


class EvidenceRetentionTests(unittest.TestCase):
    receipt = "abcdef012345"

    def test_prune_only_old_generated_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            old = root / ("after-" + self.receipt + ".jpg")
            active = root / ("before-" + self.receipt + ".json")
            original = root / "original-video.mp4"
            foreign = root / "notes.json"
            for p in (old, active, original, foreign):
                p.write_bytes(b"video-or-proof")
            now = time.time()
            os.utime(old, (now - 2400, now - 2400))
            result = gc.prune(root, now=now)
            self.assertEqual(1, result["removed"])
            self.assertFalse(old.exists())
            for p in (active, original, foreign):
                self.assertTrue(p.exists())
            self.assertEqual(0o700, root.stat().st_mode & 0o777)

    def test_active_receipt_never_purged(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            active = root / ("before-" + self.receipt + ".json")
            active.write_text("pending action")
            with self.assertRaisesRegex(PolicyError, "Active pre-action"):
                gc.acknowledge(root, self.receipt, confirmed_reviewed=True)
            self.assertTrue(active.exists())

    def test_acknowledge_only_one_reviewed_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            current = root / ("after-" + self.receipt + ".jpg")
            other = root / "after-111111111111.jpg"
            user_video = root / "user-video.mp4"
            for file in (current, other, user_video):
                file.write_bytes(b"data")
            with self.assertRaisesRegex(PolicyError, "explicit review"):
                gc.acknowledge(root, self.receipt, confirmed_reviewed=False)
            result = gc.acknowledge(root, self.receipt, confirmed_reviewed=True)
            self.assertEqual(1, result["removed"])
            self.assertFalse(current.exists())
            self.assertTrue(other.exists())
            self.assertTrue(user_video.exists())

    def test_refuse_symlinked_evidence_file_and_root(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            evidence = base / "evidence"
            evidence.mkdir()
            target = base / "private.mp4"
            target.write_bytes(b"private")
            (evidence / ("after-" + self.receipt + ".jpg")).symlink_to(target)
            with self.assertRaisesRegex(PolicyError, "Unsafe"):
                gc.prune(evidence)
            self.assertEqual(b"private", target.read_bytes())
            alias = base / "alias"
            alias.symlink_to(evidence, target_is_directory=True)
            with self.assertRaisesRegex(PolicyError, "symlink"):
                gc.prune(alias)

    def test_bounded_cache_rejects_growth(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(PolicyError, "exceeds"):
                gc.reserve(Path(folder), gc.MAX_BYTES + 1)

    def test_written_jpeg_is_private_and_gc_scoped(self):
        with tempfile.TemporaryDirectory() as folder:
            frame = {"imageBase64": base64.b64encode(b"\xff\xd8jpeg\xff\xd9").decode()}
            with patch.object(visible_desktop, "EVIDENCE", Path(folder)):
                filename = visible_desktop._write_image("after-" + self.receipt + ".jpg", frame)
                path = Path(filename)
                self.assertEqual(b"\xff\xd8jpeg\xff\xd9", path.read_bytes())
                self.assertEqual(0o600, path.stat().st_mode & 0o777)
                with self.assertRaises(FileExistsError):
                    visible_desktop._write_image(path.name, frame)
                with self.assertRaisesRegex(PolicyError, "unsafe generated"):
                    visible_desktop._write_image("video-export.mp4", frame)


    def test_recognized_review_previews_expire_unknown_photos_remain(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            expired = root / "preview-aabbccddeeff.jpg"
            fresh = root / "whisper-progress-2.jpg"
            unknown = root / "family-photo.jpg"
            source = root / "user-media.mp4"
            for file in (expired, fresh, unknown, source):
                file.write_bytes(b"original-or-review")
            now = time.time()
            os.utime(expired, (now - 2000, now - 2000))
            os.utime(unknown, (now - 2400, now - 2400))
            result = gc.prune(root, now=now)
            self.assertEqual(1, result["removed"])
            self.assertFalse(expired.exists())
            for file in (fresh, unknown, source):
                self.assertTrue(file.exists())

    def test_expired_before_preview_is_pruned_without_touching_media(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            before = root / "preview-before-aabbccddeeff.jpg"
            fresh = root / "preview-before-112233445566.jpg"
            original = root / "source.mp4"
            unknown = root / "user-photo.jpg"
            for file in (before, fresh, original, unknown):
                file.write_bytes(b"preserve-or-preview")
            now = time.time()
            os.utime(before, (now - 1900, now - 1900))
            os.utime(unknown, (now - 5000, now - 5000))
            result = gc.prune(root, now=now)
            self.assertEqual(1, result["removed"])
            self.assertFalse(before.exists())
            self.assertTrue(fresh.exists())
            self.assertEqual(b"preserve-or-preview", original.read_bytes())
            self.assertTrue(unknown.exists())

    def test_before_preview_symlink_never_followed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            media = root / "source.mp4"
            media.write_bytes(b"untouched")
            (root / "preview-before-aabbccddeeff.jpg").symlink_to(media)
            with self.assertRaisesRegex(PolicyError, "Unsafe CCER diagnostic"):
                gc.prune(root)
            self.assertEqual(b"untouched", media.read_bytes())

    def test_diagnostic_symlink_refused_without_deleting_original(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.mp4"
            source.write_bytes(b"original")
            (root / "preview-aabbccddeeff.jpg").symlink_to(source)
            with self.assertRaisesRegex(PolicyError, "Unsafe CCER diagnostic"):
                gc.prune(root)
            self.assertEqual(b"original", source.read_bytes())

    def test_oversized_preview_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            preview = root / "srt-portal-preview.jpg"
            with preview.open("wb") as out:
                out.truncate(gc._MAX_DIAGNOSTIC_BYTES + 1)
            with self.assertRaisesRegex(PolicyError, "Unsafe CCER diagnostic"):
                gc.prune(root)
            self.assertTrue(preview.exists())

if __name__ == "__main__":
    unittest.main()
