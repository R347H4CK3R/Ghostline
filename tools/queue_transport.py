"""Authenticated queue API; loopback only until an encrypted device transport is paired."""
import hmac,json,pathlib,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from tools.video_queue import VideoQueue

def create_server(root,token,port=0):
 if len(token)<32:raise ValueError('Use a strong pairing token')
 root=pathlib.Path(root);root.mkdir(parents=True,exist_ok=True);lock=threading.Lock()
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*args):pass # Do not log tokens or submitted names/links.
  def respond(self,code,data):
   body=json.dumps(data).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
  def authorized(self):return hmac.compare_digest(self.headers.get('Authorization','').encode('utf-8'),('Bearer '+token).encode('utf-8'))
  def do_GET(self):
   if not self.authorized():return self.respond(401,dict(error='Pairing required'))
   if self.path!='/status':return self.respond(404,dict(error='Unknown action'))
   q=VideoQueue(str(root/'queue.db'))
   try:
    result=q.export()
    self.respond(200,result)
   finally:q.close()
  def do_POST(self):
   if not self.authorized():return self.respond(401,dict(error='Pairing required'))
   if self.path!='/queue':return self.respond(404,dict(error='Unknown action'))
   try:
    length=int(self.headers.get('Content-Length','0'))
    if not 0<length<=65536:raise ValueError('Queue request is too large or empty')
    body=json.loads(self.rfile.read(length));videos=body['videos']
    if not isinstance(videos,list) or len(videos)>200:raise ValueError('Send up to 200 videos')
    with lock:
     q=VideoQueue(str(root/'queue.db'))
     try:
      result=q.add_named(videos)
     finally:q.close()
    self.respond(200,dict(result,namesStored=True,pipelineConnected=False))
   except (ValueError,KeyError,TypeError,json.JSONDecodeError):self.respond(400,dict(error='Invalid queue request; no valid list was imported'))
 server=ThreadingHTTPServer(('127.0.0.1',port),Handler);server.daemon_threads=True;return server
