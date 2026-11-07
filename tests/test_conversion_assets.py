import base64,hashlib,json,struct,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
from assets import conversion_tensor
class ConversionAssetTests(unittest.TestCase):
 def setUp(self):
  self.base=dict(id='base',engine='phonon31m',sha256='b'*64)
  self.profile=dict(id='original',baseVoiceID='base',engine='phonon31m-openvoicev2',converterRevision='pinned')
  self.data=dict(id='original',ttsEmbeddingSHA256='b'*64,converterRevision='pinned',embeddingFP16Base64=base64.b64encode(struct.pack('<256e',*([0.25]*256))).decode())
 def test_compact_conditioning_is_valid_and_metadata_does_not_change_tensor_identity(self):
  first=conversion_tensor(json.dumps(self.data).encode(),self.profile,[self.base,self.profile])
  self.data['note']='This is not another voice'
  self.assertEqual(first,conversion_tensor(json.dumps(self.data).encode(),self.profile,[self.base,self.profile]))
 def test_wrong_base_binding_is_rejected(self):
  self.data['ttsEmbeddingSHA256']='c'*64
  with self.assertRaises(ValueError):conversion_tensor(json.dumps(self.data).encode(),self.profile,[self.base,self.profile])
 def test_nonfinite_conditioning_is_rejected(self):
  self.data['embeddingFP16Base64']=base64.b64encode(struct.pack('<256e',*([float('nan')]*256))).decode()
  with self.assertRaises(ValueError):conversion_tensor(json.dumps(self.data).encode(),self.profile,[self.base,self.profile])
