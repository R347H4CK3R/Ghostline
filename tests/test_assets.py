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
