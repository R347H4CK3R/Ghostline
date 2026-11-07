"""Desktop RVC training adapter. Training outputs remain unverified until conversion checks.

Upstream CLI pinned to 81eed5e8f68b6bed1789f682fe78cdd324495afc.
No engine installation, downloading or training on the gaming laptop is implicit.
"""
import array,hashlib,json,os,pathlib,re,shutil,subprocess,sys,time,wave

UPSTREAM='81eed5e8f68b6bed1789f682fe78cdd324495afc'

def audit_dataset(directory):
 seen=set();rows=[];duplicates=[];rejected=[];seconds=0
 for path in sorted(pathlib.Path(directory).glob('*.wav')):
  try:
   with wave.open(str(path)) as w:
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
    if frame and sum(x*x for x in frame)/len(frame)>327.67**2:active+=len(frame)/rate
   if not samples or active<.5:raise ValueError('Insufficient non-silent audio')
   if sum(abs(x)>=32767 for x in samples)/len(samples)>.001:raise ValueError('Clipped recording')
   rows.append(dict(file=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),activeSeconds=active));seconds+=active
  except (ValueError,wave.Error,EOFError) as error:rejected.append(dict(file=path.name,error=str(error)))
 # Sixty unique non-silent seconds is an engineering admission floor, not a quality guarantee.
 return dict(status='ready-for-training' if seconds>=60 and not rejected else 'insufficient-data',uniqueSeconds=round(seconds,3),minimumSeconds=60,files=rows,duplicates=duplicates,rejected=rejected)

def training_commands(root,dataset,experiment,python,epochs):
 if not re.fullmatch('[a-z0-9_-]{1,80}',experiment):raise ValueError('Unsafe experiment name')
 if not isinstance(epochs,int) or not 1<=epochs<=1200:raise ValueError('Epochs must be 1–1200')
 exp=str(pathlib.Path(root).resolve()/'logs'/experiment)
 return dict(
  preprocess=[python,'train/preprocess.py',str(pathlib.Path(dataset).resolve()),'40000','2',exp,'True','3.7'],
  pitch=[python,'train/dataset/extract_f0.py','cpu',exp,'2','pm'],
  features=[python,'train/dataset/extract_hubert_feature.py','cpu','1','0',exp,'v2','false'],
  train=[python,'train/train.py','-e',experiment,'-sr','40k','-f0','1','-bs','1','-g','','-te',str(epochs),'-se','5','-pg','assets/pretrained_v2/f0G40k.pth','-pd','assets/pretrained_v2/f0D40k.pth','-l','1','-c','0','-sw','1','-v','v2'],
  index=[python,'train/train_index.py',experiment,'v2','assets/indices','2','single'])

def prepare_filelist(exp):
 exp=pathlib.Path(exp).resolve();rows=[]
 for wav in sorted((exp/'0_gt_wavs').glob('*.wav')):
  paths=[wav,exp/'3_feature768'/(wav.stem+'.npy'),exp/'2a_f0'/(wav.name+'.npy'),exp/'2b-f0nsf'/(wav.name+'.npy')]
  if any(not p.is_file() or not p.stat().st_size for p in paths):raise ValueError('Missing extracted feature for '+wav.name)
  if any('|' in str(p) or '\n' in str(p) for p in paths):raise ValueError('Unsafe training path')
  rows.append('|'.join(str(p) for p in paths)+'|0')
 if not rows:raise ValueError('No usable preprocessed training samples')
 (exp/'filelist.txt').write_text('\n'.join(rows)+'\n');return len(rows)

def train(root,dataset,experiment,permission,python=sys.executable,epochs=200,cancel=None):
 """Execute real upstream preparation/training/index stages. No verified-model claim."""
 if not permission.strip():raise ValueError('Record permission to use the training audio')
 root=pathlib.Path(root).resolve();commands=training_commands(root,dataset,experiment,python,epochs)
 report=audit_dataset(dataset)
 if report['status']!='ready-for-training':return report
 revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
 if revision!=UPSTREAM:raise ValueError('Use the pinned RVC source revision')
 for asset in ['configs/v1/40k.json','assets/pretrained_v2/f0G40k.pth','assets/pretrained_v2/f0D40k.pth','assets/hubert_base/config.json']:
  if not (root/asset).is_file():raise ValueError('Missing offline RVC resource: '+asset)
 if not any((root/'assets/hubert_base').glob('*.safetensors')) and not any((root/'assets/hubert_base').glob('*.bin')):raise ValueError('Missing local HuBERT weights')
 exp=root/'logs'/experiment
 # A new experiment prevents stale features/checkpoints from another dataset being silently reused.
 exp.mkdir(parents=True,exist_ok=False)
 shutil.copyfile(root/'configs/v1/40k.json',exp/'config.json')
 state=dict(status='preparing',sourceRevision=revision,dataset=report,permission=permission,completedStages=[])
 def save():
  target=exp/'voicematrix-training.json';temporary=target.with_suffix('.tmp');temporary.write_text(json.dumps(state,indent=2));temporary.replace(target)
 save();env=dict(os.environ,HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='2')
 try:
  for stage,command in commands.items():
   if cancel and cancel.is_set():raise InterruptedError('Training cancelled')
   if stage=='train':prepare_filelist(exp)
   state['status']=stage;save()
   with (exp/('voicematrix-'+stage+'.log')).open('ab') as log:
    child=subprocess.Popen(command,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=os.name!='nt')
    try:
     while child.poll() is None:
      if cancel and cancel.is_set():raise InterruptedError('Training cancelled')
      time.sleep(.25)
     if child.returncode:raise RuntimeError(stage+' failed; inspect the local stage log')
    finally:
     if child.poll() is None:
      if os.name!='nt':
       import signal
       os.killpg(child.pid,signal.SIGTERM)
      else:child.terminate()
      child.wait(timeout=20)
   state['completedStages'].append(stage);save()
  model=root/'assets/weights'/(experiment+'.pth');indices=sorted(exp.glob('added_*.index'))
  if not model.is_file() or not indices:raise ValueError('Training did not produce an inference model and added index')
  state.update(status='trained-needs-independent-conversion-check',model=str(model),indices=[str(p) for p in indices],modelSHA256=hashlib.sha256(model.read_bytes()).hexdigest(),verified=False)
 except Exception as error:
  state.update(status='cancelled' if isinstance(error,InterruptedError) else 'failed',error=str(error));save();raise
 save();return state
