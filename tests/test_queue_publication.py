import pathlib,tempfile,unittest,sqlite3
from tools.video_queue import VideoQueue

class PublicationTests(unittest.TestCase):
 def test_prepared_spec_commit_holds_ownership_without_completing_job(self):
  with tempfile.TemporaryDirectory() as d:
   p=str(pathlib.Path(d)/'q.db');a=VideoQueue(p);b=VideoQueue(p);b.db.execute('PRAGMA busy_timeout=1')
   a.add(['https://youtu.be/EAT0nWoEzJ8']);job=a.claim()
   def operation():
    with self.assertRaises(sqlite3.OperationalError):b.db.execute('BEGIN IMMEDIATE')
    return 'prepared'
   self.assertEqual(a.owned_call(job['id'],job['token'],operation),'prepared')
   self.assertEqual(a.export()['videos'][0]['status'],'processing');a.close();b.close()
 def test_stale_prepared_spec_commit_never_executes(self):
  a=VideoQueue(':memory:');a.add(['https://youtu.be/EAT0nWoEzJ8']);job=a.claim(now=100,lease_seconds=1);a.claim(now=102);called=[]
  with self.assertRaises(ValueError):a.owned_call(job['id'],job['token'],lambda:called.append(True))
  self.assertEqual(called,[]);a.close()
 def test_review_callback_is_fenced_against_second_connection(self):
  with tempfile.TemporaryDirectory() as d:
   p=str(pathlib.Path(d)/'q.db');a=VideoQueue(p);b=VideoQueue(p);b.db.execute('PRAGMA busy_timeout=1')
   a.add(['https://youtu.be/EAT0nWoEzJ8']);job=a.claim()
   def operation():
    with self.assertRaises(sqlite3.OperationalError):b.db.execute('BEGIN IMMEDIATE')
    return dict(published=True)
   self.assertTrue(hasattr(a,'review_with'),'Owned publication transaction is missing')
   self.assertEqual(a.review_with(job['id'],job['token'],operation),dict(published=True))
   self.assertEqual(a.export()['videos'][0]['status'],'needs-review');a.close();b.close()
 def test_stale_owner_callback_never_runs(self):
  a=VideoQueue(':memory:');a.add(['https://youtu.be/EAT0nWoEzJ8']);job=a.claim(now=100,lease_seconds=1);a.claim(now=102)
  called=[]
  self.assertTrue(hasattr(a,'review_with'),'Owned publication transaction is missing')
  with self.assertRaises(ValueError):a.review_with(job['id'],job['token'],lambda:called.append(True),now=102)
  self.assertEqual(called,[]);a.close()

