import json,pathlib,tempfile,unittest,wave,os
from tools.voice_pack import export_reference_pack
from tools import master_voices

class PublishTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name);self.master=self.root/'Voices'
 def tearDown(self):self.tmp.cleanup()
 def pack(self,id,value=4000,text='Reference words.'):
  path=self.root/(id+str(value)+'.wav')
  with wave.open(str(path),'wb') as w:
   w.setparams((1,2,24000,0,'NONE','not compressed'));w.writeframes(value.to_bytes(2,'little',signed=True)*24000)
  return export_reference_pack(path,dict(id=id,name=id,categories=['Animation','Fantasy'],source='Synthetic fixture',permission='Original synthetic fixture',referenceText=text),self.root/(id+str(value)+'.vmpack'))
 def publish(self,packs):
  self.assertTrue(hasattr(master_voices,'publish'),'Incremental native-folder publisher is missing')
  return master_voices.publish(packs,self.master)
 def test_append_preserves_existing_voice_and_native_folder_shape(self):
  self.publish([self.pack('first')]);before=(self.master/'first/reference.wav').read_bytes()
  r=self.publish([self.pack('second',6000)])
  index=json.loads((self.master/'collection.json').read_text())
  self.assertEqual(index['voices'],[dict(id='first',folder='first'),dict(id='second',folder='second')])
  self.assertEqual((self.master/'first/reference.wav').read_bytes(),before)
  self.assertEqual(r['added'],['second']);self.assertFalse(r['nativeIOSVerified'])
 def test_changed_existing_voice_is_quarantined_not_activated(self):
  self.publish([self.pack('first')]);before=(self.master/'first/reference.wav').read_bytes();index=(self.master/'collection.json').read_bytes()
  r=self.publish([self.pack('first',6000)])
  self.assertEqual(r['needsReview'],['first']);self.assertEqual((self.master/'collection.json').read_bytes(),index)
  self.assertEqual((self.master/'first/reference.wav').read_bytes(),before)
  candidate=list((self.master.parent/'Voices-Candidates'/'first').glob('*/reference.wav'))
  self.assertEqual(len(candidate),1);self.assertNotEqual(candidate[0].read_bytes(),before)
 def test_idempotent_repeat_does_not_duplicate(self):
  p=self.pack('first');self.publish([p]);r=self.publish([p])
  self.assertEqual(r['unchanged'],['first']);self.assertEqual(r['added'],[])
  self.assertEqual(len(json.loads((self.master/'collection.json').read_text())['voices']),1)
 def test_duplicate_audio_under_new_id_leaves_master_unchanged(self):
  self.publish([self.pack('first')]);before=(self.master/'collection.json').read_bytes()
  with self.assertRaises(ValueError):self.publish([self.pack('second')])
  self.assertEqual((self.master/'collection.json').read_bytes(),before)
  self.assertFalse((self.master/'second').exists())
 def test_bad_pack_cannot_partially_publish_valid_pack(self):
  self.publish([self.pack('first')]);before=(self.master/'collection.json').read_bytes()
  bad=self.root/'bad.vmpack';bad.write_bytes(b'broken')
  with self.assertRaises(ValueError):self.publish([self.pack('second',6000),bad])
  self.assertEqual((self.master/'collection.json').read_bytes(),before);self.assertFalse((self.master/'second').exists())
 def test_conflicting_orphan_folder_is_not_overwritten(self):
  self.publish([self.pack('first')]);orphan=self.master/'second';orphan.mkdir();(orphan/'keep.txt').write_text('keep')
  with self.assertRaises(ValueError):self.publish([self.pack('second',6000)])
  self.assertEqual((orphan/'keep.txt').read_text(),'keep')
 def test_duplicate_id_in_one_batch_is_rejected(self):
  p=self.pack('first')
  with self.assertRaises(ValueError):self.publish([p,p])
  self.assertFalse((self.master/'collection.json').exists())
 def test_symlinked_candidate_parent_cannot_escape_master_location(self):
  self.publish([self.pack('first')]);outside=self.root/'outside';outside.mkdir()
  try:(self.root/'Voices-Candidates').symlink_to(outside,target_is_directory=True)
  except OSError:self.skipTest('Directory symlink creation is unavailable')
  with self.assertRaises(ValueError):self.publish([self.pack('first',6000)])
  self.assertEqual(list(outside.iterdir()),[])
 def test_relative_alias_uses_the_same_exclusive_publisher_lock(self):
  p=self.pack('first');self.publish([p]);old=pathlib.Path.cwd()
  try:
   os.chdir(self.master)
   with master_voices._publish_lock(self.root/'.Voices.publish.lock'):
    for alias in ['.','../Voices']:
     with self.assertRaises(ValueError):master_voices.publish([p],alias)
  finally:os.chdir(old)
 def test_relative_master_places_candidates_beside_master(self):
  self.publish([self.pack('first')]);p=self.pack('first',6000);old=pathlib.Path.cwd()
  try:os.chdir(self.master);master_voices.publish([p],'.')
  finally:os.chdir(old)
  self.assertEqual(len(list((self.root/'Voices-Candidates/first').glob('*/reference.wav'))),1)
  self.assertFalse((self.master/'-Candidates').exists())
 def test_normal_parent_alias_resolves_to_same_master(self):
  actual=self.root/'real-parent';actual.mkdir();alias=self.root/'parent-alias'
  try:alias.symlink_to(actual,target_is_directory=True)
  except OSError:self.skipTest('Directory symlink creation is unavailable')
  p=self.pack('first')
  r=master_voices.publish([p],alias/'Voices')
  self.assertEqual(r['added'],['first'])
  self.assertTrue((actual/'Voices/collection.json').exists())

if __name__=='__main__':unittest.main()
