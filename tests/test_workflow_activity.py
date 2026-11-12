import json,pathlib,sqlite3,tempfile,unittest
from tools.video_queue import VideoQueue

VIDEO='EAT0nWoEzJ8'
class WorkflowActivityTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name);self.path=self.root/'queue.db';self.q=VideoQueue(str(self.path))
 def tearDown(self):self.q.close();self.tmp.cleanup()
 def snapshot(self,**kwargs):
  from tools.workflow_activity import snapshot
  return snapshot(self.path,VIDEO,**kwargs)
 def test_receipt_is_recorded_once_and_survives_restart(self):
  self.q.add(['https://youtu.be/'+VIDEO]);self.q.add(['https://youtu.be/'+VIDEO])
  self.q.close();self.q=VideoQueue(str(self.path))
  events=self.snapshot()['videos'][0]['events']
  self.assertEqual([e['stage'] for e in events],['received','already_queued'])
  self.q.add(['https://youtu.be/'+VIDEO]);self.assertEqual(len(self.snapshot()['videos'][0]['events']),3)
 def test_worker_stage_is_fenced_and_history_is_bounded(self):
  self.q.add(['https://youtu.be/'+VIDEO]);job=self.q.claim(now=10)
  for n in range(170):self.q.stage(VIDEO,job['token'],'synthesizing',completed=n,total=200,now=11)
  with self.assertRaises(ValueError):self.q.stage(VIDEO,'old-owner','publishing',now=12)
  result=self.snapshot(now=12)['videos'][0]
  self.assertEqual(len(result['events']),160);self.assertTrue(result['workerActive'])
  self.assertEqual(result['events'][-1]['completed'],169)
  self.assertFalse(self.snapshot(now=200)['videos'][0]['workerActive'])
 def test_failure_history_never_copies_exception_paths_or_tokens(self):
  self.q.add(['https://youtu.be/'+VIDEO]);job=self.q.claim(now=10)
  self.q.fail(VIDEO,job['token'],'secret-token C:\\Users\\Private\\voice.wav secret transcript',now=11)
  result=self.snapshot(now=12);encoded=json.dumps(result)
  self.assertNotIn('secret',encoded);self.assertNotIn('Private',encoded)
  self.assertEqual(result['videos'][0]['events'][-1]['stage'],'retry')
 def test_read_only_snapshot_does_not_migrate_legacy_database_or_invent_events(self):
  self.q.add(['https://youtu.be/'+VIDEO]);self.q.db.execute('DROP TABLE workflow_events');self.q.db.commit()
  result=self.snapshot(now=20)['videos'][0]
  self.assertFalse(result['historyAvailable']);self.assertEqual(result['events'],[])
  self.assertNotIn('workflow_events',[r[0] for r in self.q.db.execute("SELECT name FROM sqlite_master WHERE type='table'")])
 def test_same_progress_heartbeat_does_not_add_events(self):
  self.q.add(['https://youtu.be/'+VIDEO]);job=self.q.claim(now=10)
  self.q.progress(VIDEO,.5,token=job['token'],now=11)
  count=len(self.snapshot(now=12)['videos'][0]['events'])
  self.q.progress(VIDEO,.5,token=job['token'],now=12)
  self.assertEqual(len(self.snapshot(now=13)['videos'][0]['events']),count)
 def test_repeated_waiting_claim_does_not_churn_timeline(self):
  self.q.add(['https://youtu.be/'+VIDEO]);job=self.q.claim(now=10)
  self.q.pause(VIDEO,job['token'],now=11,status='awaiting-preparation')
  first=self.snapshot(now=12)['videos'][0]['events']
  job=self.q.claim(now=20);self.q.pause(VIDEO,job['token'],now=21,status='awaiting-preparation')
  self.assertEqual(self.snapshot(now=22)['videos'][0]['events'],first)
 def test_invalid_stage_and_counters_are_not_recorded(self):
  self.q.add(['https://youtu.be/'+VIDEO]);job=self.q.claim(now=10)
  with self.assertRaises(ValueError):self.q.stage(VIDEO,job['token'],'private free text',now=11)
  with self.assertRaises(ValueError):self.q.stage(VIDEO,job['token'],'synthesizing',completed=-1,now=11)

 def test_overview_and_single_video_histories_are_bounded_under_phone_byte_limit(self):
  from tools.workflow_activity import snapshot
  ids=[str(n).zfill(11) for n in range(201)]
  self.q.add(['https://youtu.be/'+v for v in ids])
  with self.q.db:
   for v in ids:
    for n in range(21):self.q.db.execute('INSERT INTO workflow_events(video_id,time,stage,attempt,completed,total) VALUES (?,?,?,?,?,?)',(v,1,'needs_review',1,n,100))
  result=snapshot(self.path,now=2)
  self.assertEqual(len(result['videos']),200);self.assertTrue(result['hasMore'])
  self.assertTrue(all(len(v['events'])==20 and not v['historyAvailable'] for v in result['videos']))
  self.assertLess(len(json.dumps(result).encode()),2*1024*1024)
  self.assertEqual(len(snapshot(self.path,ids[0],now=2)['videos'][0]['events']),22)
 def test_mirror_does_not_claim_new_external_submission(self):
  self.q.add(['https://youtu.be/'+VIDEO]);self.q.add(['https://youtu.be/'+VIDEO],record_duplicates=False)
  self.assertEqual([e['stage'] for e in self.snapshot()['videos'][0]['events']],['received'])

 def test_explicit_listening_and_duplicate_receipts_keep_each_timestamp(self):
  from tools.workflow_activity import append
  self.q.add(['https://youtu.be/'+VIDEO])
  with self.q.db:
   for at in [10,11,12]:append(self.q.db,VIDEO,'listening_recorded',attempt=1,now=at)
  events=self.snapshot()['videos'][0]['events']
  self.assertEqual([e['time'] for e in events if e['stage']=='listening_recorded'],[10,11,12])

 def test_publication_end_timestamp_follows_actual_operation(self):
  import time
  self.q.add(['https://youtu.be/'+VIDEO]);job=self.q.claim();ended=[]
  def publish():time.sleep(.02);ended.append(time.time())
  self.q.review_with(VIDEO,job['token'],publish)
  result=self.snapshot()['videos'][0]
  self.assertGreaterEqual(result['events'][-1]['time'],ended[0])
