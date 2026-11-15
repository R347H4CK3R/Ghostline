"""Publish only the inspected unfinished build8; never replace old releases."""
import base64,copy,datetime,hashlib,json,os,pathlib,subprocess,sys,zipfile
REPO='R347H4CK3R/Ghostline'
DEV='R347H4CK3R/VoiceMatrix-Development'
SOURCE='9bab67df2040cb64532e3db1502e3f1bfd587d3c'
RUN=43700381325
VERIFY_RUN=43702738247
FULL_UI_RUN=43701134106
FULL_UI_SOURCE='dc99d3d928f80c238d36f7fd634c3cd7344c5667'
UI_RUN=43703719776
UI_SOURCE='c38b2cfb7dd0626ea19b1e608c5d822041899ced'
ARTIFACT=14157246549
ZIP_HASH='c02ea9d57886175a642a103feef9ef4614dd24c9b6712a727f75666119f00aad'
IPA_HASH='c9fb738468f9fb7e0497c6735440416753a81273a1bfa4309985df06a4869284'
IPA_BYTES=1314419227
TAG='voicematrix-v0.4.9-build8'
IPA='VoiceMatrix-0.4.9-build8.ipa'
FEEDS=('strata-source.json','source.json','livecontainer-test.json')
DESCRIPTION='Unfinished preview: MP3/AIFF import, retained-source integrity checks, transcription and screening repairs. Native macOS audio/video fixture pipelines and simulator checks passed; not physical-iPhone or likeness verification. Existing voices retained. Experimental RVC needs compatible imported packs; music separation and reliable overlapping-speaker extraction remain incomplete. Requires sideload signing; not finished 1.0.0.'
NOTES='''VoiceMatrix 0.4.9 build 8 — unfinished development preview

Unsigned ARM64 IPA for iOS 26+, requiring signing through your sideloading setup. Update the existing app without deleting its data.

Compared with build 7: common MP3/AIFF import, retained-media mutation detection, transcription recovery and sound-screening corrections. Existing user voice assets are preserved. No stock celebrity voices or trained RVC profiles are bundled. Experimental RVC requires compatible imported packs. Music separation and reliable overlapping-speaker extraction remain incomplete.

Exact source: 9bab67df2040cb64532e3db1502e3f1bfd587d3c. Packaging run 43700381325 and independent artifact verification 43702738247 passed. Actual macOS audio/video fixture pipelines generated word-checked speech, retained interrupted sources and preserved profiles; these are not physical-iPhone tests or proof of voice likeness. The full suite at package source had one obsolete build5 assertion; separately reviewed test-only correction dc99d3d passed 792 tests on Linux (6 skipped) and macOS (17 skipped), with app/tools/project/package workflow unchanged. The original exact-package-source full UI run 43700381312 passed its first batch but failed the second batch at a scrolling-helper geometry assertion after import/select and long text entry. Targeted repeat 43703719776 on test-only correction c38b2cfb retained all visibility, import, playback and relaunch assertions and passed both tests; app/tools/project/package workflow bytes are unchanged. This is a targeted two-test repeat, not a replacement claim that the original full UI run passed. Separately, full simulator run 43701134106 on test-expectation-only correction dc99d3d passed 55 unit tests and 13 UI tests with unchanged production source. Windows full-suite checks remain blocked by missing Swift tooling. Do not interpret this as all-platform green.

Physical-iPhone installation, performance, human listening, character identity and likeness remain unverified. Not completed 1.0.0.
'''
def gh(*args):return subprocess.check_output(['gh',*args],text=True)
def api(path,method='GET',body=None):
 args=['api',path]
 if method!='GET':args+=['--method',method]
 if body is not None:
  return json.loads(subprocess.check_output(['gh',*args,'--input','-'],input=json.dumps(body),text=True))
 return json.loads(gh(*args))
