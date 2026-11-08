"""Private prepared-reference queue processor; no automatic identity/rights claims."""
import argparse,array,hashlib,json,math,pathlib,subprocess,sys,tempfile,threading,time,wave
from tools.video_queue import VideoQueue,video_id
from tools.voice_pack import export_reference_pack,validate_pack
from tools.pack_speech import speak
from tools.master_voices import publish

TEXT='I found a strange device near the portal.'
WHISPER_SHA='921e4cf8686fdd993dcd081a5da5b6c365bfde1162e72b08d75ac75289920b1f'

def digest(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def atomic(path,value):
 path.parent.mkdir(parents=True,exist_ok=True)
 temporary=path.with_suffix('.new');temporary.write_text(json.dumps(value,indent=2)+'\n',encoding='utf8');temporary.replace(path)

def audio_check(path):
 with wave.open(str(path)) as f:
  if (f.getnchannels(),f.getsampwidth(),f.getframerate(),f.getcomptype())!=(1,2,24000,'NONE') or not 1200<=f.getnframes()<=14400000:raise ValueError('Generated WAV format or duration failed')
  frames=f.getnframes();pcm=f.readframes(frames)
 if len(pcm)!=frames*2:raise ValueError('Generated WAV is truncated')
 samples=array.array('h',pcm)
 if sys.byteorder!='little':samples.byteswap()
 rms=math.sqrt(sum(x*x for x in samples)/len(samples))/32768
 if rms<=.0001 or any(abs(x)>=32767 for x in samples):raise ValueError('Generated WAV is silent or clipped')
 return dict(wavSHA256=digest(path),seconds=frames/24000,rms=rms,fullScaleSamples=0)

def checked_process(command,*,timeout,cancelled):
 with subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE) as process:
  deadline=time.monotonic()+timeout
  try:
   while True:
    if cancelled():raise InterruptedError('Processing paused during audio verification')
    if time.monotonic()>=deadline:raise TimeoutError('Audio verification timed out')
    try:
     stdout,stderr=process.communicate(timeout=.2)
     if process.returncode:raise subprocess.CalledProcessError(process.returncode,command,stdout,stderr)
     return
    except subprocess.TimeoutExpired:pass
  finally:
   if process.poll() is None:
    process.terminate()
    try:process.wait(timeout=2)
    except subprocess.TimeoutExpired:process.kill();process.wait()

def recognizer(cli,model,cancelled=lambda:False):
 if digest(model)!=WHISPER_SHA:raise ValueError('Independent recognizer model checksum failed')
 cli=pathlib.Path(cli).resolve();model=pathlib.Path(model).resolve()
 if not cli.is_file():raise ValueError('Missing independent recognizer executable')
 def verify(audio,text):
  from tools.character_evidence import words,edits
  with tempfile.TemporaryDirectory(prefix='voicematrix-wordcheck-') as directory:
   root=pathlib.Path(directory);decoded=root/'input.wav';prefix=root/'asr'
   checked_process(['ffmpeg','-v','error','-y','-i',str(audio),'-ar','16000','-ac','1',str(decoded)],timeout=60,cancelled=cancelled)
   checked_process([str(cli),'-m',str(model),'-f',str(decoded),'-l','en','-t','2','-nf','-otxt','-of',str(prefix)],timeout=120,cancelled=cancelled)
   recognized=(root/'asr.txt').read_text();wer=edits(words(text),words(recognized))/len(words(text))
   return dict(passed=wer<=.1,wordErrorRate=wer,wavSHA256=digest(audio),recognizerSHA256=digest(cli),recognizerModelSHA256=WHISPER_SHA)
 return verify

class AttemptModel:
 def __init__(self,model,attempt,cancelled=lambda:False):self.model=model;self.seed=346+attempt;self.cancelled=cancelled
 def check(self,*args):
  if self.cancelled():raise InterruptedError('Processing paused during synthesis')
 def infer(self,**kwargs):
  self.check();kwargs['seed']=self.seed;hook=None
  transformer=getattr(getattr(self.model,'ema_model',None),'transformer',None)
  if transformer is not None:hook=transformer.register_forward_pre_hook(self.check)
  try:
   result=self.model.infer(**kwargs);self.check();return result
  finally:
   if hook:hook.remove()

