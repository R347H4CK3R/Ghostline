import hashlib, importlib.util, json, tempfile, unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('assets',Path(__file__).parents[1]/'tools/assets.py')
a=importlib.util.module_from_spec(spec)
if spec.loader: spec.loader.exec_module(a)
class AssetsTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
  (self.root/'voice.bin').write_bytes(b'voice')
  self.entry={'path':'voice.bin','sha256':hashlib.sha256(b'voice').hexdigest(),'size':5}
 def tearDown(self): self.tmp.cleanup()
 def test_valid_asset(self): self.assertEqual(a.validate(self.root,[self.entry]),5)
 def test_changed_asset(self):
  (self.root/'voice.bin').write_bytes(b'wrong')
  with self.assertRaises(ValueError): a.validate(self.root,[self.entry])
 def test_missing_asset(self):
  (self.root/'voice.bin').unlink()
  with self.assertRaises(ValueError): a.validate(self.root,[self.entry])
 def test_path_traversal(self):
  with self.assertRaises(ValueError): a.validate(self.root,[dict(self.entry,path='../voice.bin')])
 def test_duplicate_path(self):
  with self.assertRaises(ValueError): a.validate(self.root,[self.entry,self.entry])
 def test_duplicate_profile(self):
  p={'id':'a','sha256':'0'*64}
  with self.assertRaises(ValueError): a.unique_profiles([p,dict(p,id='b')])
if __name__=='__main__': unittest.main()

class TensorTests(unittest.TestCase):
 def test_metadata_does_not_make_a_distinct_voice(self):
  import struct
  def tensor(label):
   header=json.dumps({'emb':{'dtype':'F32','shape':[1,1,2],'data_offsets':[0,8]},'__metadata__':{'label':label}}).encode()
   return struct.pack('<Q',len(header))+header+struct.pack('<ff',0.2,0.4)
  self.assertEqual(a.tensor_digest(tensor('first')),a.tensor_digest(tensor('second')))
 def test_nonfinite_conditioning_rejected(self):
  import struct
  h=json.dumps({'emb':{'dtype':'F32','shape':[1,1,2],'data_offsets':[0,8]}}).encode()
  with self.assertRaises(ValueError): a.tensor_digest(struct.pack('<Q',len(h))+h+struct.pack('<ff',float('nan'),1))

class QAReportTests(unittest.TestCase):
 def setUp(self):
  self.lock={'revision':'pinned','voices':[{'id':'a','sha256':'1'*64}]}
  self.report={'modelRevision':'pinned','profiles':[{'id':'a','embeddingSHA256':'1'*64,'audioSeconds':1.5,'elapsedSeconds':2.0,'nonSilentWAVDecoded':True}]}
 def test_valid_report(self): self.assertEqual(a.validate_qa_report(self.report,self.lock),1)
 def test_wrong_embedding(self):
  self.report['profiles'][0]['embeddingSHA256']='2'*64
  with self.assertRaises(ValueError): a.validate_qa_report(self.report,self.lock)
 def test_missing_voice(self):
  self.report['profiles']=[]
  with self.assertRaises(ValueError): a.validate_qa_report(self.report,self.lock)
 def test_failed_generation(self):
  self.report['profiles'][0]['nonSilentWAVDecoded']=False
  with self.assertRaises(ValueError): a.validate_qa_report(self.report,self.lock)
