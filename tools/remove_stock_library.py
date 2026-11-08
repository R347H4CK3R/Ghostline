"""Remove only bundled stock profiles from a staging resource directory, never app user data."""
import json
import sys
from pathlib import Path, PurePosixPath

def remove_stock(resources):
 resources=Path(resources)
 ph=resources/'Phonon'; cv=resources/'OpenVoice'
 manifest=json.loads((ph/'manifest.json').read_text())
 converter=json.loads((cv/'model-manifest.json').read_text())
 paths={v['path'] for v in manifest['voices']}
 if any(not p.startswith('voices/') or '..' in PurePosixPath(p).parts for p in paths):
  raise ValueError('Refusing unexpected profile path')
 companions={e['path'] for e in converter['files'] if e['path'].startswith('Profiles/')}
 if any('..' in PurePosixPath(p).parts for p in companions):raise ValueError('Unsafe converter profile path')
 count=len(manifest['voices'])
 for path in paths:(ph/path).unlink(missing_ok=True)
 for path in companions:(cv/path).unlink(missing_ok=True)
 manifest['voices']=[]
 manifest['files']=[e for e in manifest['files'] if e['path'] not in paths]
 converter['files']=[e for e in converter['files'] if e['path'] not in companions]
 (ph/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 (cv/'model-manifest.json').write_text(json.dumps(converter,indent=2)+'\n')
 for name in ['voice-synthesis-results.json','inference-fingerprint.json']:(ph/name).unlink(missing_ok=True)
 print(json.dumps({'removedProfiles':count,'removedConverterProfiles':len(companions),'remainingLibraryProfiles':0}))
if __name__=='__main__':remove_stock(sys.argv[1])
