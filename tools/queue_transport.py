"""Authenticated queue API; loopback only until an encrypted device transport is paired."""
import hmac,json,pathlib,threading,secrets,re
from urllib.parse import urlsplit,parse_qs
from tools.source_review import save_initial_review,page
from tools.master_voices import PublishBusy
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from tools.video_queue import VideoQueue,video_id
from tools.private_voices import PrivateVoices,TransferError

def create_server(root,token,port=0,trusted_login=None,master=None):
 if len(token)<32:raise ValueError('Use a strong pairing token')
 root=pathlib.Path(root);root.mkdir(parents=True,exist_ok=True);lock=threading.Lock()
 csrf=secrets.token_urlsafe(32)
 voices=PrivateVoices(master) if master is not None else None
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*args):pass # Do not log tokens or submitted names/links.
  def respond(self,code,data):
   body=json.dumps(data).encode();self.send_response(code);self.send_header('Cache-Control','no-store');self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
  def authorized(self):
   if hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+token):return True
   # Opt-in only, on this loopback-bound server behind Tailscale Serve.
   # Serve strips client-supplied identity headers before injecting authenticated identity.
   login=self.headers.get('Tailscale-User-Login','')
   return bool(trusted_login and login and hmac.compare_digest(login,trusted_login))
  def do_GET(self):
   if not self.authorized():return self.respond(401,dict(error='Pairing required'))
   address=urlsplit(self.path)
   if address.path=='/review':
    selection=parse_qs(address.query,keep_blank_values=True)
    if selection and (set(selection)!={'video'} or len(selection['video'])!=1 or not re.fullmatch(r'[A-Za-z0-9_-]{11}',selection['video'][0])):return self.respond(400,dict(error='Invalid source selection'))
    body=page(csrf);self.send_response(200);self.send_header('Cache-Control','no-store');self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'nonce-"+csrf+"'; style-src 'nonce-"+csrf+"'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'");self.end_headers();self.wfile.write(body);return
   if self.path=='/voices' or self.path.startswith('/voices/'):
    if voices is None:return self.respond(404,dict(error='Private master is not configured'))
    try:
     if self.path=='/voices':return self.respond(200,voices.catalog())
     parts=self.path.split('/',3)
     if len(parts)!=4:return self.respond(404,dict(error='Unknown voice asset'))
     data=voices.file(parts[2],parts[3]);self.send_response(200);self.send_header('Cache-Control','no-store');self.send_header('Content-Type','application/octet-stream');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
    except TransferError as error:return self.respond(error.status,dict(error='Private voice snapshot unavailable or changed; refresh the catalog'))
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
   if self.path=='/review':
    if not hmac.compare_digest(self.headers.get('X-VoiceMatrix-Review',''),csrf):return self.respond(403,dict(error='Reload the source review page before submitting'))
    try:
     length=int(self.headers.get('Content-Length','0'))
     if not 0<length<=512000 or self.headers.get('Content-Type','')!='application/json':raise ValueError('Invalid review request')
     result=save_initial_review(root,json.loads(self.rfile.read(length)));return self.respond(200,result)
    except (FileExistsError,PublishBusy):return self.respond(409,dict(error='An existing review or busy writer was preserved; replacements need a separate reviewed update'))
    except (ValueError,TypeError,KeyError,OverflowError):return self.respond(400,dict(error='Review rejected: check queued video, source-use record, labels and 0.5–15 second segments'))
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

