"""Scan an expanding master folder without treating previews as working models."""
import hashlib,json,pathlib,contextlib,io,os,re,shutil,tempfile,zipfile
from tools.voice_pack import validate_pack

class PublishBusy(ValueError):pass

def scan(directory):
 root=pathlib.Path(directory).resolve()
 if not root.is_dir():raise ValueError('Choose an existing Voices folder')
 profiles={};errors=[]
 for path in sorted(root.rglob('*.vmpack')):
  try:
   if path.is_symlink() or root not in path.resolve().parents:raise ValueError('Voice file is outside the selected folder')
   metadata=validate_pack(path);identifier=metadata['id']
   revision=hashlib.sha256(path.read_bytes()).hexdigest()
   if identifier in profiles:raise ValueError('Repeated voice ID: '+identifier)
   profiles[identifier]=dict(id=identifier,name=metadata['name'],categories=metadata['categories'],engine=metadata['engine'],revision=revision,file=str(path.relative_to(root)),nativeIOSVerified=False)
  except (ValueError,OSError) as error:errors.append(dict(file=str(path.relative_to(root)),error=str(error)))
 # A conflicting collection must be repaired before publishing its index.
 return dict(schemaVersion=1,status='ready' if not errors else 'needs-repair',voices=list(profiles.values()),errors=errors)

def compare(previous,current):
 if current['status']!='ready':raise ValueError('Repair invalid or conflicting voices before updating')
 old={v['id']:v for v in previous.get('voices',[])};new={v['id']:v for v in current['voices']}
 return dict(added=sorted(new.keys()-old.keys()),updated=sorted(k for k in new.keys()&old.keys() if new[k]['revision']!=old[k]['revision']),missing=sorted(old.keys()-new.keys()))

@contextlib.contextmanager
def _publish_lock(path):
 if path.is_symlink():raise ValueError('Invalid publisher lock')
 with path.open('a+b') as lock:
  if not path.stat().st_size:lock.write(b'0');lock.flush()
  lock.seek(0)
  try:
   if os.name=='nt':
    import msvcrt
    msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
   else:
    import fcntl
    fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
  except OSError as e:raise PublishBusy('Another voice publisher is active') from e
  try:yield
  finally:
   lock.seek(0)
   if os.name=='nt':msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
   else:fcntl.flock(lock.fileno(),fcntl.LOCK_UN)

def _folder_bytes(path):
 if path.is_symlink() or not path.is_dir():raise ValueError('Invalid voice folder')
 content={}
 for name,limit in [('manifest.json',65536),('reference.wav',848000)]:
  p=path/name
  if p.is_symlink() or not p.is_file() or p.stat().st_size>limit:raise ValueError('Invalid voice file')
  content[name]=p.read_bytes()
 memory=io.BytesIO()
 with zipfile.ZipFile(memory,'w') as z:
  for name,data in content.items():z.writestr(name,data)
 memory.seek(0);m=validate_pack(memory)
 return m,content['reference.wav']

