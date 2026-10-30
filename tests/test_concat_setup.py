"""Regression tests for official release metadata and safe Concat bootstrap."""
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from ccer import concat_setup as setup


class ConcatSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = b"valid-synthetic-AppImage"
        self.sha = hashlib.sha256(self.data).hexdigest()
        self.release = {
            "tag": "v0.2.8", "name": "Concat-0.2.8-x86_64.AppImage",
            "url": "https://github.com/jub0t/Concat/releases/download/v0.2.8/Concat-0.2.8-x86_64.AppImage",
            "size": len(self.data), "sha256": self.sha,
        }

    def payload(self):
        return {"tag_name": self.release["tag"], "assets": [{
            "name": self.release["name"], "browser_download_url": self.release["url"],
            "digest": "sha256:" + self.sha, "size": 1234567,
        }]}

    def test_valid_release_metadata(self):
        found = setup.select_release(self.payload(), "x86_64")
        self.assertEqual(found["sha256"], self.sha)
        self.assertEqual(found["tag"], "v0.2.8")

    def test_refuse_insecure_urls_and_missing_checksums(self):
        for change in [
            {"browser_download_url": "http://github.com/jub0t/Concat/releases/download/v0.2.8/" + self.release["name"]},
            {"browser_download_url": "https://evil.invalid/" + self.release["name"]},
            {"browser_download_url": self.release["url"] + "?token=[REDACTED]"},
            {"digest": None}, {"digest": "sha256:" + "0" * 63}, {"size": 0},
        ]:
            with self.subTest(change=change):
                payload = self.payload()
                payload["assets"][0].update(change)
                with self.assertRaises(setup.SetupError):
                    setup.select_release(payload, "x86_64")

    def test_wrong_version_and_arch_rejected(self):
        payload = self.payload()
        payload["tag_name"] = "latest"
        with self.assertRaises(setup.SetupError):
            setup.select_release(payload, "x86_64")
        with self.assertRaises(setup.SetupError):
            setup.select_release(self.payload(), "aarch64")

    def test_install_is_atomic_idempotent_and_does_not_replay_download(self):
        calls = []
        def downloader(url, target, maximum):
            calls.append(url)
            target.write_bytes(self.data)
            return len(self.data), self.sha
        link = setup.install_release(self.release, home=self.root, downloader=downloader)
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.read_bytes(), self.data)
        self.assertEqual(len(calls), 1)
        second = setup.install_release(self.release, home=self.root, downloader=downloader)
        self.assertEqual(second, link)
        self.assertEqual(len(calls), 1)

    def test_bad_digest_fails_closed_without_activating(self):
        def bad(url, target, limit):
            target.write_bytes(self.data)
            return len(self.data), "0" * 64
        with self.assertRaises(setup.SetupError):
            setup.install_release(self.release, home=self.root, downloader=bad)
        self.assertFalse(setup.managed_binary(self.root).exists())
        self.assertFalse((setup.install_directory(self.root) / self.release["name"]).exists())

    def test_existing_tampered_download_is_not_overwritten(self):
        path = setup.install_directory(self.root) / self.release["name"]
        path.parent.mkdir(parents=True)
        path.write_bytes(b"tampered content")
        with self.assertRaises(setup.SetupError):
            setup.install_release(self.release, home=self.root,
                                  downloader=lambda *_: self.fail("Unexpected download"))
        self.assertEqual(path.read_bytes(), b"tampered content")

    def test_explicit_binary_precedence_and_offline_discovery(self):
        fake = self.root / "my-patched-concat"
        fake.write_bytes(b"patched")
        with patch.dict(os.environ, {"CCER_CONCAT_BIN": str(fake)}):
            self.assertEqual(setup.default_binary(self.root), fake)
        with patch.dict(os.environ, {"CCER_CONCAT_BIN": ""}):
            self.assertEqual(setup.default_binary(self.root), setup.managed_binary(self.root))

    def test_offline_status_never_contacts_github(self):
        with patch.dict(os.environ, {"CCER_CONCAT_BIN": ""}):
            with patch.object(setup, "latest_release", side_effect=AssertionError("No network")):
                self.assertEqual(setup.main(["--status"]), 1)


if __name__ == "__main__":
    unittest.main()
