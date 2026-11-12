import json,pathlib,tempfile,threading,unittest,urllib.request,urllib.error
from tools.queue_transport import create_server

class CandidateRequestTransportTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name);self.server=create_server(self.root,'x'*48,trusted_login='owner@example.test')
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.base='http://127.0.0.1:'+str(self.server.server_port)
  self.body=dict(schemaVersion=1,requestID='b3e5fa2b-2b08-44ba-946a-299860f2e765',videoURL='https://youtu.be/EAT0nWoEzJ8',displayName='',sourceUse=dict(decision='approved-private-candidates',record='My authorized recording'))
 def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
 def post(self,body,auth=True,content_type='application/json'):
  headers={'Content-Type':content_type}
  if auth:headers['Authorization']='Bearer '+'x'*48
  request=urllib.request.Request(self.base+'/requests',data=json.dumps(body).encode(),headers=headers)
  try:
   with urllib.request.urlopen(request) as r:return r.status,json.load(r)
  except urllib.error.HTTPError as r:return r.code,json.load(r)
 def test_request_requires_auth_and_json_no_unintended_queue(self):
  self.assertEqual(self.post(self.body,auth=False)[0],401)
  self.assertEqual(self.post(self.body,content_type='text/plain')[0],400)
  self.assertFalse((self.root/'queue.db').exists())
 def test_valid_request_bound_receipt_and_conflict(self):
  status,result=self.post(self.body);self.assertEqual(status,200);self.assertTrue(result['accepted']);self.assertEqual(result['requestID'],self.body['requestID']);self.assertEqual(result['videoID'],'EAT0nWoEzJ8')
  changed=dict(self.body,sourceUse=dict(decision='approved-private-candidates',record='changed'))
  self.assertEqual(self.post(changed)[0],409)
 def test_no_affirmation_or_oversized_request_is_rejected(self):
  self.assertEqual(self.post(dict(self.body,sourceUse={}))[0],400)
  self.assertEqual(self.post(dict(self.body,displayName='x'*17000))[0],400)
  self.assertFalse((self.root/'queue.db').exists())
