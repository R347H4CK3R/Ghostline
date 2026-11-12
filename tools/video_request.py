"""Explicit source-use requests, transactionally coupled to the private video queue."""
import json,pathlib,time,uuid
from tools.video_queue import VideoQueue,video_id
from tools.workflow_activity import append


def validate(body):
 if not isinstance(body,dict) or set(body)!={'schemaVersion','requestID','videoURL','displayName','sourceUse'} or type(body['schemaVersion']) is not int or body['schemaVersion']!=1:raise ValueError('Invalid candidate request')
 if not isinstance(body['requestID'],str) or str(uuid.UUID(body['requestID']))!=body['requestID']:raise ValueError('Invalid request identifier')
 if not isinstance(body['videoURL'],str) or len(body['videoURL'])>2048:raise ValueError('Invalid source URL')
 identifier=video_id(body['videoURL'])
 name=body['displayName']
 if not isinstance(name,str) or len(name)>200 or any(ord(c)<32 for c in name):raise ValueError('Invalid optional source hint')
 use=body['sourceUse']
 if not isinstance(use,dict) or set(use)!={'decision','record'} or use['decision']!='approved-private-candidates' or not isinstance(use['record'],str) or not 1<=len(use['record'].strip())<=3000:raise ValueError('Explicit source-use affirmation is required')
 return dict(body,videoURL='https://www.youtube.com/watch?v='+identifier,displayName=name.strip(),sourceUse=dict(use,record=use['record'].strip()))


def load(db,identifier):
 if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='candidate_requests'").fetchone():return None
 row=db.execute('SELECT body FROM candidate_requests WHERE video_id=?',(identifier,)).fetchone()
 if row is None:return None
 body=validate(json.loads(row[0]))
 if video_id(body['videoURL'])!=identifier:raise ValueError('Saved request does not match this job')
 return body


def preparation_wait(db,request_id):
 if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='candidate_preparation_waits'").fetchone():return None
 row=db.execute('SELECT reason FROM candidate_preparation_waits WHERE request_id=?',(request_id,)).fetchone()
 return None if row is None else row[0]


def record_preparation_wait(db,request_id,reason):
 """Called inside the queue owner's transaction; retains the immutable request."""
 db.execute('CREATE TABLE IF NOT EXISTS candidate_preparation_waits (request_id TEXT PRIMARY KEY,reason TEXT NOT NULL)')
 db.execute('INSERT OR IGNORE INTO candidate_preparation_waits VALUES (?,?)',(request_id,reason))


def submit(root,body):
 body=validate(body);identifier=video_id(body['videoURL']);root=pathlib.Path(root)
 root.mkdir(parents=True,exist_ok=True)
 q=VideoQueue(str(root/'queue.db'))
 try:
  q.db.execute('BEGIN IMMEDIATE')
  q.db.execute('CREATE TABLE IF NOT EXISTS candidate_requests (video_id TEXT PRIMARY KEY,request_id TEXT UNIQUE NOT NULL,body TEXT NOT NULL,created REAL NOT NULL)')
  repeated=q.db.execute('SELECT video_id FROM candidate_requests WHERE request_id=?',(body['requestID'],)).fetchone()
  if repeated and repeated[0]!=identifier:raise FileExistsError('Request identifier already belongs to another source')
  previous=load(q.db,identifier)
  if previous is not None:
   # Different retry IDs are fine; a changed scope/record is a separately reviewed operation.
   if any(previous[k]!=body[k] for k in ('videoURL','sourceUse','displayName')):raise FileExistsError('Existing request scope was preserved')
   q.db.commit();return dict(schemaVersion=1,accepted=True,videoID=identifier,requestID=body['requestID'],alreadyRequested=True,format='f5-reference',identityVerified=False)
  old=q.db.execute('SELECT status FROM jobs WHERE video_id=?',(identifier,)).fetchone()
  if old and old[0] not in ('waiting','paused','awaiting-preparation'):raise FileExistsError('Active or finished work was preserved')
  if any((root/folder/(identifier+'.json')).exists() for folder in ('recipes','specifications')):raise FileExistsError('Existing prepared work was preserved')
  now=time.time()
  row=q.db.execute('INSERT OR IGNORE INTO jobs VALUES (?,?,?,?,?)',(identifier,body['videoURL'],'waiting',0,now))
  q.db.execute("INSERT OR IGNORE INTO job_control VALUES (?,0,NULL,0,0,'')",(identifier,))
  if row.rowcount:append(q.db,identifier,'received',now=now)
  q.db.execute('INSERT INTO candidate_requests VALUES (?,?,?,?)',(identifier,body['requestID'],json.dumps(body,sort_keys=True),now))
  q.db.execute('CREATE TABLE IF NOT EXISTS names (video_id TEXT PRIMARY KEY,name TEXT NOT NULL)')
  if body['displayName']:q.db.execute('INSERT OR IGNORE INTO names VALUES (?,?)',(identifier,body['displayName']))
  attempt=q.db.execute('SELECT attempts FROM job_control WHERE video_id=?',(identifier,)).fetchone()[0]
  append(q.db,identifier,'candidate_requested',attempt=attempt,now=now)
  q.db.commit()
  return dict(schemaVersion=1,accepted=True,videoID=identifier,requestID=body['requestID'],alreadyRequested=False,format='f5-reference',identityVerified=False)
 except BaseException:q.db.rollback();raise
 finally:q.close()
