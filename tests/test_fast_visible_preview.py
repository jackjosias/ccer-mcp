import unittest
from unittest.mock import patch
from ccer.controls import PolicyError
from ccer.fast_visible_preview import benchmark,preview

JPEG=bytes.fromhex("ffd8")+b"p"*600+bytes.fromhex("ffd9")
STATE={"pid":12345,"display":":1"}
WINDOW=[{"windowId":"0x03c00005","pid":12345,"title":"Concat"}]

class FastVisiblePreviewTests(unittest.TestCase):
    def test_bounds_fail_closed(self):
        for n in (0,6,True,2.2,"3"):
            with self.assertRaises(PolicyError): benchmark(n)
    def test_no_live_app(self):
        with patch("ccer.fast_visible_preview.desktop._file_state",return_value=None),patch(
             "ccer.fast_visible_preview.desktop._live",return_value=False):
            with self.assertRaisesRegex(PolicyError,"attested visible"): preview()
    def test_window_identity_fail_closed(self):
        for windows in ([],[dict(WINDOW[0],pid=99)],[WINDOW[0],WINDOW[0]]):
            with patch("ccer.fast_visible_preview.desktop._file_state",return_value=STATE),patch(
                 "ccer.fast_visible_preview.desktop._live",return_value=True),patch(
                 "ccer.fast_visible_preview.desktop._desktop",return_value=":1"),patch(
                 "ccer.fast_visible_preview.desktop._windows",return_value=windows),patch(
                 "ccer.fast_visible_preview.frame") as capture:
                with self.assertRaises(PolicyError): preview()
                capture.assert_not_called()
    def test_display_mismatch_denied(self):
        with patch("ccer.fast_visible_preview.desktop._file_state",return_value=STATE),patch(
             "ccer.fast_visible_preview.desktop._live",return_value=True),patch(
             "ccer.fast_visible_preview.desktop._desktop",return_value=":2"),patch(
             "ccer.fast_visible_preview.frame") as capture:
            with self.assertRaises(PolicyError): preview()
            capture.assert_not_called()
    def test_window_change_refuses_preview(self):
        with patch("ccer.fast_visible_preview.desktop._file_state",return_value=STATE),patch(
             "ccer.fast_visible_preview.desktop._live",return_value=True),patch(
             "ccer.fast_visible_preview.desktop._desktop",return_value=":1"),patch(
             "ccer.fast_visible_preview.desktop._windows",side_effect=[WINDOW,[]]),patch(
             "ccer.fast_visible_preview.frame",return_value=JPEG):
            with self.assertRaisesRegex(PolicyError,"identity changed"): preview()
    def test_uses_existing_ffmpeg_without_input_or_action_authority(self):
        with patch("ccer.fast_visible_preview.desktop._file_state",return_value=STATE),patch(
             "ccer.fast_visible_preview.desktop._live",return_value=True),patch(
             "ccer.fast_visible_preview.desktop._desktop",return_value=":1"),patch(
             "ccer.fast_visible_preview.desktop._windows",return_value=WINDOW),patch(
             "ccer.fast_visible_preview.frame",return_value=JPEG) as capture:
            result=preview()
        self.assertEqual(result["jpeg"],JPEG)
        self.assertFalse(result["physicalInputUsed"])
        self.assertFalse(result["actionAuthority"])
        self.assertFalse(result["slintReceipt"])
        self.assertEqual(capture.call_count,1)
        self.assertEqual(capture.call_args.args[1],"0x03c00005")
    def test_benchmark_does_not_save_images(self):
        with patch("ccer.fast_visible_preview.preview",return_value={"latencyMs":310.0,"jpegBytes":602}):
            result=benchmark(3)
        self.assertEqual(result["medianMs"],310.0)
        self.assertEqual(result["savedFrames"],0)
        self.assertFalse(result["actionAuthority"])
