"""Persistent local queue monitor. A configured, validated pipeline is still required."""
import argparse,ctypes,json,os,pathlib,subprocess,sys,time

def atomic(path,value):
 temporary=path.with_suffix('.new');temporary.write_text(json.dumps(value,indent=2),encoding='utf8');temporary.replace(path)

def gaming():
 if os.name!='nt':return False
 result=subprocess.run(['tasklist','/FO','CSV','/NH'],capture_output=True,text=True,creationflags=0x08000000,timeout=15)
 if result.returncode:return True # Do not launch expensive work if gaming state cannot be checked.
 names={line.split(',')[0].strip('"').lower() for line in result.stdout.splitlines()}
 return bool(names & {'cod.exe','cod22-cod.exe','modernwarfare.exe','fortniteclient-win64-shipping.exe','halo.exe'})

def tick(root):
 queue=root/'video-queue.txt';queue.touch(exist_ok=True)
 lines=[s.strip() for s in queue.read_text(encoding='utf-8-sig').splitlines() if s.strip() and not s.lstrip().startswith('#')]
 state=dict(updated=time.time(),pendingLines=len(lines),status='waiting-for-videos',pipelineConnected=False)
 if (root/'pause').exists():state['status']='paused'
 elif lines:
  state['status']='waiting-for-pipeline-setup'
  state['reason']='Queue monitoring is running. The video-to-native-voice pipeline is not connected yet. Links remain queued.'
 if gaming():state.update(gamingDetected=True,status='paused-for-game' if lines else 'waiting-for-videos')
 atomic(root/'status.json',state)
 # Dashboard content derives only from fixed status strings and integer counts.
 (root/'Progress.html').write_text('<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="15"><title>VoiceMatrix</title><style>body{background:#10091d;color:#eee;font:22px system-ui;padding:40px}h1{color:#bc91ff}</style><h1>VoiceMatrix Studio</h1><p>Queue monitor: running</p><p>Pending videos: '+str(len(lines))+'</p><p>'+state['status'].replace('-',' ')+'</p><p>'+state.get('reason','Add video links to video-queue.txt. Completed voice processing is not connected yet.')+'</p>',encoding='utf8')
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
