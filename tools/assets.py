"""Development-only asset integrity and pinned Phonon bundling; never run by the app."""
import argparse, hashlib, json, os, urllib.request, urllib.parse
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
 validate(root,lock['files']); unique_profiles(lock['voices'])
 (root/'manifest.json').write_text(json.dumps(lock,indent=2)+'\n')

if __name__=='__main__':
 p=argparse.ArgumentParser(); p.add_argument('--lock',default='models/phonon-lock.json'); p.add_argument('--root',default='VoiceMatrix/Resources/Phonon'); p.add_argument('--verify',action='store_true'); args=p.parse_args()
 lock=json.loads(Path(args.lock).read_text())
 if args.verify: print('Verified bytes:',validate(args.root,lock['files'])); unique_profiles(lock['voices'])
 else: bundle(lock,args.root)