def run_once(database,specifications,work,master,*,model_factory,verify,synthesize=speak,paused=lambda:False,retry_delay=30):
 if paused():return None
 q=VideoQueue(str(database));job=None;stop=threading.Event();lost=threading.Event();percent=[0.0];thread=None;report=None
 def heartbeat():
  pulse=VideoQueue(str(database))
  try:
   while not stop.wait(5):
    try:pulse.progress(job['id'],percent[0],token=job['token'])
    except Exception:lost.set();return
  finally:pulse.close()
 def progress(value):
  if lost.is_set():raise ValueError('Worker ownership was lost')
  if paused():raise InterruptedError('Processing paused; retained for resume')
  percent[0]=value;q.progress(job['id'],value,token=job['token'])
 try:
  job=q.claim()
  if not job:return None
  if video_id(job['url'])!=job['id']:raise ValueError('Queued video identity is invalid')
  out=pathlib.Path(work)/job['id']/('attempt-'+str(job['attempt']));out.mkdir(parents=True,exist_ok=True)
  report=dict(videoID=job['id'],attempt=job['attempt'],profiles=[],status='processing',physicalDeviceVerified=False,likenessVerified=False,nativePerProfileVerified=False)
  thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
  specroot=pathlib.Path(specifications).resolve();path=specroot/(job['id']+'.json')
  if not path.is_file():
   report.update(status='needs-review',reason='Prepared labeled reference specification is missing; link remains queued')
   atomic(out/'result.json',report);q.progress(job['id'],0,'needs-review',token=job['token']);return report
  if path.is_symlink() or path.stat().st_size>2000000:raise ValueError('Invalid prepared job specification')
  spec=json.loads(path.read_text(encoding='utf8'))
  if not isinstance(spec,dict) or spec.get('schemaVersion')!=1 or video_id(spec.get('videoURL',''))!=job['id'] or not isinstance(spec.get('profiles'),list) or not 1<=len(spec['profiles'])<=64:raise ValueError('Invalid prepared video reference specification')
  packs=[];ids=set();hashes=set()
  for n,row in enumerate(spec['profiles']):
   progress(.1*(n+1)/len(spec['profiles']))
   name=row.get('referenceFile','')
   if not isinstance(name,str) or not name or '\\' in name or ':' in name or pathlib.Path(name).is_absolute() or '..' in pathlib.Path(name).parts:raise ValueError('Unsafe prepared reference path')
   reference=specroot/name
   if reference.is_symlink() or specroot not in reference.resolve().parents or reference.stat().st_size>848000 or digest(reference)!=row.get('referenceSHA256'):raise ValueError('Prepared reference checksum or location failed')
   metadata=row['metadata'];identifier=metadata['id']
   # Use the pack validator before incorporating any ID into an output path.
   pack=out/('profile-'+str(n)+'.vmpack');export_reference_pack(reference,metadata,pack);m=validate_pack(pack)
   if m['referenceSHA256']!=row['referenceSHA256']:raise ValueError('Reference changed during preparation')
   if identifier in ids or m['referenceSHA256'] in hashes:raise ValueError('Repeated profile ID or reference in prepared job')
   ids.add(identifier);hashes.add(m['referenceSHA256']);packs.append(pack)
  progress(.15);model=AttemptModel(model_factory(),job['attempt'],paused)
  for n,pack in enumerate(packs):
   progress(.15+.7*n/len(packs));m=validate_pack(pack);audio=out/(m['id']+'-preview.wav')
   synthesize(pack,TEXT,audio,model)
   progress(.15+.7*(n+.5)/len(packs))
   checked=audio_check(audio);words=verify(audio,TEXT)
   report['profiles'].append(dict(id=m['id'],referenceSHA256=m['referenceSHA256'],audio=checked,wordcheck=words,seed=model.seed))
   atomic(out/'progress.json',report)
   if words.get('passed') is not True or not isinstance(words.get('wordErrorRate'),(int,float)) or not 0<=words['wordErrorRate']<=.1 or words.get('wavSHA256')!=checked['wavSHA256']:raise ValueError('Independent generated-word check failed (WER '+str(words.get('wordErrorRate'))+')')
  progress(.95)
  def publication():
   if paused():raise InterruptedError('Processing paused before publication')
   report['publication']=publish(packs,master)
   report.update(status='needs-review',reason='Desktop audio passed; character likeness and individual native/device checks remain pending')
   atomic(out/'result.json',report)
  q.review_with(job['id'],job['token'],publication);return report
 except Exception as error:
  if not job:raise
  reason=(type(error).__name__+': '+str(error))[:1000]
  if isinstance(error,InterruptedError):
   q.pause(job['id'],job['token']);status='paused'
  else:
   try:q.fail(job['id'],job['token'],reason,retry_delay=retry_delay)
   except ValueError:raise ValueError('Job ownership was lost; this worker cannot change its status') from error
   status='failed' if job['attempt']>=4 else 'retry'
  report=report or dict(videoID=job['id'],attempt=job['attempt'],profiles=[])
  report.update(status=status,reason=reason,physicalDeviceVerified=False,likenessVerified=False)
  if 'out' in locals():atomic(out/'result.json',report)
  return report
 finally:
  stop.set()
  if thread:thread.join()
  q.close()

def main():
 from tools.local_f5 import load_local_model
 from tools.laptop_supervisor import gaming
 p=argparse.ArgumentParser(description='Process prepared private references; does not automatically identify characters or download videos')
 for key in ['database','specifications','work','master','checkpoint','vocoder-directory','vocab','whisper-cli','whisper-model']:p.add_argument('--'+key,required=True)
 p.add_argument('--poll-seconds',type=float,default=30);p.add_argument('--once',action='store_true');a=p.parse_args()
 if not math.isfinite(a.poll_seconds) or not 5<=a.poll_seconds<=3600:p.error('Poll every 5–3600 seconds')
 model=[None]
 def factory():
  if model[0] is None:model[0]=load_local_model(a.checkpoint,a.vocoder_directory,a.vocab)
  return model[0]
 root=pathlib.Path(a.work);root.mkdir(parents=True,exist_ok=True)
 last_game=[0.0,False]
 def paused():
  if (root/'pause').exists() or (root/'stop').exists():return True
  now=time.monotonic()
  if now-last_game[0]>=1:last_game[:]=[now,gaming()]
  return last_game[1]
 verifier=recognizer(a.whisper_cli,a.whisper_model,paused)
 while not (root/'stop').exists():
  result=run_once(a.database,a.specifications,a.work,a.master,model_factory=factory,verify=verifier,paused=paused)
  if result:print(json.dumps({key:result[key] for key in ['videoID','attempt','status']}),flush=True)
  if a.once:break
  time.sleep(a.poll_seconds)
if __name__=='__main__':main()
