"""The model readiness probe is observation-only and fails closed."""
import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ccer import asr_readiness
from ccer.controls import PolicyError


class AsrReadinessTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        root = Path(t.name)
        self.model = root / "app.concat.editor/whisper-models/ggml-small.bin"
        self.model.parent.mkdir(parents=True)
        e = patch.dict(os.environ, {"XDG_DATA_HOME": str(root)})
        e.start()
        self.addCleanup(e.stop)
        m = patch.object(asr_readiness, "_available_memory", return_value=8 * 1024**3)
        m.start()
        self.addCleanup(m.stop)
        l = patch.object(os, "getloadavg", return_value=(0, 0, 0))
        l.start()
        self.addCleanup(l.stop)

    def test_missing_not_inferred(self):
        r = asr_readiness.status()
        self.assertFalse(r["installed"])
        self.assertFalse(r["modelLoaded"])
        self.assertFalse(r["transcriptionPerformed"])
        self.assertFalse(r["downloadPerformed"])

    def test_size_does_not_mean_hash_verified(self):
        self.model.write_bytes(b"demo")
        with patch.object(asr_readiness, "MODEL_BYTES", 4):
            r = asr_readiness.status()
        self.assertTrue(r["installed"])
        self.assertEqual("not_verified", r["integrity"])

    def test_hash_opt_in_and_invalid_hash(self):
        contents = b"speech-model-test"
        self.model.write_bytes(contents)
        with (patch.object(asr_readiness, "MODEL_BYTES", len(contents)),
              patch.object(asr_readiness, "MODEL_SHA256", hashlib.sha256(contents).hexdigest())):
            self.assertTrue(asr_readiness.status(verify_sha256=True)["digestVerified"])
        with (patch.object(asr_readiness, "MODEL_BYTES", len(contents)),
              patch.object(asr_readiness, "MODEL_SHA256", "0" * 64)):
            self.assertEqual("mismatch", asr_readiness.status(verify_sha256=True)["integrity"])

    def test_symlink_rejected(self):
        target = self.model.parent / "other"
        target.write_bytes(b"demo")
        self.model.symlink_to(target)
        self.assertEqual("not_owner_regular_file",
                         asr_readiness.status()["invalidReason"])

    def test_load_pressure_no_model_run(self):
        self.model.write_bytes(b"x")
        with (patch.object(asr_readiness, "MODEL_BYTES", 1),
              patch.object(asr_readiness, "_available_memory", return_value=1024)):
            self.assertEqual("defer_heavy_transcription",
                             asr_readiness.status()["resourceAdvisory"])
        with self.assertRaises(PolicyError):
            asr_readiness.status(verify_sha256="no")

    def test_mcp_is_observe_only(self):
        from ccer.direct_gateway import READ_CCER
        from ccer.production import Production
        from ccer.server import Gateway
        from tests.test_ccer import FakeConcat
        self.assertIn("ccer_asr_status", READ_CCER)
        with patch.object(asr_readiness, "status", return_value={"installed":True}) as fn:
            with tempfile.TemporaryDirectory() as root:
                self.assertEqual({"installed":True},
                                 Production(FakeConcat(), root).run("ccer_asr_status", {"verifySha256":False}))
                fn.assert_called_once_with(verify_sha256=False)
                row = next(t for t in Gateway(FakeConcat(), root).catalogue
                           if t["name"] == "ccer_asr_status")
                self.assertTrue(row["annotations"]["readOnlyHint"])
