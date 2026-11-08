"""Fail before model compilation when an input fixture is damaged or too short."""
import hashlib,json,pathlib,wave
root=pathlib.Path(__file__).resolve().parents[1]/'tests/fixtures'
for record in json.loads((root/'conversion-inputs.json').read_text())['files']:
 path=root/record['file'];data=path.read_bytes()
 assert len(data)==record['bytes'] and hashlib.sha256(data).hexdigest()==record['sha256']
 with wave.open(str(path)) as f:
  assert (f.getframerate(),f.getnchannels(),f.getsampwidth())==(24000,1,2)
  seconds=f.getnframes()/f.getframerate()
  assert .5<=seconds<=10
 print(json.dumps(dict(role=record['role'],seconds=seconds,sha256=record['sha256'])))
