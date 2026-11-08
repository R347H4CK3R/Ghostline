"""Authenticated, hash-bound private conditioning transfers; never serve arbitrary paths."""
import hashlib,json,pathlib,re,threading
from tools.master_voices import _folder_bytes

class TransferError(ValueError):
 def __init__(self,status):self.status=status

def digest(data):return hashlib.sha256(data).hexdigest()

def revision(files):
 return digest(''.join(r['path']+':'+r['sha256']+':'+str(r['bytes'])+'\n' for r in sorted(files,key=lambda x:x['path'])).encode())

class PrivateVoices:
 def __init__(self,root):self.root=pathlib.Path(root);self.lock=threading.Lock();self.current=None
 def read(self,path,limit):
  if self.root.is_symlink() or path.is_symlink() or path.parent.is_symlink() or not path.is_file() or path.stat().st_size>limit:raise TransferError(409)
  with path.open('rb') as f:data=f.read(limit+1)
  if len(data)>limit:raise TransferError(409)
  return data
 def catalog(self):
  with self.lock:
   try:
    index=self.read(self.root/'collection.json',256000);value=json.loads(index);entries=value['voices']
    if value.get('schemaVersion')!=1 or not isinstance(entries,list) or not 1<=len(entries)<=1000:raise TransferError(409)
    files={'collection.json':index};seen=set();owners=set();total=len(index)
    for entry in entries:
     identifier=entry['id']
     if not isinstance(identifier,str) or not re.fullmatch(r'[a-z0-9_-]{1,100}',identifier) or entry['folder']!=identifier or identifier in seen:raise TransferError(409)
     seen.add(identifier);folder=self.root/identifier;metadata,audio=_folder_bytes(folder)
     manifest=self.read(folder/'manifest.json',65536)
     if metadata['id']!=identifier or metadata['referenceSHA256'] in owners or digest(audio)!=metadata['referenceSHA256']:raise TransferError(409)
     # Revalidate the exact pair captured for this snapshot, not a later reread.
     captured=json.loads(manifest)
     if captured!=metadata:raise TransferError(409)
     owners.add(metadata['referenceSHA256']);files[identifier+'/manifest.json']=manifest;files[identifier+'/reference.wav']=audio
     total+=len(manifest)+len(audio)
     if total>67108864:raise TransferError(413)
    if self.read(self.root/'collection.json',256000)!=index:raise TransferError(409)
    rows=[dict(path=p,sha256=digest(data),bytes=len(data)) for p,data in sorted(files.items())]
    result=dict(schemaVersion=1,revision=revision(rows),files=rows)
    self.current=result
    return result
   except TransferError:raise
   except (OSError,ValueError,KeyError,TypeError):raise TransferError(409)
 def file(self,snapshot,name):
  with self.lock:
   if self.current is None or snapshot!=self.current['revision']:raise TransferError(409)
   row=next((r for r in self.current['files'] if r['path']==name),None)
   if row is None:raise TransferError(404)
   try:data=self.read(self.root/name,row['bytes'])
   except OSError:raise TransferError(409)
   if len(data)!=row['bytes'] or digest(data)!=row['sha256']:raise TransferError(409)
   return data
