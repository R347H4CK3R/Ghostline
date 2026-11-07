import pathlib,tempfile,unittest
from unittest.mock import Mock
from tools.local_f5 import load_local_model

class LocalF5Tests(unittest.TestCase):
 def test_missing_weights_never_initialize_engine(self):
  factory=Mock()
  with self.assertRaisesRegex(ValueError,'Missing local'):load_local_model('missing','missing','missing',factory=factory)
  factory.assert_not_called()
 def test_corrupt_weights_never_initialize_engine(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)
   for name in ['weights','vocab','config.yaml','pytorch_model.bin']:(p/name).write_bytes(b'bad')
   factory=Mock()
   with self.assertRaisesRegex(ValueError,'checksum'):load_local_model(p/'weights',p,p/'vocab',factory=factory)
   factory.assert_not_called()

if __name__=='__main__':unittest.main()
