import copy, unittest
from tools import publish_voicematrix_047 as publisher

class SyncLogReleaseTests(unittest.TestCase):
 def test_existing_release_must_be_complete_public_and_exact_before_feeds(self):
  source='a'*40
  names=[publisher.IPA,publisher.IPA+'.sha256','character-release-verification.json','dependency-notices.json','speech-evidence.json','conversion-result.json']
  release=dict(tag_name=publisher.TAG,draft=False,prerelease=False,published_at='2026-11-12T00:00:00Z',assets=[dict(name=name,size=10,digest='sha256:'+'b'*64) for name in names])
  report=dict(ipaSHA256='b'*64,ipaBytes=10)
  self.assertTrue(hasattr(publisher,'validate_published_release'),'Must validate published release, not just IPA bytes')
  publisher.validate_published_release(release,dict(type='commit',sha=source),source,report)
  for mutation in [dict(draft=True),dict(prerelease=True),dict(published_at=None),dict(assets=release['assets'][:-1]),dict(tag_name='other')]:
   with self.subTest(mutation=mutation),self.assertRaises(AssertionError):publisher.validate_published_release(dict(release,**mutation),dict(type='commit',sha=source),source,report)
  with self.assertRaises(AssertionError):publisher.validate_published_release(release,dict(type='commit',sha='c'*40),source,report)
  changed=copy.deepcopy(release);changed['assets'][0]['digest']='sha256:'+'c'*64
  with self.assertRaises(AssertionError):publisher.validate_published_release(changed,dict(type='commit',sha=source),source,report)

 def test_publisher_rejects_conflicting_existing_feed_asset(self):
  entry=dict(version='0.4.7',buildVersion='1',downloadURL='https://example.test/app.ipa',sha256='a'*64,size=100)
  feed=dict(apps=[dict(bundleIdentifier='com.voicematrix.app',versions=[dict(entry,sha256='b'*64)])])
  self.assertTrue(hasattr(publisher,'publication_feed'),'Publisher must use feed conflict validation')
  with self.assertRaises(AssertionError):publisher.publication_feed(feed,entry,'Live sync')

 def test_existing_tag_conflict_is_rejected_before_publication(self):
  self.assertTrue(hasattr(publisher,'validate_tag_target'),'Existing tag must be checked before release creation')
  publisher.validate_tag_target(None,'a'*40)
  publisher.validate_tag_target(dict(type='commit',sha='a'*40),'a'*40)
  with self.assertRaises(AssertionError):publisher.validate_tag_target(dict(type='commit',sha='b'*40),'a'*40)
  with self.assertRaises(AssertionError):publisher.validate_tag_target(dict(type='tag',sha='a'*40),'a'*40)
