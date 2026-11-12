import importlib, pathlib, unittest
class BuildTwoReleaseTests(unittest.TestCase):
 def test_identity_never_overwrites_build_one(self):
  p=importlib.import_module('tools.publish_voicematrix_049_build2')
  self.assertEqual(p.VERSION,'0.4.9');self.assertEqual(p.BUILD,'2')
  self.assertEqual(p.TAG,'voicematrix-v0.4.9-build2')
  self.assertEqual(p.IPA,'VoiceMatrix-0.4.9-build2.ipa')
  self.assertEqual(len(p.REQUIRED_GATES),8)
  self.assertEqual(set(p.GATES),set(p.REQUIRED_GATES))
  self.assertIn('not finished 1.0.0',p.NOTES)
  self.assertIn('physical iPhone',p.NOTES)
 def test_package_and_feed_explicitly_require_build_two(self):
  s=pathlib.Path('tools/publish_voicematrix_049_build2.py').read_text()
  self.assertIn('expected_build=BUILD',s)
  self.assertIn('buildVersion=BUILD',s)
  self.assertNotIn('buildVersion="1"',s)
  self.assertIn('local-pipeline/pipeline-evidence.json',s)
  self.assertIn('sourceCommit',s)
  self.assertIn('--prerelease',s)

 def test_published_assets_and_prerelease_identity(self):
  p=importlib.import_module('tools.publish_voicematrix_049_build2')
  names=[p.IPA,p.IPA+'.sha256','character-release-verification.json','dependency-notices.json','speech-evidence.json','conversion-result.json','pipeline-evidence.json']
  release=dict(tag_name=p.TAG,draft=False,prerelease=True,published_at='2026-11-12',assets=[dict(name=n,size=10,digest='sha256:'+'b'*64) for n in names])
  target=dict(type='commit',sha='a'*40);report=dict(ipaSHA256='b'*64,ipaBytes=10)
  p.validate_published_release(release,target,'a'*40,report)
  for change in [dict(draft=True),dict(prerelease=False),dict(assets=release['assets'][:-1]),dict(tag_name='voicematrix-v0.4.9')]:
   with self.assertRaises(AssertionError):p.validate_published_release(dict(release,**change),target,'a'*40,report)