def _write_folder(destination,metadata,audio):
 if any(p.is_symlink() for p in [destination,*destination.parents]):raise ValueError('Linked voice destinations are not supported')
 if destination.exists() or destination.is_symlink():
  old,data=_folder_bytes(destination)
  if old!=metadata or data!=audio:raise ValueError('An existing voice folder conflicts; repair it before publishing')
  return
 destination.parent.mkdir(parents=True,exist_ok=True)
 stage=pathlib.Path(tempfile.mkdtemp(prefix='.publish-',dir=destination.parent))
 try:
  for name,data in [('manifest.json',(json.dumps(metadata,indent=2)+'\n').encode('utf8')),('reference.wav',audio)]:
   with (stage/name).open('wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
  _folder_bytes(stage)
  _sync_directory(stage)
  os.rename(stage,destination)
  _sync_directory(destination.parent)
 finally:
  if stage.exists():shutil.rmtree(stage)

def _sync_directory(path):
 # Windows fsync applies to the files above; opening directories is unsupported.
 if os.name!='nt':
  fd=os.open(path,os.O_RDONLY|getattr(os,'O_DIRECTORY',0))
  try:os.fsync(fd)
  finally:os.close(fd)

def publish(packs,directory):
 """Append native-format profiles; changed existing IDs remain separate candidates.

 The collection index is the final atomic commit. Existing voice bytes are never
 replaced. Unindexed folders left by interruption are reusable only if identical.
 """
 root=pathlib.Path(directory)
 if root.is_symlink():raise ValueError('Choose a real local master folder')
 root=root.resolve()
 root.parent.mkdir(parents=True,exist_ok=True)
 with _publish_lock(root.parent/('.'+root.name+'.publish.lock')):
  current={};index=root/'collection.json'
  if index.exists() or index.is_symlink():
   if index.is_symlink() or not index.is_file() or index.stat().st_size>256000:raise ValueError('Invalid collection index')
   try:value=json.loads(index.read_text(encoding='utf8'))
   except (ValueError,UnicodeError) as e:raise ValueError('Invalid collection index') from e
   if not isinstance(value,dict) or value.get('schemaVersion')!=1 or not isinstance(value.get('voices'),list) or not 1<=len(value['voices'])<=1000:raise ValueError('Invalid collection index')
   for entry in value['voices']:
    if not isinstance(entry,dict) or not isinstance(entry.get('id'),str) or not re.fullmatch(r'[a-z0-9_-]{1,100}',entry['id']) or entry.get('folder')!=entry['id'] or entry['id'] in current:raise ValueError('Invalid or duplicated collection entry')
    m,audio=_folder_bytes(root/entry['id'])
    if m['id']!=entry['id']:raise ValueError('Voice ID does not match its folder')
    current[m['id']]=(m,audio)
  incoming={}
  for pack in packs:
   m=validate_pack(pack)
   with zipfile.ZipFile(pack) as z:audio=z.read('reference.wav')
   if hashlib.sha256(audio).hexdigest()!=m['referenceSHA256'] or len(audio)!=m['referenceBytes']:raise ValueError('Pack changed during publication')
   if len(m['categories'])>50:raise ValueError('At most 50 categories per voice')
   if m['id'] in incoming:raise ValueError('Repeated voice ID in publication')
   incoming[m['id']]=(m,audio)
  if not incoming:raise ValueError('Choose at least one reusable voice pack')
  if len(current.keys()|incoming.keys())>1000:raise ValueError('At most 1000 voices per collection')
  owners={}
  # Both old and proposed references participate, including rejected replacements.
  for identifier,(m,_) in list(current.items())+list(incoming.items()):
   ref=m['referenceSHA256']
   if ref in owners and owners[ref]!=identifier:raise ValueError('Repeated reference audio under another voice name')
   owners[ref]=identifier
  # Preflight orphan conflicts before writing any profile or changing the index.
  for identifier,(m,audio) in incoming.items():
   if identifier not in current and (root/identifier).exists():
    old,data=_folder_bytes(root/identifier)
    if old!=m or data!=audio:raise ValueError('An unindexed voice folder conflicts')
  result=dict(added=[],unchanged=[],needsReview=[],nativeIOSVerified=False)
  root.mkdir(exist_ok=True)
  _sync_directory(root.parent)
  for identifier,(m,audio) in incoming.items():
   if identifier in current:
    if current[identifier]==(m,audio):result['unchanged'].append(identifier)
    else:
     revision=hashlib.sha256(json.dumps(m,sort_keys=True).encode()+audio).hexdigest()
     _write_folder(root.parent/(root.name+'-Candidates')/identifier/revision,m,audio)
     result['needsReview'].append(identifier)
   else:
    _write_folder(root/identifier,m,audio);current[identifier]=(m,audio);result['added'].append(identifier)
  if result['added']:
   body=json.dumps(dict(schemaVersion=1,voices=[dict(id=k,folder=k) for k in sorted(current)]),indent=2)+'\n'
   fd,name=tempfile.mkstemp(prefix='.collection-',dir=root)
   try:
    with os.fdopen(fd,'w',encoding='utf8') as f:f.write(body);f.flush();os.fsync(f.fileno())
    os.replace(name,index)
    _sync_directory(root)
   finally:pathlib.Path(name).unlink(missing_ok=True)
  return result

