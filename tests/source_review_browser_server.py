import pathlib,sys,tempfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from tools.video_queue import VideoQueue
from tools.queue_transport import create_server
with tempfile.TemporaryDirectory() as root:
 q=VideoQueue(str(pathlib.Path(root)/'queue.db'));q.add(['https://youtu.be/SYNTHETIC03']);q.close()
 server=create_server(root,'s'*48)
 print(server.server_port,flush=True)
 try:server.serve_forever()
 finally:server.server_close()
