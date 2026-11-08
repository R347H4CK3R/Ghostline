"""Persistent laptop queue: canonical video IDs and transactional duplicate protection."""
import hashlib,json,re,sqlite3,time
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
  self.db.execute('CREATE TABLE IF NOT EXISTS jobs (video_id TEXT PRIMARY KEY, url TEXT NOT NULL, status TEXT NOT NULL, progress REAL NOT NULL, updated REAL NOT NULL)')
  self.db.execute('CREATE TABLE IF NOT EXISTS names (video_id TEXT PRIMARY KEY,name TEXT NOT NULL)')
  self.db.execute('CREATE TABLE IF NOT EXISTS imports (digest TEXT PRIMARY KEY)');self.db.commit()
 def close(self):self.db.close()
 def add(self,urls):
  return self.add_named([dict(url=url) for url in urls])
 def _validate_named(self,videos):
  rows=[]
  for video in videos:
   if not isinstance(video,dict) or not isinstance(video.get('url'),str) or not isinstance(video.get('name',''),str):
    raise ValueError('Invalid video request')
   name=video.get('name','').strip()
   if len(name)>1000:raise ValueError('Names are too long')
   rows.append((video_id(video['url']),name))
  return rows
 def _insert_named(self,rows):
  added=[];duplicates=[]
  for identifier,name in rows:
   row=self.db.execute('INSERT OR IGNORE INTO jobs VALUES (?, ?, ?, ?, ?)',(identifier,'https://www.youtube.com/watch?v='+identifier,'waiting',0,time.time()))
   (added if row.rowcount else duplicates).append(identifier)
   if name:self.db.execute('INSERT INTO names VALUES (?,?) ON CONFLICT(video_id) DO UPDATE SET name=excluded.name',(identifier,name))
  return dict(added=added,duplicates=duplicates)
 def add_named(self,videos):
  # Validate the whole request before either jobs or labels can change.
  rows=self._validate_named(videos)
  with self.db:return self._insert_named(rows)
 def import_text(self,text):
  """Import an iPhone tab-separated export or one HTTPS URL per line.

  Keep a durable receipt so the monitor cannot reapply an unchanged file's
  older labels over a later API edit. The caller retains the source file.
  """
  if not isinstance(text,str):raise ValueError('Queue must be text')
  if len(text.encode('utf8'))>1024*1024:raise ValueError('Queue file exceeds 1 MiB')
  videos=[]
  for line in text.lstrip('\ufeff').splitlines():
   if not line.strip() or line.lstrip().startswith('#'):continue
   parts=line.split('\t')
   if len(parts)>2:raise ValueError('Expected a name and one video link per line')
   videos.append(dict(name=parts[0].strip() if len(parts)==2 else '',url=parts[-1].strip()))
  rows=self._validate_named(videos)
  digest=hashlib.sha256(text.encode('utf8')).hexdigest()
  self.db.execute('BEGIN IMMEDIATE')
  try:
   if self.db.execute('SELECT 1 FROM imports WHERE digest=?',(digest,)).fetchone():
    result=dict(added=[],duplicates=[identifier for identifier,_ in rows])
   else:
    result=self._insert_named(rows)
    self.db.execute('INSERT INTO imports VALUES (?)',(digest,))
   self.db.commit();return result
  except BaseException:self.db.rollback();raise
 def claim(self):
  self.db.execute('BEGIN IMMEDIATE')
  try:
   row=self.db.execute("SELECT video_id,url FROM jobs WHERE status='waiting' ORDER BY updated,video_id LIMIT 1").fetchone()
   if row:self.db.execute("UPDATE jobs SET status='processing',updated=? WHERE video_id=?",(time.time(),row[0]))
   self.db.commit();return dict(id=row[0],url=row[1]) if row else None
  except BaseException:self.db.rollback();raise
 def progress(self,identifier,fraction,status='processing'):
  if status not in ('processing','needs-review','failed','completed') or not 0<=fraction<=1:raise ValueError('Invalid job progress')
  with self.db:
   row=self.db.execute('UPDATE jobs SET status=?,progress=?,updated=? WHERE video_id=?',(status,fraction,time.time(),identifier))
   if not row.rowcount:raise ValueError('Unknown job')
 def export(self):
  return dict(schemaVersion=1,videos=[dict(id=r[0],url=r[1],status=r[2],progress=r[3],updated=r[4],name=r[5]) for r in self.db.execute("SELECT jobs.*, COALESCE(names.name,'') FROM jobs LEFT JOIN names USING(video_id) ORDER BY updated,video_id")])
