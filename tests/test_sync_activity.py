import json, threading, unittest, urllib.error, urllib.request, uuid
from unittest.mock import patch
from tests import test_private_voice_transfer as fixtures
from tools.private_voices import PrivateVoices

class SyncActivityTests(unittest.TestCase):
 setUp=fixtures.PrivateTransferTests.setUp
 tearDown=fixtures.PrivateTransferTests.tearDown
 def request(self, path, sync_id=None, authorized=True):
  headers={'Authorization':'Bearer '+'x'*48} if authorized else {}
  if sync_id is not None: headers['X-VoiceMatrix-Sync-ID']=sync_id
  return urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:'+str(self.server.server_port)+path,headers=headers),timeout=5)
 def test_receipt_is_visible_while_catalog_is_still_processing(self):
  identifier=str(uuid.uuid4()); entered=threading.Event(); release=threading.Event(); original=PrivateVoices.catalog
  def delayed(source, *args, **kwargs):
   entered.set();release.wait(4);return original(source,*args,**kwargs)
  result=[]
  with patch.object(PrivateVoices,'catalog',delayed):
   def download():
    with self.request('/voices',identifier) as response:result.append(json.load(response))
   worker=threading.Thread(target=download);worker.start()
   try:
    self.assertTrue(entered.wait(2))
    with self.request('/voice-sync/'+identifier) as response:status=json.load(response)
    self.assertEqual(status['syncID'],identifier)
    self.assertEqual([e['stage'] for e in status['events']],['received','validating'])
    self.assertNotIn('catalog_ready',[e['stage'] for e in status['events']])
   finally:release.set();worker.join()
  self.assertEqual(len(result),1)
 def test_transfer_log_has_counts_but_no_private_content(self):
  identifier=str(uuid.uuid4())
  with self.request('/voices',identifier) as response:
   self.assertEqual(response.headers['X-VoiceMatrix-Sync-ID'],identifier);catalog=json.load(response)
  for row in catalog['files']:
   with self.request('/voices/'+catalog['revision']+'/'+row['path'],identifier) as response:response.read()
  with self.request('/voice-sync/'+identifier) as response:status=json.load(response)
  stages=[e['stage'] for e in status['events']]
  self.assertIn('catalog_ready',stages);self.assertEqual(stages[-1],'file_sent')
  self.assertEqual(status['events'][-1]['completed'],3)
  serialized=json.dumps(status)
  for secret in ['original-test','Private fixture','A reference sentence','reference.wav',catalog['revision'],'x'*48]:self.assertNotIn(secret,serialized)
  with self.request('/sync-log') as response:self.assertIn(b'Live voice sync log',response.read())
 def test_activity_requires_auth_and_valid_random_id(self):
  for path in ['/voice-sync','/voice-sync/'+str(uuid.uuid4()),'/sync-log']:
   with self.assertRaises(urllib.error.HTTPError) as error:self.request(path,authorized=False)
   self.assertEqual(error.exception.code,401)
  with self.assertRaises(urllib.error.HTTPError) as error:self.request('/voices','private-name')
  self.assertEqual(error.exception.code,400)
 def test_failed_snapshot_is_reported_without_exception_text(self):
  identifier=str(uuid.uuid4());(self.root/'Voices/collection.json').write_text('private broken catalog')
  with self.assertRaises(urllib.error.HTTPError):self.request('/voices',identifier)
  with self.request('/voice-sync/'+identifier) as response:status=json.load(response)
  self.assertEqual(status['events'][-1]['stage'],'failed')
  self.assertNotIn('private broken',json.dumps(status))

if __name__=='__main__':unittest.main()

class ActivityBoundsTests(unittest.TestCase):
 def test_limits_duplicates_and_expiration(self):
  from tools.sync_activity import SyncActivity
  activity=SyncActivity();identifier=activity.start(None)
  with self.assertRaises(ValueError):activity.start(identifier)
  for _ in range(250):activity.add(identifier,'file_sent',file_key='one-file')
  snapshot=activity.snapshot(identifier)
  self.assertEqual(len(snapshot['events']),160)
  self.assertEqual(snapshot['events'][-1]['completed'],1)
  for _ in range(40):activity.start(None)
  self.assertEqual(len(activity.snapshot()['sessions']),32)
  self.assertIsNone(activity.snapshot(identifier))
  for session in activity.sessions.values():session['updated']-=901
  self.assertEqual(activity.snapshot()['sessions'],[])
