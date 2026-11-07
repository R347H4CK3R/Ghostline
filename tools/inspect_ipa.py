import hashlib,json,plistlib,struct,sys,zipfile
from pathlib import PurePosixPath

def inspect(path):
 with zipfile.ZipFile(path) as z:
  if z.testzip() is not None: raise ValueError('Corrupt archive')
  prefix='Payload/VoiceMatrix.app/'
  info=plistlib.loads(z.read(prefix+'Info.plist'))
  assert info['CFBundleIdentifier']=='com.voicematrix.app'
  assert info['CFBundleShortVersionString']=='0.2.0'
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
  print(json.dumps({'bundle':info['CFBundleIdentifier'],'version':info['CFBundleShortVersionString'],'profiles':len(voices),'deviceVerified':0,'archive':'passed'},indent=2))
if __name__=='__main__': inspect(sys.argv[1])
