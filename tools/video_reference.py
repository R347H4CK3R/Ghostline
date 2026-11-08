"""Development helper: accessible public video -> labeled reference slices.
No cookies, authentication bypass, model training claim, or model-file renaming.
"""
import hashlib,json,pathlib,re,shutil,subprocess,tempfile,math
from tools.process_control import checked_process
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
def download_video(url,root,ff,downloader_factory=None,*,cancelled=lambda:False,max_duration=1800,max_bytes=268435456):
 """Download implementation used by a separately bounded production child."""
 def metadata_filter(info,*,incomplete=False):
  if cancelled():raise InterruptedError('Video preparation paused')
  duration=info.get('duration')
  if duration is None and incomplete:return None
  if isinstance(duration,bool) or not isinstance(duration,(int,float)) or not math.isfinite(duration) or not 0<duration<=max_duration:return 'Video duration is unknown or exceeds the configured limit'
 def progress_hook(info):
  if cancelled():raise InterruptedError('Video preparation paused')
  if info.get('downloaded_bytes',0)>max_bytes:raise ValueError('Downloaded video exceeds the byte limit')
 if downloader_factory is None:
  try:from yt_dlp import YoutubeDL
  except ImportError as e:raise ValueError('Install the local yt-dlp download dependency') from e
  downloader_factory=YoutubeDL
 options=dict(format='best[ext=mp4][height<=480]',outtmpl=str(root/'source.%(ext)s'),noplaylist=True,socket_timeout=25,retries=0,fragment_retries=0,extractor_retries=0,file_access_retries=0,ffmpeg_location=ff,max_filesize=max_bytes,match_filter=metadata_filter,progress_hooks=[progress_hook],quiet=True,no_warnings=True)
 node=shutil.which('node')
 if node:options['js_runtimes']={'node':{'path':node}}
 try:
  with downloader_factory(options) as downloader:metadata=downloader.extract_info(url,download=True)
 except Exception:
  if cancelled():raise InterruptedError('Video preparation paused')
  raise
 if not isinstance(metadata,dict) or metadata_filter(metadata):raise ValueError('Video duration is missing or exceeds the limit')
 return {k:metadata[k] for k in ['id','title','duration']}

@contextmanager
def acquire(url,segments,downloader_factory=None,*,cancelled=lambda:False,max_duration=1800,max_bytes=268435456,max_download_seconds=300):
 validate_request(url,segments);ff=ffmpeg_path()
 if isinstance(max_duration,bool) or not isinstance(max_duration,(int,float)) or not math.isfinite(max_duration) or not 1<=max_duration<=3600:raise ValueError('Video duration limit must be 1–3600 seconds')
 if isinstance(max_bytes,bool) or not isinstance(max_bytes,int) or not 1024<=max_bytes<=1073741824:raise ValueError('Video byte limit must be 1 KiB–1 GiB')
 if isinstance(max_download_seconds,bool) or not isinstance(max_download_seconds,(int,float)) or not math.isfinite(max_download_seconds) or not .1<=max_download_seconds<=900:raise ValueError('Download deadline must be 0.1–900 seconds')
 with tempfile.TemporaryDirectory(prefix='voicematrix-reference-') as temporary:
  root=pathlib.Path(temporary)
  if downloader_factory is None:
   import importlib.util,sys
   if importlib.util.find_spec('yt_dlp') is None:raise ValueError('Install the local yt-dlp download dependency')
   command=[sys.executable,str(pathlib.Path(__file__).with_name('video_download.py')),url,str(root),ff,str(max_duration),str(max_bytes)]
   try:checked_process(command,timeout=max_download_seconds,cancelled=cancelled)
   except subprocess.CalledProcessError as e:raise ValueError('Video download failed: '+e.stderr.decode(errors='replace')[-800:]) from e
   record=root/'download-metadata.json'
   if not record.is_file() or record.stat().st_size>65536:raise ValueError('Invalid video metadata')
   metadata=json.loads(record.read_text(encoding='utf8'))
  else:
   # In-process factory injection is a test seam; the real downloader is a child.
   metadata=download_video(url,root,ff,downloader_factory,cancelled=cancelled,max_duration=max_duration,max_bytes=max_bytes)
  movie=root/'source.mp4'
  if not movie.is_file() or movie.is_symlink() or movie.stat().st_size>max_bytes:raise ValueError('Video is missing or exceeds the byte limit')
  checked_process([ff,'-v','error','-i',str(movie),'-t','0.2','-map','0:v:0','-map','0:a:0','-f','null','-'],timeout=60,cancelled=cancelled)
  rows=[]
  for s in segments:
   if s['end']>metadata['duration']:raise ValueError('Reference extends beyond video')
   output=root/(s['id']+'.wav')
   checked_process([ff,'-v','error','-ss',str(s['start']),'-i',str(movie),'-t',str(s['end']-s['start']),'-vn','-ac','1','-ar','24000','-c:a','pcm_s16le',str(output)],timeout=60,cancelled=cancelled)
   rows.append(dict(s,audioPath=str(output),sha256=hashlib.sha256(output.read_bytes()).hexdigest()))
  with movie.open('rb') as f:source_hash=hashlib.file_digest(f,'sha256').hexdigest()
  yield dict(sourceURL=url,title=metadata['title'],videoID=metadata['id'],sourceSHA256=source_hash,segments=rows,characterIdentification='Reviewed source labels, not biometric identification.',authorizedLikeness=False)
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

