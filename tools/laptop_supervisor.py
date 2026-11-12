"""Persistent local queue monitor. A configured, validated pipeline is still required."""
from urllib.parse import urlsplit,urlunsplit,quote
import re
import argparse,ctypes,json,os,pathlib,subprocess,sys,time,html
from tools.video_queue import VideoQueue,video_id

def atomic(path,value):
 temporary=path.with_suffix('.new');temporary.write_text(json.dumps(value,indent=2),encoding='utf8');temporary.replace(path)

def gaming():
 if os.name!='nt':return False
 result=subprocess.run(['tasklist','/FO','CSV','/NH'],capture_output=True,text=True,creationflags=0x08000000,timeout=15)
 if result.returncode:return True # Do not launch expensive work if gaming state cannot be checked.
 names={line.split(',')[0].strip('"').lower() for line in result.stdout.splitlines()}
 return bool(names & {'cod.exe','cod22-cod.exe','modernwarfare.exe','fortniteclient-win64-shipping.exe','halo.exe'})

def queue_rows(q):
 q.db.execute('CREATE TABLE IF NOT EXISTS names (video_id TEXT PRIMARY KEY,name TEXT NOT NULL)')
 names=dict(q.db.execute('SELECT video_id,name FROM names'));rows=q.export()['videos']
 for row in rows:row['name']=names.get(row['id'],'')
 return rows

def database_snapshot(root):
 q=VideoQueue(str(root/'queue.db'))
 try:return queue_rows(q)
 finally:q.close()

def queue_snapshot(root):
 path=root/'video-queue.txt'
 if path.is_symlink():raise ValueError('The pending text file cannot be a symbolic link')
 path.touch(exist_ok=True)
 if path.stat().st_size>1048576:raise ValueError('Pending text exceeds 1 MiB; entries were retained')
 raw=path.read_bytes();text=raw.decode('utf-8-sig');incoming={}
 for line in text.splitlines():
  if not line.strip() or (line.lstrip().startswith('#') and '\t' not in line):continue
  name,url=line.rsplit('\t',1) if '\t' in line else ('',line)
  identifier=video_id(url.strip());name=name.strip()
  if len(name)>1000:raise ValueError('A pending name exceeds 1000 characters')
  incoming[identifier]=(name,url.strip())
 q=VideoQueue(str(root/'queue.db'))
 try:
  q.add([row[1] for row in incoming.values()],record_duplicates=False)
  with q.db:
   q.db.execute('CREATE TABLE IF NOT EXISTS names (video_id TEXT PRIMARY KEY,name TEXT NOT NULL)')
   for identifier,(name,url) in incoming.items():
    if name:q.db.execute("INSERT INTO names VALUES (?,?) ON CONFLICT(video_id) DO UPDATE SET name=excluded.name WHERE names.name=''",(identifier,name))
  videos=queue_rows(q)
  additions=[]
  for row in videos:
   if row['id'] not in incoming:
    # Append only: comments, user edits and review/failed links are never erased.
    label=' '.join(row['name'].split())
    additions.append(label+'\thttps://youtu.be/'+row['id']+'\n')
  if additions:
   suffix=(('\n' if raw and not raw.endswith((b'\n',b'\r')) else '')+''.join(additions)).encode('utf8')
   if len(raw)+len(suffix)>1048576:raise ValueError('Pending mirror is full; all links remain in the database')
   # Single monitor writer; a concurrent external edit is detected before append.
   if path.read_bytes()!=raw:raise ValueError('Pending text changed during sync; retrying next poll')
   with path.open('ab') as f:f.write(suffix);f.flush();os.fsync(f.fileno())
  return videos
 finally:q.close()