def digest(p):
 with pathlib.Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def validate_run(r,sha,path):
 assert r['head_sha']==sha and r['path']==path
 assert r['status']=='completed' and r['conclusion']=='success'
 assert r['repository']['full_name']==DEV

def new_feed(feed,entry,name):
 result=copy.deepcopy(feed)
 apps=[a for a in result['apps'] if a.get('bundleIdentifier')=='com.voicematrix.app'];assert len(apps)==1
 a=apps[0];old=a['versions'];assert old
 # Fail closed on any later/conflicting publication; never downgrade or overwrite.
 assert all(tuple(map(int,v['version'].split('.'))) <= (0,4,9) for v in old)
 assert not any(v['version']=='0.4.9' and int(v.get('buildVersion','0'))>8 for v in old)
 baseline={'strata-source.json':'7','source.json':'7','livecontainer-test.json':'3'}[name]
 assert any(v['version']=='0.4.9' and str(v.get('buildVersion'))==baseline for v in old)
 same=[v for v in old if v['version']=='0.4.9' and str(v.get('buildVersion'))=='8']
 if same:
  assert len(same)==1 and old[0]==same[0]
  assert all(same[0].get(k)==entry[k] for k in ('downloadURL','size','sha256'))
  return result # Already published: preserve exact prior date/description and older entries.
 a['versions']=[copy.deepcopy(entry)]+old
 assert a['versions'][1:]==next(x for x in feed['apps'] if x.get('bundleIdentifier')=='com.voicematrix.app')['versions']
 return result

def validate_asset(asset):
 assert asset['name']==IPA and asset['state']=='uploaded'
 assert asset['size']==IPA_BYTES and asset['digest']=='sha256:'+IPA_HASH
 assert asset['browser_download_url']==f'https://github.com/{REPO}/releases/download/{TAG}/{IPA}'

def optional_api(path):
 r=subprocess.run(['gh','api',path],capture_output=True,text=True)
 if r.returncode==0:return json.loads(r.stdout)
 if '(HTTP 404)' in r.stderr:return None
 raise RuntimeError('GitHub lookup failed, not confirmed absence: '+r.stderr)

def find_release():
 # The releases list includes accessible drafts; /releases/tags only finds published tags.
 found=[]
 for page in range(1,21):
  rows=api(f'repos/{REPO}/releases?per_page=100&page={page}')
  found.extend(r for r in rows if r['tag_name']==TAG)
  assert len(found)<=1,'Ambiguous release identity'
  if len(rows)<100:return found[0] if found else None
 raise RuntimeError('Release listing exceeded bounded lookup; no publication')


def validate_release_identity(release,tag,publication):
 assert tag is not None and tag['object']['type']=='commit' and tag['object']['sha']==publication
 assert release['tag_name']==TAG and release['target_commitish']==publication and release['prerelease'] is True

def missing_assets(existing,wanted):
 names=[a['name'] for a in existing];assert len(names)==len(set(names))
 for a in existing:
  assert a['name'] in wanted and a['state']=='uploaded'
  assert all(a[k]==wanted[a['name']][k] for k in ('size','digest'))
 return [name for name in wanted if name not in names]

def get_feeds():
 head=api(f'repos/{REPO}/git/ref/heads/main')['object']['sha']
 tree=api(f'repos/{REPO}/git/commits/{head}')['tree']['sha'];feeds={}
 for name in FEEDS:
  x=api(f'repos/{REPO}/contents/{name}?ref={head}')
  assert x['encoding']=='base64'
  feeds[name]=json.loads(base64.b64decode(x['content']))
 return head,tree,feeds

