"""Authenticated queue API; loopback only until an encrypted device transport is paired."""
import hmac,json,pathlib,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from tools.video_queue import VideoQueue,video_id

def create_server(root,token,port=0):
 if len(token)<32:raise ValueError('Use a strong pairing token')
 root=pathlib.Path(root);root.mkdir(parents=True,exist_ok=True);lock=threading.Lock()
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*args):pass # Do not log tokens or submitted names/links.
  def respond(self,code,data):
   body=json.dumps(data).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
  def authorized(self):return hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+token)
  def do_GET(self):
   if not self.authorized():return self.respond(401,dict(error='Pairing required'))
   if self.path!='/status':return self.respond(404,dict(error='Unknown action'))
   q=VideoQueue(str(root/'queue.db'))
   try:
    q.db.execute('CREATE TABLE IF NOT EXISTS names (video_id TEXT PRIMARY KEY,name TEXT NOT NULL)')
    result=q.export();names=dict(q.db.execute('SELECT video_id,name FROM names'))
    for video in result['videos']:video['name']=names.get(video['id'],'')
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
    if any(not isinstance(v,dict) or not isinstance(v.get('url'),str) or not isinstance(v.get('name',''),str) for v in videos):raise ValueError('Invalid video request')
    names=[(video_id(v['url']),v.get('name','').strip()) for v in videos]
    if any(len(name)>1000 for _,name in names):raise ValueError('Names are too long')
    with lock:
     q=VideoQueue(str(root/'queue.db'))
     try:
      result=q.add([v['url'] for v in videos])
      with q.db:
       q.db.execute('CREATE TABLE IF NOT EXISTS names (video_id TEXT PRIMARY KEY,name TEXT NOT NULL)')
       for identifier,name in names:
        if name:q.db.execute('INSERT INTO names VALUES (?,?) ON CONFLICT(video_id) DO UPDATE SET name=excluded.name',(identifier,name))
     finally:q.close()
    self.respond(200,dict(result,namesStored=True,pipelineConnected=False))
   except (ValueError,KeyError,TypeError,json.JSONDecodeError):self.respond(400,dict(error='Invalid queue request; no valid list was imported'))
 server=ThreadingHTTPServer(('127.0.0.1',port),Handler);server.daemon_threads=True;return server
