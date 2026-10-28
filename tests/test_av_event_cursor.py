"""Event pages preserve source times, provenance, safety and bounded memory."""
import unittest
from ccer.av_event_cursor import event_page
from ccer.controls import PolicyError

class EventCursorTests(unittest.TestCase):
    def setUp(self):
        self.report = {
            "window": {"startSeconds": 1, "endSeconds": 5},
            "frames": [{"timeSeconds": 2, "mimeType": "image/jpeg",
                        "imageBase64": "SECRET_JPEG"}],
            "sceneCutsSeconds": [3], "audioSilences": [{"start": 2.5, "end": 2.8}],
            "findings": [{"kind": "black_interval", "startSeconds": .7,
                          "endSeconds": 1.4},
                         {"kind": "freeze_candidate", "timeSeconds": 3.5}],
            "transcriptCues": [{"index": 0, "startSeconds": .8,
                                "endSeconds": 2.2, "text": "Bitcoin",
                                "provenance": "external_srt_unverified"}]}
    def test_source_times_and_no_jpeg_leak(self):
        result = event_page(self.report)
        self.assertEqual(6, result["totalEvents"])
        self.assertEqual(sorted(e["timeSeconds"] for e in result["events"]),
                         [e["timeSeconds"] for e in result["events"]])
        cue = next(e for e in result["events"] if e["kind"] == "supplied_caption")
        self.assertEqual(.8, cue["sourceStartSeconds"])
        self.assertEqual(1, cue["timeSeconds"])
        self.assertNotIn("SECRET_JPEG", str(result))
        self.assertFalse(result["transcriptionPerformed"])
    def test_pagination_and_cursor_stability(self):
        a = event_page(self.report, page_size=2)
        b = event_page(self.report, cursor=a["nextCursor"], page_size=2)
        c = event_page(self.report, cursor=b["nextCursor"], page_size=2)
        self.assertEqual([f"event-{i}" for i in range(6)],
                         [e["id"] for e in a["events"]+b["events"]+c["events"]])
        self.assertIsNone(c["nextCursor"])
        self.assertEqual([], event_page(self.report, cursor=6)["events"])
    def test_invalid_cursor_and_page(self):
        for params in ({"cursor": -1}, {"cursor": 9}, {"cursor": True},
                       {"page_size": 0}, {"page_size": 101}, {"page_size": 1.5}):
            with self.subTest(params=params), self.assertRaises(PolicyError):
                event_page(self.report, **params)
    def test_no_fabricated_speech(self):
        self.report["transcriptCues"][0]["provenance"] = "whisper_verified"
        with self.assertRaises(PolicyError):
            event_page(self.report)
    def test_no_nan_or_unbounded_events(self):
        self.report["sceneCutsSeconds"] = [float("nan")]
        with self.assertRaises(PolicyError):
            event_page(self.report)
        self.report["sceneCutsSeconds"] = [1 + i / 500 for i in range(1001)]
        with self.assertRaises(PolicyError):
            event_page(self.report)
    def test_out_of_window_candidates_excluded(self):
        self.report["sceneCutsSeconds"] = [-3, 8]
        self.report["audioSilences"] = [{"start": 9, "end": 10}]
        kinds = [e["kind"] for e in event_page(self.report)["events"]]
        self.assertNotIn("scene_cut_candidate", kinds)
        self.assertNotIn("audio_silence_candidate", kinds)

if __name__ == "__main__":
    unittest.main()
