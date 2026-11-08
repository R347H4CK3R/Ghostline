import pathlib,sys,tempfile,threading,time,subprocess,shutil
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from tools.video_queue import VideoQueue
from tools.queue_transport import create_server
with tempfile.TemporaryDirectory() as root:
 q=VideoQueue(str(pathlib.Path(root)/'queue.db'));q.add(['https://youtu.be/SYNTHETIC03','https://youtu.be/SYNTHETIC04']);q.close()
 root=pathlib.Path(root);movie=root/'fixture.mp4'
 subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=purple:s=160x90:d=5','-f','lavfi','-i','sine=frequency=440:sample_rate=16000:duration=5','-af',"volume=volume=0:enable='not(between(t,1,2)+between(t,3,4))'",'-c:v','mpeg4','-c:a','aac','-shortest',str(movie)],check=True,capture_output=True)
 class Downloader:
  def __init__(self,o):self.root=pathlib.Path(o['outtmpl']).parent
  def __enter__(self):return self
  def __exit__(self,*args):pass
  def extract_info(self,*args,**kwargs):shutil.copyfile(movie,self.root/'source.mp4');return dict(id='SYNTHETIC03',title='Synthetic fixture',duration=5)
 def inspect_queued_fixture():
  from tools.queue_processor import run_once
  from tools.source_inspection import inspect_source
  while not (root/'inspections/SYNTHETIC03.json').exists():time.sleep(.05)
  # Use the actual owned worker once; only external acquisition is a fixture.
  run_once(root/'queue.db',root/'specifications',root,root/'Voices',model_factory=lambda:(_ for _ in ()).throw(AssertionError('No synthesis during inspection')),verify=lambda *args:{},inspection_job=lambda *args,**kw:inspect_source(*args,**kw,downloader_factory=Downloader))
 threading.Thread(target=inspect_queued_fixture,daemon=True).start()
 server=create_server(root,'s'*48)
 print(server.server_port,flush=True)
 try:server.serve_forever()
 finally:server.server_close()
