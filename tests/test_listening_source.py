import importlib.util
from pathlib import Path
import plistlib
import tempfile
import unittest
import zipfile
import hashlib
spec=importlib.util.spec_from_file_location('listening_source',Path(__file__).parents[1]/'tools/listening_source.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class ListeningSourceTests(unittest.TestCase):
    def make_ipa(self,path,build='10'):
        with zipfile.ZipFile(path,'w') as z:
            z.writestr('Payload/VoiceMatrix.app/Info.plist',plistlib.dumps(dict(CFBundleIdentifier='com.voicematrix.app',CFBundleShortVersionString='0.3.2',CFBundleVersion=build,MinimumOSVersion='26.0')))
    def test_exact_identity_size_hash_and_release_urls(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.ipa';self.make_ipa(p);feed=m.generate(p);v=feed['apps'][0]['versions'][0]
            self.assertEqual(v['size'],p.stat().st_size);self.assertEqual(v['sha256'],hashlib.sha256(p.read_bytes()).hexdigest())
            self.assertEqual(feed['sourceURL'],m.BASE+'/livecontainer-listening.json');self.assertEqual(v['downloadURL'],m.BASE+'/'+m.IPA_NAME)
            self.assertEqual(len(feed['apps'][0]['versions']),1)
    def test_wrong_build_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.ipa';self.make_ipa(p,'9')
            with self.assertRaises(ValueError):m.generate(p)
