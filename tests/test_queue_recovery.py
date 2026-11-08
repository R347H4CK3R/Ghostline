import pathlib, sqlite3, tempfile, unittest, threading, concurrent.futures, time
from tools.video_queue import VideoQueue

URL = 'https://youtu.be/EAT0nWoEzJ8'
ID = 'EAT0nWoEzJ8'

class RecoveryTests(unittest.TestCase):
 def test_blocked_heartbeat_cannot_renew_expired_ownership(self):
  with tempfile.TemporaryDirectory() as d:
   p=str(pathlib.Path(d)/'queue.db');q=VideoQueue(p);q.add([URL])
   ready=threading.Event();start=threading.Event()
   def worker():
    candidate=VideoQueue(p);job=candidate.claim(lease_seconds=1);ready.set();start.wait(timeout=5)
    try:
     candidate.progress(ID,.5,token=job['token'])
     return 'renewed'
    except ValueError:return 'expired'
    finally:candidate.close()
   with concurrent.futures.ThreadPoolExecutor(1) as pool:
    future=pool.submit(worker);self.assertTrue(ready.wait(timeout=5))
    q.db.execute('BEGIN IMMEDIATE');start.set()
    try:time.sleep(1.2)
    finally:q.db.commit()
    self.assertEqual(future.result(timeout=5),'expired')
   self.assertEqual(q.claim()['attempt'],2);q.close()

 def test_lock_wait_does_not_return_an_already_expired_lease(self):
  with tempfile.TemporaryDirectory() as d:
   p=str(pathlib.Path(d)/'queue.db');q=VideoQueue(p);q.add([URL])
   ready=threading.Event();start=threading.Event()
   def worker():
    candidate=VideoQueue(p);ready.set();start.wait(timeout=5)
    try:return candidate.claim(lease_seconds=1)
    finally:candidate.close()
   with concurrent.futures.ThreadPoolExecutor(1) as pool:
    future=pool.submit(worker);self.assertTrue(ready.wait(timeout=5))
    q.db.execute('BEGIN IMMEDIATE');start.set()
    try:time.sleep(1.2)
    finally:q.db.commit()
    claimed=future.result(timeout=5)
   self.assertGreater(claimed['leaseUntil'],time.time())
   self.assertIsNone(q.claim());q.close()

 def test_two_workers_claim_once_and_tokens_are_not_exported(self):
  with tempfile.TemporaryDirectory() as d:
   p=str(pathlib.Path(d)/'queue.db');q=VideoQueue(p);q.add([URL]);q.close()
   barrier=threading.Barrier(2)
   def worker():
    queue=VideoQueue(p)
    try:barrier.wait(timeout=5);return queue.claim(now=100)
    finally:queue.close()
   with concurrent.futures.ThreadPoolExecutor(2) as pool:
    results=list(pool.map(lambda _:worker(),range(2)))
   winners=[x for x in results if x is not None]
   self.assertEqual(len(winners),1);self.assertEqual(winners[0]['attempt'],1)
   q=VideoQueue(p)
   self.assertNotIn(winners[0]['token'],str(q.export()));q.close()

 def test_expired_heartbeat_cannot_resurrect_before_another_claim(self):
  q=VideoQueue(':memory:');q.add([URL]);job=q.claim(now=100,lease_seconds=10)
  with self.assertRaises(ValueError):q.progress(ID,.4,token=job['token'],now=110)
  self.assertEqual(q.claim(now=110)['attempt'],2);q.close()

 def test_stopped_worker_recovers_and_old_owner_cannot_write(self):
  q=VideoQueue(':memory:'); q.add([URL])
  first=q.claim(now=100,lease_seconds=10)
  self.assertIsNone(q.claim(now=109))
  second=q.claim(now=110,lease_seconds=10)
  self.assertEqual(second['attempt'],2)
  self.assertNotEqual(first['token'],second['token'])
  with self.assertRaises(ValueError):q.progress(ID,.9,token=first['token'],now=111)
  with self.assertRaises(ValueError):q.fail(ID,first['token'],'stale failure',now=111)
  q.progress(ID,.5,token=second['token'],now=111)
  self.assertEqual(q.export()['videos'][0]['progress'],.5); q.close()

 def test_three_retries_then_persist_final_reason_without_fifth_attempt(self):
  with tempfile.TemporaryDirectory() as d:
   p=str(pathlib.Path(d)/'queue.db'); q=VideoQueue(p); q.add([URL])
   for attempt in range(1,5):
    job=q.claim(now=attempt*100)
    self.assertEqual(job['attempt'],attempt)
    q.fail(ID,job['token'],'Audio check failed '+str(attempt),now=attempt*100+1,retry_delay=10)
    self.assertIsNone(q.claim(now=attempt*100+5))
   q.close(); q=VideoQueue(p)
   self.assertIsNone(q.claim(now=10000))
   result=q.export()['videos'][0]
   self.assertEqual(result['status'],'failed'); self.assertEqual(result['attempts'],4)
   self.assertEqual(result['reason'],'Audio check failed 4')
   self.assertEqual(len(result['attemptHistory']),4); q.close()

 def test_four_worker_crashes_terminate_with_reason(self):
  q=VideoQueue(':memory:'); q.add([URL])
  for n in range(4):self.assertEqual(q.claim(now=n*10,lease_seconds=10)['attempt'],n+1)
  self.assertIsNone(q.claim(now=40))
  job=q.export()['videos'][0]
  self.assertEqual(job['status'],'failed'); self.assertIn('lease expired',job['reason'])
  self.assertEqual(len(job['attemptHistory']),4); q.close()

 def test_heartbeat_extends_ownership_and_review_does_not_auto_complete(self):
  q=VideoQueue(':memory:'); q.add([URL]); job=q.claim(now=100,lease_seconds=10)
  q.progress(ID,.3,token=job['token'],now=109,lease_seconds=10)
  self.assertIsNone(q.claim(now=111))
  q.progress(ID,1,'needs-review',token=job['token'],now=112)
  self.assertIsNone(q.claim(now=1000))
  self.assertEqual(q.export()['videos'][0]['status'],'needs-review')
  with self.assertRaises(ValueError):q.progress(ID,1,'completed',token=job['token'],now=113)
  q.close()

 def test_invalid_lease_or_progress_cannot_poison_queue(self):
  q=VideoQueue(':memory:'); q.add([URL])
  for lease in [0,-1,float('nan'),float('inf'),3601]:
   with self.assertRaises(ValueError):q.claim(now=100,lease_seconds=lease)
  job=q.claim(now=100)
  for value in [float('nan'),float('inf'),-.1,1.1,True]:
   with self.assertRaises(ValueError):q.progress(ID,value,token=job['token'],now=101)
  with self.assertRaises(ValueError):q.progress(ID,.3,now=101)
  self.assertEqual(q.export()['videos'][0]['progress'],0);q.close()

 def test_legacy_database_preserves_names_and_recovers_unowned_processing(self):
  with tempfile.TemporaryDirectory() as d:
   p=str(pathlib.Path(d)/'old.db'); db=sqlite3.connect(p)
   db.execute('CREATE TABLE jobs (video_id TEXT PRIMARY KEY,url TEXT NOT NULL,status TEXT NOT NULL,progress REAL NOT NULL,updated REAL NOT NULL)')
   db.execute('INSERT INTO jobs VALUES (?,?,?,?,?)',(ID,URL,'processing',.4,1))
   db.execute('CREATE TABLE names (video_id TEXT PRIMARY KEY,name TEXT NOT NULL)')
   db.execute('INSERT INTO names VALUES (?,?)',(ID,'Example role'));db.commit();db.close()
   q=VideoQueue(p); job=q.claim(now=100)
   self.assertEqual(job['id'],ID);self.assertEqual(job['attempt'],1)
   self.assertEqual(q.db.execute('SELECT name FROM names').fetchone()[0],'Example role')
   self.assertEqual(q.add([URL])['duplicates'],[ID]);q.close()

if __name__=='__main__':unittest.main()
