import json,tempfile,threading,unittest,urllib.request,urllib.error
from tools.queue_transport import create_server

class TransportTests(unittest.TestCase):
 def test_pairing_and_duplicate_protection_over_http(self):
  with tempfile.TemporaryDirectory() as d:
   server=create_server(d,'a'*40);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
   url='http://127.0.0.1:'+str(server.server_port)
   try:
    with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(url+'/status')
    self.assertEqual(error.exception.code,401)
    data=json.dumps(dict(videos=[dict(url='https://youtu.be/EAT0nWoEzJ8')])).encode()
    for expected in [1,0]:
     request=urllib.request.Request(url+'/queue',data=data,headers={'Authorization':'Bearer '+'a'*40,'Content-Type':'application/json'})
     with urllib.request.urlopen(request) as response:result=json.load(response)
     self.assertEqual(len(result['added']),expected);self.assertFalse(result['pipelineConnected'])
   finally:server.shutdown();server.server_close();thread.join()


class InvalidRequestTests(unittest.TestCase):
 def setUp(self):
  self.directory=tempfile.TemporaryDirectory()
  self.server=create_server(self.directory.name,'a'*40)
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
 def tearDown(self):
  self.server.shutdown();self.server.server_close();self.thread.join();self.directory.cleanup()
 def test_non_ascii_authorization_is_rejected_without_dropping_connection(self):
  import http.client
  conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=2)
  try:
   conn.request('GET','/status',headers={'Authorization':'Bearer café'})
   response=conn.getresponse()
   self.assertEqual(response.status,401)
   self.assertEqual(json.loads(response.read())['error'],'Pairing required')
  finally:conn.close()
 def test_invalid_utf8_returns_json_error_without_import(self):
  import http.client
  conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=2)
  try:
   conn.request('POST','/queue',body=b'\xff',headers={'Authorization':'Bearer '+'a'*40})
   response=conn.getresponse();self.assertEqual(response.status,400)
   self.assertIn('error',json.loads(response.read()))
  finally:conn.close()

if __name__=='__main__':unittest.main()
