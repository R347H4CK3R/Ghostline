"""Development helper: accessible public video -> labeled reference slices.
No cookies, authentication bypass, model training claim, or model-file renaming.
"""
import hashlib,json,pathlib,re,shutil,subprocess,tempfile
from urllib.parse import urlparse
from contextlib import contextmanager
def validate_request(url,segments):
 parsed=urlparse(url)
 if parsed.scheme!='https' or parsed.hostname not in {'youtube.com','www.youtube.com','youtu.be'} or parsed.username or parsed.password:
  raise ValueError('Use a public HTTPS YouTube link')
 seen=set()
 for s in segments:
  if not re.fullmatch(r'[a-z0-9_-]+',s['id']) or s['id'] in seen:raise ValueError('Unsafe or repeated profile ID')
  seen.add(s['id'])
  if not isinstance(s['start'],(int,float)) or not isinstance(s['end'],(int,float)) or not 0<=s['start']<s['end'] or not .5<=s['end']-s['start']<=15:
   raise ValueError('Choose a single-speaker reference between 0.5 and 15 seconds')
 if not seen:raise ValueError('No labeled reference segments')
def ffmpeg_path():
 path=shutil.which('ffmpeg')
 if path:return path
 import imageio_ffmpeg
 return imageio_ffmpeg.get_ffmpeg_exe()
@contextmanager
def acquire(url,segments,downloader_factory=None):
 validate_request(url,segments);ff=ffmpeg_path()
 if downloader_factory is None:
  from yt_dlp import YoutubeDL
  downloader_factory=YoutubeDL
 with tempfile.TemporaryDirectory(prefix='voicematrix-reference-') as temporary:
  root=pathlib.Path(temporary)
  options=dict(format='best[ext=mp4][height<=480]',outtmpl=str(root/'source.%(ext)s'),noplaylist=True,socket_timeout=25,retries=1,fragment_retries=1,ffmpeg_location=ff)
  node=shutil.which('node')
  if node:options['js_runtimes']={'node':{'path':node}}
  with downloader_factory(options) as downloader:metadata=downloader.extract_info(url,download=True)
  movie=root/'source.mp4'
  # Decode both streams: an HTML error page or audio-only file must never pass.
  subprocess.run([ff,'-v','error','-i',str(movie),'-t','0.2','-map','0:v:0','-map','0:a:0','-f','null','-'],check=True,timeout=60,capture_output=True)
  rows=[]
  for s in segments:
   if s['end']>metadata['duration']:raise ValueError('Reference extends beyond video')
   output=root/(s['id']+'.wav')
   subprocess.run([ff,'-v','error','-ss',str(s['start']),'-i',str(movie),'-t',str(s['end']-s['start']),'-vn','-ac','1','-ar','24000','-c:a','pcm_s16le',str(output)],check=True,timeout=60,capture_output=True)
   rows.append(dict(s,audioPath=str(output),sha256=hashlib.sha256(output.read_bytes()).hexdigest()))
  yield dict(sourceURL=url,title=metadata['title'],videoID=metadata['id'],segments=rows,characterIdentification='Caller must inspect on-screen labels and isolated speech before assigning identities.',authorizedLikeness=False)
 # TemporaryDirectory removes source and extracted references even on failure.
def synthesize(references,texts,output_directory,model=None):
 import numpy as np
 import soundfile as sf
 from f5_tts.api import F5TTS
 output=pathlib.Path(output_directory);output.mkdir(parents=True,exist_ok=True)
 if model is None:model=F5TTS(model='F5TTS_v1_Base',device='cpu')
 report=dict(engine='F5TTS_v1_Base',runtime='development only; not native iOS',sourceURL=references['sourceURL'],authorizedLikeness=False,listeningVerified=False,outputs=[])
 for segment in references['segments']:
  identifier=segment['id']
  if not segment.get('referenceText','').strip():raise ValueError('Transcribe and check reference text before generation')
  wav,sr,_=model.infer(ref_file=segment['audioPath'],ref_text=segment['referenceText'],gen_text=texts[identifier],nfe_step=32,seed=347)
  if not np.isfinite(wav).all() or len(wav)<.3*sr:raise ValueError('Invalid generated audio')
  gain=min(1,.98/max(float(np.max(np.abs(wav))),1e-8));wav=np.asarray(wav)*gain
  rms=float(np.sqrt(np.mean(wav**2)))
  if rms<=.0001:raise ValueError('Silent generated audio')
  path=output/(identifier+'-AI-imitation.wav');sf.write(path,wav,sr,subtype='PCM_16')
  report['outputs'].append(dict(id=identifier,character=segment.get('character',identifier),categories=segment.get('categories',[]),referenceSHA256=segment['sha256'],file=path.name,audioSHA256=hashlib.sha256(path.read_bytes()).hexdigest(),seconds=len(wav)/sr,rms=rms,text=texts[identifier]))
 (output/'generation-report.json').write_text(json.dumps(report,indent=2)+'\n')
 return report
