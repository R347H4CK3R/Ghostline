"""Bounded audio-activity suggestions. These are NOT diarization or character labels."""
import array,hashlib,json,math,os,pathlib,re,sys,tempfile,time,wave
from tools.video_queue import video_id
from tools.video_reference import acquire,ffmpeg_path
from tools.process_control import checked_process
from tools.private_voices import PrivateVoices
from tools.master_voices import _publish_lock

def checksum(data):return hashlib.sha256(data).hexdigest()
def validate_request(request):
 if not isinstance(request,dict) or set(request)!={'schemaVersion','videoURL','decision','reviewer','record'} or request['schemaVersion']!=1:raise ValueError('Invalid inspection request')
 if not isinstance(request['videoURL'],str):raise ValueError('Video URL must be text')
 identifier=video_id(request['videoURL'])
 if request['decision']!='approved-local-inspection' or any(not isinstance(request[k],str) or not request[k].strip() or len(request[k])>3000 for k in ['reviewer','record']):raise ValueError('Explicit local inspection use record is required')
 return identifier

def read_index(root,identifier):
 if not re.fullmatch(r'[A-Za-z0-9_-]{11}',identifier):raise ValueError('Invalid video selection')
 folder=pathlib.Path(root).resolve()/'proposals'
 reader=PrivateVoices(folder)
 value=json.loads(reader.read(folder/identifier/'index.json',128000))
 if not isinstance(value,dict):raise ValueError('Invalid proposal index')
 unsigned={k:v for k,v in value.items() if k!='revision'}
 if checksum(json.dumps(unsigned,sort_keys=True,separators=(',',':')).encode())!=value.get('revision') or value.get('videoID')!=identifier or value.get('speakerSeparated') is not False or value.get('likenessVerified') is not False:raise ValueError('Invalid proposal revision')
 if value.get('schemaVersion')!=1 or value.get('status')!='needs-source-review' or any(not isinstance(value.get(k),str) or not re.fullmatch(r'[a-f0-9]{64}',value[k]) for k in ['sourceSHA256','requestSHA256']):raise ValueError('Invalid proposal provenance')
 if not isinstance(value.get('segments'),list) or len(value['segments'])>32:raise ValueError('Invalid proposal count')
 for n,row in enumerate(value['segments']):
  if not isinstance(row,dict) or any(isinstance(row.get(k),bool) or not isinstance(row.get(k),(int,float)) or not math.isfinite(row[k]) for k in ['start','end']) or not 0<=row['start']<row['end']<=1800 or not .499<=row['end']-row['start']<=12.001:raise ValueError('Invalid proposal timing')
  if row.get('file')!='clip-'+str(n)+'.wav' or row.get('labelStatus')!='uncertain' or not re.fullmatch(r'[a-f0-9]{64}',row.get('sha256','')):raise ValueError('Invalid proposal file')
 return value

def preview(root,identifier,revision,name):
 index=read_index(root,identifier)
 if index['revision']!=revision or not re.fullmatch(r'[a-f0-9]{64}',revision):raise ValueError('Proposal changed')
 row=next((x for x in index['segments'] if x['file']==name),None)
 if row is None:raise ValueError('Unknown proposal clip')
 folder=pathlib.Path(root).resolve()/'proposals';data=PrivateVoices(folder).read(folder/identifier/revision/name,848000)
 if checksum(data)!=row['sha256']:raise ValueError('Proposal clip changed')
 return data

def activity_spans(path,cancelled):
 active=[];start=None;last=None
 with wave.open(str(path)) as f:
  if (f.getnchannels(),f.getsampwidth(),f.getframerate())!=(1,2,16000) or not 0<f.getnframes()<=16000*1800:raise ValueError('Inspection PCM exceeds limits')
  duration=f.getnframes()/16000;position=0
  while True:
   if cancelled():raise InterruptedError('Source inspection paused')
   data=f.readframes(320)
   if not data:break
   samples=array.array('h',data)
   if sys.byteorder!='little':samples.byteswap()
   sound=sum(x*x for x in samples)/len(samples)>(32768*.01)**2
   now=position/16000;position+=len(samples)
   if sound:
    if start is None:start=max(0,now-.1)
    last=position/16000
   elif start is not None and now-last>=.25:active.append((start,min(duration,last+.1)));start=None
  if start is not None:active.append((start,min(duration,last+.1)))
 result=[]
 for start,end in active:
  while end-start>=.5 and len(result)<32:
   stop=min(start+12,end);result.append((round(start,3),round(stop,3)));start=stop
 return result

