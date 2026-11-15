import copy,importlib.util,pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools'))
import recover_preview8 as r
class RecoveryTests(unittest.TestCase):
 def release(self):
  return dict(id=r.RELEASE,tag_name=r.p.TAG,target_commitish=r.PUBLICATION,prerelease=True,draft=True,body=r.p.NOTES,assets=[dict(name=n,state='uploaded',id=x[0],size=x[1],digest=x[2],browser_download_url='draft-url') for n,x in r.ASSETS.items()])
 def test_exact_draft_allows_temporary_url(self):r.validate(self.release(),dict(object=dict(type='commit',sha=r.PUBLICATION)))
 def test_identity_asset_and_metadata_mismatches_fail(self):
  for key,value in [('id',1),('tag_name','wrong'),('target_commitish','wrong'),('prerelease',False),('body','wrong')]:
   with self.subTest(key=key),self.assertRaises(AssertionError):r.validate({**self.release(),key:value},dict(object=dict(type='commit',sha=r.PUBLICATION)))
  for key,value in [('id',1),('size',0),('digest','wrong'),('state','open'),('name','extra')]:
   a=self.release();a['assets'][0][key]=value
   with self.subTest(asset=key),self.assertRaises(AssertionError):r.validate(a,dict(object=dict(type='commit',sha=r.PUBLICATION)))
  a=self.release();a['assets'].pop()
  with self.assertRaises(AssertionError):r.validate(a,dict(object=dict(type='commit',sha=r.PUBLICATION)))
 def test_published_requires_final_url(self):
  a=self.release();a['draft']=False
  with self.assertRaises(AssertionError):r.validate(a,dict(object=dict(type='commit',sha=r.PUBLICATION)))
  for x in a['assets']:x['browser_download_url']=f'https://github.com/{r.p.REPO}/releases/download/{r.p.TAG}/{x["name"]}'
  r.validate(a,dict(object=dict(type='commit',sha=r.PUBLICATION)))
 def test_no_upload_create_or_tag_change(self):
  t=pathlib.Path(r.__file__).read_text();self.assertNotIn("'POST'",t);self.assertNotIn('release\',\'upload',t);self.assertIn('if release[\'draft\']:',t)
if __name__=='__main__':unittest.main()