def sync_catalogs(entry):
 # CAS retries re-read all three feeds. Never force or replay a stale whole feed.
 catalog_commit=None
 for attempt in range(3):
  head,tree,feeds=get_feeds();updated={n:new_feed(f,entry,n) for n,f in feeds.items()}
  if updated==feeds:catalog_commit=head;break
  entries=[dict(path=n,mode='100644',type='blob',content=json.dumps(f,indent=2)+'\n') for n,f in updated.items()]
  t=api(f'repos/{REPO}/git/trees','POST',dict(base_tree=tree,tree=entries))
  c=api(f'repos/{REPO}/git/commits','POST',dict(message='Add inspected unfinished VoiceMatrix build8 preview to catalogs',tree=t['sha'],parents=[head]))
  if api(f'repos/{REPO}/git/ref/heads/main')['object']['sha']!=head:continue
  try:api(f'repos/{REPO}/git/refs/heads/main','PATCH',dict(sha=c['sha'],force=False))
  except subprocess.CalledProcessError:
   current=api(f'repos/{REPO}/git/ref/heads/main')['object']['sha']
   if current==head:raise
   # Includes uncertain successful update. Fresh read next iteration verifies all feeds.
   continue
  catalog_commit=c['sha'];break
 assert catalog_commit is not None,'Catalog raced repeatedly; exact release preserved; rerun to resume'
 _,_,actual=get_feeds()
 assert all(new_feed(f,entry,n)==f for n,f in actual.items()),'Catalog verification failed; rerun exact workflow to resume'
 return catalog_commit

def ensure_release(root,assets,publication):
 release=find_release()
 tag=optional_api(f'repos/{REPO}/git/ref/tags/{TAG}')
 if tag is not None:assert tag['object']['type']=='commit' and tag['object']['sha']==publication
 if release is not None:
  assert release['tag_name']==TAG and release['target_commitish']==publication and release['prerelease'] is True
 if tag is None:
  api(f'repos/{REPO}/git/refs','POST',dict(ref='refs/tags/'+TAG,sha=publication))
  tag=api(f'repos/{REPO}/git/ref/tags/{TAG}')
 assert tag['object']['type']=='commit' and tag['object']['sha']==publication
 wanted={name:dict(size=(root/name).stat().st_size,digest='sha256:'+digest(root/name)) for name in assets}
 if release is None:
  gh('release','create',TAG,'--repo',REPO,'--target',publication,'--title','VoiceMatrix 0.4.9 build 8 — unfinished preview','--notes-file',str(root/'release-notes.md'),'--draft','--prerelease')
  release=find_release();assert release is not None
  tag=api(f'repos/{REPO}/git/ref/tags/{TAG}')
 validate_release_identity(release,tag,publication)
 missing=missing_assets(release['assets'],wanted)
 assert release['draft'] or not missing, 'Published release has missing assets; stop instead of modifying it'
 for name in missing:gh('release','upload',TAG,str(root/name),'--repo',REPO)
 release=find_release();assert release is not None
 assert not missing_assets(release['assets'],wanted)
 matched=[a for a in release['assets'] if a['name']==IPA];assert len(matched)==1;validate_asset(matched[0])
 return release

