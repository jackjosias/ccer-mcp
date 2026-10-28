import unittest
from ccer.gtk_portal_readonly import snapshot
from ccer.controls import PolicyError

class GtkPortalReadonlyTests(unittest.TestCase):
    def test_denied_wrong_target(self):
        with self.assertRaises(PolicyError):
            snapshot("Unrelated save dialog")
    def test_bound_rejects_invalid(self):
        for n in (-1, 0, 151, True):
            with self.assertRaises(PolicyError):
                snapshot(limit=n)

if __name__ == "__main__":
    unittest.main()
