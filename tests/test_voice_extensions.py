import tempfile
import unittest
from pathlib import Path
from ccer.controls import PolicyError
from ccer.voice_extensions import flite_available, synthesize_flite

class VoiceExtensionTests(unittest.TestCase):
    def test_language_and_voice_guards(self):
        with tempfile.TemporaryDirectory() as d:
            output = Path(d) / "voice.wav"
            with self.assertRaises(PolicyError):
                synthesize_flite("Bonjour", output, language="fr")
            with self.assertRaises(PolicyError):
                synthesize_flite("Hello", output, speaker="kal:evilfilter")
            self.assertFalse(output.exists())

    @unittest.skipUnless(flite_available(), "FFmpeg flite unavailable")
    def test_real_wav_without_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            output = Path(d) / "voice.wav"
            result = synthesize_flite("Hello CCER, this is an offline voice test.", output)
            self.assertTrue(result["verified"])
            self.assertGreater(result["durationSeconds"], 0)
            with self.assertRaises(PolicyError):
                synthesize_flite("Again", output)