def inspect_source(request_path,root,*,cancelled=lambda:False,downloader_factory=None,commit=None,expected_video=None):
 request_path=pathlib.Path(request_path).absolute();root=pathlib.Path(root).resolve()
 if any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in [request_path,*request_path.parents]) or request_path.stat().st_size>16384:raise ValueError('Invalid inspection request file')
 # Expand legitimate Windows short names before exact opened-handle comparison.
 request_path=request_path.resolve(strict=True)
 if root not in request_path.parents:raise ValueError('Inspection request is outside queue root')
 reader=PrivateVoices(root)
 raw=reader.read(request_path,16384);request=json.loads(raw);identifier=validate_request(request);request_hash=checksum(raw);started=time.monotonic()
 if expected_video is not None and identifier!=expected_video:raise ValueError('Inspection request does not match queued video')
 def paused():return cancelled() or time.monotonic()-started>600 or request_path.with_suffix('.cancel').exists() or reader.read(request_path,16384)!=raw
 if paused():raise InterruptedError('Source inspection paused')
 try:
  cached=read_index(root,identifier)
  if cached['requestSHA256']==request_hash:
   for row in cached['segments']:
    if paused():raise InterruptedError('Source inspection paused')
    preview(root,identifier,cached['revision'],row['file'])
   return cached
 except FileNotFoundError:pass
 except OSError:pass
 destination=root/'proposals'/identifier
 if any(p.is_symlink() for p in [destination,*destination.parents]):raise ValueError('Linked proposal folders are unsupported')
 destination.mkdir(parents=True,exist_ok=True)
 with _publish_lock(root/('.'+identifier+'.inspection.lock')):
  with tempfile.TemporaryDirectory(prefix='.inspecting-',dir=destination) as temporary:
   stage=pathlib.Path(temporary);ff=ffmpeg_path()
   # Acquisition remains bounded/cancellable; its temporary original is deleted on exit.
   with acquire(request['videoURL'],[dict(id='inspection-probe',start=0,end=.5)],downloader_factory,cancelled=paused) as source:
    if source['videoID']!=identifier:raise ValueError('Inspected source does not match the queued video')
    decoded=stage/'analysis.wav'
    checked_process([ff,'-v','error','-threads','1','-i',source['privateMoviePath'],'-t','1800.02','-fs','57600800','-vn','-ac','1','-ar','16000','-c:a','pcm_s16le',str(decoded)],timeout=90,cancelled=paused)
    spans=activity_spans(decoded,paused);rows=[]
    for n,(start,end) in enumerate(spans):
     name='clip-'+str(n)+'.wav';path=stage/name
     checked_process([ff,'-v','error','-threads','1','-ss',str(start),'-i',source['privateMoviePath'],'-t',str(end-start),'-vn','-ac','1','-ar','24000','-c:a','pcm_s16le',str(path)],timeout=30,cancelled=paused)
     with path.open('r+b') as stream:os.fsync(stream.fileno())
     data=path.read_bytes()
     if len(data)>848000:raise ValueError('Proposal clip too large')
     rows.append(dict(start=start,end=end,file=name,sha256=checksum(data),labelStatus='uncertain'))
    result=dict(schemaVersion=1,videoID=identifier,status='needs-source-review',requestSHA256=request_hash,sourceSHA256=source['sourceSHA256'],speakerSeparated=False,likenessVerified=False,segments=rows,scope='Audio activity suggestions only; names, clean speakers and reference use require explicit review')
   decoded.unlink();result['revision']=checksum(json.dumps(result,sort_keys=True,separators=(',',':')).encode())
   if paused():raise InterruptedError('Source inspection paused before publication')
   target=destination/result['revision']
   def publish():
    if paused():raise InterruptedError('Source inspection paused before publication')
    if target.exists():
     if target.is_symlink() or any((target/r['file']).read_bytes()!=(stage/r['file']).read_bytes() for r in rows):raise ValueError('Conflicting proposal revision')
    else:os.rename(stage,target)
    fd,name=tempfile.mkstemp(prefix='.index-',dir=destination)
    try:
     with os.fdopen(fd,'w',encoding='utf8') as f:json.dump(result,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
     os.replace(name,destination/'index.json')
    finally:pathlib.Path(name).unlink(missing_ok=True)
   if commit is None:publish()
   else:commit(publish)
   return result
