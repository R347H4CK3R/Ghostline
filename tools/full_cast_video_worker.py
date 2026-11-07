"""Resumable full-cast reference-conditioned preview worker. Not RVC training or iOS admission."""
import os,pathlib,json,time,hashlib,re,subprocess,wave,tempfile,zipfile,contextlib,traceback
from local_f5 import load_local_model
ROOT=pathlib.Path(os.environ.get('VOICEMATRIX_CAST_JOB',str(pathlib.Path.cwd()/'full-cast-video'))).resolve()
REF=ROOT/'references';OUT=ROOT/'generated';OUT.mkdir(exist_ok=True)
TMP=ROOT/'private-temp';TMP.mkdir(exist_ok=True);tempfile.tempdir=str(TMP)
STATE=ROOT/'job-state.json'
TEXT="I found a strange device near the portal."
WHISPER=os.environ.get('VOICEMATRIX_WHISPER_CLI','whisper-cli')
ASR_MODEL=os.environ.get('VOICEMATRIX_WHISPER_MODEL','ggml-tiny.en.bin')
FF='ffmpeg'
def write(path,obj):
 temporary=path.with_suffix(path.suffix+'.new');temporary.write_text(json.dumps(obj,indent=2)+'\n');temporary.replace(path)
def words(s):return re.findall(r'[a-z0-9]+',s.lower())
def distance(a,b):
 previous=list(range(len(b)+1))
 for i,x in enumerate(a,1):
  row=[i]
  for j,y in enumerate(b,1):row.append(min(row[-1]+1,previous[j]+1,previous[j-1]+(x!=y)))
  previous=row
 return previous[-1]
def transcribe(audio,prefix):
 subprocess.run([WHISPER,'-m',ASR_MODEL,'-f',str(audio),'-l','en','-t','2','-nf','-otxt','-of',str(prefix)],check=True,capture_output=True,timeout=120)
 return prefix.with_suffix('.txt').read_text().strip()
def convert(src,dst,rate):
 subprocess.run([FF,'-v','error','-i',str(src),'-ac','1','-ar',str(rate),'-c:a','pcm_s16le','-y',str(dst)],check=True,capture_output=True,timeout=60)
def sha(path):
 with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
manifest=json.loads((REF/'manifest.json').read_text())
state=json.loads(STATE.read_text()) if STATE.exists() else dict(status='preparing-references',startedAt=time.time(),updatedAt=time.time(),totalCandidates=len(manifest['profiles']),alreadyAccepted=['Rick','Morty'],completed=[],sourceURL=manifest['sourceURL'])
def update(**changes):
 state.update(changes,updatedAt=time.time());write(STATE,state)
