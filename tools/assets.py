"""Development-only asset integrity and pinned Phonon bundling; never run by the app."""
import argparse, hashlib, json, os, urllib.request, urllib.parse, struct, math
from pathlib import Path

def validate(root, entries):
 root=Path(root).resolve(); seen=set(); total=0
 for e in entries:
  rel=Path(e['path'])
  if rel.is_absolute() or '..' in rel.parts or e['path'] in seen: raise ValueError('Unsafe or duplicate asset path')
  seen.add(e['path']); p=(root/rel).resolve()
  if not p.is_relative_to(root) or not p.is_file(): raise ValueError('Missing asset: '+str(rel))
  if p.stat().st_size != e['size']: raise ValueError('Wrong size: '+str(rel))
  with p.open('rb') as f: digest=hashlib.file_digest(f,'sha256').hexdigest()
  if digest!=e['sha256']: raise ValueError('Checksum mismatch: '+str(rel))
  total+=e['size']
 return total

def unique_profiles(profiles):
 ids=set(); hashes=set()
 for p in profiles:
  if p['id'] in ids or p['sha256'] in hashes: raise ValueError('Duplicate voice profile')
  ids.add(p['id']); hashes.add(p['sha256'])

def tensor_digest(data):
 if len(data)<8: raise ValueError('Truncated safetensors header')
 n=struct.unpack_from('<Q',data)[0]
 if n>len(data)-8: raise ValueError('Invalid safetensors header length')
 header=json.loads(data[8:8+n]); tensor=header.get('emb')
 if not tensor or tensor['dtype']!='F32': raise ValueError('Expected F32 voice conditioning')
 shape=tensor['shape']; start,end=tensor['data_offsets']
 if not shape or any(not isinstance(x,int) or x<=0 for x in shape) or start<0 or end<start or end>len(data)-8-n or end-start!=math.prod(shape)*4: raise ValueError('Invalid tensor dimensions')
 raw=data[8+n+start:8+n+end]
 if any(not math.isfinite(v[0]) for v in struct.iter_unpack('<f',raw)): raise ValueError('Non-finite voice conditioning')
 return hashlib.sha256(json.dumps(shape).encode()+raw).hexdigest()

def validate_profiles(root, profiles):
 unique_profiles(profiles); seen=set()
 for profile in profiles:
  digest=tensor_digest((Path(root)/profile['path']).read_bytes())
  if digest in seen: raise ValueError('Duplicate conditioning data: '+profile['id'])
  if profile.get('tensorSha256') and digest!=profile['tensorSha256']: raise ValueError('Conditioning checksum mismatch')
  seen.add(digest)
 return len(seen)

def bundle(lock, root):
 root=Path(root); root.mkdir(parents=True,exist_ok=True)
 for e in lock['files']:
  path=root/e['path']; path.parent.mkdir(parents=True,exist_ok=True)
  try: validate(root,[e]); continue
  except ValueError: pass
  url=lock['baseURL']+'/'+urllib.parse.quote(e['remotePath'],safe='/')
  tmp=path.with_suffix(path.suffix+'.partial')
  with urllib.request.urlopen(url,timeout=120) as src, tmp.open('wb') as dst:
   while block:=src.read(1024*1024): dst.write(block)
  tmp.replace(path); validate(root,[e]); print('Verified',e['path'],flush=True)
 validate(root,lock['files']); validate_profiles(root,lock['voices'])
 (root/'manifest.json').write_text(json.dumps(lock,indent=2)+'\n')

if __name__=='__main__':
 p=argparse.ArgumentParser(); p.add_argument('--lock',default='models/phonon-lock.json'); p.add_argument('--root',default='VoiceMatrix/Resources/Phonon'); p.add_argument('--verify',action='store_true'); args=p.parse_args()
 lock=json.loads(Path(args.lock).read_text())
 if args.verify: print('Verified bytes:',validate(args.root,lock['files'])); validate_profiles(args.root,lock['voices'])
 else: bundle(lock,args.root)
