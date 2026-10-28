import unittest
from unittest.mock import patch
from ccer.controls import PolicyError
from ccer.gtk_portal_save import save_srt, preflight

class GtkPortalSaveTests(unittest.TestCase):
    def test_no_unconfirmed_dialog_mutation(self):
        with patch("ccer.gtk_portal_save.preflight") as p:
            with self.assertRaises(PolicyError):
                save_srt(confirm=False)
            p.assert_not_called()
    def test_preflight_rejects_missing_project(self):
        with patch("ccer.gtk_portal_save.PROJECT") as root:
            root.is_symlink.return_value = False
            root.is_dir.return_value = False
            with self.assertRaises(PolicyError):
                preflight()

    def test_existing_srt_never_overwritten_even_with_confirm(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            target = project / "Untitled project 8.srt"
            target.write_bytes(b"already verified native SRT")
            with patch("ccer.gtk_portal_save.PROJECT", project), \
                 patch("ccer.gtk_portal_save.inspect") as inspect:
                with self.assertRaises(PolicyError):
                    save_srt(confirm=True)
                inspect.assert_not_called()
            self.assertEqual(b"already verified native SRT", target.read_bytes())

    def test_portal_wrong_filename_rejected_before_action(self):
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            fake_project = {"captionQA": {"passed": True},
                            "titleCount": 1, "audioInSourceVideos": True}
            window = SimpleNamespace(stdout='0x3200007 "Exporter en SRT…": ("xdg-desktop-portal-gtk" "Xdg-desktop-portal-gtk")')
            bad_nodes = [{"role": "file chooser", "name": "Exporter en SRT…"},
                         {"role": "text", "text": "Not this project.srt"},
                         {"role": "push button", "name": "Save", "actionCount": 1}]
            with patch("ccer.gtk_portal_save.PROJECT", project), \
                 patch("ccer.gtk_portal_save.inspect", return_value=fake_project), \
                 patch("ccer.gtk_portal_save.subprocess.run", return_value=window), \
                 patch("ccer.gtk_portal_save.snapshot", return_value={"nodes": bad_nodes}):
                with self.assertRaises(PolicyError):
                    preflight()

    def test_portal_duplicate_dialogues_refused(self):
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            verified = {"captionQA": {"passed": True},
                        "titleCount": 1, "audioInSourceVideos": True}
            window = SimpleNamespace(stdout='0x3200007 "Exporter en SRT…": ("xdg-desktop-portal-gtk" "Xdg-desktop-portal-gtk")')
            dialogue = {"role": "file chooser", "name": "Exporter en SRT…"}
            nodes = [dialogue, dialogue, {"role": "text", "text": "Untitled project 8.srt"},
                     {"role": "push button", "name": "Save", "actionCount": 1}]
            with patch("ccer.gtk_portal_save.PROJECT", project), \
                 patch("ccer.gtk_portal_save.inspect", return_value=verified), \
                 patch("ccer.gtk_portal_save.subprocess.run", return_value=window), \
                 patch("ccer.gtk_portal_save.snapshot", return_value={"nodes": nodes}):
                with self.assertRaises(PolicyError):
                    preflight()

if __name__ == "__main__":
    unittest.main()
