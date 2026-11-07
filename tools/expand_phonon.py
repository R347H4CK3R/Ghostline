"""Audit the pinned publisher catalog for additional distinct conditioning tensors.
Development only. New profiles remain candidates until native synthesis/English QA.
"""
import concurrent.futures,hashlib,json,urllib.parse,urllib.request
from pathlib import Path
from assets import tensor_digest,validate_profiles

def expand(lock_path=Path('models/phonon-lock.json'),root=Path('VoiceMatrix/Resources/Phonon')):
 lock=json.loads(lock_path.read_text());prefix='phonon/phonon-31m-en/voices/'
 url='https://huggingface.co/api/models/FluidInference/pocket-tts-coreml/tree/'+lock['revision']+'/'+prefix.rstrip('/')+'?recursive=true&limit=1000'
 with urllib.request.urlopen(url,timeout=60) as response:items=json.load(response)
 items=sorted((e for e in items if e['type']=='file' and e['path'].endswith('.safetensors')),key=lambda e:e['path'])
 def download(e):
  rel='voices/'+e['path'].split('/')[-1];out=root/rel;out.parent.mkdir(parents=True,exist_ok=True)
  if not out.exists():
   with urllib.request.urlopen(lock['baseURL']+'/'+urllib.parse.quote(e['path'],safe='/'),timeout=120) as response:out.write_bytes(response.read())
  data=out.read_bytes();digest=hashlib.sha256(data).hexdigest()
  if len(data)!=e['size'] or (e.get('lfs') and digest!=e['lfs']['oid']):raise ValueError('Publisher checksum mismatch: '+rel)
  return e,dict(path=rel,remotePath=e['path'],sha256=digest,size=len(data)),tensor_digest(data)
 with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:downloaded=list(pool.map(download,items))
 seen={v['tensorSha256'] for v in lock['voices']};ids={v['id'] for v in lock['voices']};added=[];duplicates=[]
 locales={'de_de':'German reference','fr_fr':'French reference','es_es':'Spanish reference','es_mx':'Mexican Spanish reference','pt_br':'Brazilian Portuguese reference'}
 for e,asset,digest in downloaded:
  vid=Path(asset['path']).stem
  if vid in ids:continue
  if digest in seen:duplicates.append(vid);continue
  if vid=='default':duplicates.append('default (unnamed; not counted)');continue
  locale=vid.rsplit('_',1)[0]
  if locale not in locales:raise ValueError('Unreviewed source locale: '+locale)
  voice=dict(id=vid,name=vid.rsplit('_',1)[-1],category='International Voices',language='en',accent=locales[locale]+'; English speech',path=asset['path'],sha256=asset['sha256'],size=asset['size'],engine='phonon31m',source='gradium/phonon-voices',permissions='Apache-2.0 publisher catalog; original named performance, no recognizable likeness claim',qualityStatus='candidate-not-listening-tested',deviceVerified=False,tensorSha256=digest,sourceLocale=locale)
  lock['files'].append(asset);lock['voices'].append(voice);seen.add(digest);ids.add(vid);added.append(vid)
 validate_profiles(root,lock['voices']);lock_path.write_text(json.dumps(lock,indent=2)+'\n');(root/'manifest.json').write_text(json.dumps(lock,indent=2)+'\n')
 report=dict(revision=lock['revision'],publisherProfiles=len(items),added=added,excluded=duplicates,totalDistinctProfiles=len(lock['voices']),status='Candidates awaiting native synthesis and English intelligibility tests; no physical or listening verification')
 Path('models/expansion-audit.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':expand()
