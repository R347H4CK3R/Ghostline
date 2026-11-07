import io,json,pathlib,tempfile,unittest,wave,zipfile
from tools.voice_pack import export_reference_pack, validate_pack

class VoicePackTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name)
  self.audio=self.root/'reference.wav'
  with wave.open(str(self.audio),'wb') as w:
   w.setparams((1,2,24000,0,'NONE','not compressed'));w.writeframes(b'\x00\x10'*24000)
  self.meta=dict(id='original-voice',name='Original Voice',categories=['Animation','Fantasy'],source='Consented recording',permission='Creator authorized',referenceText='A clean reference sentence.')
 def tearDown(self):self.tmp.cleanup()
 def test_roundtrip(self):
  p=export_reference_pack(self.audio,self.meta,self.root/'voice.vmpack');m=validate_pack(p)
  self.assertEqual(m['kind'],'f5-reference');self.assertEqual(m['categories'],['Animation','Fantasy']);self.assertFalse(m['trainedModel']);self.assertEqual(m['engine'],'F5TTS_v1_Base')
 def test_missing_provenance_rejected(self):
  self.meta['permission']=''
  with self.assertRaises(ValueError):export_reference_pack(self.audio,self.meta,self.root/'bad.vmpack')
 def test_corruption_rejected(self):
  p=export_reference_pack(self.audio,self.meta,self.root/'voice.vmpack')
  with zipfile.ZipFile(p) as z:manifest=z.read('manifest.json')
  with zipfile.ZipFile(p,'w') as z:z.writestr('manifest.json',manifest);z.writestr('reference.wav',b'bad')
  with self.assertRaises(ValueError):validate_pack(p)
 def test_traversal_rejected(self):
  p=export_reference_pack(self.audio,self.meta,self.root/'voice.vmpack')
  with zipfile.ZipFile(p,'a') as z:z.writestr('../outside',b'bad')
  with self.assertRaises(ValueError):validate_pack(p)
 def test_silent_reference_rejected(self):
  with wave.open(str(self.audio),'wb') as w:w.setparams((1,2,24000,0,'NONE','not compressed'));w.writeframes(b'\0\0'*24000)
  with self.assertRaises(ValueError):export_reference_pack(self.audio,self.meta,self.root/'bad.vmpack')

if __name__=='__main__':unittest.main()
