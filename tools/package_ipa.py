"""Package an unsigned Payload using canonical Unicode ZIP filenames."""
import argparse,unicodedata,zipfile
from pathlib import Path

def package(payload,output):
 payload=Path(payload);seen=set()
 with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as z:
  for path in sorted(payload.rglob('*')):
   name=unicodedata.normalize('NFC',str(path.relative_to(payload.parent)))
   if name in seen:raise ValueError('Canonically duplicate archive path: '+name)
   seen.add(name);z.write(path,name)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('payload');p.add_argument('output');a=p.parse_args();package(a.payload,a.output)
