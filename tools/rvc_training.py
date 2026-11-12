"""Desktop RVC training adapter. Training outputs remain unverified until conversion checks.

Upstream CLI pinned to 81eed5e8f68b6bed1789f682fe78cdd324495afc.
No engine installation, downloading or training on the gaming laptop is implicit.
"""
import array,hashlib,io,json,math,os,pathlib,re,shutil,signal,subprocess,sys,time,wave

from fractions import Fraction

UPSTREAM='81eed5e8f68b6bed1789f682fe78cdd324495afc'

def audit_dataset(directory):
 seen=set();rows=[];duplicates=[];rejected=[];seconds=Fraction(0)
 for path in sorted(pathlib.Path(directory).glob('*.wav')):
  try:
   # Hash the exact bytes inspected, even if the source is replaced mid-audit.
   with path.open('rb') as stream:raw=stream.read(64*1024*1024+1)
   if len(raw)>64*1024*1024:raise ValueError('Recording exceeds the bounded WAV size')
   with wave.open(io.BytesIO(raw)) as w:
    if w.getnchannels()!=1 or w.getsampwidth()!=2 or not 16000<=w.getframerate()<=48000:raise ValueError('Use mono PCM16 WAV at 16–48 kHz')
    if w.getnframes()>w.getframerate()*600:raise ValueError('Split recordings longer than ten minutes')
    rate=w.getframerate();pcm=w.readframes(w.getnframes())
    if len(pcm)!=w.getnframes()*2:raise ValueError('Truncated WAV')
   digest=hashlib.sha256(pcm+str(rate).encode()).hexdigest()
   if digest in seen:duplicates.append(path.name);continue
   seen.add(digest);samples=array.array('h',pcm)
   if sys.byteorder!='little':samples.byteswap()
   size=rate//50;active=0
   for i in range(0,len(samples),size):
    frame=samples[i:i+size]
    if frame and sum(x*x for x in frame)/len(frame)>327.67**2:active+=len(frame)
   if not samples or active*2<rate:raise ValueError('Insufficient non-silent audio')
   if sum(abs(x)>=32767 for x in samples)/len(samples)>.001:raise ValueError('Clipped recording')
   rows.append(dict(file=path.name,sha256=hashlib.sha256(raw).hexdigest(),activeSeconds=active/rate));seconds+=Fraction(active,rate)
  except (ValueError,wave.Error,EOFError) as error:rejected.append(dict(file=path.name,error=str(error)))
 # Sixty unique non-silent seconds is an engineering admission floor, not a quality guarantee.
 return dict(status='ready-for-training' if seconds>=60 and not rejected else 'insufficient-data',uniqueSeconds=round(float(seconds),3),minimumSeconds=60,files=rows,duplicates=duplicates,rejected=rejected)

def training_commands(root,dataset,experiment,python,epochs):
 if not re.fullmatch('[a-z0-9_-]{1,80}',experiment):raise ValueError('Unsafe experiment name')
 if not isinstance(epochs,int) or not 1<=epochs<=1200:raise ValueError('Epochs must be 1–1200')
 exp=str(pathlib.Path(root).resolve()/'logs'/experiment)
 return dict(
  preprocess=[python,str(pathlib.Path(__file__).with_name('rvc_preprocess.py').resolve()),'--root',str(pathlib.Path(root).resolve()),'--dataset',str(pathlib.Path(dataset).resolve()),'--experiment',exp],
  pitch=[python,'-m','train.dataset.extract_f0','cpu',exp,'2','pm'],
  features=[python,'-m','train.dataset.extract_hubert_feature','cpu','1','0',exp,'v2','false'],
  train=[python,str(pathlib.Path(__file__).with_name('rvc_train_cpu.py').resolve()),'--root',str(pathlib.Path(root).resolve()),'--','-e',experiment,'-sr','40k','-f0','1','-bs','1','-g','','-te',str(epochs),'-se','5','-pg','assets/pretrained_v2/f0G40k.pth','-pd','assets/pretrained_v2/f0D40k.pth','-l','1','-c','0','-sw','1','-v','v2'],
  index=[python,'-m','train.train_index',experiment,'v2','assets/indices','2','single'])