def review_url(root):
 try:
  path=root/'LaptopSettings.json'
  if path.is_symlink() or not path.is_file() or path.stat().st_size>16384:return None
  settings=json.loads(path.read_text(encoding='utf-8-sig'))
  if not isinstance(settings,dict) or not isinstance(settings.get('url'),str):return None
  if set(settings)!={'url','authentication'} or settings['authentication']!='tailscale-same-account':return None
  raw=settings['url']
  if '\\' in raw or any(ord(c)<33 or ord(c)==127 for c in raw):return None
  parsed=urlsplit(raw)
  if parsed.scheme!='https' or not (parsed.hostname or '').endswith('.ts.net') or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/'):return None
  host=parsed.hostname
  if len(host)>253 or not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+ts\.net',host):return None
  port=parsed.port
  if port is not None and not 1<=port<=65535:return None
  return urlunsplit(('https',host+(':'+str(port) if port is not None else ''),'/review','',''))
 except (OSError,ValueError,TypeError,KeyError):return None

def tick(root):
 state=dict(updated=time.time(),pendingLines=0,status='waiting-for-videos',pipelineConnected=False,videos=[])
 try:
  state['videos']=queue_snapshot(root);state['pendingLines']=len(state['videos'])
  if state['videos']:state['status']='queue-active'
 except (ValueError,UnicodeError,OSError) as error:
  rows=database_snapshot(root)
  state.update(status='queue-input-error',reason=str(error),videos=rows,pendingLines=len(rows))
 if (root/'pause').exists():state['status']='paused'
 if gaming():state.update(gamingDetected=True,status='paused-for-game' if state['pendingLines'] else state['status'])
 review=review_url(root)
 if review:
  state['sourceReviewURL']=review
  state['workflowLogURL']=review.rsplit('/',1)[0]+'/workflow-log'
 atomic(root/'status.json',state)
 rows=[]
 for row in state['videos']:
  cells=[row.get('name') or row['id'],row['status'],str(round(row['progress']*100))+'%',str(row['attempts'])+'/4',row.get('reason','')]
  action='Separate recovery / replacement review required'
  if row['status'] in ['waiting','awaiting-preparation','paused']:
   if (root/'recipes'/(row['id']+'.json')).exists() or (root/'specifications'/(row['id']+'.json')).exists():action='Review saved'
   elif review:action='<a href="'+html.escape(review+'?video='+quote(row['id']),quote=True)+'" target="_blank" rel="noopener noreferrer">Review source</a>'
   else:action='Review connection is not configured'
  rows.append('<tr>'+''.join('<td>'+html.escape(str(c))+'</td>' for c in cells)+'<td>'+action+'</td></tr>')
 page='<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="15"><title>VoiceMatrix</title><style>body{background:#10091d;color:#eee;font:20px system-ui;padding:32px}h1{color:#bc91ff}td,th{text-align:left;padding:12px;border-bottom:1px solid #65437c}table{width:100%}</style><h1>VoiceMatrix Studio</h1><p>'+html.escape(state['status'].replace('-',' '))+'</p><p>'+html.escape(state.get('reason','Prepared references and reviewed recipes process automatically. Raw links still need source review.'))+'</p><p>Queued videos: '+str(state['pendingLines'])+'</p><table><tr><th>Voice / video</th><th>Stage</th><th>Progress</th><th>Attempt</th><th>Reason</th><th>Source review</th></tr>'+''.join(rows)+'</table><p>Listening review is separate from audio checks. No links are cleared by this monitor.</p>'
 if review:page+='<p><a href="'+html.escape(state['workflowLogURL'],quote=True)+'" target="_blank" rel="noopener noreferrer">Open live video workflow log</a></p>'
 (root/'Progress.html').write_text(page,encoding='utf8')
 return state

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);parser.add_argument('--once',action='store_true');args=parser.parse_args()
 root=pathlib.Path(args.root);root.mkdir(parents=True,exist_ok=True)
 if os.name=='nt':
  import msvcrt
  lock=(root/'supervisor.lock').open('a+b');lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0)
  try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
  except OSError:return
  from tools.companion_runtime import lower_priority
  lower_priority()
 while not (root/'stop').exists():
  try:tick(root)
  except Exception as error:
   with (root/'errors.log').open('a',encoding='utf8') as log:log.write(str(time.time())+' '+str(error)+'\n')
  if args.once:break
  time.sleep(30)

if __name__=='__main__':main()

