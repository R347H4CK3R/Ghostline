import os,pathlib,subprocess,sys,tempfile,unittest
from unittest.mock import patch

class CompanionRuntimeTests(unittest.TestCase):
 def test_duplicate_cli_exits_before_missing_models_are_initialized(self):
  from tools.companion_runtime import worker_lock
  with tempfile.TemporaryDirectory() as d:
   root=pathlib.Path(d);db=root/'queue.db'
   args=[sys.executable,'-m','tools.queue_processor']
   for key in ['database','specifications','work','master','checkpoint','vocoder-directory','vocab','whisper-cli','whisper-model']:
    args += ['--'+key,str(db if key=='database' else root/key)]
   with worker_lock(db):
    result=subprocess.run(args,capture_output=True,text=True,timeout=10)
    self.assertEqual(result.returncode,3,result.stderr)
    self.assertIn('already running',result.stderr.lower())
    self.assertFalse((root/'work').exists())
 def contender(self,database):
  code='from tools.companion_runtime import worker_lock,WorkerBusy\nimport sys\ntry:\n with worker_lock(sys.argv[1]): print("acquired")\nexcept WorkerBusy: print("busy");sys.exit(3)'
  return subprocess.run([sys.executable,'-c',code,str(database)],capture_output=True,text=True,timeout=10)
 def test_alias_contends_other_database_works_and_release_allows_restart(self):
  from tools.companion_runtime import worker_lock
  with tempfile.TemporaryDirectory() as d:
   root=pathlib.Path(d);(root/'nested').mkdir();database=root/'queue.db'
   with worker_lock(database):
    blocked=self.contender(root/'nested'/'..'/'queue.db')
    self.assertEqual(blocked.returncode,3,blocked.stderr);self.assertEqual(blocked.stdout.strip(),'busy')
    self.assertEqual(self.contender(root/'different.db').returncode,0)
   self.assertEqual(self.contender(database).returncode,0)
 def test_process_crash_releases_lock(self):
  with tempfile.TemporaryDirectory() as d:
   database=pathlib.Path(d)/'queue.db'
   code='from tools.companion_runtime import worker_lock\nimport sys,time\nwith worker_lock(sys.argv[1]):\n print("locked",flush=True);time.sleep(60)'
   proc=subprocess.Popen([sys.executable,'-u','-c',code,str(database)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
   try:
    self.assertEqual(proc.stdout.readline().strip(),'locked')
    self.assertEqual(self.contender(database).returncode,3)
   finally:
    proc.kill();proc.communicate(timeout=10)
   self.assertEqual(self.contender(database).returncode,0)
 def test_lower_priority_uses_a_valid_native_process_handle(self):
  code="from tools.companion_runtime import lower_priority\nimport os,ctypes\nbefore = os.getpriority(os.PRIO_PROCESS,0) if os.name != 'nt' else 0\nlower_priority()\nif os.name=='nt':\n from ctypes import wintypes\n k=ctypes.WinDLL('kernel32');k.GetCurrentProcess.restype=wintypes.HANDLE\n k.GetPriorityClass.argtypes=[wintypes.HANDLE];k.GetPriorityClass.restype=wintypes.DWORD\n assert k.GetPriorityClass(k.GetCurrentProcess())==0x4000\nelse: assert os.getpriority(os.PRIO_PROCESS,0)>=min(19,before+10), (before,os.getpriority(os.PRIO_PROCESS,0))\nprint('lowered')"
  result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=10)
  self.assertEqual(result.returncode,0,result.stderr)
  self.assertEqual(result.stdout.strip(),'lowered')
 def test_cpu_limits_apply_to_lazy_model_without_reimporting_threads(self):
  from tools.companion_runtime import cpu_environment,configure_torch
  class FakeTorch:
   threads=8;interop=8
   def set_num_threads(self,n):self.threads=n
   def get_num_interop_threads(self):return self.interop
   def set_num_interop_threads(self,n):
    if self.interop==1:raise RuntimeError('Cannot set interop twice')
    self.interop=n
  with patch.dict(os.environ,{},clear=True):
   cpu_environment(2)
   self.assertEqual([os.environ[x] for x in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS')],['2']*3)
   fake=FakeTorch();configure_torch(2,fake);configure_torch(2,fake)
   self.assertEqual((fake.threads,fake.interop),(2,1))
  for invalid in (0,5,True,1.5):
   with self.assertRaises(ValueError):cpu_environment(invalid)

if __name__=='__main__':unittest.main()
