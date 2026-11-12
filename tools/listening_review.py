"""Private immutable-audio listening records. Never activate voices or complete jobs."""
import hashlib,io,json,math,pathlib,re,sqlite3,time,uuid,zipfile,zlib
from tools.private_voices import PrivateVoices
from tools.voice_pack import validate_pack
from tools.workflow_activity import initialize,append
import wave

def digest(data):return hashlib.sha256(data).hexdigest()
class ListeningReview:
 def __init__(self,work,database):self.work=pathlib.Path(work).resolve();self.database=str(database);self.reader=PrivateVoices(self.work)
 def connection(self):
  db=sqlite3.connect(self.database,timeout=15)
  db.execute('CREATE TABLE IF NOT EXISTS listening_reviews (id TEXT PRIMARY KEY, created REAL NOT NULL, snapshot TEXT NOT NULL, record TEXT NOT NULL)')
  initialize(db)
  return db
 def snapshot(self,video,attempt,index):
  try:return self._snapshot(video,attempt,index)
  except (OSError,EOFError,wave.Error,zipfile.BadZipFile,KeyError,TypeError,IndexError,NotImplementedError,RuntimeError,zlib.error) as error:raise ValueError("Listening output unavailable or malformed") from error
 def _snapshot(self,video,attempt,index):
  if not isinstance(video,str) or not re.fullmatch(r'[A-Za-z0-9_-]{11}',video) or type(attempt) is not int or not 1<=attempt<=4 or type(index) is not int or not 0<=index<64:raise ValueError('Invalid listening selection')
  db=self.connection()
  try:state=db.execute('SELECT j.status,c.attempts FROM jobs j JOIN job_control c USING(video_id) WHERE video_id=?',(video,)).fetchone()
  finally:db.close()
  if state!=('needs-review',attempt):raise ValueError('Job no longer awaits this listening review')
  folder=self.work/video/('attempt-'+str(attempt));raw=self.reader.read(folder/'result.json',2000000);result=json.loads(raw)
  if not isinstance(result,dict) or result.get('status')!='needs-review' or result.get('videoID')!=video or result.get('attempt')!=attempt or not isinstance(result.get('profiles'),list) or index>=len(result['profiles']):raise ValueError('No technically checked output for this selection')
  row=result['profiles'][index];pack=self.reader.read(folder/('profile-'+str(index)+'.vmpack'),1200000);metadata=validate_pack(io.BytesIO(pack))
  if row['id']!=metadata['id'] or row['referenceSHA256']!=metadata['referenceSHA256']:raise ValueError('Reference snapshot changed')
  preview=self.reader.read(folder/(metadata['id']+'-preview.wav'),28800128)
  # Verify PCM from the captured bytes, independent of any later path reread.
  import array,sys,wave
  with wave.open(io.BytesIO(preview)) as f:
   if (f.getnchannels(),f.getsampwidth(),f.getframerate(),f.getcomptype())!=(1,2,24000,'NONE'):raise ValueError('Invalid preview PCM')
   frames=f.getnframes();pcm=f.readframes(frames)
  if not 1200<=frames<=14400000 or len(pcm)!=frames*2:raise ValueError('Invalid preview duration')
  samples=array.array('h',pcm)
  if sys.byteorder!='little':samples.byteswap()
  if math.sqrt(sum(x*x for x in samples)/len(samples))/32768<=.0001 or any(abs(x)>=32767 for x in samples):raise ValueError('Preview is silent or clipped')
  generated=digest(preview);words=row['wordcheck']
  if not isinstance(words,dict):raise ValueError('Invalid word check evidence')
  if row['audio']['wavSHA256']!=generated or words.get('wavSHA256')!=generated or words.get('passed') is not True or type(words.get('wordErrorRate')) not in (int,float) or not 0<=words['wordErrorRate']<=.1:raise ValueError('Preview word/audio evidence changed')
  with zipfile.ZipFile(io.BytesIO(pack)) as z:reference=z.read('reference.wav')
  token=digest(raw+pack+preview)
  return dict(videoID=video,attempt=attempt,profileIndex=index,id=metadata['id'],name=metadata['name'],snapshot=token,referenceSHA256=digest(reference),generatedSHA256=generated,wordErrorRate=words['wordErrorRate'],nativePerProfileVerified=result.get('nativePerProfileVerified') is True,physicalDeviceVerified=result.get('physicalDeviceVerified') is True,activated=False,completed=False),reference,preview
 def catalog(self):
  db=self.connection();rows=[];errors=[]
  try:
   jobs=db.execute("SELECT j.video_id,c.attempts FROM jobs j JOIN job_control c USING(video_id) WHERE j.status='needs-review' ORDER BY j.updated DESC LIMIT 200").fetchall()
   for video,attempt in jobs:
    if len(rows)>=200:break
    try:
     result=json.loads(self.reader.read(self.work/video/('attempt-'+str(attempt))/'result.json',2000000))
     if not isinstance(result,dict) or not isinstance(result.get('profiles'),list) or not 1<=len(result['profiles'])<=64:raise ValueError('Invalid profile list')
     for index in range(len(result['profiles'])):
      if len(rows)>=200:break
      row,_,_=self.snapshot(video,attempt,index);row['reviews']=[json.loads(r[0]) for r in db.execute('SELECT record FROM listening_reviews WHERE snapshot=? ORDER BY created,id LIMIT 200',(row['snapshot'],))];rows.append(row)
    except (OSError,ValueError,KeyError,TypeError,IndexError):errors.append(dict(videoID=video,error='Output unavailable or changed; check laptop diagnostics'))
   return dict(candidates=rows,errors=errors,activated=False,completed=False)
  finally:db.close()
 def audio(self,video,attempt,index,token,kind):
  row,reference,preview=self.snapshot(video,attempt,index)
  if token!=row['snapshot'] or kind not in ['reference','preview']:raise ValueError('Listening snapshot changed')
  return reference if kind=='reference' else preview
 def decide(self,body):
  if not isinstance(body,dict) or set(body)!={'videoID','attempt','profileIndex','snapshot','decision','reviewer','note'} or body['decision'] not in ['Matches','DoesntMatch','Unsure'] or not isinstance(body['reviewer'],str) or not body['reviewer'].strip() or len(body['reviewer'])>200 or not isinstance(body['note'],str) or len(body['note'])>3000:raise ValueError('Explicit listening decision and reviewer required')
  if not isinstance(body['videoID'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{11}',body['videoID']) or type(body['attempt']) is not int or not 1<=body['attempt']<=4 or type(body['profileIndex']) is not int or not 0<=body['profileIndex']<64 or not isinstance(body['snapshot'],str) or not re.fullmatch(r'[a-f0-9]{64}',body['snapshot']):raise ValueError('Invalid listening selection')
  db=self.connection()
  try:
   db.execute('BEGIN IMMEDIATE')
   state=db.execute('SELECT j.status,c.attempts FROM jobs j JOIN job_control c USING(video_id) WHERE video_id=?',(body['videoID'],)).fetchone()
   if state!=('needs-review',body['attempt']):raise ValueError('Job no longer awaits this listening review')
   row,_,_=self.snapshot(body['videoID'],body['attempt'],body['profileIndex'])
   if row['snapshot']!=body['snapshot']:raise ValueError('Listening snapshot changed; reload and listen again')
   record=dict(row,decision=body['decision'],reviewer=body['reviewer'].strip(),note=body['note'],reviewID=uuid.uuid4().hex,created=time.time(),scope='Subjective listening only; technical, native and authorization gates remain separate')
   db.execute('INSERT INTO listening_reviews VALUES (?,?,?,?)',(record['reviewID'],record['created'],row['snapshot'],json.dumps(record)))
   append(db,body['videoID'],'listening_recorded',attempt=body['attempt'])
   db.commit();return record
  finally:db.close()

def page(csrf):return pathlib.Path(__file__).with_name('listening_review.html').read_text(encoding='utf8').replace('__CSRF__',csrf).encode()
