import json, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
class RemoveStockLibraryTests(unittest.TestCase):
 def test_removes_profiles_and_preserves_engine_and_personal_data(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory); ph=root/'Phonon'; cv=root/'OpenVoice'
   (ph/'voices').mkdir(parents=True); (cv/'Profiles').mkdir(parents=True)
   (ph/'voices/base.bin').write_bytes(b'voice'); (cv/'Profiles/base.json').write_text('{}')
   (ph/'engine.bin').write_bytes(b'engine'); (cv/'engine.bin').write_bytes(b'converter')
   personal=root/'Documents';personal.mkdir();(personal/'mine.vmvoice').write_bytes(b'personal')
   (ph/'manifest.json').write_text(json.dumps({'voices':[{'id':'base','path':'voices/base.bin'}],'files':[{'path':'voices/base.bin'},{'path':'engine.bin'}],'revision':'same'}))
   (cv/'model-manifest.json').write_text(json.dumps({'files':[{'path':'Profiles/base.json'},{'path':'engine.bin'}]}))
   for name in ['voice-synthesis-results.json','inference-fingerprint.json']:(ph/name).write_text('old profiles')
   result=subprocess.run([sys.executable,str(ROOT/'tools/remove_stock_library.py'),str(root)],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stderr)
   self.assertEqual(json.loads((ph/'manifest.json').read_text())['voices'],[])
   self.assertFalse((ph/'voices/base.bin').exists());self.assertFalse((cv/'Profiles/base.json').exists())
   self.assertEqual(json.loads((ph/'manifest.json').read_text())['files'],[{'path':'engine.bin'}])
   self.assertEqual(json.loads((cv/'model-manifest.json').read_text())['files'],[{'path':'engine.bin'}])
   self.assertEqual((ph/'engine.bin').read_bytes(),b'engine');self.assertEqual((cv/'engine.bin').read_bytes(),b'converter')
   self.assertEqual((personal/'mine.vmvoice').read_bytes(),b'personal')
   self.assertFalse((ph/'voice-synthesis-results.json').exists());self.assertFalse((ph/'inference-fingerprint.json').exists())
