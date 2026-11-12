import copy,json,pathlib,tempfile,unittest
from tools.video_queue import VideoQueue

class AutomaticRequestTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.temp.name)
  self.body=dict(schemaVersion=1,requestID='b3e5fa2b-2b08-44ba-946a-299860f2e765',videoURL='https://youtu.be/EAT0nWoEzJ8',displayName='Optional source hint',sourceUse=dict(decision='approved-private-candidates',record='I may use this recording privately.'))
 def tearDown(self):self.temp.cleanup()
 def submit(self,body=None):
  from tools.video_request import submit
  return submit(self.root,self.body if body is None else body)
 def test_request_is_saved_atomically_with_queue_and_fixed_event(self):
  from tools.video_request import load
  result=self.submit();self.assertEqual(result['videoID'],'EAT0nWoEzJ8');self.assertTrue(result['accepted']);self.assertFalse(result['alreadyRequested'])
  q=VideoQueue(str(self.root/'queue.db'))
  try:
   self.assertEqual(q.export()['videos'][0]['status'],'waiting')
   record=load(q.db,'EAT0nWoEzJ8');self.assertEqual(record['sourceUse'],self.body['sourceUse'])
   stages=[x[0] for x in q.db.execute('SELECT stage FROM workflow_events ORDER BY sequence')]
   self.assertEqual(stages,['received','candidate_requested'])
  finally:q.close()
 def test_identical_retry_does_not_duplicate_or_reset_job(self):
  first=self.submit();q=VideoQueue(str(self.root/'queue.db'));job=q.claim();q.pause(job['id'],job['token']);q.close()
  second=self.submit();self.assertTrue(second['alreadyRequested']);self.assertEqual(first['requestID'],second['requestID'])
  q=VideoQueue(str(self.root/'queue.db'))
  try:self.assertEqual(len(q.export()['videos']),1);self.assertEqual(q.export()['videos'][0]['attempts'],1)
  finally:q.close()
 def test_changed_record_or_reused_id_is_rejected_and_original_preserved(self):
  from tools.video_request import load
  self.submit()
  for key,value in [('videoURL','https://youtu.be/ZNFskLKrhx4'),('sourceUse',dict(decision='approved-private-candidates',record='different'))]:
   changed=copy.deepcopy(self.body);changed[key]=value
   with self.assertRaises(FileExistsError):self.submit(changed)
  q=VideoQueue(str(self.root/'queue.db'))
  try:self.assertEqual(load(q.db,'EAT0nWoEzJ8')['sourceUse'],self.body['sourceUse']);self.assertEqual(len(q.export()['videos']),1)
  finally:q.close()
 def test_identical_retry_remains_idempotent_after_preparation(self):
  self.submit();folder=self.root/'specifications';folder.mkdir();(folder/'EAT0nWoEzJ8.json').write_bytes(b'preserved')
  self.assertTrue(self.submit()['alreadyRequested'])
 def test_invalid_or_unapproved_request_does_not_create_database(self):
  for change in [dict(sourceUse={}),dict(sourceUse=dict(decision='approved-private-candidates',record='')),dict(requestID='../bad'),dict(videoURL='http://youtu.be/EAT0nWoEzJ8'),dict(schemaVersion=True),dict(unexpected='field')]:
   body=dict(self.body,**change)
   with self.assertRaises((ValueError,TypeError)):self.submit(body)
   self.assertFalse((self.root/'queue.db').exists())
 def test_preexisting_prepared_inputs_are_never_overwritten(self):
  folder=self.root/'recipes';folder.mkdir();path=folder/'EAT0nWoEzJ8.json';path.write_bytes(b'preserved')
  with self.assertRaises(FileExistsError):self.submit()
  self.assertEqual(path.read_bytes(),b'preserved')
 def test_legacy_waiting_job_can_be_explicitly_requested(self):
  q=VideoQueue(str(self.root/'queue.db'));q.add([self.body['videoURL']]);job=q.claim();q.pause(job['id'],job['token'],status='awaiting-preparation');q.close()
  self.assertTrue(self.submit()['accepted'])
 def test_completed_or_active_legacy_job_is_not_changed(self):
  q=VideoQueue(str(self.root/'queue.db'));q.add([self.body['videoURL']]);q.claim();q.close()
  with self.assertRaises(FileExistsError):self.submit()

if __name__=='__main__':unittest.main()
