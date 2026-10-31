"""Native setup tested on tiny disposable Git repositories; never launches Concat."""
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import subprocess
import unittest
from unittest.mock import patch
from ccer import native_setup as setup


class NativeSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.file = self.source / "src/crates/concat/src/ccer_server.rs"
        self.file.parent.mkdir(parents=True)
        self.file.write_text("original\n")
        self.git("init", "-q")
        self.git("add", ".")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "commit", "-qm", "base")
        self.base = self.git("rev-parse", "HEAD")
        self.git("remote", "add", "origin", setup.UPSTREAM)
        self.file.write_text("patched\n")
        patch_data = subprocess.run(["git", "diff", "--", "src/crates/concat/src/ccer_server.rs"],
                                    cwd=self.source, check=True, capture_output=True).stdout
        self.patch_dir = self.root / "patches"
        self.patch_dir.mkdir()
        self.patch_path = self.patch_dir / "fixture.patch"
        self.patch_path.write_bytes(patch_data)
        self.digests = (("fixture.patch", hashlib.sha256(patch_data).hexdigest()),)
        self.git("checkout", "--", "src/crates/concat/src/ccer_server.rs")
        self.dest = self.root / "new-native"
        for attr, value in (("ROOT", self.root), ("BASE", self.base), ("EXPECTED_FILES", {})):
            guard = patch.object(setup, attr, value)
            guard.start()
            self.addCleanup(guard.stop)

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.source, check=True,
                              text=True, capture_output=True).stdout.strip()

    def prepare(self, patches=None):
        return setup.prepare(self.source, self.dest, patch_dir=self.patch_dir,
                             patches=patches if patches is not None else self.digests)

    def test_offline_patch_integrity(self):
        self.assertEqual(setup.patches_verified(self.patch_dir, self.digests), [self.patch_path])
        self.patch_path.write_text("modified")
        with self.assertRaisesRegex(setup.SetupError, "SHA-256"):
            self.prepare()
        self.assertFalse(self.dest.exists())

    def test_prepare_verify_idempotent(self):
        self.assertEqual(self.prepare(), self.dest)
        self.assertEqual((self.dest / "src/crates/concat/src/ccer_server.rs").read_text(), "patched\n")
        self.assertEqual(self.prepare(), self.dest)
        self.assertEqual(setup.verify(self.dest, patches=self.digests), self.dest)
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertEqual(self.git("rev-parse", "HEAD"), self.base)

    def test_manifest_tamper_refused(self):
        self.prepare()
        (self.dest / ".ccer-native-manifest.json").write_text('{"incorrect":true}')
        with self.assertRaisesRegex(setup.SetupError, "manifest"):
            setup.verify(self.dest, patches=self.digests)

    def test_modified_native_file_refused(self):
        self.prepare()
        with patch.object(setup, "EXPECTED_FILES", {"src/crates/concat/src/ccer_server.rs": "0" * 64}):
            with self.assertRaisesRegex(setup.SetupError, "certified native fork"):
                setup.verify(self.dest, patches=self.digests)

    def test_network_opt_in_requires_build_and_forwards_choice(self):
        with patch.object(setup, "patches_verified", return_value=[]):
            self.assertEqual(setup.main(["--check", "--allow-downloads"]), 1)
            with patch.object(setup, "build", return_value=self.root / "concat") as build:
                self.assertEqual(setup.main(["--build", "--allow-downloads"]), 0)
                build.assert_called_once_with(setup.DEST, None, True)

    def test_dirty_source_refused(self):
        self.file.write_text("unsaved\n")
        with self.assertRaisesRegex(setup.SetupError, "local edits"):
            self.prepare()
        self.assertFalse(self.dest.exists())

    def test_unofficial_remote_refused(self):
        self.git("remote", "set-url", "origin", "https://example.invalid/forged")
        with self.assertRaisesRegex(setup.SetupError, "official Concat"):
            self.prepare()

    def test_bad_later_patch_rolls_back(self):
        bad = self.patch_dir / "bad.patch"
        bad.write_text("not a git diff\n")
        patches = self.digests + (("bad.patch", hashlib.sha256(bad.read_bytes()).hexdigest()),)
        with self.assertRaises(setup.SetupError):
            self.prepare(patches)
        self.assertFalse(self.dest.exists())
        self.assertEqual(self.git("worktree", "list", "--porcelain").count("worktree "), 1)

    def test_existing_directory_preserved(self):
        self.dest.mkdir()
        (self.dest / "valuable.txt").write_text("KEEP")
        with self.assertRaisesRegex(setup.SetupError, "manifest"):
            self.prepare()
        self.assertEqual((self.dest / "valuable.txt").read_text(), "KEEP")

    def test_external_path_and_symlink_refused(self):
        with self.assertRaisesRegex(setup.SetupError, "inside CCER"):
            setup.safe_destination(self.root.parent / "elsewhere")
        shortcut = self.root / "shortcut"
        shortcut.symlink_to(self.root)
        with self.assertRaisesRegex(setup.SetupError, "non-symlink"):
            setup.safe_destination(shortcut)


if __name__ == "__main__":
    unittest.main()
