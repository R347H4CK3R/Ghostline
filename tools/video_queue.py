"""Persistent laptop queue: canonical video IDs and transactional duplicate protection."""
import json,re,sqlite3,time,math,uuid
from urllib.parse import urlparse,parse_qs

def video_id(url):
 p=urlparse(url.strip())
 if p.scheme!='https' or p.username or p.password:raise ValueError('Use an HTTPS YouTube video link')
 if p.hostname=='youtu.be':identifier=p.path.strip('/')
 elif p.hostname in ('youtube.com','www.youtube.com','m.youtube.com'):
  parts=p.path.strip('/').split('/')
  identifier=parse_qs(p.query).get('v',[''])[0] if p.path=='/watch' else parts[1] if len(parts)==2 and parts[0] in ('live','shorts','embed') else ''
 else:raise ValueError('Unsupported video host')
 if not re.fullmatch(r'[A-Za-z0-9_-]{11}',identifier):raise ValueError('Invalid video ID')
 return identifier

class VideoQueue:
 def __init__(self,path):
  self.db=sqlite3.connect(path,timeout=30)
  with self.db:
   self.db.execute('CREATE TABLE IF NOT EXISTS jobs (video_id TEXT PRIMARY KEY, url TEXT NOT NULL, status TEXT NOT NULL, progress REAL NOT NULL, updated REAL NOT NULL)')
   self.db.execute('CREATE TABLE IF NOT EXISTS job_control (video_id TEXT PRIMARY KEY, attempts INTEGER NOT NULL, token TEXT, lease_until REAL NOT NULL, next_attempt REAL NOT NULL, reason TEXT NOT NULL)')
   self.db.execute('CREATE TABLE IF NOT EXISTS job_attempts (video_id TEXT NOT NULL, attempt INTEGER NOT NULL, started REAL NOT NULL, ended REAL, outcome TEXT, reason TEXT, PRIMARY KEY(video_id,attempt))')
   # Legacy processing jobs had no owner or heartbeat and cannot resume safely.
   self.db.execute("UPDATE jobs SET status='waiting' WHERE status='processing' AND video_id NOT IN (SELECT video_id FROM job_control)")
   self.db.execute("INSERT OR IGNORE INTO job_control SELECT video_id,0,NULL,0,0,'' FROM jobs")
 def close(self):self.db.close()
 def add(self,urls):
  # Validate the entire list before changing the queue.
  ids=[video_id(url) for url in urls];added=[];duplicates=[]
  with self.db:
   for identifier in ids:
    row=self.db.execute('INSERT OR IGNORE INTO jobs VALUES (?, ?, ?, ?, ?)',(identifier,'https://www.youtube.com/watch?v='+identifier,'waiting',0,time.time()))
    self.db.execute("INSERT OR IGNORE INTO job_control VALUES (?,0,NULL,0,0,'')",(identifier,))
    (added if row.rowcount else duplicates).append(identifier)
  return dict(added=added,duplicates=duplicates)
 @staticmethod
 def _number(value,minimum,maximum):
  if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not minimum<=value<=maximum:raise ValueError('Invalid queue time or progress')
  return value
 def _now(self,now):return self._number(time.time() if now is None else now,0,1e15)
 def claim(self,*,now=None,lease_seconds=120):
  if now is not None:self._now(now)
  self._number(lease_seconds,1,3600)
  self.db.execute('BEGIN IMMEDIATE')
  try:
   now=self._now(now)
   expired=self.db.execute("SELECT j.video_id,c.attempts FROM jobs j JOIN job_control c USING(video_id) WHERE j.status='processing' AND c.lease_until<=?",(now,)).fetchall()
   for identifier,attempt in expired:
    self._end(identifier,attempt,'Worker lease expired before the stage finished',now,0)
   row=self.db.execute("SELECT j.video_id,j.url,c.attempts,j.status FROM jobs j JOIN job_control c USING(video_id) WHERE j.status IN ('waiting','retry','paused','awaiting-preparation') AND c.next_attempt<=? AND (c.attempts<4 OR j.status IN ('paused','awaiting-preparation')) ORDER BY j.updated,j.video_id LIMIT 1",(now,)).fetchone()
   result=None
   if row:
    identifier,url,attempt,status=row;attempt+=0 if status in ('paused','awaiting-preparation') else 1;token=uuid.uuid4().hex
    self.db.execute("UPDATE jobs SET status='processing',progress=0,updated=? WHERE video_id=?",(now,identifier))
    self.db.execute('UPDATE job_control SET attempts=?,token=?,lease_until=?,next_attempt=0 WHERE video_id=?',(attempt,token,now+lease_seconds,identifier))
    self.db.execute('INSERT INTO job_attempts VALUES (?,?,?,NULL,NULL,NULL) ON CONFLICT(video_id,attempt) DO UPDATE SET ended=NULL,outcome=NULL,reason=NULL',(identifier,attempt,now))
    result=dict(id=identifier,url=url,attempt=attempt,token=token,leaseUntil=now+lease_seconds)
   self.db.commit();return result
  except BaseException:self.db.rollback();raise
 def pause(self,identifier,token,*,now=None,status='paused'):
  if status not in ('paused','awaiting-preparation'):raise ValueError('Invalid waiting state')
  self.db.execute('BEGIN IMMEDIATE')
  try:
   now=self._now(now);attempt=self._owner(identifier,token,now)
   self.db.execute('UPDATE jobs SET status=?,updated=? WHERE video_id=?',(status,now,identifier))
   self.db.execute('UPDATE job_control SET token=NULL,lease_until=0,next_attempt=0 WHERE video_id=?',(identifier,))
   self.db.execute("UPDATE job_attempts SET ended=?,outcome='paused' WHERE video_id=? AND attempt=?",(now,identifier,attempt));self.db.commit()
  except BaseException:self.db.rollback();raise
 def review_with(self,identifier,token,operation,*,now=None):
  """Fence a trusted publisher against reclaim; this is review, not completion."""
  self.db.execute('BEGIN IMMEDIATE')
  try:
   now=self._now(now);attempt=self._owner(identifier,token,now)
   result=operation()
   self.db.execute("UPDATE jobs SET status='needs-review',progress=1,updated=? WHERE video_id=?",(now,identifier))
   self.db.execute('UPDATE job_control SET token=NULL,lease_until=0 WHERE video_id=?',(identifier,))
   self.db.execute("UPDATE job_attempts SET ended=?,outcome='needs-review' WHERE video_id=? AND attempt=?",(now,identifier,attempt));self.db.commit();return result
  except BaseException:self.db.rollback();raise
 def owned_call(self,identifier,token,operation):
  """Commit a prepared-spec pointer only while this worker still owns the job."""
  self.db.execute('BEGIN IMMEDIATE')
  try:
   self._owner(identifier,token,self._now(None));result=operation();self.db.commit();return result
  except BaseException:self.db.rollback();raise
 def _owner(self,identifier,token,now):
  row=self.db.execute("SELECT c.attempts FROM job_control c JOIN jobs j USING(video_id) WHERE c.video_id=? AND c.token=? AND c.lease_until>? AND j.status='processing'",(identifier,token,now)).fetchone()
  if not token or not row:raise ValueError('Worker no longer owns this job')
  return row[0]
 def _end(self,identifier,attempt,reason,now,retry_delay):
  status='failed' if attempt>=4 else 'retry'
  self.db.execute('UPDATE jobs SET status=?,updated=? WHERE video_id=?',(status,now,identifier))
  self.db.execute('UPDATE job_control SET token=NULL,lease_until=0,next_attempt=?,reason=? WHERE video_id=?',(now+retry_delay,reason,identifier))
  self.db.execute("UPDATE job_attempts SET ended=?,outcome='failed',reason=? WHERE video_id=? AND attempt=?",(now,reason,identifier,attempt))
 def fail(self,identifier,token,reason,*,now=None,retry_delay=30):
  if now is not None:self._now(now)
  self._number(retry_delay,0,86400)
  if not isinstance(reason,str) or not reason.strip() or len(reason)>1000:raise ValueError('Give a short failure reason')
  self.db.execute('BEGIN IMMEDIATE')
  try:
   now=self._now(now)
   attempt=self._owner(identifier,token,now)
   self._end(identifier,attempt,reason.strip(),now,retry_delay);self.db.commit()
  except BaseException:self.db.rollback();raise
 def progress(self,identifier,fraction,status='processing',*,token=None,now=None,lease_seconds=120):
  if now is not None:self._now(now)
  self._number(fraction,0,1);self._number(lease_seconds,1,3600)
  # Completion requires a future validated-export transaction, not a progress flag.
  if status not in ('processing','needs-review'):raise ValueError('Invalid job progress')
  self.db.execute('BEGIN IMMEDIATE')
  try:
   now=self._now(now)
   attempt=self._owner(identifier,token,now)
   self.db.execute('UPDATE jobs SET status=?,progress=?,updated=? WHERE video_id=?',(status,fraction,now,identifier))
   if status=='processing':self.db.execute('UPDATE job_control SET lease_until=? WHERE video_id=?',(now+lease_seconds,identifier))
   else:
    self.db.execute('UPDATE job_control SET token=NULL,lease_until=0 WHERE video_id=?',(identifier,))
    self.db.execute("UPDATE job_attempts SET ended=?,outcome='needs-review' WHERE video_id=? AND attempt=?",(now,identifier,attempt))
   self.db.commit()
  except BaseException:self.db.rollback();raise
 def export(self):
  videos=[]
  for r in self.db.execute('SELECT j.*,c.attempts,c.next_attempt,c.reason FROM jobs j JOIN job_control c USING(video_id) ORDER BY j.updated,j.video_id'):
   history=[dict(attempt=h[0],started=h[1],ended=h[2],outcome=h[3],reason=h[4]) for h in self.db.execute('SELECT attempt,started,ended,outcome,reason FROM job_attempts WHERE video_id=? ORDER BY attempt',(r[0],))]
   videos.append(dict(id=r[0],url=r[1],status=r[2],progress=r[3],updated=r[4],attempts=r[5],nextAttempt=r[6],reason=r[7],attemptHistory=history))
  return dict(schemaVersion=1,videos=videos)

