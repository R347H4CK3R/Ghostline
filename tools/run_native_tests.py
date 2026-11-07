"""Bound the complete xcodebuild test process and retain its diagnostic tail."""
import json,os,signal,subprocess,sys,time
from pathlib import Path

def run(command,log,timeout=420):
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

if __name__=='__main__':
 devices=json.loads(subprocess.check_output(['xcrun','simctl','list','devices','available','-j']))
 device=next(d['udid'] for group in devices['devices'].values() for d in group if 'iPhone' in d['name'])
 command=['xcodebuild','-project','VoiceMatrix.xcodeproj','-scheme','VoiceMatrix','-destination','platform=iOS Simulator,id='+device,'-derivedDataPath','test-build','-parallel-testing-enabled','NO','-test-timeouts-enabled','YES','-default-test-execution-time-allowance','120','-maximum-test-execution-time-allowance','180','CODE_SIGNING_ALLOWED=NO','test']
 sys.exit(run(command,'native-tests.log'))
