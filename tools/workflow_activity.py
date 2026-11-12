"""Bounded private workflow evidence. Only fixed stage messages and numeric counters.

Readers never migrate the queue, inspect private assets, or invent historical events.
Writers use the queue's transaction so a rolled-back transition leaves no receipt.
"""
import math,pathlib,re,sqlite3,time

MESSAGES={
 'received':'Laptop saved the video link in its queue; processing has not started.',
 'already_queued':'Laptop received this link again; the existing queue entry was kept.',
 'claimed':'Worker claimed this video attempt.',
 'resumed':'Worker resumed the paused attempt.',
 'awaiting_preparation':'Waiting for reviewed source segments or prepared references; no voice processing is active.',
 'paused':'Worker paused; this video and its existing outputs are retained.',
 'retry':'Attempt failed; retry is scheduled. Check the preceding stage and private laptop diagnostics.',
 'failed':'Attempt failed; automatic retries are exhausted. Existing voices and this link are retained.',
 'lease_expired':'Worker heartbeat expired before the attempt finished.',
 'review_saved':'Source review was saved; waiting for the worker to prepare the approved segments.',
 'inspection_requested':'Source inspection was requested; waiting for the worker.',
 'inspection_stop_requested':'Inspection stop requested; this is not yet a worker acknowledgement.',
 'inspection_started':'Worker is inspecting the approved source request.',
 'inspection_analyzing':'Worker is finding audio activity and creating private review previews; speaker labels are not inferred.',
 'inspection_ready':'Private source previews are ready; source and speaker-label review is still required.',
 'preparation_started':'Worker is preparing the reviewed source segments.',
 'download_started':'Worker is attempting the bounded source download.',
 'download_finished':'Source download returned; media checks are next.',
 'media_checking':'Worker is checking downloaded media.',
 'extracting':'Worker is extracting a source audio segment.',
 'transcribing':'Worker is transcribing missing reference words locally; the transcript still needs review.',
 'preparation_ready':'Prepared references were saved for this video.',
 'references_checking':'Worker is validating prepared references and building voice packs.',
 'model_loading':'Worker is obtaining the local speech model.',
 'synthesizing':'Worker is generating test speech for a prepared profile.',
 'audio_checking':'Worker is checking generated audio format, level and clipping.',
 'words_checking':'Worker is checking generated words with the independent recognizer.',
 'publishing':'Worker is publishing checked new profiles to the private master; existing-voice replacement stays guarded.',
 'needs_review':'Technical processing ended. Likeness and individual native/device checks remain pending; this job is not complete.',
 'listening_recorded':'A listening decision was saved. It does not complete or activate the video job.',
}

def initialize(db):
 db.execute('CREATE TABLE IF NOT EXISTS workflow_events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, video_id TEXT NOT NULL, time REAL NOT NULL, stage TEXT NOT NULL, attempt INTEGER NOT NULL, completed INTEGER NOT NULL, total INTEGER NOT NULL)')
 db.execute('CREATE INDEX IF NOT EXISTS workflow_video_sequence ON workflow_events(video_id,sequence)')

def append(db,identifier,stage,*,attempt=0,completed=0,total=0,now=None):
 if stage not in MESSAGES:raise ValueError('Unknown workflow stage')
 if not isinstance(identifier,str) or not re.fullmatch(r'[A-Za-z0-9_-]{11}',identifier):raise ValueError('Invalid video identifier')
 if any(type(n) is not int or not 0<=n<=1000000 for n in [attempt,completed,total]) or completed>total:raise ValueError('Invalid workflow counters')
 now=time.time() if now is None else now
 if type(now) not in (int,float) or not math.isfinite(now) or not 0<=now<=1e15:raise ValueError('Invalid workflow time')
 previous=db.execute('SELECT stage,attempt,completed,total FROM workflow_events WHERE video_id=? ORDER BY sequence DESC LIMIT 1',(identifier,)).fetchone()
 # Coalesce repeated idle/worker observations, never distinct external receipts.
 if stage not in {'already_queued','review_saved','inspection_requested','inspection_stop_requested','listening_recorded'} and previous==(stage,attempt,completed,total):return
 db.execute('INSERT INTO workflow_events(video_id,time,stage,attempt,completed,total) VALUES (?,?,?,?,?,?)',(identifier,now,stage,attempt,completed,total))
 db.execute('DELETE FROM workflow_events WHERE video_id=? AND sequence NOT IN (SELECT sequence FROM workflow_events WHERE video_id=? ORDER BY sequence DESC LIMIT 160)',(identifier,identifier))

def snapshot(database,identifier=None,*,now=None):
 if identifier is not None and (not isinstance(identifier,str) or not re.fullmatch(r'[A-Za-z0-9_-]{11}',identifier)):raise ValueError('Invalid video selection')
 now=time.time() if now is None else now
 event_limit=160 if identifier is not None else 20
 result=dict(schemaVersion=1,observedAt=now,videos=[],hasMore=False,eventLimit=event_limit)
 path=pathlib.Path(database)
 if not path.exists():return result
 db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=10)
 try:
  db.execute('BEGIN')
  tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
  if not {'jobs','job_control'}<=tables:return result
  clause='WHERE j.video_id=?' if identifier is not None else ''
  rows=db.execute('SELECT j.video_id,j.status,j.progress,j.updated,c.attempts,c.next_attempt,c.lease_until FROM jobs j JOIN job_control c USING(video_id) '+clause+' ORDER BY j.updated DESC,j.video_id LIMIT 201',() if identifier is None else (identifier,)).fetchall()
  result['hasMore']=len(rows)>200
  for video,status,progress,updated,attempts,next_attempt,lease in rows[:200]:
   events=[]
   if 'workflow_events' in tables:
    for sequence,at,stage,attempt,completed,total in reversed(db.execute('SELECT sequence,time,stage,attempt,completed,total FROM workflow_events WHERE video_id=? ORDER BY sequence DESC LIMIT ?',(video,event_limit)).fetchall()):
     if stage in MESSAGES:events.append(dict(sequence=sequence,time=at,stage=stage,message=MESSAGES[stage],attempt=attempt,completed=completed,total=total))
   result['videos'].append(dict(id=video,status=status,progress=progress,updated=updated,attempts=attempts,nextAttempt=next_attempt,workerLeaseUntil=lease,workerActive=status=='processing' and lease>now,historyAvailable=bool(events and events[0]['stage']=='received'),events=events))
  return result
 finally:db.close()

def page(nonce):
 return pathlib.Path(__file__).with_name('workflow_log.html').read_text(encoding='utf8').replace('__NONCE__',nonce).encode()
