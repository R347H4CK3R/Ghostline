import sys,tempfile,unittest,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
from package_ipa import package
class UnicodePackagingTests(unittest.TestCase):
 def test_decomposed_macos_filename_is_canonical_in_ipa(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);payload=p/'Payload';app=payload/'VoiceMatrix.app';app.mkdir(parents=True)
   (app/'Luci\u0301a.bin').write_bytes(b'voice payload')
   package(payload,p/'app.ipa')
   with zipfile.ZipFile(p/'app.ipa') as z:self.assertEqual(z.read('Payload/VoiceMatrix.app/Lucía.bin'),b'voice payload')
