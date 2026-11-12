import json,pathlib,tempfile,threading,unittest,urllib.request,urllib.error
from tools.queue_transport import create_server
from tools.video_queue import VideoQueue

class WorkflowTransportTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name)
  self.server=create_server(self.root,'x'*48,trusted_login='owner@example.test')
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
  self.base='http://127.0.0.1:'+str(self.server.server_port)
 def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
 def get(self,path,auth=True):
  request=urllib.request.Request(self.base+path,headers={'Tailscale-User-Login':'owner@example.test'} if auth else {})
  try:
   with urllib.request.urlopen(request) as r:return r.status,r.read(),dict(r.headers)
  except urllib.error.HTTPError as r:return r.code,r.read(),dict(r.headers)
 def test_workflow_page_and_api_require_authentication(self):
  for path in ['/workflow-log','/workflow','/workflow?video=EAT0nWoEzJ8']:
   self.assertEqual(self.get(path,auth=False)[0],401)
  status,body,headers=self.get('/workflow-log');self.assertEqual(status,200)
  self.assertIn('no-store',headers['Cache-Control']);self.assertIn("default-src 'none'",headers['Content-Security-Policy'])
  self.assertIn(b'/sync-log',body);self.assertNotIn(b'innerHTML',body)
 def test_reads_do_not_create_database_and_selection_is_validated(self):
  status,body,_=self.get('/workflow');self.assertEqual(status,200);self.assertEqual(json.loads(body)['videos'],[])
  self.assertFalse((self.root/'queue.db').exists())
  for path in ['/workflow?video=bad','/workflow?video=EAT0nWoEzJ8&video=EAT0nWoEzJ8','/workflow?token=secret']:
   self.assertEqual(self.get(path)[0],400)
 def test_real_receipt_is_private_bounded_and_filterable(self):
  q=VideoQueue(str(self.root/'queue.db'));q.add(['https://youtu.be/EAT0nWoEzJ8','https://youtu.be/SYNTHETIC03'])
  q.db.execute('CREATE TABLE names(video_id TEXT,name TEXT)');q.db.execute('INSERT INTO names VALUES (?,?)',('EAT0nWoEzJ8','Private name and transcript'));q.db.commit();q.close()
  status,body,headers=self.get('/workflow?video=EAT0nWoEzJ8');self.assertEqual(status,200)
  data=json.loads(body);self.assertEqual([v['id'] for v in data['videos']],['EAT0nWoEzJ8'])
  self.assertEqual(data['videos'][0]['events'][0]['stage'],'received');self.assertNotIn(b'Private name',body)
  self.assertIn('no-store',headers['Cache-Control']);self.assertEqual(data['eventLimit'],160)
