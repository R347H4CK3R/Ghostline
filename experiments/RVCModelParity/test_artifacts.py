import pathlib,tempfile,unittest
from artifacts import manifest,verify
class Artifacts(unittest.TestCase):
 def test_manifest_binds_every_generated_byte(self):
  with tempfile.TemporaryDirectory() as t:
   p=pathlib.Path(t);(p/'a.bin').write_bytes(b'actual bytes');m=manifest(p,['a.bin'],'1'*40)
   verify(p,m,'1'*40)
   (p/'a.bin').write_bytes(b'changed');self.assertRaises(ValueError,verify,p,m,'1'*40)
 def test_path_and_source_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   p=pathlib.Path(t);(p/'a.bin').write_bytes(b'a');m=manifest(p,['a.bin'],'1'*40)
   self.assertRaises(ValueError,verify,p,m,'2'*40)
   m['files'][0]['name']='../a.bin';self.assertRaises(ValueError,verify,p,m,'1'*40)
 def test_duplicate_and_symlink_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   p=pathlib.Path(t);(p/'a.bin').write_bytes(b'a');self.assertRaises(ValueError,manifest,p,['a.bin','a.bin'],'1'*40)
   (p/'b.bin').symlink_to(p/'a.bin');self.assertRaises(ValueError,manifest,p,['b.bin'],'1'*40)
if __name__=='__main__':unittest.main()