def prepare_filelist(exp,admitted_files=None):
 from tools.rvc_preprocess import validate_arrays
 exp=pathlib.Path(exp).resolve();rows=[]
 for wav in sorted((exp/'0_gt_wavs').glob('*.wav')):
  if admitted_files is not None and wav.name not in admitted_files:continue
  paths=[wav,exp/'3_feature768'/(wav.stem+'.npy'),exp/'2a_f0'/(wav.name+'.npy'),exp/'2b-f0nsf'/(wav.name+'.npy')]
  if any(not p.is_file() or not p.stat().st_size for p in paths):raise ValueError('Missing extracted feature for '+wav.name)
  if any('|' in str(p) or '\n' in str(p) for p in paths):raise ValueError('Unsafe training path')
  validate_arrays(*paths[1:])
  rows.append('|'.join(str(p) for p in paths)+'|0')
 if not rows:raise ValueError('No usable preprocessed training samples')
 (exp/'filelist.txt').write_text('\n'.join(rows)+'\n');return len(rows)

def snapshot_dataset(source, destination, report):
 """Freeze only admitted, unique WAVs and verify the audited hashes after copy."""
 source=pathlib.Path(source).resolve();destination=pathlib.Path(destination)
 destination.mkdir(exist_ok=False)
 if not report['files']:raise ValueError('No audited training files')
 for row in report['files']:
  name=row['file']
  if pathlib.Path(name).name!=name or not name.endswith('.wav'):raise ValueError('Unsafe dataset filename')
  target=destination/name
  shutil.copyfile(source/name,target)
  if _output_hash(target)!=row['sha256']:raise ValueError('Training audio changed after audit: '+name)
 return destination

class _WindowsJob:
 """Contain descendants before opening the wrapper's stdin launch gate."""
 def __init__(self):
  import ctypes
  from ctypes import wintypes
  # Fixed-width Windows ABI fields; SIZE_T/ULONG_PTR follow pointer width.
  class BasicLimits(ctypes.Structure):
   _fields_=[('PerProcessUserTimeLimit',ctypes.c_int64),('PerJobUserTimeLimit',ctypes.c_int64),('LimitFlags',ctypes.c_uint32),('MinimumWorkingSetSize',ctypes.c_size_t),('MaximumWorkingSetSize',ctypes.c_size_t),('ActiveProcessLimit',ctypes.c_uint32),('Affinity',ctypes.c_size_t),('PriorityClass',ctypes.c_uint32),('SchedulingClass',ctypes.c_uint32)]
  class IOCounters(ctypes.Structure):
   _fields_=[(name,ctypes.c_uint64) for name in ('ReadOperationCount','WriteOperationCount','OtherOperationCount','ReadTransferCount','WriteTransferCount','OtherTransferCount')]
  class ExtendedLimits(ctypes.Structure):
   _fields_=[('BasicLimitInformation',BasicLimits),('IoInfo',IOCounters),('ProcessMemoryLimit',ctypes.c_size_t),('JobMemoryLimit',ctypes.c_size_t),('PeakProcessMemoryUsed',ctypes.c_size_t),('PeakJobMemoryUsed',ctypes.c_size_t)]
  class BasicAccounting(ctypes.Structure):
   _fields_=[('TotalUserTime',ctypes.c_int64),('TotalKernelTime',ctypes.c_int64),('ThisPeriodTotalUserTime',ctypes.c_int64),('ThisPeriodTotalKernelTime',ctypes.c_int64),('TotalPageFaultCount',ctypes.c_uint32),('TotalProcesses',ctypes.c_uint32),('ActiveProcesses',ctypes.c_uint32),('TotalTerminatedProcesses',ctypes.c_uint32)]
  self.accounting_type=BasicAccounting
  self.api=ctypes.WinDLL('kernel32',use_last_error=True)
  for name,args,result in [
   ('CreateJobObjectW',[wintypes.LPVOID,wintypes.LPCWSTR],wintypes.HANDLE),
   ('SetInformationJobObject',[wintypes.HANDLE,ctypes.c_int,wintypes.LPVOID,wintypes.DWORD],wintypes.BOOL),
   ('AssignProcessToJobObject',[wintypes.HANDLE,wintypes.HANDLE],wintypes.BOOL),
   ('QueryInformationJobObject',[wintypes.HANDLE,ctypes.c_int,wintypes.LPVOID,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD)],wintypes.BOOL),
   ('TerminateJobObject',[wintypes.HANDLE,wintypes.UINT],wintypes.BOOL),
   ('CloseHandle',[wintypes.HANDLE],wintypes.BOOL)]:
   function=getattr(self.api,name);function.argtypes=args;function.restype=result
  self.handle=self.api.CreateJobObjectW(None,None)
  if not self.handle:raise ctypes.WinError(ctypes.get_last_error())
  limits=ExtendedLimits();limits.BasicLimitInformation.LimitFlags=0x2000 # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
  if not self.api.SetInformationJobObject(self.handle,9,ctypes.byref(limits),ctypes.sizeof(limits)):
   error=ctypes.WinError(ctypes.get_last_error())
   self.api.CloseHandle(self.handle);self.handle=None
   raise error
 def assign(self,child):
  if not self.api.AssignProcessToJobObject(self.handle,int(child._handle)):
   import ctypes
   raise ctypes.WinError(ctypes.get_last_error())
 def close(self):
  if not self.handle:return
  import ctypes
  try:
   if not self.api.TerminateJobObject(self.handle,1):raise ctypes.WinError(ctypes.get_last_error())
   # Termination is asynchronous. The leader may be gone while descendants
   # still hold the stage's cwd or output files, so drain the whole job first.
   deadline=time.monotonic()+5
   while True:
    accounting=self.accounting_type()
    if not self.api.QueryInformationJobObject(self.handle,1,ctypes.byref(accounting),ctypes.sizeof(accounting),None):raise ctypes.WinError(ctypes.get_last_error())
    if accounting.ActiveProcesses==0:break
    if time.monotonic()>=deadline:raise TimeoutError('Windows job processes did not exit within five seconds')
    time.sleep(.05)
  finally:self.api.CloseHandle(self.handle);self.handle=None

