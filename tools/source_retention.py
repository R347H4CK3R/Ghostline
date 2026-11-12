"""Private bounded retained inputs. No deletion or delivery acknowledgement API.

Server-side file responses are not evidence of destination storage. Every entry
remains ineligible for cleanup until a future authenticated sync protocol exists.
"""
import contextlib,hashlib,json,os,pathlib,shutil,stat,tempfile,time,uuid
from tools.master_voices import _publish_lock

MAX_STORE_BYTES=8*1024**3
MAX_ENTRIES=4096
MAX_SOURCE_ATTEMPTS=32

def reject_reparse(info):
 # Windows junctions are reparse points but need not report as symlinks.
 if getattr(info,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0x400):raise ValueError('Reparse retention directory or artifact')

def real_directory(path):
 path=pathlib.Path(path).absolute()
 if '..' in path.parts:raise ValueError('Noncanonical retention directory')
 for ancestor in (path,*path.parents):
  if ancestor.is_symlink():raise ValueError('Linked retention directory')
  try:reject_reparse(ancestor.lstat())
  except FileNotFoundError:pass
 # Callers pass canonical paths, including resolved macOS temporary aliases.
 if path.exists() and not path.is_dir():raise ValueError('Retention root is not a directory')
 path.mkdir(parents=True,exist_ok=True,mode=0o700)
 return path.resolve()

def check_capacity(root,reserve=0):
 total=0;count=0
 for base,dirs,files in os.walk(root,followlinks=False):
  for name in dirs+files:
   p=pathlib.Path(base)/name;st=p.lstat();reject_reparse(st);count+=1
   if stat.S_ISLNK(st.st_mode) or not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)):raise ValueError('Unsafe retained artifact')
   if stat.S_ISREG(st.st_mode):total+=st.st_size
   if count>MAX_ENTRIES-128 or total+reserve>MAX_STORE_BYTES:raise ValueError('Retention capacity reached; existing data preserved')
 if shutil.disk_usage(root).free<reserve+128*1024**2:raise ValueError('Insufficient disk for retained source')

@contextlib.contextmanager
def retained_directory(*,dir,prefix):
 root=real_directory(dir)
 with _publish_lock(root/'.retained-allocation.lock'):
  check_capacity(root)
  path=pathlib.Path(tempfile.mkdtemp(prefix=prefix,dir=root))
 yield str(path) # Deliberately no cleanup, including exceptions and cancellation.

def write_record(path,value):
 data=json.dumps(value,sort_keys=True,allow_nan=False).encode('utf8')
 if len(data)>65536:raise ValueError('Retained record exceeds bound')
 fd,name=tempfile.mkstemp(prefix='.record-',dir=path.parent)
 try:
  with os.fdopen(fd,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
  if path.is_symlink():raise ValueError('Linked retained record')
  os.replace(name,path)
 finally:pass # A failed atomic record write remains available for diagnosis.

def digest(path):
 with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

@contextlib.contextmanager
def source_slot(root,url,max_bytes,request_id=None):
 if root is None:raise ValueError('Explicit persistent retention_root required')
 if request_id is not None and (not isinstance(request_id,str) or str(uuid.UUID(request_id))!=request_id):raise ValueError('Invalid retained request ID')
 root=real_directory(root)
 # Whole-store lock bounds concurrent allocation and prevents two writers reusing
 # source bytes while one consumer is extracting them. Cross-process, no TTL lease.
 with _publish_lock(root/'.source-store.lock'):
  check_capacity(root)
  key=hashlib.sha256(url.encode('utf8')).hexdigest();folder=root/key
  if folder.is_symlink():raise ValueError('Linked retained source')
  folder.mkdir(exist_ok=True,mode=0o700)
  chosen=None;cached=None
  attempts=sorted(folder.iterdir())
  if len(attempts)>MAX_SOURCE_ATTEMPTS:raise ValueError('Retained attempt capacity exceeded')
  for attempt in attempts:
   if not attempt.is_dir() or attempt.is_symlink():raise ValueError('Invalid retained attempt')
   record=attempt/'source.json'
   if not record.exists():continue
   if record.is_symlink() or record.stat().st_size>65536:raise ValueError('Invalid retained manifest')
   data=json.loads(record.read_text(encoding='utf8'))
   if data.get('schemaVersion')!=1 or data.get('sourceURL')!=url or data.get('cleanupEligible') is not False:raise ValueError('Invalid retained source binding')
   movie=attempt/'source.mp4'
   if movie.is_symlink() or not movie.is_file() or not 0<movie.stat().st_size<=max_bytes or movie.stat().st_size!=data.get('sourceBytes') or digest(movie)!=data.get('sourceSHA256'):raise ValueError('Retained source changed; original evidence preserved')
   chosen=attempt;cached=data;break
  if chosen is None:
   if len(attempts)>=MAX_SOURCE_ATTEMPTS:raise ValueError('Retained attempt capacity reached; existing data preserved')
   check_capacity(root,max_bytes*2+512*1024**2)
   chosen=pathlib.Path(tempfile.mkdtemp(prefix='attempt-',dir=folder))
  if cached is not None:check_capacity(root,512*1024**2)
  usage=pathlib.Path(tempfile.mkdtemp(prefix='use-',dir=chosen))
  state=dict(schemaVersion=1,sourceURL=url,requestID=request_id,startedAt=time.time(),status='acquiring',cleanupEligible=False)
  write_record(usage/'state.json',state)
  try:
   yield chosen,usage,cached
  except BaseException as error:
   state.update(status='interrupted' if isinstance(error,(InterruptedError,KeyboardInterrupt)) else 'failed',errorType=type(error).__name__,updatedAt=time.time())
   write_record(usage/'state.json',state);raise
  else:
   state.update(status='retained-awaiting-verified-delivery',updatedAt=time.time());write_record(usage/'state.json',state)
