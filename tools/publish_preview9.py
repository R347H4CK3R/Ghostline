"""Publish only the inspected unfinished build9; never replace old releases."""
import base64,copy,datetime,hashlib,json,os,pathlib,subprocess,sys,zipfile
REPO='R347H4CK3R/Ghostline'
DEV='R347H4CK3R/VoiceMatrix-Development'
SOURCE='9c3407118de70e8e0b7352c1d590beb6525de464'
RUN=43738877778
VERIFY_RUN=43742616281
FULL_UI_RUN=43742276690
FULL_UI_SOURCE='e2713281cff51e513414457b37bfe00093a4ab6c'
RUNTIME_ARTIFACT=14172844511
RUNTIME_HASH='fc0a079d1d23e9a482acf277d7b6b8f987ec906ca1add642a53ad2fe29cdc924'
ARTIFACT=14172383471
ZIP_HASH='74a90cf8ca52fc8377fbb492e8ca338ee50d92d0bb26a6dc323a898f8a7eec26'
IPA_HASH='b32850e21695e4d88d8d61a3009cf81b1beb370d75d55a4b70dfc7eca029a0ca'
IPA_BYTES=1314535068
TAG='voicematrix-v0.4.9-build9'
IPA='VoiceMatrix-0.4.9-build9.ipa'
FEEDS=('strata-source.json','source.json','livecontainer-test.json')
DESCRIPTION='Unfinished preview: bounded six-candidate reference screening and source-vendored end-of-file diarization repair. Two complete human recordings passed the local macOS pipeline with word-checked new speech; simulator checks passed. Existing voices retained. Physical-iPhone behavior and likeness unverified. Music separation, reliable overlapping-speaker extraction and full RVC training remain incomplete. Not finished 1.0.0.'
NOTES='''VoiceMatrix 0.4.9 build 9 — unfinished development preview

Unsigned ARM64 IPA for iOS 26+, requiring signing through your sideloading setup. Update the existing app without deleting its data. Build 8 remains available.

Compared with build 8: up to six bounded reference candidates while retaining at most three synthesis attempts; source-vendored FluidAudio end-of-file timeline correction, with pinned upstream source, preserved licenses and exact source inventory. No experimental reference padding or automatic case conversion was adopted. No stock celebrity voices or trained RVC profiles are bundled.

Exact package source: 9c3407118de70e8e0b7352c1d590beb6525de464. Package/run 43738877778 and independent archive verification 43742616281 passed. The native retry in that run passed eight EOF boundary tests and both known complete licensed human recordings through the actual local coordinator: transcription, speaker analysis, screening, reference preview, import, retained-source pause/resume and new speech with zero measured word errors. The initial native attempt failed on an external source-download HTTP 502 before inference; retained evidence remains separate. Native runtime and packaged IPA used the same frozen dependency graph and exact vendor/source proof. These are controlled macOS tests, not physical-iPhone results or general-input acceptance.

Full simulator run 43742276690 on test-only correction e2713281cff51e513414457b37bfe00093a4ab6c passed 56 unit tests and 13 UI tests. App, project and vendor bytes match the packaged source. The original simulator run failed a scrolling-helper geometry assertion; bounded gutter drags corrected the test navigation without removing visibility, import, playback, long-text or relaunch assertions. Linux source suite passed 833 tests with six skips. Broad Windows checks are not all green: missing Swift/bash and checkout portability issues were separate; focused portability correction is not in this package.

Physical-iPhone installation, memory/performance, human listening, character identity and likeness remain unverified. Music separation, reliable overlapping-speaker extraction and full RVC training remain incomplete. A harder truncated-reference fixture still failed new-speech verification; passing the two complete recordings does not repair or conceal that case. Experimental RVC requires compatible imported packs. Not completed 1.0.0.
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
 assert not any(v['version']=='0.4.9' and int(v.get('buildVersion','0'))>9 for v in old)
 baseline='8'
 assert name in FEEDS
 assert any(v['version']=='0.4.9' and str(v.get('buildVersion'))==baseline for v in old)
 same=[v for v in old if v['version']=='0.4.9' and str(v.get('buildVersion'))=='9']
 if same:
  assert len(same)==1 and old[0]==same[0]
  assert all(same[0].get(k)==entry[k] for k in ('downloadURL','size','sha256'))
  return result # Already published: preserve exact prior date/description and older entries.
 a['versions']=[copy.deepcopy(entry)]+old
 assert a['versions'][1:]==next(x for x in feed['apps'] if x.get('bundleIdentifier')=='com.voicematrix.app')['versions']
 return result

def validate_asset(asset,draft=False):
 assert asset['name']==IPA and asset['state']=='uploaded'
 assert asset['size']==IPA_BYTES and asset['digest']=='sha256:'+IPA_HASH
 if not draft:assert asset['browser_download_url']==f'https://github.com/{REPO}/releases/download/{TAG}/{IPA}'

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
 assert release['body']==NOTES and type(release['draft']) is bool

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

def stage_catalogs(entry):
 head,tree,feeds=get_feeds();updated={n:new_feed(f,entry,n) for n,f in feeds.items()}
 entries=[dict(path=n,mode='100644',type='blob',content=json.dumps(f,indent=2)+'\n') for n,f in updated.items()]
 t=api(f'repos/{REPO}/git/trees','POST',dict(base_tree=tree,tree=entries))
 c=api(f'repos/{REPO}/git/commits','POST',dict(message='Stage verified unfinished VoiceMatrix build9 catalog entries',tree=t['sha'],parents=[head]))
 return dict(base=head,commit=c['sha'])

def sync_catalogs(entry):
 # CAS retries re-read all three feeds. Never force or replay a stale whole feed.
 catalog_commit=None
 for attempt in range(3):
  head,tree,feeds=get_feeds();updated={n:new_feed(f,entry,n) for n,f in feeds.items()}
  if updated==feeds:catalog_commit=head;break
  entries=[dict(path=n,mode='100644',type='blob',content=json.dumps(f,indent=2)+'\n') for n,f in updated.items()]
  t=api(f'repos/{REPO}/git/trees','POST',dict(base_tree=tree,tree=entries))
  c=api(f'repos/{REPO}/git/commits','POST',dict(message='Add inspected unfinished VoiceMatrix build9 preview to catalogs',tree=t['sha'],parents=[head]))
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
  gh('release','create',TAG,'--repo',REPO,'--target',publication,'--title','VoiceMatrix 0.4.9 build 9 — unfinished preview','--notes-file',str(root/'release-notes.md'),'--draft','--prerelease')
  release=find_release();assert release is not None
  tag=api(f'repos/{REPO}/git/ref/tags/{TAG}')
 validate_release_identity(release,tag,publication)
 missing=missing_assets(release['assets'],wanted)
 assert release['draft'] or not missing, 'Published release has missing assets; stop instead of modifying it'
 for name in missing:gh('release','upload',TAG,str(root/name),'--repo',REPO)
 release=find_release();assert release is not None
 assert not missing_assets(release['assets'],wanted)
 matched=[a for a in release['assets'] if a['name']==IPA];assert len(matched)==1;validate_asset(matched[0],draft=release['draft'])
 return release

def validate_runtime(root,candidate,proof):
 a=api(f'repos/{DEV}/actions/artifacts/{RUNTIME_ARTIFACT}')
 assert a['workflow_run']['id']==RUN and a['workflow_run']['head_sha']==SOURCE
 assert a['digest']=='sha256:'+RUNTIME_HASH and not a['expired']
 path=root/'runtime.zip'
 with path.open('wb') as f:subprocess.run(['gh','api',f'repos/{DEV}/actions/artifacts/{RUNTIME_ARTIFACT}/zip'],stdout=f,check=True)
 assert digest(path)==RUNTIME_HASH
 with zipfile.ZipFile(path) as z:
  assert len(z.namelist())==len(set(z.namelist())) and z.testzip() is None
  assert json.loads(z.read('source-proof.json'))==proof
  graph=z.read('Package.resolved');assert hashlib.sha256(graph).hexdigest()==proof['dependencyResolvedSHA256']
  assert all(json.loads(z.read(n))==proof['vendoredDependencies']['FluidAudio'] for n in ['vendor-before.json','vendor-after-tests.json','vendor-after-build.json'])
  for part in ('first','second'):
   e=json.loads(z.read(part+'/pipeline-evidence.json'))
   assert e['sourceCommit']==SOURCE and e['newSpeechWordErrorRate']==0 and len(e['importedIDs'])==1
   assert all(e[k] is True for k in ['resumeCompleted','cancellationRetainedSource','freshStoreReloadPreservedIDs','priorProfilePreserved'])
   assert hashlib.sha256(z.read(part+'/complete-source.wav')).hexdigest()==e['sourceRetainedSHA256']==e['fixtureSHA256']
   assert hashlib.sha256(z.read(part+'/work/new-speech.wav')).hexdigest()==e['newSpeechSHA256']==json.loads(z.read(part+'/work/new-speech-asr.json'))['inputSHA256']
   assert json.loads(z.read(part+'/source-transcript-check.json'))['wordErrorRate']==0
   (root/(part+'-pipeline-evidence.json')).write_text(json.dumps(e,indent=2)+'\n')
  (root/'Package.resolved').write_bytes(graph)
 from tools.character_evidence import source_proof
 old=pathlib.Path.cwd();oldsha=os.environ['GITHUB_SHA']
 try:
  os.chdir(candidate);os.environ['GITHUB_SHA']=SOURCE
  assert source_proof((root/'Package.resolved').resolve())==proof
 finally:os.chdir(old);os.environ['GITHUB_SHA']=oldsha

def main():
 assert os.environ['GITHUB_REPOSITORY']==REPO
 validate_run(api(f'repos/{DEV}/actions/runs/{RUN}'),SOURCE,'.github/workflows/iphone-build9.yml')
 validate_run(api(f'repos/{DEV}/actions/runs/{FULL_UI_RUN}'),FULL_UI_SOURCE,'.github/workflows/character-ui-smoke.yml')
 validate_run(api(f'repos/{DEV}/actions/runs/{VERIFY_RUN}'),'71d068990e0c6d517886bee56581f5a2bbba1f1d','.github/workflows/verify-build9-artifact.yml')
 art=api(f'repos/{DEV}/actions/artifacts/{ARTIFACT}')
 assert art['workflow_run']['id']==RUN and art['digest']=='sha256:'+ZIP_HASH and not art['expired']
 root=pathlib.Path('preview9-evidence').resolve();root.mkdir()
 with (root/'artifact.zip').open('wb') as f:subprocess.run(['gh','api',f'repos/{DEV}/actions/artifacts/{ARTIFACT}/zip'],stdout=f,check=True)
 assert digest(root/'artifact.zip')==ZIP_HASH
 with zipfile.ZipFile(root/'artifact.zip') as z:
  expected={IPA,'character-inspection.json','character-ipa.sha256','source-proof.json','dependency-notices.json','assets.json','packaging-status.json','vendor-before.json','vendor-after.json'}
  assert len(z.namelist())==len(expected) and set(z.namelist())==expected and z.testzip() is None
  z.extractall(root)
 assert digest(root/IPA)==IPA_HASH and (root/IPA).stat().st_size==IPA_BYTES
 assert (root/'character-ipa.sha256').read_text().split()==[IPA_HASH,IPA]
 # Independently rerun trusted artifact inspection from exact package source checkout.
 candidate=pathlib.Path('package-source').resolve();sys.path.insert(0,str(candidate))
 from tools.character_package import inspect_ipa,PREFIX
 notices=json.loads((root/'dependency-notices.json').read_text())
 inspection=inspect_ipa(root/IPA,dependency_proof=notices['proof'],expected_version='0.4.9',expected_build='9')
 assert inspection==json.loads((root/'character-inspection.json').read_text())
 proof=json.loads((root/'source-proof.json').read_text());assert proof['sourceCommit']==SOURCE
 with zipfile.ZipFile(root/IPA) as z:assert json.loads(z.read(PREFIX+'VoiceMatrix-Source-Proof.json'))==proof
 validate_runtime(root,candidate,proof)
 assert json.loads((root/'vendor-before.json').read_text())==json.loads((root/'vendor-after.json').read_text())==proof['vendoredDependencies']['FluidAudio']
 status=json.loads((root/'packaging-status.json').read_text())
 assert status['sourceCommit']==SOURCE and status['build']=='9' and status['version']=='0.4.9'
 assert status['physicalDeviceVerified'] is False and status['likenessVerified'] is False
 for tool in ('bundle_asr.py','bundle_diarization.py'):
  subprocess.run([sys.executable,str(candidate/'tools'/tool),'--inspect-ipa',str((root/IPA).resolve())],check=True,cwd=candidate)
 entry=dict(version='0.4.9',buildVersion='9',date=datetime.datetime.now(datetime.timezone.utc).date().isoformat(),downloadURL=f'https://github.com/{REPO}/releases/download/{TAG}/{IPA}',localizedDescription=DESCRIPTION,minOSVersion='26.0',size=IPA_BYTES,sha256=IPA_HASH)
 _,_,preflight=get_feeds()
 for n,f in preflight.items():new_feed(f,entry,n)
 publication=os.environ['GITHUB_SHA']
 metadata=dict(sourceCommit=SOURCE,version='0.4.9',buildVersion='9',size=IPA_BYTES,sha256=IPA_HASH,packagingRun=RUN,independentVerificationRun=VERIFY_RUN,runtimeArtifact=RUNTIME_ARTIFACT,runtimeArtifactSHA256=RUNTIME_HASH,fullUIRun=FULL_UI_RUN,fullUISource=FULL_UI_SOURCE,publicationSource=publication,physicalDeviceVerified=False,likenessVerified=False,unfinishedPreview=True)
 (root/'release-metadata.json').write_text(json.dumps(metadata,indent=2)+'\n');(root/'release-notes.md').write_text(NOTES)
 assets=[IPA,'character-inspection.json','source-proof.json','packaging-status.json','release-metadata.json','dependency-notices.json','vendor-before.json','vendor-after.json']
 release=ensure_release(root,assets,publication)
 staged=stage_catalogs(entry)
 (root/'staged-catalog.json').write_text(json.dumps(staged,indent=2)+'\n')
 # Publish only verified uploaded bytes; no broken download is ever added to feeds.
 if release['draft']:api(f"repos/{REPO}/releases/{release['id']}",'PATCH',{'draft':False,'prerelease':True,'make_latest':'false'})
 release=api(f"repos/{REPO}/releases/{release['id']}");assert not release['draft'] and release['prerelease']
 validate_release_identity(release,api(f'repos/{REPO}/git/ref/tags/{TAG}'),publication)
 assert not missing_assets(release['assets'],{n:dict(size=(root/n).stat().st_size,digest='sha256:'+digest(root/n)) for n in assets})
 for a in release['assets']:assert a['browser_download_url']==f'https://github.com/{REPO}/releases/download/{TAG}/{a["name"]}'
 validate_asset(next(a for a in release['assets'] if a['name']==IPA))
 entry['date']=release['published_at'][:10]
 catalog_commit=sync_catalogs(entry)
 print(json.dumps(dict(releaseURL=release['html_url'],catalogCommit=catalog_commit,metadata=metadata),indent=2))
if __name__=='__main__':main()
