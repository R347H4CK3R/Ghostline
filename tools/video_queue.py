"""Persistent laptop queue: canonical video IDs and transactional duplicate protection."""
import json,re,sqlite3,time
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
  self.db.execute('CREATE TABLE IF NOT EXISTS jobs (video_id TEXT PRIMARY KEY, url TEXT NOT NULL, status TEXT NOT NULL, progress REAL NOT NULL, updated REAL NOT NULL)');self.db.commit()
 def close(self):self.db.close()
 def add(self,urls):
  # Validate the entire list before changing the queue.
  ids=[video_id(url) for url in urls];added=[];duplicates=[]
  with self.db:
   for identifier in ids:
    row=self.db.execute('INSERT OR IGNORE INTO jobs VALUES (?, ?, ?, ?, ?)',(identifier,'https://www.youtube.com/watch?v='+identifier,'waiting',0,time.time()))
    (added if row.rowcount else duplicates).append(identifier)
  return dict(added=added,duplicates=duplicates)
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
  return dict(schemaVersion=1,videos=[dict(id=r[0],url=r[1],status=r[2],progress=r[3],updated=r[4]) for r in self.db.execute('SELECT * FROM jobs ORDER BY updated,video_id')])
