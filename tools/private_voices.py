"""Authenticated, hash-bound private conditioning transfers; never serve arbitrary paths."""
import hashlib,json,pathlib,re,threading,os,stat,io,zipfile
from tools.voice_pack import validate_pack

CATALOG_BYTE_LIMIT=1048576

class TransferError(ValueError):
 def __init__(self,status):self.status=status

def digest(data):return hashlib.sha256(data).hexdigest()

def revision(files):
 return digest(''.join(r['path']+':'+r['sha256']+':'+str(r['bytes'])+'\n' for r in sorted(files,key=lambda x:x['path'])).encode())

class PrivateVoices:
 def __init__(self,root):
  root=pathlib.Path(root)
  if root.is_symlink():raise TransferError(409)
  self.root=root.resolve();self.lock=threading.Lock();self.current=None
  try:info=self.root.stat();self.identity=(info.st_dev,info.st_ino)
  except OSError:self.identity=None
 def read(self,path,limit):
  def identity(info):return (info.st_dev,info.st_ino)
  def windows_path(f):
   import ctypes,msvcrt
   from ctypes import wintypes
   api=ctypes.WinDLL('kernel32',use_last_error=True).GetFinalPathNameByHandleW
   api.argtypes=[wintypes.HANDLE,wintypes.LPWSTR,wintypes.DWORD,wintypes.DWORD];api.restype=wintypes.DWORD
   buffer=ctypes.create_unicode_buffer(32768);n=api(msvcrt.get_osfhandle(f.fileno()),buffer,len(buffer),0)
   if n==0 or n>=len(buffer):raise TransferError(409)
   value=buffer.value
   if value.startswith('\\\\?\\UNC\\'):value='\\\\'+value[8:]
   elif value.startswith('\\\\?\\'):value=value[4:]
   return os.path.normcase(os.path.normpath(value))
  if self.identity is None:self.identity=identity(self.root.stat())
  if identity(self.root.stat())!=self.identity or self.root.resolve()!=self.root:raise TransferError(409)
  if os.name=='nt':
   with path.open('rb') as f:
    expected=os.path.normcase(os.path.normpath(str(path)))
    if windows_path(f)!=expected or not stat.S_ISREG(os.fstat(f.fileno()).st_mode):raise TransferError(409)
    data=f.read(limit+1)
    if windows_path(f)!=expected:raise TransferError(409)
  else:
   fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
   try:
    walked=pathlib.Path('/')
    for part in path.parts[1:-1]:
     child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=child;walked=walked/part
     if walked==self.root and identity(os.fstat(fd))!=self.identity:raise TransferError(409)
    leaf=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=fd)
    with os.fdopen(leaf,'rb') as f:
     if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):raise TransferError(409)
     data=f.read(limit+1)
   finally:os.close(fd)
  if len(data)>limit or identity(self.root.stat())!=self.identity:raise TransferError(409)
  return data
 def catalog(self,progress=lambda completed,total:None):
  with self.lock:
   try:
    index=self.read(self.root/'collection.json',256000);value=json.loads(index);entries=value['voices']
    if value.get('schemaVersion')!=1 or not isinstance(entries,list) or not 1<=len(entries)<=1000:raise TransferError(409)
    files={'collection.json':index};seen=set();owners=set();total=len(index);profiles=[]
    for entry in entries:
     identifier=entry['id']
     if not isinstance(identifier,str) or not re.fullmatch(r'[a-z0-9_-]{1,100}',identifier) or entry['folder']!=identifier or identifier in seen:raise TransferError(409)
     seen.add(identifier);folder=self.root/identifier
     manifest=self.read(folder/'manifest.json',65536);audio=self.read(folder/'reference.wav',848000)
     memory=io.BytesIO()
     with zipfile.ZipFile(memory,'w') as z:z.writestr('manifest.json',manifest);z.writestr('reference.wav',audio)
     memory.seek(0);metadata=validate_pack(memory)
     if metadata['id']!=identifier or metadata['referenceSHA256'] in owners or digest(audio)!=metadata['referenceSHA256']:raise TransferError(409)
     # Revalidate the exact pair captured for this snapshot, not a later reread.
     captured=json.loads(manifest)
     if captured!=metadata:raise TransferError(409)
     profiles.append(metadata)
     owners.add(metadata['referenceSHA256']);files[identifier+'/manifest.json']=manifest;files[identifier+'/reference.wav']=audio
     total+=len(manifest)+len(audio)
     if total>67108864:raise TransferError(413)
     progress(len(seen),len(entries))
    if self.read(self.root/'collection.json',256000)!=index:raise TransferError(409)
    rows=[dict(path=p,sha256=digest(data),bytes=len(data)) for p,data in sorted(files.items())]
    result=dict(schemaVersion=1,revision=revision(rows),files=rows,voices=profiles)
    if len(json.dumps(result).encode())>CATALOG_BYTE_LIMIT:raise TransferError(413)
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
