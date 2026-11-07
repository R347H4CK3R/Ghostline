import hashlib,json,plistlib,struct,sys,zipfile
from pathlib import PurePosixPath
from assets import validate_qa_report
from inference_fingerprint import verify

def inspect(path):
 with zipfile.ZipFile(path) as z:
  if z.testzip() is not None: raise ValueError('Corrupt archive')
  prefix='Payload/VoiceMatrix.app/'
  info=plistlib.loads(z.read(prefix+'Info.plist'))
  assert info['CFBundleIdentifier']=='com.voicematrix.app'
  assert info['CFBundleShortVersionString']=='0.3.0'
  assert tuple(map(int,info['MinimumOSVersion'].split('.'))) >= (26,0)
  binary=z.read(prefix+info['CFBundleExecutable'])
  assert binary[:4]==b'\xcf\xfa\xed\xfe' and struct.unpack_from('<I',binary,4)[0]==0x100000c,'Not arm64 Mach-O'
  assert prefix+'Assets.car' in z.namelist(),'Missing app icon assets'
  root=prefix+'Phonon/'
  manifest=json.loads(z.read(root+'manifest.json'))
  for e in manifest['files']:
   assert '..' not in PurePosixPath(e['path']).parts
   data=z.read(root+e['path'])
   assert len(data)==e['size'] and hashlib.sha256(data).hexdigest()==e['sha256'],e['path']
  voices=manifest['voices']
  assert len({v['id'] for v in voices})==len(voices)
  assert len({v['sha256'] for v in voices})==len(voices)
  qa=json.loads(z.read(root+'voice-synthesis-results.json'))
  validate_qa_report(qa,manifest)
  cvroot=prefix+'OpenVoice/'
  cv=json.loads(z.read(cvroot+'model-manifest.json'))
  assert cv['engine']=='OpenVoiceV2'
  verify(lambda p:z.read(prefix+p),manifest,cv,qa,[n.removeprefix(prefix) for n in z.namelist() if n.startswith(prefix) and not n.endswith('/')])
  for entry in cv['files']:
   assert '..' not in PurePosixPath(entry['path']).parts
   payload=z.read(cvroot+entry['path'])
   assert len(payload)==entry['size'] and hashlib.sha256(payload).hexdigest()==entry['sha256'],entry['path']
  for voice in voices:
   if voice['engine']=='phonon31m':
    profile=json.loads(z.read(cvroot+'Profiles/'+voice['id']+'.json'))
    assert profile['id']==voice['id'] and profile['ttsEmbeddingSHA256']==voice['sha256']
   else:
    profile=json.loads(z.read(root+voice['path']))
    base=next(v for v in voices if v['id']==voice['baseVoiceID'])
    assert profile['id']==voice['id'] and profile['ttsEmbeddingSHA256']==base['sha256']
   assert profile['converterRevision']==cv['sourceRevision']
  print(json.dumps({'bundle':info['CFBundleIdentifier'],'version':info['CFBundleShortVersionString'],'profiles':len(voices),'deviceVerified':0,'archive':'passed'},indent=2))
if __name__=='__main__': inspect(sys.argv[1])
