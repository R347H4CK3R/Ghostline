"""Canonical, content-addressed inference inputs, independent of QA and executable bytes.

Keep the full tested descriptor when approving a subset. Verification permits only
removal of unapproved conditioning files, never a change to a retained input.
All compiled graph/weight/runtime files are bound; no compiled bytes are ignored.
"""
import hashlib,json
from pathlib import Path,PurePosixPath

NAME='inference-fingerprint.json'
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def digest(data):return hashlib.sha256(data).hexdigest()
def safe(path):
 p=PurePosixPath(path)
 if p.is_absolute() or '..' in p.parts:raise ValueError('Unsafe inference input path')
 return path

def inputs(read,phonon,converter,names=None):
 entries={}
 for folder,manifest in [('Phonon',phonon),('OpenVoice',converter)]:
  for e in manifest['files']:
   path=folder+'/'+safe(e['path']);data=read(path)
   if len(data)!=e['size'] or digest(data)!=e['sha256']:raise ValueError('Inference input checksum mismatch: '+path)
   if path in entries:raise ValueError('Duplicate inference input')
   # Notices/provenance are not consumed by inference. All compiled files,
   # including metadata, graphs and weights, and all conditioning are retained.
   if folder=='Phonon' or '.mlmodelc/' in path or path.startswith('OpenVoice/Profiles/'):
    # Compiler JSON object ordering can vary across otherwise identical builds.
    if '.mlmodelc/' in path and path.endswith('.json'):data=canonical(json.loads(data))
    entries[path]=digest(data)
 if names is not None:
  required={n for n in names if '.mlmodelc/' in n or n.startswith('OpenVoice/Profiles/')}
  if not required<=entries.keys():raise ValueError('Unsealed inference input')
 return entries

def fingerprint(document):
 return digest(canonical({k:v for k,v in document.items() if k!='sha256'}))

def create(resources,source=Path('.')):
 resources=Path(resources);source=Path(source)
 ph=json.loads((resources/'Phonon/manifest.json').read_text());cv=json.loads((resources/'OpenVoice/model-manifest.json').read_text())
 code={str(p.relative_to(source)):digest(p.read_bytes()) for p in sorted((source/'VoiceMatrix').rglob('*.swift'))}
 for relative in ['project.yml','tools/inference_fingerprint.py']:
  p=source/relative
  if p.exists():code[relative]=digest(p.read_bytes())
 if not code:raise ValueError('Missing inference code/dependency identity')
 document=dict(schemaVersion=1,files=inputs(lambda p:(resources/p).read_bytes(),ph,cv,[str(p.relative_to(resources)) for p in resources.rglob('*') if p.is_file()]),voices=ph['voices'],modelRevision=ph['revision'],converterRevision=cv['sourceRevision'],code=code)
 document['sha256']=fingerprint(document)
 (resources/'Phonon'/NAME).write_text(json.dumps(document,indent=2)+'\n')
 return document

def verify(read,phonon,converter,report=None,names=None):
 document=json.loads(read('Phonon/'+NAME))
 if document.get('schemaVersion')!=1 or document.get('sha256')!=fingerprint(document):raise ValueError('Invalid inference fingerprint')
 if report is not None and report.get('inferenceFingerprint')!=document['sha256']:raise ValueError('QA inference fingerprint does not match bundle')
 if document['modelRevision']!=phonon['revision'] or document['converterRevision']!=converter['sourceRevision']:raise ValueError('Changed inference revision')
 original={v['id']:v for v in document['voices']};current={v['id']:v for v in phonon['voices']}
 if len(current)!=len(phonon['voices']) or not current or any(original.get(k)!=v for k,v in current.items()):raise ValueError('Changed inference routing/catalog')
 actual=inputs(read,phonon,converter,names);expected=dict(document['files'])
 removed=set(original)-set(current)
 for vid in removed:
  voice=original[vid]
  expected.pop('Phonon/'+voice.get('path',''),None)
  expected.pop('OpenVoice/Profiles/'+vid+'.json',None)
 if actual!=expected:raise ValueError('Changed inference assets or conversion targets')
 return document['sha256']

def validate_evidence(report):
 value=report.get('inferenceFingerprint','')
 if not isinstance(value,str) or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):raise ValueError('Missing native inference fingerprint')
 return value