def main():
 assert os.environ['GITHUB_REPOSITORY']==REPO
 validate_run(api(f'repos/{DEV}/actions/runs/{RUN}'),SOURCE,'.github/workflows/iphone-build8.yml')
 validate_run(api(f'repos/{DEV}/actions/runs/{FULL_UI_RUN}'),FULL_UI_SOURCE,'.github/workflows/character-ui-smoke.yml')
 validate_run(api(f'repos/{DEV}/actions/runs/{UI_RUN}'),UI_SOURCE,'.github/workflows/character-ui-smoke.yml')
 validate_run(api(f'repos/{DEV}/actions/runs/{VERIFY_RUN}'),'a4b162b119b011ca2c29311101745c17a7bc2271','.github/workflows/verify-build8-artifact.yml')
 art=api(f'repos/{DEV}/actions/artifacts/{ARTIFACT}')
 assert art['workflow_run']['id']==RUN and art['digest']=='sha256:'+ZIP_HASH and not art['expired']
 root=pathlib.Path('preview8-evidence');root.mkdir()
 with (root/'artifact.zip').open('wb') as f:subprocess.run(['gh','api',f'repos/{DEV}/actions/artifacts/{ARTIFACT}/zip'],stdout=f,check=True)
 assert digest(root/'artifact.zip')==ZIP_HASH
 with zipfile.ZipFile(root/'artifact.zip') as z:
  expected={IPA,'character-inspection.json','character-ipa.sha256','source-proof.json','dependency-notices.json','assets.json','packaging-status.json'}
  assert len(z.namelist())==len(expected) and set(z.namelist())==expected and z.testzip() is None
  z.extractall(root)
 assert digest(root/IPA)==IPA_HASH and (root/IPA).stat().st_size==IPA_BYTES
 assert (root/'character-ipa.sha256').read_text().split()==[IPA_HASH,IPA]
 # Independently rerun trusted artifact inspection from exact package source checkout.
 candidate=pathlib.Path('package-source').resolve();sys.path.insert(0,str(candidate))
 from tools.character_package import inspect_ipa,PREFIX
 notices=json.loads((root/'dependency-notices.json').read_text())
 inspection=inspect_ipa(root/IPA,dependency_proof=notices['proof'],expected_version='0.4.9',expected_build='8')
 assert inspection==json.loads((root/'character-inspection.json').read_text())
 proof=json.loads((root/'source-proof.json').read_text());assert proof['sourceCommit']==SOURCE
 with zipfile.ZipFile(root/IPA) as z:assert json.loads(z.read(PREFIX+'VoiceMatrix-Source-Proof.json'))==proof
 status=json.loads((root/'packaging-status.json').read_text())
 assert status['sourceCommit']==SOURCE and status['build']=='8' and status['version']=='0.4.9'
 assert status['physicalDeviceVerified'] is False and status['likenessVerified'] is False
 for tool in ('bundle_asr.py','bundle_diarization.py'):
  subprocess.run([sys.executable,str(candidate/'tools'/tool),'--inspect-ipa',str((root/IPA).resolve())],check=True,cwd=candidate)
 entry=dict(version='0.4.9',buildVersion='8',date=datetime.datetime.now(datetime.timezone.utc).date().isoformat(),downloadURL=f'https://github.com/{REPO}/releases/download/{TAG}/{IPA}',localizedDescription=DESCRIPTION,minOSVersion='26.0',size=IPA_BYTES,sha256=IPA_HASH)
 _,_,preflight=get_feeds()
 for n,f in preflight.items():new_feed(f,entry,n)
 publication=os.environ['GITHUB_SHA']
 metadata=dict(sourceCommit=SOURCE,version='0.4.9',buildVersion='8',size=IPA_BYTES,sha256=IPA_HASH,packagingRun=RUN,independentVerificationRun=VERIFY_RUN,targetedUIRun=UI_RUN,targetedUISource=UI_SOURCE,fullUIRun=FULL_UI_RUN,fullUISource=FULL_UI_SOURCE,publicationSource=publication,physicalDeviceVerified=False,likenessVerified=False,unfinishedPreview=True)
 (root/'release-metadata.json').write_text(json.dumps(metadata,indent=2)+'\n');(root/'release-notes.md').write_text(NOTES)
 assets=[IPA,'character-inspection.json','source-proof.json','packaging-status.json','release-metadata.json','dependency-notices.json']
 release=ensure_release(root,assets,publication)
 # Publish only verified uploaded bytes; no broken download is ever added to feeds.
 if release['draft']:api(f"repos/{REPO}/releases/{release['id']}",'PATCH',{'draft':False,'prerelease':True,'make_latest':'false'})
 release=api(f"repos/{REPO}/releases/{release['id']}");assert not release['draft'] and release['prerelease'];validate_asset(next(a for a in release['assets'] if a['name']==IPA))
 entry['date']=release['published_at'][:10]
 catalog_commit=sync_catalogs(entry)
 print(json.dumps(dict(releaseURL=release['html_url'],catalogCommit=catalog_commit,metadata=metadata),indent=2))
if __name__=='__main__':main()
