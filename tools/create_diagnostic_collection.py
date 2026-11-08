"""Create one test-only, native-format conditioning profile from pinned synthetic audio."""
import hashlib,json,pathlib,wave
root=pathlib.Path(__file__).resolve().parents[1]
records=json.loads((root/'tests/fixtures/conversion-inputs.json').read_text())['files']
reference=next(x for x in records if x['role']=='reference');source=root/'tests/fixtures'/reference['file']
assert hashlib.sha256(source.read_bytes()).hexdigest()==reference['sha256']
collection=root/'tests/fixtures/DiagnosticVoices';folder=collection/'diagnostic-neutral';folder.mkdir(parents=True,exist_ok=True)
for p in (collection,folder):assert not p.is_symlink()
with wave.open(str(source)) as f:
 assert (f.getframerate(),f.getnchannels(),f.getsampwidth())==(24000,1,2)
 frames=f.readframes(f.getnframes());seconds=len(frames)/48000
output=folder/'reference.wav';assert not output.is_symlink()
with wave.open(str(output),'wb') as f:f.setparams((1,2,24000,0,'NONE','not compressed'));f.writeframes(frames)
manifest=dict(schemaVersion=1,id='diagnostic-neutral',name='Synthetic diagnostic voice',source='Neutral synthetic F5 diagnostic; source audio hash '+reference['sha256'],permission='Noncommercial test fixture, no character recording or likeness claim',referenceText=reference['text'],kind='f5-reference',engine='F5TTS_v1_Base',trainedModel=False,categories=['Original & Comedy'],referenceFile='reference.wav',referenceSHA256=hashlib.sha256(output.read_bytes()).hexdigest(),referenceBytes=output.stat().st_size,seconds=seconds)
(folder/'manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n')
(collection/'collection.json').write_text(json.dumps(dict(schemaVersion=1,voices=[dict(id='diagnostic-neutral',folder='diagnostic-neutral')]),sort_keys=True,indent=2)+'\n')
print(json.dumps(dict(testOnlyProfiles=1,referenceSHA256=manifest['referenceSHA256'],seconds=seconds)))
