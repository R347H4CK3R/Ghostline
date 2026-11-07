"""Build-time only: validate, compile and seal the licensed OpenVoice models."""
import argparse,hashlib,json,subprocess,urllib.request,urllib.parse,shutil
from pathlib import Path
from assets import validate

def seal(root,lock):
 entries=[]
 for path in sorted(Path(root).rglob('*')):
  if not path.is_file() or path.name=='model-manifest.json': continue
  with path.open('rb') as f: digest=hashlib.file_digest(f,'sha256').hexdigest()
  entries.append({'path':str(path.relative_to(root)),'size':path.stat().st_size,'sha256':digest})
 manifest={'schemaVersion':1,'engine':'OpenVoiceV2','sourceRevision':lock['revision'],'sourceRepository':lock['repository'],'sourceFiles':lock['files'],'files':entries}
 (Path(root)/'model-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 validate(root,entries)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--seal');args=p.parse_args();lock=json.loads(Path('models/openvoice-lock.json').read_text())
 if args.seal: seal(Path(args.seal),lock);raise SystemExit(0)
 source=Path('build/openvoice-source');source.mkdir(parents=True,exist_ok=True)
 for entry in lock['files']:
  target=source/entry['path'];target.parent.mkdir(parents=True,exist_ok=True)
  try: validate(source,[entry]);continue
  except ValueError: pass
  with urllib.request.urlopen(lock['baseURL']+'/'+urllib.parse.quote(entry['path'],safe='/'),timeout=180) as r: target.write_bytes(r.read())
  validate(source,[entry])
 output=Path('VoiceMatrix/Resources/OpenVoice');output.mkdir(parents=True,exist_ok=True)
 for name in ['OpenVoice_SpeakerEncoder','OpenVoice_VoiceConverter']:
  subprocess.run(['xcrun','coremlcompiler','compile',str(source/(name+'.mlpackage')),str(output)],check=True)
  assert (output/(name+'.mlmodelc')).is_dir()
 profiles=json.loads(Path('models/original-conversion-lock.json').read_text())['profiles']
 destination=output/'Profiles';destination.mkdir(exist_ok=True)
 for entry in profiles:
  profile_source=Path(entry['path']);data=profile_source.read_bytes()
  if len(data)!=entry['size'] or hashlib.sha256(data).hexdigest()!=entry['sha256']:raise ValueError('Damaged source conditioning')
  value=json.loads(data)
  if value['id']!=entry['id'] or value['ttsEmbeddingSHA256']!=entry['ttsEmbeddingSHA256'] or value['converterRevision']!=lock['revision']:raise ValueError('Incompatible source conditioning')
  (destination/(entry['id']+'.json')).write_bytes(data)
 for notice in Path('LICENSES').glob('REFERENCE-*'):shutil.copyfile(notice,output/notice.name)
 for name in ['reference-provenance.json','original-conversion-lock.json']:
  shutil.copyfile(Path('models')/name,output/name)
 shutil.copyfile('LICENSES/OpenVoice-LICENSE',output/'OpenVoice-LICENSE.txt')
 shutil.copyfile(source/'README.md',output/'Model-Card.md')
 (output/'NOTICE.txt').write_text('OpenVoice V2: MyShell AI, MIT. Community Core ML conversion: CoreML-Models / Daisuke Majima, model card MIT. Pinned source revision: '+lock['revision']+'\nNo third-party Swift demo code is included.\n')
 seal(output,lock)
