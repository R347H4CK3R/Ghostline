"""Bound the complete xcodebuild test process and retain its diagnostic tail."""
import json,os,signal,subprocess,sys,time,shutil,hashlib
from pathlib import Path

def run(command,log,timeout=1200):
 log=Path(log)
 with log.open('wb') as output:
  process=subprocess.Popen(command,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
  started=time.monotonic()
  try:
   while True:
    try: return process.wait(timeout=min(30,max(0.01,timeout-(time.monotonic()-started))))
    except subprocess.TimeoutExpired:
     if time.monotonic()-started>=timeout: break
     print('Native test process is active; elapsed seconds:',round(time.monotonic()-started),flush=True)
   print('Native test process exceeded its wall-clock deadline.',flush=True)
   try: os.killpg(process.pid,signal.SIGTERM)
   except ProcessLookupError: pass
   try: process.wait(timeout=10)
   except subprocess.TimeoutExpired:
    try: os.killpg(process.pid,signal.SIGKILL)
    except ProcessLookupError: pass
    process.wait()
   return 124
  finally:
   output.flush()
   print('\n'.join(log.read_text(errors='replace').splitlines()[-200:]),flush=True)

def find_qa_folder(root,lock):
 expected={v['id'] for v in lock['voices']}
 matches=Path(root).glob('*/data/Containers/Data/Application/*/Documents/VoiceMatrix-QA/voice-synthesis-results.json')
 for path in sorted(matches,key=lambda p:p.stat().st_mtime,reverse=True):
  try:
   report=json.loads(path.read_text())
   if report['modelRevision']==lock['revision'] and {p['id'] for p in report['profiles']}==expected and all((path.parent/(p['id']+'.wav')).stat().st_size>44 for p in report['profiles']): return path.parent
  except (OSError,ValueError,KeyError): pass
 raise FileNotFoundError('No complete QA output in simulator application data')

def collect_qa(lock):
 from assets import validate_qa_report
 try:
  source=find_qa_folder(Path.home()/'Library/Developer/CoreSimulator/Devices',lock)
  shutil.copytree(source,'qa-audio',dirs_exist_ok=True)
 except FileNotFoundError:
  result=max(Path('test-build/Logs/Test').glob('*.xcresult'),key=lambda p:p.stat().st_mtime)
  subprocess.run(['xcrun','xcresulttool','export','attachments','--path',str(result),'--output-path','qa-attachments'],check=True)
  candidates=list(Path('qa-attachments').rglob('*'))
  report=None
  for p in candidates:
   if not p.is_file() or p.stat().st_size>1000000: continue
   try:
    candidate=json.loads(p.read_text());validate_qa_report(candidate,lock);report=candidate;break
   except (OSError,ValueError,KeyError,TypeError): pass
  if report is None: raise ValueError('No complete synthesis proof in XCTest attachments')
  Path('qa-audio').mkdir(exist_ok=True)
  files={}
  for p in candidates:
   if p.is_file():
    with p.open('rb') as f: files[hashlib.file_digest(f,'sha256').hexdigest()]=p
  for profile in report['profiles']: shutil.copyfile(files[profile['audioSHA256']],Path('qa-audio')/(profile['id']+'.wav'))
  Path('qa-audio/voice-synthesis-results.json').write_text(json.dumps(report,indent=2)+'\n')
 report=json.loads(Path('qa-audio/voice-synthesis-results.json').read_text());validate_qa_report(report,lock)
 for profile in report['profiles']:
  with (Path('qa-audio')/(profile['id']+'.wav')).open('rb') as f: digest=hashlib.file_digest(f,'sha256').hexdigest()
  if digest!=profile['audioSHA256']: raise ValueError('QA WAV checksum mismatch')
 shutil.copyfile('qa-audio/voice-synthesis-results.json','voice-synthesis-results.json')
 print('Validated and retained actual WAV output for all profiles:',len(report['profiles']),flush=True)

if __name__=='__main__':
 devices=json.loads(subprocess.check_output(['xcrun','simctl','list','devices','available','-j']))
 device=next(d['udid'] for group in devices['devices'].values() for d in group if 'iPhone' in d['name'])
 command=['xcodebuild','-project','VoiceMatrix.xcodeproj','-scheme','VoiceMatrix','-destination','platform=iOS Simulator,id='+device,'-derivedDataPath','test-build','-parallel-testing-enabled','NO','-test-timeouts-enabled','YES','-default-test-execution-time-allowance','120','-maximum-test-execution-time-allowance','900','CODE_SIGNING_ALLOWED=NO','test']
 code=run(command,'native-tests.log')
 if code==0: collect_qa(json.loads(Path('models/phonon-lock.json').read_text()))
 sys.exit(code)
