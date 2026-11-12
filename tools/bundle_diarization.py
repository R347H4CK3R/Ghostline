"""Build-time only: stage immutable, hash-verified CoreML assets, never user audio.
Runtime does not call this downloader. Existing mismatched bytes are never deleted.
"""
import hashlib,json,pathlib,urllib.request,urllib.parse,zipfile
REVISION='df2625ac79a7ac6b65ad868fee6d80f320da4232'
BASE=f'https://huggingface.co/FluidInference/speaker-diarization-coreml/resolve/{REVISION}/'
LOCK=pathlib.Path(__file__).with_name('diarization-resource-lock.json')
def stage(destination,lock,fetch):
 destination=pathlib.Path(destination)
 if destination.is_symlink():raise ValueError('Bundle root cannot be a link')
 for path,entry in lock['files'].items():
  parts=pathlib.PurePosixPath(path).parts
  if not parts or path.startswith('/') or '\\' in path or any(p in ('.','..') for p in parts):raise ValueError('Unsafe bundle path')
  if not isinstance(entry['size'],int) or not 0<entry['size']<=25_000_000:raise ValueError('Invalid byte limit')
  target=destination.joinpath(*parts)
  for parent in [destination,*target.parents,target]:
   if parent.is_symlink():raise ValueError('Links are not bundle files')
  if target.exists():
   if not target.is_file() or target.stat().st_size!=entry['size']:raise ValueError('Existing bundle differs; retained unchanged')
   data=target.read_bytes()
   if len(data)!=entry['size'] or hashlib.sha256(data).hexdigest()!=entry['sha256']:raise ValueError('Existing bundle differs; retained unchanged')
   continue
  data=fetch(path)
  if len(data)!=entry['size'] or hashlib.sha256(data).hexdigest()!=entry['sha256']:raise ValueError('Downloaded bundle hash/size mismatch')
  target.parent.mkdir(parents=True,exist_ok=True)
  # Exclusive creation means a concurrent writer is never replaced.
  with target.open('xb') as out:out.write(data)
 return destination

def inspect_ipa(path,lock):
 prefix='Payload/VoiceMatrix.app/Diarization/'
 with zipfile.ZipFile(path) as archive:
  names=archive.namelist()
  if len(names)!=len(set(names)):raise ValueError('Duplicate archive entry')
  for name,expected in lock['files'].items():
   info=archive.getinfo(prefix+name)
   if info.file_size!=expected['size']:raise ValueError('Packaged diarization size differs')
   if hashlib.sha256(archive.read(info)).hexdigest()!=expected['sha256']:raise ValueError('Packaged diarization hash differs')
  if archive.read(prefix+'resource-lock.json')!=LOCK.read_bytes():raise ValueError('Packaged diarization lock differs')
 return {'diarizationBundle':'verified','files':len(lock['files']),'modelRevision':REVISION}

def main():
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--inspect-ipa',type=pathlib.Path);parser.add_argument('--destination',type=pathlib.Path,default=pathlib.Path('VoiceMatrix/Resources/Diarization'));args=parser.parse_args()
 lock=json.loads(LOCK.read_text())
 if args.inspect_ipa:
  print(json.dumps(inspect_ipa(args.inspect_ipa,lock)));return
 def fetch(path):
  limit=lock['files'][path]['size']
  with urllib.request.urlopen(BASE+urllib.parse.quote(path),timeout=90) as response:return response.read(limit+1)
 root=stage(args.destination,lock,fetch)
 manifest=root/'resource-lock.json'
 data=LOCK.read_bytes()
 if manifest.exists() and manifest.read_bytes()!=data:raise ValueError('Existing lock differs; retained unchanged')
 if not manifest.exists():
  with manifest.open('xb') as out:out.write(data)
 print(json.dumps({'files':len(lock['files']),'bytes':sum(f['size'] for f in lock['files'].values()),'destination':str(root)}))
if __name__=='__main__':main()
