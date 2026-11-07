import hashlib,json,sys,tempfile,unittest,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
from prepare_studio_ipa import prepare,APP,PH,CV
from inference_fingerprint import create,NAME,verify
class StudioReleaseTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.candidate=self.root/'candidate.ipa';self.output=self.root/'approved.ipa'
  assets=[dict(path='voices/'+name+'.bin',size=1,sha256=hashlib.sha256(name.encode()).hexdigest()) for name in ['a','b']]
  voices=[dict(id=n,path=e['path'],category='Everyday Voices',engine='phonon31m',sha256=e['sha256']) for n,e in zip(['a','b'],assets)]
  self.original=dict(revision='pinned',requiresVoiceConversionChecks=True,files=assets,voices=voices)
  self.approved=dict(self.original,files=assets[:1],voices=voices[:1])
  rows=[dict(id=n,embeddingSHA256=e['sha256'],audioSHA256=n*64,audioSeconds=2.0,elapsedSeconds=1.0,nonSilentWAVDecoded=True) for n,e in zip(['a','b'],assets)]
  self.qa=dict(modelRevision='pinned',profiles=rows,conversionChecks=rows,additionalEnglishChecks=[])
  self.asr=dict(profiles=[dict(id=n,check=k,audioSHA256=n*64,wordErrorRate=0.0,rms=0.1,fullScaleSampleFraction=0.0) for n in ['a','b'] for k in ['baseline','voice-conversion']])
  provenance=json.dumps(dict(profiles=[dict(id=n) for n in ['a','b']])).encode()
  cvfiles=[dict(path='reference-provenance.json',size=len(provenance),sha256=hashlib.sha256(provenance).hexdigest())]+[dict(path='Profiles/'+n+'.json',size=2,sha256=hashlib.sha256(b'{}').hexdigest()) for n in ['a','b']]
  weights=b'original converter weights'
  cvfiles.append(dict(path='converter.mlmodelc/weights/weight.bin',size=len(weights),sha256=hashlib.sha256(weights).hexdigest()))
  with zipfile.ZipFile(self.candidate,'w') as z:
   z.writestr(PH+'manifest.json',json.dumps(self.original));z.writestr(CV+'model-manifest.json',json.dumps(dict(sourceRevision="converter",files=cvfiles)))
   z.writestr(CV+'reference-provenance.json',provenance);z.writestr(CV+'converter.mlmodelc/weights/weight.bin',weights)
   for n in ['a','b']:z.writestr(PH+'voices/'+n+'.bin',n.encode());z.writestr(CV+'Profiles/'+n+'.json',b'{}')
   z.writestr(APP+'VoiceMatrix',b'original compiled executable')
  resources=self.root/'resources'
  with zipfile.ZipFile(self.candidate) as z:
   for name in z.namelist():
    if name.startswith(PH) or name.startswith(CV):
     p=resources/name.removeprefix(APP);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(name))
  identity=create(resources,Path(__file__).parents[1]);self.qa['inferenceFingerprint']=identity['sha256']
  with zipfile.ZipFile(self.candidate,'a') as z:z.writestr(PH+NAME,(resources/'Phonon'/NAME).read_bytes())
 def tearDown(self):self.tmp.cleanup()
 def test_filter_injects_matched_proof_without_modifying_executable(self):
  prepare(self.candidate,self.output,self.approved,self.qa,self.asr)
  with zipfile.ZipFile(self.output) as z:
   self.assertEqual(z.read(APP+'VoiceMatrix'),b'original compiled executable')
   self.assertNotIn(PH+'voices/b.bin',z.namelist());self.assertNotIn(CV+'Profiles/b.json',z.namelist())
   proof=json.loads(z.read(PH+'voice-synthesis-results.json'));self.assertEqual(len(proof['conversionChecks']),1)
   verify(lambda p:z.read(APP+p),json.loads(z.read(PH+'manifest.json')),json.loads(z.read(CV+'model-manifest.json')),proof)
   cv=json.loads(z.read(CV+'model-manifest.json'))
   for e in cv['files']:self.assertEqual(hashlib.sha256(z.read(CV+e['path'])).hexdigest(),e['sha256'])
 def test_bad_converted_speech_does_not_ship_as_verified(self):
  self.asr['profiles'][1]['wordErrorRate']=.5
  with self.assertRaises(ValueError):prepare(self.candidate,self.output,self.approved,self.qa,self.asr)
 def test_wrong_native_recording_hash_is_rejected(self):
  self.asr['profiles'][1]['audioSHA256']='c'*64
  with self.assertRaises(ValueError):prepare(self.candidate,self.output,self.approved,self.qa,self.asr)

 def rewrite_candidate(self,changes):
  with zipfile.ZipFile(self.candidate) as z:contents={n:z.read(n) for n in z.namelist()}
  contents.update(changes)
  # Simulate an attacker resealing the OpenVoice inventory after changing bytes.
  cv=json.loads(contents[CV+'model-manifest.json'])
  for name,data in changes.items():
   if name.startswith(CV):
    relative=name.removeprefix(CV)
    entry=next((e for e in cv['files'] if e['path']==relative),None)
    if entry is None:entry=dict(path=relative);cv['files'].append(entry)
    entry.update(size=len(data),sha256=hashlib.sha256(data).hexdigest())
  contents[CV+'model-manifest.json']=json.dumps(cv).encode()
  with zipfile.ZipFile(self.candidate,'w') as z:
   for name,data in contents.items():z.writestr(name,data)
 def test_resealed_original_conversion_target_is_rejected(self):
  self.rewrite_candidate({CV+'Profiles/a.json':b'{"changedTarget":true}'})
  with self.assertRaisesRegex(ValueError,'inference assets'):prepare(self.candidate,self.output,self.approved,self.qa,self.asr)
 def test_resealed_converter_weights_are_rejected(self):
  self.rewrite_candidate({CV+'converter.mlmodelc/weights/weight.bin':b'changed weights'})
  with self.assertRaisesRegex(ValueError,'inference assets'):prepare(self.candidate,self.output,self.approved,self.qa,self.asr)
 def test_changed_routing_is_rejected(self):
  self.original['voices'][0]['baseVoiceID']='different'
  self.rewrite_candidate({PH+'manifest.json':json.dumps(self.original).encode()})
  with self.assertRaisesRegex(ValueError,'routing'):prepare(self.candidate,self.output,self.approved,self.qa,self.asr)
 def test_changed_approved_routing_is_rejected(self):
  self.approved['voices']=[dict(self.approved['voices'][0],baseVoiceID='different')]
  with self.assertRaises(ValueError):prepare(self.candidate,self.output,self.approved,self.qa,self.asr)
 def test_mismatched_fingerprint_is_rejected(self):
  self.qa['inferenceFingerprint']='0'*64
  with self.assertRaisesRegex(ValueError,'fingerprint'):prepare(self.candidate,self.output,self.approved,self.qa,self.asr)
 def test_missing_fingerprint_is_rejected(self):
  del self.qa['inferenceFingerprint']
  with self.assertRaisesRegex(ValueError,'fingerprint'):prepare(self.candidate,self.output,self.approved,self.qa,self.asr)
