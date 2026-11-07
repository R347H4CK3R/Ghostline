"""Two-identity CPU development experiment; no IPA, runtime admission or weight distribution."""
import argparse,gc,hashlib,json,os,pathlib,sys,time,urllib.request,zipfile
from types import SimpleNamespace
import numpy as np
import scipy.signal
import soundfile as sf
import torch
def sha(path):
 with pathlib.Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def download(url,path,limit=600_000_000):
 path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 with urllib.request.urlopen(url,timeout=180) as src,path.open('wb') as dst:
  total=0
  while block:=src.read(1024*1024):
   total+=len(block)
   if total>limit:raise ValueError('Download exceeds development limit')
   dst.write(block)
 return sha(path)
def main():
 p=argparse.ArgumentParser();p.add_argument('--rvc',required=True);p.add_argument('--source-zip',required=True);a=p.parse_args()
 root=pathlib.Path(a.rvc).resolve();sys.path.insert(0,str(root));os.environ['RVC_CUDA_GRAPH']='0'
 torch.set_num_threads(2);torch.manual_seed(347)
 from infer.hubert import load_hubert_model
 from infer.module.models import SynthesizerTrnMs768NSFsid
 from infer.vc.pipeline import Pipeline
 output=pathlib.Path('prototype-audio');output.mkdir(exist_ok=True)
 report=dict(kind='AI character-imitation development prototype',includedInApp=False,authorizedLikeness=False,physicalDeviceVerified=False,listeningVerified=False,referenceResemblanceVerified=False,indexRate=0,f0Method='pm',sourceRevision=os.environ['RVC_SOURCE_REVISION'],voices=[],outputs=[])
 pathlib.Path('prototype-report.json').write_text(json.dumps(report,indent=2))
 # The official encoder snapshot is pinned and every downloaded byte is recorded.
 metadata=json.load(urllib.request.urlopen('https://huggingface.co/api/models/lj1995/VoiceConversionWebUI',timeout=60))
 revision=metadata['sha'];encoder=[]
 for name in ['config.json','preprocessor_config.json','pytorch_model.bin']:
  path=root/'assets/hubert_base'/name
  digest=download('https://huggingface.co/lj1995/VoiceConversionWebUI/resolve/'+revision+'/hubert_base/'+name,path)
  encoder.append(dict(path=name,sha256=digest,bytes=path.stat().st_size))
 report['encoder']=dict(repository='lj1995/VoiceConversionWebUI',revision=revision,files=encoder)
 hubert=load_hubert_model('cpu',False)
 with zipfile.ZipFile(a.source_zip) as z:
  proof=json.loads(z.read('voice-synthesis-results.json'))
  reference=[]
  for kind,rows in [('speech',proof['profiles']),('recording',proof['conversionChecks'])]:
   row=next(v for v in rows if v['id']=='en_us_Micah')
   name=row.get('file',row['id']+'.wav');raw=z.read(name)
   if hashlib.sha256(raw).hexdigest()!=row['audioSHA256']:raise ValueError('Source WAV hash mismatch')
   import io
   signal,rate=sf.read(io.BytesIO(raw),dtype='float32')
   ratio=__import__('fractions').Fraction(16000,rate);signal=scipy.signal.resample_poly(signal,ratio.numerator,ratio.denominator)
   signal/=max(1,float(np.max(np.abs(signal)))/.95)
   reference.append((kind,signal,row.get('referenceText','Hello. This is a voice test.'),row['audioSHA256']))
 models=[
  ('Rick Sanchez AI imitation','rick','brookieisthatyou/MY-RVC-V2-MODELS','e6680da4b9700f32ee689726246f3f6cdee45345','RickSanchez.zip','00cd0fb703be068e508f82eaf316a0accbaf62f7c68cc6a1368bc6996a097435',[0,-3]),
  ('Morty Smith AI imitation','morty','MrSpringtroll/morty','a66af1de19814391a3b2501bba0a1d25375e7677','morty.zip','88cf7460392400356c702022d03e6c45ba6542fcee6fafeb34151006c3e2beaa',[5,8])]
 for title,slug,repo,rev,file,digest,pitches in models:
  archive=pathlib.Path('work')/(slug+'.zip');actual=download('https://huggingface.co/'+repo+'/resolve/'+rev+'/'+file,archive)
  if actual!=digest:raise ValueError('Candidate model archive changed')
  with zipfile.ZipFile(archive) as z:
   files=[n for n in z.namelist() if n.lower().endswith('.pth')]
   if len(files)!=1:raise ValueError('Need exactly one checkpoint')
   checkpoint=pathlib.Path('work')/(slug+'.pth');checkpoint.write_bytes(z.read(files[0]))
  # Never fall back to unrestricted pickle execution for community checkpoints.
  state=torch.load(checkpoint,map_location='cpu',weights_only=True)
  if state.get('version')!='v2' or state.get('f0',1)!=1:raise ValueError('Unsupported experiment model')
  weights=state['weight']
  if not all(isinstance(v,torch.Tensor) and torch.isfinite(v).all() for v in weights.values()):raise ValueError('Invalid model tensors')
  config=list(state['config']);config[-3]=weights['emb_g.weight'].shape[0];rate=int(config[-1]) if isinstance(config[-1],int) else {'32k':32000,'40k':40000,'48k':48000}[config[-1]]
  net=SynthesizerTrnMs768NSFsid(*config,is_half=False);del net.enc_q
  missing,unexpected=net.load_state_dict(weights,strict=False)
  if missing or any(not k.startswith('enc_q.') for k in unexpected):raise ValueError('Checkpoint architecture mismatch: '+str((missing,unexpected)))
  net.eval().float();del state,weights;gc.collect()
  converter=Pipeline(rate,SimpleNamespace(x_pad=1,x_query=6,x_center=38,x_max=41,is_half=False,device='cpu'))
  report['voices'].append(dict(name=title,franchise='Rick and Morty',genres=['Animation & Cartoons','Science Fiction & Superheroes'],repository=repo,revision=rev,checkpointSHA256=sha(checkpoint),archiveSHA256=actual,rights='Unestablished; development experiment only'))
  for kind,signal,text,sourcehash in reference:
   for pitch in pitches:
    started=time.monotonic();torch.manual_seed(347)
    with torch.inference_mode():
     converted=converter.pipeline(hubert,net,0,signal.copy(),[0,0,0],pitch,'pm','',0,1,rate,0,1,'v2',.33)
    data=converted.astype(np.float64)/32768
    if not len(data) or not np.isfinite(data).all():raise ValueError('Invalid audio')
    seconds=len(data)/rate;rms=float(np.sqrt(np.mean(data**2)));peak=float(np.max(np.abs(data)));clip=float(np.mean(np.abs(data)>=32767/32768))
    if rms<=.0001 or clip!=0 or abs(seconds-len(signal)/16000)>.15:raise ValueError('Audio functionality check failed')
    filename=f'{slug}-{kind}-pitch{pitch:+d}-AI-IMITATION.wav';path=output/filename;sf.write(path,converted,rate,subtype='PCM_16')
    row=dict(voice=slug,file=filename,sampleRate=rate,audioSeconds=seconds,sourceAudioSHA256=sourcehash,audioSHA256=sha(path),referenceText=text,rms=rms,peak=peak,fullScaleSampleFraction=clip,pitchSemitones=pitch,elapsedSeconds=time.monotonic()-started)
    report['outputs'].append(row);print(json.dumps(row),flush=True)
    pathlib.Path('prototype-report.json').write_text(json.dumps(report,indent=2)+'\n')
  del net,converter;gc.collect()
 pathlib.Path('prototype-report.json').write_text(json.dumps(report,indent=2)+'\n')
 (output/'READ-ME.txt').write_text('AI IMITATIONS: experimental Rick and Morty character-style conversion. Not official performances. Character resemblance, naturalness and native iPhone execution unverified. Two candidate identities, multiple parameter trials; not eight distinct voices. Weights are not included or admitted to the app.\n')
if __name__=='__main__':main()
