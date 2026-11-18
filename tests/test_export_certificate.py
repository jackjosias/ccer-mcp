import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from ccer.controls import PolicyError
from ccer.export_certificate import timeline, certify

PROJECT={"clips":[{"kind":"text","start":0,"duration":3,"mediaId":""},
                 {"kind":"video","start":3,"duration":2,"mediaId":"m"}],
         "media":[{"id":"m","name":"source.mp4"}]}
META={"streams":[{"codec_type":"video","codec_name":"h264","width":1920,"height":1080,
                  "avg_frame_rate":"24/1"},
                 {"codec_type":"audio","codec_name":"aac","sample_rate":"48000"}],
      "format":{"duration":"5.000"}}
OK=SimpleNamespace(returncode=0,stderr="")
AUDIO=SimpleNamespace(returncode=0,stderr="mean_volume: -24.1 dB")

class ExportCertificateTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(prefix="ccer-cert-")
        self.addCleanup(t.cleanup)
        self.project=Path(t.name)/"concat.json"
        self.export=Path(t.name)/"out.mp4"
        self.project.write_text(json.dumps(PROJECT))
        self.export.write_bytes(b"video placeholder, only mocked ffprobe")
    def run_cert(self, meta=META, decode=OK, audio=AUDIO):
        with patch("ccer.export_certificate.media_probe",return_value=meta),patch(
             "ccer.export_certificate.shutil.which",return_value="/usr/bin/ffmpeg"),patch(
             "ccer.export_certificate.subprocess.run",side_effect=[decode,audio]) as run:
            result=certify(self.project,self.export)
        return result,run
    def test_valid_export_is_read_only(self):
        original=(self.project.read_bytes(),self.export.read_bytes())
        data,run=self.run_cert()
        self.assertTrue(data["passed"])
        self.assertEqual(data["clipCount"],2)
        self.assertEqual(data["audioMeanDb"],-24.1)
        self.assertEqual(data["decode"],"PASS")
        self.assertEqual(run.call_count,2)
        self.assertEqual((self.project.read_bytes(),self.export.read_bytes()),original)
    def test_gap_rejected(self):
        p=json.loads(self.project.read_text())
        p["clips"][1]["start"]=4
        with self.assertRaisesRegex(PolicyError,"gap"):timeline(p)
    def test_no_video_rejected(self):
        with self.assertRaisesRegex(PolicyError,"no real video"):
            timeline({"clips":[{"kind":"text","start":0,"duration":3}],"media":[]})
    def test_missing_media_rejected(self):
        p=json.loads(self.project.read_text());p["clips"][1]["mediaId"]="absent"
        with self.assertRaisesRegex(PolicyError,"source media"):timeline(p)
    def test_mismatched_duration_rejected(self):
        bad={**META,"format":{"duration":"4.3"}}
        with self.assertRaisesRegex(PolicyError,"truncated"):self.run_cert(meta=bad)
    def test_missing_audio_rejected(self):
        bad={**META,"streams":META["streams"][:1]}
        with self.assertRaisesRegex(PolicyError,"AV streams"):self.run_cert(meta=bad)
    def test_bad_codec_rejected(self):
        bad={**META,"streams":[{**META["streams"][0],"codec_name":"hevc"},META["streams"][1]]}
        with self.assertRaisesRegex(PolicyError,"H.264"):self.run_cert(meta=bad)
    def test_silence_rejected(self):
        with self.assertRaisesRegex(PolicyError,"silent"):
            self.run_cert(audio=SimpleNamespace(returncode=0,stderr="mean_volume: -inf dB"))
    def test_corrupt_decode_rejected(self):
        with self.assertRaisesRegex(PolicyError,"decode"):
            self.run_cert(decode=SimpleNamespace(returncode=1,stderr="invalid bitstream"))
    def test_symlink_rejected(self):
        link=self.export.with_name("link.mp4");link.symlink_to(self.export)
        with self.assertRaisesRegex(PolicyError,"untrusted"):
            certify(self.project,link)
    def test_max_duration_guard(self):
        with self.assertRaisesRegex(PolicyError,"budget"):
            certify(self.project,self.export,max_seconds=2)
