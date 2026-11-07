"""Compact existing native speaker profiles without changing their float16 model input."""
import argparse,base64,hashlib,json,pathlib,struct

def prepare(artifacts):
 lock=json.loads(pathlib.Path('models/phonon-lock.json').read_text());voices={v['id']:v for v in lock['voices'] if v['engine']=='phonon31m'}
 root=pathlib.Path('models/original-conversion');root.mkdir(exist_ok=True,parents=True);entries=[]
 for path in pathlib.Path(artifacts).rglob('Profiles/*.json'):
  profile=json.loads(path.read_text());voice=voices[profile['id']]
  if profile['ttsEmbeddingSHA256']!=voice['sha256']:raise ValueError('Existing voice changed')
  raw=struct.pack('<256e',*profile.pop('embedding'));profile['embeddingFP16Base64']=base64.b64encode(raw).decode()
  data=(json.dumps(profile,sort_keys=True,separators=(',',':'))+'\n').encode();target=root/(hashlib.sha256(voice['id'].encode()).hexdigest()[:24]+'.json');target.write_bytes(data)
  entries.append(dict(id=voice['id'],path=str(target),size=len(data),sha256=hashlib.sha256(data).hexdigest(),ttsEmbeddingSHA256=voice['sha256'],referenceAudioSHA256=profile['referenceAudioSHA256']))
 if len(entries)!=len(voices) or {e['id'] for e in entries}!=voices.keys():raise ValueError('Missing existing voice conditioning')
 pathlib.Path('models/original-conversion-lock.json').write_text(json.dumps(dict(nativeRun=42393393792,profiles=entries),indent=2)+'\n');print('Prepared existing conversion profiles:',len(entries))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('artifacts');a=p.parse_args();prepare(a.artifacts)
