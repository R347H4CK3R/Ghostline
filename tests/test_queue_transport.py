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

if __name__=='__main__':unittest.main()
