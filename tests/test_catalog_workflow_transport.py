"""Authenticated workflow includes an observation, never private catalog payloads."""
import hashlib, json, threading, time, urllib.error, urllib.request, unittest
from unittest.mock import patch
from tests import test_private_voice_transfer as fixtures
from tools.private_voices import PrivateVoices

class CatalogWorkflowTransportTests(unittest.TestCase):
 setUp=fixtures.PrivateTransferTests.setUp
 tearDown=fixtures.PrivateTransferTests.tearDown
 def get(self,authorized=True):
  headers={'Authorization':'Bearer '+'x'*48} if authorized else {}
  with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:'+str(self.server.server_port)+'/workflow',headers=headers),timeout=2) as response:return json.load(response)
 def test_workflow_catalog_is_authenticated_sanitized_and_non_destructive(self):
  before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (self.root/'Voices').rglob('*') if p.is_file()}
  with self.assertRaises(urllib.error.HTTPError) as error:self.get(False)
  self.assertEqual(error.exception.code,401)
  result=self.get();deadline=time.time()+3
  while result['catalog']['state']=='checking' and time.time()<deadline:
   time.sleep(.01);result=self.get()
  self.assertEqual(result['catalog']['count'],1)
  self.assertEqual(result['catalog']['events'][0]['kind'],'observed')
  serialized=json.dumps(result)
  for secret in ['A reference sentence','reference.wav','x'*48,str(self.root)]:self.assertNotIn(secret,serialized)
  after={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (self.root/'Voices').rglob('*') if p.is_file()}
  self.assertEqual(before,after)
 def test_slow_catalog_cannot_block_queue_receipt_snapshot(self):
  entered=threading.Event();release=threading.Event();original=PrivateVoices.catalog
  def slow(source):entered.set();release.wait(4);return original(source)
  try:
   with patch.object(PrivateVoices,'catalog',slow):
    result=self.get();self.assertTrue(entered.wait(1))
    self.assertEqual(result['catalog']['state'],'checking')
    self.assertEqual(result['videos'],[])
  finally:
   release.set()
   deadline=time.time()+3
   while self.get()['catalog']['state']=='checking' and time.time()<deadline:time.sleep(.01)