def run_stage(command, *, cwd, env, log, timeout, cancel=None):
 """Bound a CLI stage and terminate its process tree before returning on abort.

 Windows gates launch until a Job Object owns the wrapper and descendants.
 POSIX kills the isolated process group, including SIGTERM-resistant children.
 Logs go directly to disk so a verbose stage cannot deadlock on a full pipe.
 """
 if not math.isfinite(timeout) or timeout<=0:raise ValueError('Stage timeout must be positive and finite')
 if cancel and cancel.is_set():raise InterruptedError('Training cancelled')
 job=_WindowsJob() if os.name=='nt' else None
 child=None
 try:
  if job:
   # No training code may execute until job assignment succeeds. Unlike taskkill,
   # the job keeps descendants addressable even after their parent has exited.
   wrapper="import subprocess,sys; token=sys.stdin.buffer.read(1); sys.exit(subprocess.call(sys.argv[1:]) if token==b'1' else 125)"
   child=subprocess.Popen([sys.executable,'-c',wrapper,*command],cwd=cwd,env=env,stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
   job.assign(child)
   child.stdin.write(b'1');child.stdin.close()
  else:child=subprocess.Popen(command,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 except BaseException:
  if child is not None:
   if child.stdin and not child.stdin.closed:child.stdin.close()
   child.kill();child.wait(timeout=5)
  if job:job.close()
  raise
 deadline=time.monotonic()+timeout
 try:
  while True:
   if cancel and cancel.is_set():raise InterruptedError('Training cancelled')
   if time.monotonic()>=deadline:raise TimeoutError('Training stage timed out')
   result=child.poll()
   if result is not None:
    if result:raise subprocess.CalledProcessError(result,command)
    return
   time.sleep(min(.1,max(0,deadline-time.monotonic())))
 finally:
  try:
   if job:job.close()
   else:
    # Do this even after the leader exits: its children can still be alive.
    try:os.killpg(child.pid,signal.SIGKILL)
    except ProcessLookupError:pass
  finally:child.wait(timeout=5)

def _output_hash(path):
 if not path.is_file() or not path.stat().st_size:raise ValueError('Missing or empty training output: '+str(path))
 digest=hashlib.sha256()
 with path.open('rb') as stream:
  for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
 return digest.hexdigest()

def train(root,dataset,experiment,permission,python=sys.executable,epochs=200,cancel=None,stage_timeout=6*60*60):
 """Execute real upstream preparation/training/index stages. No verified-model claim."""
 if not math.isfinite(stage_timeout) or stage_timeout<=0:raise ValueError('Stage timeout must be positive and finite')
 if not permission.strip():raise ValueError('Record permission to use the training audio')
 root=pathlib.Path(root).resolve();commands=training_commands(root,dataset,experiment,python,epochs)
 report=audit_dataset(dataset)
 if report['status']!='ready-for-training':return report
 revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True,timeout=10).strip()
 if revision!=UPSTREAM:raise ValueError('Use the pinned RVC source revision')
 if subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=root,text=True,timeout=10).strip():raise ValueError('Pinned RVC tracked source is modified')
 for asset in ['configs/v1/40k.json','assets/pretrained_v2/f0G40k.pth','assets/pretrained_v2/f0D40k.pth','assets/hubert_base/config.json','assets/hubert_base/preprocessor_config.json']:
  if not (root/asset).is_file():raise ValueError('Missing offline RVC resource: '+asset)
 if not any((root/'assets/hubert_base').glob('*.safetensors')) and not any((root/'assets/hubert_base').glob('*.bin')):raise ValueError('Missing local HuBERT weights')
 exp=root/'logs'/experiment
 for output_dir in (root/'assets/weights',root/'assets/indices',root/'logs'):
  if output_dir.resolve()!=output_dir:raise ValueError('Output directory redirects through a symlink or junction: '+str(output_dir))
 # Exported weights/indices can outlive logs. Refuse rather than overwrite them.
 conflicts=list((root/'assets/weights').glob(experiment+'*.pth'))+list((root/'assets/indices').glob('*'+experiment+'*.index'))
 if conflicts:raise FileExistsError('Experiment already has exported outputs: '+str(conflicts[0]))
 # A new experiment prevents stale features/checkpoints from another dataset being silently reused.
 exp.mkdir(parents=True,exist_ok=False)
 shutil.copyfile(root/'configs/v1/40k.json',exp/'config.json')
 state=dict(status='preparing',experiment=experiment,epochs=epochs,stageTimeoutSeconds=stage_timeout,sourceRevision=revision,dataset=report,permission=permission,completedStages=[])
 def save():
  target=exp/'voicematrix-training.json';temporary=target.with_suffix('.tmp');temporary.write_text(json.dumps(state,indent=2));temporary.replace(target)
 save();env=dict(os.environ,PYTHONPATH=str(root),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='2')
 try:
  snapshot=snapshot_dataset(dataset,exp/'source-audio',report)
  commands=training_commands(root,snapshot,experiment,python,epochs)
  for stage,command in commands.items():
   if cancel and cancel.is_set():raise InterruptedError('Training cancelled')
   if stage=='train':
    from tools.rvc_preprocess import audit_preprocessed
    state['effectiveDataset']=audit_preprocessed(exp,expected_sources=len(report['files']),validate_features=True);save()
    if state['effectiveDataset']['status']!='ready-for-training':raise ValueError('Insufficient effective training audio after feature alignment')
    prepare_filelist(exp,{row['file'] for row in state['effectiveDataset']['files']})
   state['status']=stage;save()
   with (exp/('voicematrix-'+stage+'.log')).open('ab') as log:
    run_stage(command,cwd=root,env=env,log=log,timeout=stage_timeout,cancel=cancel)
   if stage=='train':
    from tools.rvc_train_cpu import MODE,PINNED_SOURCE_SHA256
    model=root/'assets/weights'/(experiment+'.pth')
    state.update(model=str(model),modelSHA256=_output_hash(model));save()
    provenance=json.loads((exp/'voicematrix-train-adapter.json').read_text(encoding='utf-8'))
    if provenance.get('mode')!=MODE or provenance.get('normalizedSourceSHA256')!=PINNED_SOURCE_SHA256 or provenance.get('sourceModified') is not False:raise ValueError('Missing guarded CPU training provenance')
    state['trainingAdapter']=provenance
   if stage=='preprocess':
    from tools.rvc_preprocess import audit_preprocessed,TRANSFORM,PINNED_SOURCE_SHA256
    state['preprocessingDataset']=audit_preprocessed(exp,expected_sources=len(report['files']));save()
    if state['preprocessingDataset']['status']!='ready-for-features':raise ValueError('Insufficient effective training audio after preprocessing')
    provenance=json.loads((exp/'voicematrix-preprocess-adapter.json').read_text(encoding='utf-8'))
    if provenance.get('transform')!=TRANSFORM or provenance.get('normalizedSourceSHA256')!=PINNED_SOURCE_SHA256 or provenance.get('sourceModified') is not False:raise ValueError('Missing guarded preprocessing provenance')
    state['preprocessingAdapter']=provenance
   state['completedStages'].append(stage);save()
  model=root/'assets/weights'/(experiment+'.pth');indices=sorted(exp.glob('added_*.index'))
  if not model.is_file() or not indices:raise ValueError('Training did not produce an inference model and added index')
  if 'modelSHA256' in state and _output_hash(model)!=state['modelSHA256']:raise ValueError('Inference model changed during index stage')
  state.update(status='trained-needs-independent-conversion-check',model=str(model),indices=[str(p) for p in indices],modelSHA256=_output_hash(model),indexSHA256={str(p):_output_hash(p) for p in indices},verified=False)
 except Exception as error:
  state.update(status='cancelled' if isinstance(error,InterruptedError) else 'failed',error=str(error));save();raise
 save();return state
