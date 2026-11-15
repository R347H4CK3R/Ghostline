"""Resume only the verified, already-uploaded build8 draft; never upload or create."""
import json,os
import publish_preview8 as p
RELEASE=445985460
PUBLICATION='09d9e94d2ceb79555f627cdde0bbfeeb92fa2ddc'
ASSETS={
 'character-inspection.json':(750691754,394,'sha256:19de2b2c909ed133949c17a028e9c53c55c86886f41e4498eebcec0e1e22a9e7'),
 'dependency-notices.json':(750691934,12898,'sha256:4abf28c2e4f8a02c264efcbb14b4cf7ff6dad225be8ed1e8125765d7a7e5e889'),
 'packaging-status.json':(750691854,394,'sha256:0e91012763c7036f04183b689aa7338888bf398a3c4c4c9e99398d98d29ecdd4'),
 'release-metadata.json':(750691884,636,'sha256:c91a2e30ae6226f8ff67d6c4a1b59426cdc649949bf9d8b86e270b4858933ff0'),
 'source-proof.json':(750691811,9922,'sha256:a2572a8905a2a02238a026fb65e28a8e1a5feb3f7676335a0dccf1b782d3c461'),
 p.IPA:(750690618,p.IPA_BYTES,'sha256:'+p.IPA_HASH),
}
def validate(release,tag):
 p.validate_release_identity(release,tag,PUBLICATION)
 assert release['id']==RELEASE and release['body']==p.NOTES
 assert type(release['draft']) is bool
 names=[x['name'] for x in release['assets']]
 assert len(names)==len(set(names)) and set(names)==set(ASSETS)
 for a in release['assets']:
  assert (a['id'],a['size'],a['digest'])==ASSETS[a['name']] and a['state']=='uploaded'
  if not release['draft']:
   assert a['browser_download_url']==f'https://github.com/{p.REPO}/releases/download/{p.TAG}/{a["name"]}'
def main():
 assert os.environ['GITHUB_REPOSITORY']==p.REPO
 for run,source,path in [(p.RUN,p.SOURCE,'.github/workflows/iphone-build8.yml'),(p.VERIFY_RUN,'a4b162b119b011ca2c29311101745c17a7bc2271','.github/workflows/verify-build8-artifact.yml'),(p.FULL_UI_RUN,p.FULL_UI_SOURCE,'.github/workflows/character-ui-smoke.yml'),(p.UI_RUN,p.UI_SOURCE,'.github/workflows/character-ui-smoke.yml')]:
  p.validate_run(p.api(f'repos/{p.DEV}/actions/runs/{run}'),source,path)
 tag=p.api(f'repos/{p.REPO}/git/ref/tags/{p.TAG}')
 release=p.api(f'repos/{p.REPO}/releases/{RELEASE}');validate(release,tag)
 entry=dict(version='0.4.9',buildVersion='8',date='2026-11-15',downloadURL=f'https://github.com/{p.REPO}/releases/download/{p.TAG}/{p.IPA}',localizedDescription=p.DESCRIPTION,minOSVersion='26.0',size=p.IPA_BYTES,sha256=p.IPA_HASH)
 _,_,feeds=p.get_feeds()
 for name,feed in feeds.items():p.new_feed(feed,entry,name)
 # Only publish exact existing draft with all six inspected assets. No upload or deletion.
 if release['draft']:
  p.api(f'repos/{p.REPO}/releases/{RELEASE}','PATCH',dict(draft=False,prerelease=True,make_latest='false'))
 release=p.api(f'repos/{p.REPO}/releases/{RELEASE}');validate(release,p.api(f'repos/{p.REPO}/git/ref/tags/{p.TAG}'))
 assert not release['draft'];entry['date']=release['published_at'][:10]
 commit=p.sync_catalogs(entry)
 print(json.dumps(dict(releaseURL=release['html_url'],catalogCommit=commit,source=p.SOURCE,publicationSource=PUBLICATION,recoverySource=os.environ['GITHUB_SHA'],sha256=p.IPA_HASH,size=p.IPA_BYTES,unfinishedPreview=True),indent=2))
if __name__=='__main__':main()
