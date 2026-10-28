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

if __name__ == "__main__":
    unittest.main()
