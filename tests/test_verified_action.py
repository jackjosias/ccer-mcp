"""Non-regression checks: one native receipt, one dispatch, no X11."""
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from ccer.controls import PolicyError
from ccer import verified_action


class VerifiedActionTests(unittest.TestCase):
    @patch.object(verified_action.desktop, "act")
    @patch.object(verified_action.desktop, "observe")
    def test_one_snapshot_one_click_without_retry(self, capture, gesture):
        capture.return_value = {
            "pid": 513711, "nativeWidth": 1400, "nativeHeight": 900,
            "image": "/private/before-abcdef012345.jpg"}
        gesture.return_value = {"sent": True, "nativeEvent": "click"}
        result = verified_action.click_once(
            expected_pid=513711, x=1130, y=228, confirmed=True)
        self.assertTrue(result["sent"])
        capture.assert_called_once_with()
        gesture.assert_called_once()
        request = gesture.call_args.args[0]
        self.assertEqual("abcdef012345", request.receipt)
        self.assertEqual((1130, 228), (request.x, request.y))

    @patch.object(verified_action, "_same_screen_except_caret")
    @patch.object(verified_action.desktop, "act")
    @patch.object(verified_action.desktop, "observe")
    def test_blink_pre_dispatch_may_resample_without_double_action(self, capture, gesture, compare):
        frame = {"pid": 513711, "windowId": "concat-main",
                 "nativeWidth": 1400, "nativeHeight": 900,
                 "image": "/private/before-abcdef012345.jpg"}
        capture.side_effect = [frame, dict(frame, image="/private/before-abcdeeff0011.jpg")]
        gesture.side_effect = [
            PolicyError("CCER: desktop changed; recapture before acting"),
            {"sent": True}]
        result = verified_action.click_once(
            expected_pid=513711, x=1130, y=228, confirmed=True)
        self.assertTrue(result["sent"])
        compare.assert_called_once()
        self.assertEqual(2, gesture.call_count)

    @patch.object(verified_action, "_same_screen_except_caret",
                  side_effect=PolicyError("Native scene changed beyond caret animation"))
    @patch.object(verified_action.desktop, "act")
    @patch.object(verified_action.desktop, "observe")
    def test_different_scene_never_attempts_second_click(self, capture, gesture, compare):
        frame = {"pid": 513711, "windowId": "concat-main",
                 "nativeWidth": 1400, "nativeHeight": 900,
                 "image": "/private/before-abcdef012345.jpg"}
        capture.side_effect = [frame, dict(frame, image="/private/before-abcdeeff0011.jpg")]
        gesture.side_effect = PolicyError("CCER: desktop changed; recapture before acting")
        with self.assertRaisesRegex(PolicyError, "Native scene changed"):
            verified_action.click_once(
                expected_pid=513711, x=1130, y=228, confirmed=True)
        gesture.assert_called_once()

    @patch.object(verified_action.desktop, "act")
    @patch.object(verified_action.desktop, "observe")
    def test_unknown_dispatch_never_retries(self, capture, gesture):
        capture.return_value = {"pid": 513711, "nativeWidth": 1400,
                                "nativeHeight": 900,
                                "image": "/private/before-abcdef012345.jpg"}
        gesture.return_value = {"state": "UNKNOWN_DISPATCH"}
        result = verified_action.click_once(
            expected_pid=513711, x=1130, y=228, confirmed=True)
        self.assertEqual("UNKNOWN_DISPATCH", result["state"])
        gesture.assert_called_once()

    @patch.object(verified_action.desktop, "_client")
    def test_reviewed_menu_refuses_outside_click(self, factory):
        with self.assertRaisesRegex(PolicyError, "outside menu bounds"):
            verified_action.click_reviewed_once(
                expected_pid=513711, x=900, y=680,
                approved_image="after-eb17f19f04f3.jpg",
                confirmed=True, menu_only=True)
        factory.assert_not_called()

    @patch.object(verified_action.desktop, "act")
    @patch.object(verified_action.desktop, "observe")
    def test_wrong_pid_rejects_without_act(self, capture, gesture):
        capture.return_value = {
            "pid": 99, "nativeWidth": 1400, "nativeHeight": 900,
            "image": "/private/before-abcdef012345.jpg"}
        with self.assertRaisesRegex(PolicyError, "PID changed"):
            verified_action.click_once(
                expected_pid=513711, x=1130, y=228, confirmed=True)
        gesture.assert_not_called()

    @patch.object(verified_action.desktop, "act")
    @patch.object(verified_action.desktop, "observe")
    def test_no_confirmation_rejects_before_observation(self, capture, gesture):
        with self.assertRaisesRegex(PolicyError, "confirmation"):
            verified_action.click_once(
                expected_pid=513711, x=1130, y=228, confirmed=False)
        capture.assert_not_called()
        gesture.assert_not_called()


    @patch.object(verified_action, "_same_screen_except_caret")
    @patch.object(verified_action.desktop, "_write_image")
    @patch.object(verified_action.desktop, "_client")
    @patch.object(verified_action.desktop, "_live", return_value=True)
    @patch.object(verified_action.desktop, "_file_state",
                  return_value={"pid": 513711})
    def test_reviewed_capture_and_dispatch_share_session(
            self, state, alive, factory, writer, compare):
        native = factory.return_value.__enter__.return_value
        native._width, native._height = 1400, 900
        native.observe.return_value = {"sha256": "a" * 64}
        native.act.return_value = {"frameNo": 2}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "before-abcdef012345.jpg"
            path.write_bytes(b"fixture")
            writer.side_effect = [str(path), str(path)]
            result = verified_action.click_reviewed_once(
                expected_pid=513711, x=35, y=16,
                approved_image="after-eb17f19f04f3.jpg", confirmed=True)
        self.assertTrue(result["sent"])
        native.observe.assert_called_once()
        native.act.assert_called_once_with(
            {"type": "click", "x": 35, "y": 16}, confirm=True,
            expected_sha256="a" * 64)
        compare.assert_called_once()

    @patch.object(verified_action.desktop, "_client")
    def test_reviewed_path_traversal_fails(self, factory):
        with self.assertRaisesRegex(PolicyError, "Approved AFTER"):
            verified_action.click_reviewed_once(
                expected_pid=513711, x=35, y=16,
                approved_image="../unsafe.jpg", confirmed=True)
        factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
