"""Fail before Apple builds if local profile files, rights labels or engine links are invalid."""
import hashlib,json
from pathlib import Path
from assets import unique_profiles,conversion_tensor
lock=json.loads(Path('models/phonon-lock.json').read_text());voices=lock['voices'];unique_profiles(voices)
seen=set()
for voice in voices:
 if voice['engine']=='phonon31m':continue
 entry=next(e for e in lock['files'] if e['path']==voice['path']);data=Path(entry['localPath']).read_bytes()
 if len(data)!=entry['size'] or hashlib.sha256(data).hexdigest()!=entry['sha256'] or entry['sha256']!=voice['sha256']:raise ValueError('Damaged local voice profile')
 digest=conversion_tensor(data,voice,voices)
 if digest!=voice['tensorSha256'] or digest in seen:raise ValueError('Duplicate or damaged neural conditioning')
 seen.add(digest)
 if voice['permissions'].startswith('CC-BY-NC') and voice.get('usageRestriction')!='Noncommercial use only':raise ValueError('Missing noncommercial label')
 if not voice.get('categories') or voice['category'] not in voice['categories']:raise ValueError('Uncategorized voice')
original=json.loads(Path('models/original-conversion-lock.json').read_text())['profiles']
if {e['id'] for e in original}!={v['id'] for v in voices if v['engine']=='phonon31m'}:raise ValueError('Missing original voice conversion profiles')
for e in original:
 data=Path(e['path']).read_bytes()
 if len(data)!=e['size'] or hashlib.sha256(data).hexdigest()!=e['sha256']:raise ValueError('Damaged original voice conditioning')
for file in ['REFERENCE-CC0-1.0.txt','REFERENCE-CC-BY-4.0.txt','REFERENCE-CC-BY-NC-4.0.txt','REFERENCE-ATTRIBUTION.txt']:
 if Path('LICENSES',file).stat().st_size<1000:raise ValueError('Missing source license notice')
print('Validated source catalog, engine bindings, categories and source conditions:',len(voices))
