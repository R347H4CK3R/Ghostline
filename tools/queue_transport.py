"""Authenticated queue API; loopback only until an encrypted device transport is paired."""
import hmac,json,pathlib,threading,secrets,re,sqlite3,math
from urllib.parse import urlsplit,parse_qs
from tools.listening_review import ListeningReview,page as listening_page
from tools.source_review import save_initial_review,page,save_inspection,stop_inspection
from tools.source_inspection import read_index,preview
from tools.video_request import submit as submit_candidate_request
from tools.master_voices import PublishBusy
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from tools.video_queue import VideoQueue,video_id
from tools.private_voices import PrivateVoices,TransferError
from tools.sync_activity import SyncActivity,page as sync_page
from tools.catalog_activity import CatalogActivity
from tools.workflow_activity import snapshot as workflow_snapshot,page as workflow_page

def _rvc_roots(root, rvc_root):
 # Check paths even before either database exists. Never initialize either root
 # when the optional RVC configuration is unsafe.
 f5 = pathlib.Path(root).resolve()
 rvc = pathlib.Path(rvc_root).absolute()
 if rvc.resolve() != rvc or any(path.is_symlink() for path in (rvc, *rvc.parents)):
  raise ValueError('Choose an unlinked private RVC root')
 if rvc == f5 or rvc in f5.parents or f5 in rvc.parents:
  raise ValueError('F5 and RVC roots must be separate and non-overlapping')
 return rvc

def _rvc_status(root):
 from tools.rvc_request import DATABASE,ensure_root
 result=dict(schemaVersion=1,format='rvc-v2-pth-index',jobs=[],truncated=False,nativeIPhoneRuntimeVerified=False)
 database=root/DATABASE
 if not database.exists() and not database.is_symlink():return result
 ensure_root(root)
 # Never use VideoQueue here: its constructor creates tables and repairs jobs.
 db=sqlite3.connect(database.as_uri()+'?mode=ro',uri=True,timeout=2)
 try:
  db.execute('PRAGMA query_only=ON')
  tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('candidate_requests','rvc_requests')")}
  if tables!={'rvc_requests'}:raise ValueError('Not an isolated RVC queue')
  rows=db.execute('SELECT substr(j.video_id,1,12),substr(j.status,1,40),j.progress,c.attempts '
                  'FROM jobs j JOIN job_control c USING(video_id) ORDER BY j.updated DESC,j.video_id LIMIT 101').fetchall()
  result['truncated']=len(rows)>100
  allowed={'waiting','processing','retry','paused','awaiting-preparation','needs-review','failed'}
  for identifier,status,progress,attempts in rows[:100]:
   if not isinstance(identifier,str) or not re.fullmatch(r'[A-Za-z0-9_-]{11}',identifier):continue
   progress=progress if type(progress) in (int,float) and math.isfinite(progress) and 0<=progress<=1 else 0
   attempts=attempts if type(attempts) is int and 0<=attempts<=4 else 0
   result['jobs'].append(dict(videoID=identifier,status=status if status in allowed else 'needs-review',progress=progress,attempts=attempts))
  return result
 finally:db.close()

