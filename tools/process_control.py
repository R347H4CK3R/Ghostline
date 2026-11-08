"""Cancellable, bounded subprocesses shared by acquisition and recognition."""
import subprocess,time,os,signal

def checked_process(command,*,timeout,cancelled):
 group=dict(creationflags=subprocess.CREATE_NEW_PROCESS_GROUP) if os.name=='nt' else dict(start_new_session=True)
 with subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**group) as process:
  deadline=time.monotonic()+timeout
  try:
   while True:
    if cancelled():raise InterruptedError('Processing paused during media processing')
    if time.monotonic()>=deadline:raise TimeoutError('Media processing timed out')
    try:
     stdout,stderr=process.communicate(timeout=.2)
     if process.returncode:raise subprocess.CalledProcessError(process.returncode,command,stdout,stderr)
     return
    except subprocess.TimeoutExpired:pass
  finally:
   if process.poll() is None:
    if os.name=='nt':subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=3)
    else:
     try:os.killpg(process.pid,signal.SIGTERM)
     except ProcessLookupError:pass
    try:process.wait(timeout=2)
    except subprocess.TimeoutExpired:
     if os.name=='nt':process.kill()
     else:
      try:os.killpg(process.pid,signal.SIGKILL)
      except ProcessLookupError:pass
     process.wait(timeout=3)
