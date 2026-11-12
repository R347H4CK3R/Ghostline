"""Run real Swift RVC contract/lifecycle checks; never substitute a fake compiler."""
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).parents[1]


class RVCOnlineNativeTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('swiftc'), 'Native Swift compiler is unavailable')
    def test_rvc_contract_and_lifecycle(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = pathlib.Path(directory) / 'rvc-online-checks'
            subprocess.run([
                'swiftc', '-strict-concurrency=complete', '-warnings-as-errors',
                str(ROOT / 'VoiceMatrix/RVCOnlineModels.swift'),
                str(ROOT / 'VoiceMatrix/RVCOnlineSession.swift'),
                str(ROOT / 'VoiceMatrix/RVCOnlineRefreshSchedule.swift'),
                str(ROOT / 'tests/native/RVCOnlineChecks.swift'),
                '-o', str(binary),
            ], check=True)
            subprocess.run([str(binary), str(ROOT / 'tests/fixtures/rvc_wav')], check=True, timeout=30)