def create_server(root,token,port=0,trusted_login=None,master=None,rvc_root=None,rvc_online=None):
 if len(token)<32:raise ValueError('Use a strong pairing token')
 if rvc_root is not None:rvc_root=_rvc_roots(root,rvc_root)
 root=pathlib.Path(root);root.mkdir(parents=True,exist_ok=True);lock=threading.Lock()
 csrf=secrets.token_urlsafe(32)
 voices=PrivateVoices(master) if master is not None else None
 activity=SyncActivity()
 catalog_activity=CatalogActivity()
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*args):pass # Do not log tokens or submitted names/links.
  def respond(self,code,data):
   body=json.dumps(data).encode();self.send_response(code);
   if getattr(self,'sync_id',None):self.send_header('X-VoiceMatrix-Sync-ID',self.sync_id)
   self.send_header('Cache-Control','no-store');self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
  def authorized(self):
   if hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+token):return True
   # Opt-in only, on this loopback-bound server behind Tailscale Serve.
   # Serve strips client-supplied identity headers before injecting authenticated identity.
   login=self.headers.get('Tailscale-User-Login','')
   return bool(trusted_login and login and hmac.compare_digest(login,trusted_login))
  def do_GET(self):
   if not self.authorized():return self.respond(401,dict(error='Pairing required'))
   from tools.rvc_online_http import dispatch
   if dispatch(self,rvc_online):return
   address=urlsplit(self.path)
   if address.path=='/rvc/capabilities':
    return self.respond(200,dict(schemaVersion=1,rvcQueueConfigured=rvc_root is not None,format='rvc-v2-pth-index',nativeIPhoneRuntimeVerified=False))
   if address.path=='/rvc/status':
    if rvc_root is None:return self.respond(404,dict(error='Private RVC queue is not configured'))
    if address.query:return self.respond(400,dict(error='Invalid RVC status selection'))
    try:
     _rvc_roots(root,rvc_root)
     return self.respond(200,_rvc_status(rvc_root))
    except (OSError,ValueError,TypeError,sqlite3.Error):return self.respond(503,dict(error='Private RVC status unavailable; existing work is unchanged'))
   if address.path in ('/workflow','/workflow-log'):
    selection=parse_qs(address.query,keep_blank_values=True)
    if selection and (set(selection)!={'video'} or len(selection['video'])!=1 or not re.fullmatch(r'[A-Za-z0-9_-]{11}',selection['video'][0])):return self.respond(400,dict(error='Invalid workflow selection'))
    if address.path=='/workflow':
     try:
      result=workflow_snapshot(root/'queue.db',selection.get('video',[None])[0])
      if voices is not None:catalog_activity.refresh(voices.catalog)
      else:catalog_activity.failed()
      result['catalog']=catalog_activity.snapshot()
      return self.respond(200,result)
     except (OSError,ValueError,sqlite3.Error):return self.respond(503,dict(error='Workflow snapshot unavailable; existing queue is unchanged'))
    body=workflow_page(csrf);self.send_response(200);self.send_header('Cache-Control','no-store');self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'nonce-"+csrf+"'; style-src 'nonce-"+csrf+"'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'");self.end_headers();self.wfile.write(body);return
   if self.path=='/voice-sync' or self.path.startswith('/voice-sync/'):
    identifier=self.path[len('/voice-sync/'):] if self.path.startswith('/voice-sync/') else None
    data=activity.snapshot(identifier)
    return self.respond(200,data) if data is not None else self.respond(404,dict(error='No receipt recorded'))
   if self.path=='/sync-log':
    body=sync_page(csrf);self.send_response(200);self.send_header('Cache-Control','no-store');self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'nonce-"+csrf+"'; style-src 'nonce-"+csrf+"'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'");self.end_headers();self.wfile.write(body);return
   if self.path=='/listening':
    body=listening_page(csrf);self.send_response(200);self.send_header('Cache-Control','no-store');self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'nonce-"+csrf+"'; style-src 'nonce-"+csrf+"'; connect-src 'self'; media-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'");self.end_headers();self.wfile.write(body);return
   if self.path=='/listening/catalog' or address.path.startswith('/listening/assets/'):
    try:
     listening=ListeningReview(root,root/'queue.db')
     if self.path=='/listening/catalog':return self.respond(200,listening.catalog())
     match=re.fullmatch(r'/listening/assets/([A-Za-z0-9_-]{11})/([1-4])/([0-9]{1,2})/([a-f0-9]{64})/(reference|preview)',self.path)
     if not match:return self.respond(404,dict(error='Unknown listening asset'))
     video,attempt,index,token,kind=match.groups();data=listening.audio(video,int(attempt),int(index),token,kind)
     self.send_response(200);self.send_header('Cache-Control','no-store');self.send_header('Content-Type','audio/wav');self.send_header('Content-Length',str(len(data)));self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data);return
    except (OSError,ValueError,TypeError):return self.respond(409,dict(error='Listening audio or evidence changed; refresh before reviewing'))
   if address.path=='/review':
    selection=parse_qs(address.query,keep_blank_values=True)
    if selection and (set(selection)!={'video'} or len(selection['video'])!=1 or not re.fullmatch(r'[A-Za-z0-9_-]{11}',selection['video'][0])):return self.respond(400,dict(error='Invalid source selection'))
    body=page(csrf);self.send_response(200);self.send_header('Cache-Control','no-store');self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'nonce-"+csrf+"'; style-src 'nonce-"+csrf+"'; connect-src 'self'; media-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'");self.end_headers();self.wfile.write(body);return
   if address.path=='/inspection':
    selection=parse_qs(address.query,keep_blank_values=True)
    if set(selection)!={'video'} or len(selection['video'])!=1 or not re.fullmatch(r'[A-Za-z0-9_-]{11}',selection['video'][0]):return self.respond(400,dict(error='Invalid inspection selection'))
    identifier=selection['video'][0]
    try:return self.respond(200,read_index(root,identifier))
    except FileNotFoundError:
     state='stop-requested' if (root/'inspections'/(identifier+'.cancel')).exists() else 'inspection-requested' if (root/'inspections'/(identifier+'.json')).is_file() else 'not-requested'
     q=VideoQueue(str(root/'queue.db'))
     try:job=next((v for v in q.export()['videos'] if v['id']==identifier),None)
     finally:q.close()
     return self.respond(200,dict(status=state,videoID=identifier,queueStatus=job['status'] if job else 'missing',reason=job['reason'] if job else 'Video is not queued'))
    except (OSError,ValueError,KeyError,TypeError):return self.respond(409,dict(error='Private proposal unavailable; preserve existing review and check laptop diagnostics'))
   if address.path.startswith('/inspection/'):
    match=re.fullmatch(r'/inspection/([A-Za-z0-9_-]{11})/([a-f0-9]{64})/(clip-[0-9]+\.wav)',self.path)
    if match is None:return self.respond(404,dict(error='Unknown private preview'))
    try:data=preview(root,*match.groups())
    except (OSError,ValueError,KeyError,TypeError):return self.respond(409,dict(error='Private preview unavailable or changed'))
    self.send_response(200);self.send_header('Cache-Control','no-store');self.send_header('Content-Type','audio/wav');self.send_header('Content-Length',str(len(data)));self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data);return
   if self.path=='/voices' or self.path.startswith('/voices/'):
    self.sync_id=self.headers.get('X-VoiceMatrix-Sync-ID')
    if self.path=='/voices':
     try:self.sync_id=activity.start(self.sync_id)
     except ValueError:
      self.sync_id=None;return self.respond(400,dict(error='Invalid or reused sync ID'))
    elif self.sync_id and activity.snapshot(self.sync_id) is None:self.sync_id=None
    if voices is None:
     activity.add(self.sync_id,'failed');return self.respond(404,dict(error='Private master is not configured'))
    try:
     if self.path=='/voices':
      activity.add(self.sync_id,'validating')
      catalog=voices.catalog(progress=lambda completed,total:activity.add(self.sync_id,'validated',completed,total))
      activity.add(self.sync_id,'catalog_ready',total=len(catalog['files']),byte_count=sum(row['bytes'] for row in catalog['files']))
      self.respond(200,catalog);activity.add(self.sync_id,'catalog_sent',total=len(catalog['files']));return
     parts=self.path.split('/',3)
     if len(parts)!=4:return self.respond(404,dict(error='Unknown voice asset'))
     data=voices.file(parts[2],parts[3]);self.send_response(200)
     if self.sync_id:self.send_header('X-VoiceMatrix-Sync-ID',self.sync_id)
     self.send_header('Cache-Control','no-store');self.send_header('Content-Type','application/octet-stream');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
     activity.add(self.sync_id,'file_sent',byte_count=len(data),file_key=parts[3]);return
    except TransferError as error:
     activity.add(self.sync_id,'failed');return self.respond(error.status,dict(error='Private voice snapshot unavailable or changed; refresh the catalog'))
    except (BrokenPipeError,ConnectionResetError):activity.add(self.sync_id,'disconnected');return
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
   from tools.rvc_online_http import dispatch
   if dispatch(self,rvc_online):return
   if self.path=='/rvc/requests':
    if rvc_root is None:return self.respond(404,dict(error='Private RVC queue is not configured'))
    try:
     length=int(self.headers.get('Content-Length','0'))
     if (not 0<length<=16384 or self.headers.get('Content-Type','')!='application/json' or
         self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length',[]))!=1):raise ValueError('Invalid request body')
     body=json.loads(self.rfile.read(length))
     from tools.rvc_request import submit
     with lock:
      _rvc_roots(root,rvc_root)
      result=submit(rvc_root,body)
     return self.respond(200,result)
    except FileExistsError:return self.respond(409,dict(error='Existing private RVC scope or work was preserved'))
    except (ValueError,TypeError,KeyError,OverflowError,RecursionError):return self.respond(400,dict(error='Check the explicit RVC format, source URL and private-training permission'))
    except (OSError,sqlite3.Error):return self.respond(503,dict(error='Private RVC queue unavailable; existing work is preserved'))
   if self.path=='/requests':
    try:
     length=int(self.headers.get('Content-Length','0'))
     if not 0<length<=16384 or self.headers.get('Content-Type','')!='application/json':raise ValueError('Invalid request body')
     result=submit_candidate_request(root,json.loads(self.rfile.read(length)))
     return self.respond(200,result)
    except FileExistsError:return self.respond(409,dict(error='Existing request or prepared work was preserved; review it before changing scope'))
    except (ValueError,TypeError,KeyError,OverflowError):return self.respond(400,dict(error='Check the source URL and explicit source-use affirmation'))
   if self.path in ['/review','/inspection','/inspection/stop','/listening/decisions']:
    if not hmac.compare_digest(self.headers.get('X-VoiceMatrix-Review',''),csrf):return self.respond(403,dict(error='Reload the source review page before submitting'))
    try:
     length=int(self.headers.get('Content-Length','0'))
     if not 0<length<=512000 or self.headers.get('Content-Type','')!='application/json':raise ValueError('Invalid review request')
     action={'/review':save_initial_review,'/inspection':save_inspection,'/inspection/stop':stop_inspection,'/listening/decisions':lambda root,body:ListeningReview(root,root/'queue.db').decide(body)}[self.path]
     result=action(root,json.loads(self.rfile.read(length)));return self.respond(200,result)
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

