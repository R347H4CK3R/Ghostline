import json,pathlib,tempfile,unittest,wave,zipfile
from tools import voice_pack

class CharacterFolderTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name)
  self.audio=self.root/'original.wav'
  with wave.open(str(self.audio),'wb') as w:
   w.setparams((1,2,24000,0,'NONE','not compressed'));w.writeframes(b'\x00\x10'*24000)
  self.meta=dict(id='original-test',name='Original Test',categories=['Animation','Fantasy'],source='Test fixture',permission='Original synthetic fixture',referenceText='A test reference.')
  self.pack=voice_pack.export_reference_pack(self.audio,self.meta,self.root/'test.vmpack')
 def tearDown(self):self.tmp.cleanup()
 def export(self,packs):
  self.assertTrue(hasattr(voice_pack,'export_collection_folder'),'Native collection folder exporter missing')
  return voice_pack.export_collection_folder(packs,self.root/'Voices')
 def test_real_folder_and_exact_reference(self):
  folder=self.export([self.pack]);index=json.loads((folder/'collection.json').read_text())
  self.assertEqual(index['voices'],[{'id':'original-test','folder':'original-test'}])
  self.assertEqual((folder/'original-test/reference.wav').read_bytes(),self.audio.read_bytes())
  m=json.loads((folder/'original-test/manifest.json').read_text());self.assertFalse(m['trainedModel'])
  self.assertEqual(m['categories'],['Animation','Fantasy'])
 def test_duplicate_id_rejected_before_replacing_old_folder(self):
  folder=self.export([self.pack]);before=(folder/'collection.json').read_bytes()
  with self.assertRaises(ValueError):self.export([self.pack,self.pack])
  self.assertEqual((folder/'collection.json').read_bytes(),before)
 def test_corrupt_pack_cannot_replace_good_collection(self):
  folder=self.export([self.pack]);before=(folder/'collection.json').read_bytes()
  self.pack.write_bytes(b'broken')
  with self.assertRaises(ValueError):self.export([self.pack])
  self.assertEqual((folder/'collection.json').read_bytes(),before)
 def test_existing_destination_is_not_silently_destroyed(self):
  folder=self.root/'Voices';folder.mkdir();(folder/'personal.txt').write_text('keep')
  with self.assertRaises(FileExistsError):self.export([self.pack])
  self.assertEqual((folder/'personal.txt').read_text(),'keep')
 def test_same_reference_under_another_name_is_rejected(self):
  second=dict(self.meta,id='renamed-copy',name='A renamed copy')
  pack=voice_pack.export_reference_pack(self.audio,second,self.root/'second.vmpack')
  with self.assertRaises(ValueError):self.export([self.pack,pack])

if __name__=='__main__':unittest.main()
