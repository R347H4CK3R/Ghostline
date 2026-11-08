"""Process lifetime ownership and conservative CPU scheduling for local workers."""
import contextlib,ctypes,os,pathlib

class WorkerBusy(RuntimeError):pass

@contextlib.contextmanager
def worker_lock(database):
 database=pathlib.Path(database).resolve()
 database.parent.mkdir(parents=True,exist_ok=True)
 path=database.with_name('.'+database.name+'.worker.lock')
 if path.is_symlink():raise ValueError('Worker lock cannot be a symbolic link')
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
  except OSError as e:raise WorkerBusy('A companion worker is already running for this queue') from e
  try:yield
  finally:
   lock.seek(0)
   if os.name=='nt':msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
   else:fcntl.flock(lock.fileno(),fcntl.LOCK_UN)
 # Never unlink: another process may already hold or be opening this inode.

def cpu_environment(threads):
 if type(threads) is not int or not 1<=threads<=4:raise ValueError('Choose 1–4 CPU threads')
 for key in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS'):
  os.environ[key]=str(threads)

def configure_torch(threads,runtime=None):
 cpu_environment(threads)
 if runtime is None:
  import torch
  runtime=torch
 runtime.set_num_threads(threads)
 if runtime.get_num_interop_threads()!=1:runtime.set_num_interop_threads(1)

def lower_priority():
 if os.name=='nt':
  # BELOW_NORMAL_PRIORITY_CLASS; never request administrator access.
  from ctypes import wintypes
  kernel=ctypes.WinDLL('kernel32',use_last_error=True)
  kernel.GetCurrentProcess.restype=wintypes.HANDLE
  kernel.SetPriorityClass.argtypes=[wintypes.HANDLE,wintypes.DWORD]
  kernel.SetPriorityClass.restype=wintypes.BOOL
  if not kernel.SetPriorityClass(kernel.GetCurrentProcess(),0x4000):raise ctypes.WinError(ctypes.get_last_error())
 elif hasattr(os,'nice'):os.nice(10)
