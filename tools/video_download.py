"""Private downloader child; its parent enforces the overall deadline/cancellation."""
import json,pathlib,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from tools.video_reference import download_video

if __name__=='__main__':
 url,root,ff,duration,size=sys.argv[1:]
 result=download_video(url,pathlib.Path(root),ff,max_duration=float(duration),max_bytes=int(size))
 (pathlib.Path(root)/'download-metadata.json').write_text(json.dumps(result),encoding='utf8')
