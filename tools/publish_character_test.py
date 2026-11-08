"""Owner-run release finalizer. Only succeeds after all actual native audio gates pass."""
import base64,datetime,hashlib,json,pathlib,subprocess,sys,os,traceback,shutil
GH=r'C:\Program Files\GitHub CLI\gh.exe'
REPO='R347H4CK3R/Ghostline';RUN=42455907106
SOURCE='830532244ebeede81434071eca3a357b3bfda037';TOOLS='830532244ebeede81434071eca3a357b3bfda037'
TAG='voicematrix-v0.4.0-character-test-1';IPA='VoiceMatrix-0.4.0-character-test.ipa'
ROOT=pathlib.Path(os.environ['LOCALAPPDATA'])/'VoiceMatrixStudio'/'CharacterTest4-830';ROOT.mkdir(exist_ok=True)
os.chdir(ROOT);sys.path.insert(0,str(ROOT))
def gh(*args,check=True):return subprocess.run([GH,*args],check=check,capture_output=True,text=True,encoding='utf-8').stdout

def main():
 with (ROOT/'progress.log').open('a',encoding='utf-8') as log:
  p=subprocess.run([GH,'run','watch',str(RUN),'--repo',REPO,'--exit-status'],stdout=log,stderr=log)
  if p.returncode:raise RuntimeError('Native test workflow did not pass; no publication performed')
 run=json.loads(gh('run','view',str(RUN),'--repo',REPO,'--json','headSha,conclusion,jobs'))
 assert run['headSha']==SOURCE and run['conclusion']=='success'
 assert {j['name'] for j in run['jobs']}=={'resolve','ipa','speech','conversion'} and all(j['conclusion']=='success' for j in run['jobs'])
 files=['tools/character_package.py','tools/character_evidence.py','tools/verify_character_kit.py','tools/f5-listening-lock.json','tools/no-stock-resource-lock.json']
 files+=['tools/listening_licenses/'+x for x in ['F5-CC-BY-NC-4.0.txt','speech-swift-APACHE-2.0.txt','ATTRIBUTION.txt','pypinyin-MIT.txt','jieba-MIT.txt','vocos-MIT.txt']]
 for name in files:
  p=ROOT/name;p.parent.mkdir(parents=True,exist_ok=True)
  data=gh('api',f'repos/{REPO}/contents/{name}?ref={TOOLS}','--jq','.content')
  p.write_bytes(base64.b64decode(data))
 for kind,name in [('ipa','Character-test-IPA'),('speech','Character-speech-evidence'),('conversion','Character-conversion-evidence')]:
  out=ROOT/kind;out.mkdir(exist_ok=True)
  if not (out/'.download-complete').exists():
   gh('run','download',str(RUN),'--repo',REPO,'-n',name,'-D',str(out));(out/'.download-complete').write_text(str(RUN))
 from tools.verify_character_kit import verify
 from tools.character_package import inspect_ipa
 from tools.character_evidence import digest
 report=verify(ROOT/'ipa',ROOT/'speech',ROOT/'conversion',SOURCE);report['workflowRun']=RUN
 verification=ROOT/'character-release-verification.json';verification.write_text(json.dumps(report,indent=2)+'\n')
 notes=ROOT/'release-notes.txt';notes.write_text('Experimental character-folder test. Includes pinned shared offline F5 speech and OpenVoice conversion engines, zero bundled characters or stock profiles. Import the separate Voices folder. Actual hosted native speech and simulator conversion word/audio gates passed with the same source fingerprint. F5 speech was tested on hosted Mac Metal; MLX documents that iOS Simulator cannot evaluate its arrays. Physical iPhone speech, performance and individual character likeness remain unverified. Conversion recordings are limited to 10 seconds. Same-account Tailscale laptop queue needs no pairing JSON. This is not the completed unattended video/model-training project.\n')
 existing=gh('release','view',TAG,'--repo',REPO,'--json','tagName',check=False)
 if not existing:
  gh('release','create',TAG,str(ROOT/'ipa'/IPA),str(verification),str(ROOT/'ipa/dependency-notices.json'),str(ROOT/'speech/speech-evidence.json'),str(ROOT/'conversion/conversion-evidence/conversion-result.json'),'--repo',REPO,'--target',SOURCE,'--prerelease','--title','VoiceMatrix 0.4.0 — character folder test','--notes-file',str(notes))
 redownload=ROOT/'published'
 if redownload.exists():shutil.rmtree(redownload)
 redownload.mkdir()
 gh('release','download',TAG,'--repo',REPO,'-p',IPA,'-D',str(redownload))
 assert digest(redownload/IPA)==report['ipaSHA256']
 dependency=json.loads((ROOT/'ipa/dependency-notices.json').read_text())['proof'];inspect_ipa(redownload/IPA,dependency_proof=dependency)
 url=f'https://github.com/{REPO}/releases/download/{TAG}/{IPA}'
 entry=dict(version='0.4.0',buildVersion='1',date=datetime.datetime.now(datetime.timezone.utc).date().isoformat(),downloadURL=url,localizedDescription='Separate character-folder import, fully offline new-text speech and neural recording conversion. No characters or stock voices bundled. Native diagnostic audio checks passed; character likeness and physical iPhone tests remain pending.',minOSVersion='26.0',size=report['ipaBytes'])
 for name in ['livecontainer-test.json','source.json','strata-source.json']:
  current=json.loads(gh('api',f'repos/{REPO}/contents/{name}?ref=main'))
  feed=json.loads(base64.b64decode(current['content']));app=next(x for x in feed['apps'] if x['bundleIdentifier']=='com.voicematrix.app')
  if app['versions'][0].get('downloadURL')==url:continue
  assert not any(x.get('version')=='0.4.0' and x.get('downloadURL')!=url for x in app['versions']),'Conflicting release version; preserve and review'
  app['versions']=[entry]+[x for x in app['versions'] if x.get('downloadURL')!=url]
  app['name']='VoiceMatrix — Character Folder Test';app['localizedDescription']=entry['localizedDescription']
  payload=dict(message='Publish verified character-folder test source '+name,sha=current['sha'],content=base64.b64encode((json.dumps(feed,indent=2)+'\n').encode()).decode())
  request=ROOT/('update-'+name);request.write_text(json.dumps(payload))
  gh('api','--method','PUT',f'repos/{REPO}/contents/{name}','--input',str(request))
  fresh=json.loads(gh('api',f'repos/{REPO}/contents/{name}?ref=main'));f=json.loads(base64.b64decode(fresh['content']))
  assert next(x for x in f['apps'] if x['bundleIdentifier']=='com.voicematrix.app')['versions'][0]==entry
 (ROOT/'status.json').write_text(json.dumps(dict(status='published-and-redownload-verified',release=TAG,url=url,**report),indent=2)+'\n')
 print('Published and verified '+url)
try:main()
except Exception as e:
 (ROOT/'status.json').write_text(json.dumps(dict(status='blocked-no-publication-guarantee',reason=str(e),run=RUN,sourceCommit=SOURCE),indent=2)+'\n')
 traceback.print_exc();sys.exit(1)
