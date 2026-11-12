import hashlib,pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class PinnedManifestCheckoutTests(unittest.TestCase):
 def test_autocrlf_checkout_preserves_pinned_manifest_bytes(self):
  original=(ROOT/'tools/asr-resource-lock.json').read_bytes()
  with tempfile.TemporaryDirectory() as tmp:
   repo=pathlib.Path(tmp);(repo/'tools').mkdir()
   (repo/'tools/asr-resource-lock.json').write_bytes(original)
   attr=ROOT/'.gitattributes'
   if attr.exists():(repo/'.gitattributes').write_bytes(attr.read_bytes())
   def git(*args):return subprocess.run(['git','-C',str(repo),*args],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
   git('init');git('config','core.autocrlf','true');git('add','.')
   (repo/'tools/asr-resource-lock.json').unlink();git('checkout-index','-a','-f')
   actual=(repo/'tools/asr-resource-lock.json').read_bytes()
   self.assertEqual(hashlib.sha256(actual).hexdigest(),hashlib.sha256(original).hexdigest())
