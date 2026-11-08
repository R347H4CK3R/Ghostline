"""Persistent local queue monitor. A configured, validated pipeline is still required."""
import argparse,ctypes,json,os,pathlib,subprocess,sys,time

if __package__:
 from .video_queue import VideoQueue
else:
 from video_queue import VideoQueue

def atomic(path,value):
 temporary=path.with_suffix('.new');temporary.write_text(json.dumps(value,indent=2),encoding='utf8');temporary.replace(path)

def gaming():
 if os.name!='nt':return False
 result=subprocess.run(['tasklist','/FO','CSV','/NH'],capture_output=True,text=True,creationflags=0x08000000,timeout=15)
 if result.returncode:return True # Do not launch expensive work if gaming state cannot be checked.
 names={line.split(',')[0].strip('"').lower() for line in result.stdout.splitlines()}
 return bool(names & {'cod.exe','cod22-cod.exe','modernwarfare.exe','fortniteclient-win64-shipping.exe','halo.exe'})

def tick(root):
 root=pathlib.Path(root);root.mkdir(parents=True,exist_ok=True)
 queue=root/'video-queue.txt';queue.touch(exist_ok=True)
 state=dict(updated=time.time(),pendingLines=0,status='waiting-for-videos',pipelineConnected=False)
 q=VideoQueue(str(root/'queue.db'))
 try:
  try:
   # Bound the input before decoding; do not ingest an unbounded dropped file.
   with queue.open('rb') as source:raw=source.read(1024*1024+1)
   if len(raw)>1024*1024:raise ValueError('Queue file too large')
   text=raw.decode('utf-8-sig')
   state['pendingLines']=sum(bool(line.strip()) and not line.lstrip().startswith('#') for line in text.splitlines())
   q.import_text(text)
  except (ValueError,UnicodeError):
   state.update(importError=True,status='queue-import-error',reason='The list could not be imported. Use one HTTPS YouTube link per line, optionally preceded by a name and a tab. No entries from this file were added.')
  videos=q.export()['videos']
 finally:q.close()
 state.update(pendingVideos=sum(v['status']=='waiting' for v in videos),
              processingVideos=sum(v['status']=='processing' for v in videos),
              completedVideos=sum(v['status']=='completed' for v in videos),
              reviewVideos=sum(v['status']=='needs-review' for v in videos),
              failedVideos=sum(v['status']=='failed' for v in videos),totalVideos=len(videos))
 if not state.get('importError') and state['pendingVideos']:
  state.update(status='waiting-for-pipeline-setup',reason='Your videos are saved in the shared queue. The video-to-native-voice pipeline is not connected yet. No processing was started.')
 try:state['gamingDetected']=gaming()
 except (OSError,subprocess.SubprocessError):
  state.update(gamingDetected=None,status='paused-game-check-unavailable',reason='Game detection is unavailable. Heavy processing remains paused.')
 if (root/'pause').exists():state['status']='paused'
 elif state.get('gamingDetected') and state['pendingVideos']:state['status']='paused-for-game'
 atomic(root/'status.json',state)
 # Only fixed messages and integer counts reach HTML, never submitted names/URLs.
 (root/'Progress.html').write_text('<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="15"><title>VoiceMatrix</title><style>body{background:#10091d;color:#eee;font:22px system-ui;padding:40px}h1{color:#bc91ff}</style><h1>VoiceMatrix Studio</h1><p>Queue monitor: running</p><p>Pending videos: '+str(state['pendingVideos'])+'</p><p>Completed videos: '+str(state['completedVideos'])+'</p><p>'+state['status'].replace('-',' ')+'</p><p>'+state.get('reason','Add or share a video list as video-queue.txt. Completed voice processing is not connected yet.')+'</p>',encoding='utf8')
 return state

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);parser.add_argument('--once',action='store_true');args=parser.parse_args()
 root=pathlib.Path(args.root);root.mkdir(parents=True,exist_ok=True)
 if os.name=='nt':
  import msvcrt
  lock=(root/'supervisor.lock').open('a+b');lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0)
  try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
  except OSError:return
  ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
 while not (root/'stop').exists():
  try:tick(root)
  except Exception as error:
   with (root/'errors.log').open('a',encoding='utf8') as log:log.write(str(time.time())+' '+str(error)+'\n')
  if args.once:break
  time.sleep(30)

if __name__=='__main__':main()