def completed_ids():return {r['id'] for r in state['completed']}
try:
 # Transcribe before loading the large synthesis model.
 for i,profile in enumerate(manifest['profiles']):
  if profile['id'] in completed_ids():continue
  identifier=profile['id'];audio=REF/profile['file']
  if not audio.exists():raise FileNotFoundError('Missing unprocessed reference '+identifier)
  if sha(audio)!=profile['referenceSHA256']:raise ValueError('Reference checksum mismatch '+identifier)
  saved=REF/(identifier+'.private.json')
  if saved.exists():
   cached=json.loads(saved.read_text())
   if cached.get('referenceSHA256')==profile['referenceSHA256'] and isinstance(cached.get('referenceText'),str):continue
  update(status='transcribing-references',currentCharacter=profile['name'],referenceIndex=i+1,error=None)
  target=TMP/(identifier+'-reference-16k.wav')
  convert(audio,target,16000)
  text=transcribe(target,TMP/(identifier+'-reference'))
  private=dict(profile,referenceText=text)
  write(REF/(identifier+'.private.json'),private)
  target.unlink(missing_ok=True);(TMP/(identifier+'-reference.txt')).unlink(missing_ok=True)
 update(status='loading-shared-model',currentCharacter=None,error=None)
 os.environ['WANDB_MODE']='disabled';os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
 import torch,numpy as np,soundfile as sf,importlib.metadata
 from f5_tts.api import F5TTS
 import f5_tts.infer.utils_infer as infer_utils
 torch.set_num_threads(4)
 cache=pathlib.Path(os.environ.get('VOICEMATRIX_F5_CACHE',str(ROOT/'model-cache')))
 checkpoint=cache/'models--SWivid--F5-TTS/snapshots/84e5a410d9cead4de2f847e7c9369a6440bdfaca/F5TTS_v1_Base/model_1250000.safetensors'
 vocoder=cache/'models--charactr--vocos-mel-24khz/snapshots/0feb3fdd929bcd6649e0e7c5a688cf7dd012ef21'
 from importlib.resources import files
 vocab=files('f5_tts').joinpath('infer/examples/vocab.txt')
 model=load_local_model(checkpoint,vocoder,str(vocab))
 update(status='generating',engine='F5TTS_v1_Base',engineVersion=importlib.metadata.version('f5-tts'),torch=torch.__version__,nfeSteps=32,cpuThreads=4)
 for profile in manifest['profiles']:
  identifier=profile['id']
  if identifier in completed_ids():continue
  source=REF/profile['file'];private=REF/(identifier+'.private.json')
  item=json.loads(private.read_text());text=item['referenceText']
  row={k:v for k,v in profile.items() if k not in ['file','status']}
  row.update(engine='F5TTS_v1_Base',authorizedLikeness=False,physicalDeviceVerified=False,listeningVerified=False,referenceWordCount=len(words(text)))
  reference=TMP/(identifier+'-ref24k.wav');processed_key=None
  try:
   if len(words(text))<3 or re.fullmatch(r'\s*[\[(](music|laughter|applause)[\])]\s*',text,re.I):
    raise ValueError('Reference has insufficient intelligible speech')
   convert(source,reference,24000)
   processed_key=hashlib.md5(reference.read_bytes()).hexdigest()
   update(status='generating',currentCharacter=profile['name'])
   trials=[]
   for seed in [347,348]:
    started=time.monotonic()
    with open(ROOT/'synthesis-private.log','a') as log,contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
     samples,sr,_=model.infer(ref_file=str(reference),ref_text=text,gen_text=TEXT,nfe_step=32,seed=seed,speed=1.0)
    if not np.isfinite(samples).all() or len(samples)<sr*.3:raise ValueError('Invalid generated audio')
    gain=min(1,.98/max(float(np.max(np.abs(samples))),1e-8));samples=np.asarray(samples)*gain
    rms=float(np.sqrt(np.mean(samples**2)))
    if rms<=.0001:raise ValueError('Silent output')
    path=OUT/(identifier+'-seed'+str(seed)+'-AI-imitation.wav');sf.write(path,samples,sr,subtype='PCM_16')
    decoded=TMP/(identifier+'-generated-16k.wav');convert(path,decoded,16000)
    transcript=transcribe(decoded,TMP/(identifier+'-generated'))
    errors=distance(words(TEXT),words(transcript));wer=errors/len(words(TEXT))
    with wave.open(str(path)) as f:
     if f.getnchannels()!=1 or f.getsampwidth()!=2:raise ValueError('Invalid WAV encoding')
     pcm=np.frombuffer(f.readframes(f.getnframes()),dtype='<i2').astype(float)
    fullscale=int(np.sum(np.abs(pcm)>=32767))
    trials.append(dict(file=path.name,audioSHA256=sha(path),sampleRate=sr,seconds=len(samples)/sr,gain=gain,rms=rms,fullScaleSamples=fullscale,seed=seed,text=TEXT,transcript=transcript,wordErrors=errors,wordErrorRate=wer,elapsedSeconds=time.monotonic()-started,passed=wer<=.1 and fullscale==0))
    if trials[-1]['passed']:break
   best=min(trials,key=lambda t:t['wordErrorRate'])
   row.update(status='generated-words-checked' if best['passed'] else 'generated-needs-intelligibility-review',selected=best,trials=trials)
  except Exception as exc:
   row.update(status='needs-reference-or-engine-repair',error=str(exc))
   with open(ROOT/'errors.log','a') as log:log.write(identifier+'\n'+traceback.format_exc()+'\n')
  finally:
   if processed_key:
    cached=infer_utils._ref_audio_cache.pop(processed_key,None)
    if cached:pathlib.Path(cached).unlink(missing_ok=True)
   source.unlink(missing_ok=True);private.unlink(missing_ok=True);reference.unlink(missing_ok=True)
   for path in TMP.glob(identifier+'*'):path.unlink(missing_ok=True)
  state['completed'].append(row)
  update(currentCharacter=None)
  print('FINISHED',profile['name'],row['status'],len(state['completed']),'/',len(manifest['profiles']),flush=True)
  # Public record contains no original dialogue or reference bytes.
  write(ROOT/'results.json',dict(sourceURL=manifest['sourceURL'],engine='F5TTS_v1_Base',scope='AI-imitation previews. No controlled likeness verification, native iOS verification, authorized-likeness claim or RVC training.',profiles=state['completed']))
 # A final package retains generated audio only.
 passed=[r for r in state['completed'] if r['status']=='generated-words-checked']
 other=[r for r in state['completed'] if r['status']!='generated-words-checked']
 (OUT/'READ-ME.txt').write_text('AI IMITATIONS from a user-supplied Rick and Morty video. Not official performances or verified replicas. Named WAVs are generated speech; word checks do not establish resemblance. These are not RVC .pth models or native iPhone profiles. See results.json for failed or incomplete roles.\n')
 with zipfile.ZipFile(ROOT/'Rick-Morty-Full-Cast-AI-Imitation-Previews.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
  z.write(ROOT/'results.json','results.json');z.write(OUT/'READ-ME.txt','READ-ME.txt')
  for row in passed:z.write(OUT/row['selected']['file'],row['selected']['file'])
 for p in REF.glob('*'):
  if p.is_file():p.unlink()
 for p in TMP.glob('*'):
  if p.is_file():p.unlink()
 (ROOT/'synthesis-private.log').unlink(missing_ok=True)
 update(status='completed',completedAt=time.time(),generatedPassing=len(passed),needsReview=len(other),referencesDeleted=True)
 print('BATCH COMPLETE',len(passed),'passed,',len(other),'need review',flush=True)
except Exception as exc:
 update(status='blocked',error=str(exc))
 raise
