import copy,hashlib,importlib.util,json,sys,tempfile,unittest,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
from prepare_expanded_release import prepare,PREFIX
class ExpandedReleaseTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.candidate=self.root/'candidate.ipa';self.output=self.root/'approved.ipa'
  assets=[dict(path='voices/'+n+'.bin',size=1,sha256=hashlib.sha256(n.encode()).hexdigest()) for n in ['a','b']]
  voices=[dict(id=n,category='International Voices',sha256=e['sha256']) for n,e in zip(['a','b'],assets)]
  self.original=dict(revision='pinned',files=assets,voices=voices)
  self.approved=dict(revision='pinned',files=assets[:1],voices=voices[:1])
  profiles=[dict(id=n,embeddingSHA256=e['sha256'],audioSHA256=n*64,nonSilentWAVDecoded=True,audioSeconds=2.0,elapsedSeconds=2.0) for n,e in zip(['a','b'],assets)]
  extras=[dict(id=n,audioSHA256=n*64) for n in ['a','b']]
  proof=dict(modelRevision='pinned',profiles=profiles,additionalEnglishChecks=extras)
  with zipfile.ZipFile(self.candidate,'w') as z:
   z.writestr(PREFIX+'manifest.json',json.dumps(self.original));z.writestr(PREFIX+'voice-synthesis-results.json',json.dumps(proof))
   z.writestr(PREFIX+'voices/a.bin',b'a');z.writestr(PREFIX+'voices/b.bin',b'b');z.writestr('Payload/VoiceMatrix.app/VoiceMatrix',b'unchanged executable')
  self.asr=dict(profiles=[dict(id='a',check=k,audioSHA256='a'*64,wordErrorRate=0.0,fullScaleSampleFraction=0.0,rms=0.1) for k in ['baseline','varied-English']])
 def tearDown(self):self.tmp.cleanup()
 def test_filter_preserves_executable_and_removes_excluded_voice(self):
  prepare(self.candidate,self.output,self.approved,self.asr)
  with zipfile.ZipFile(self.output) as z:
   self.assertEqual(z.read('Payload/VoiceMatrix.app/VoiceMatrix'),b'unchanged executable')
   self.assertNotIn(PREFIX+'voices/b.bin',z.namelist())
   self.assertEqual(json.loads(z.read(PREFIX+'manifest.json'))['voices'],self.approved['voices'])
   self.assertEqual(len(json.loads(z.read(PREFIX+'voice-synthesis-results.json'))['profiles']),1)
 def test_unintelligible_candidate_is_rejected(self):
  self.asr['profiles'][1]['wordErrorRate']=0.5
  with self.assertRaises(ValueError):prepare(self.candidate,self.output,self.approved,self.asr)
 def test_mismatched_audio_evidence_is_rejected(self):
  self.asr['profiles'][0]['audioSHA256']='c'*64
  with self.assertRaises(ValueError):prepare(self.candidate,self.output,self.approved,self.asr)
 def test_nonfinite_quality_metrics_are_rejected(self):
  self.asr['profiles'][0]['wordErrorRate']=float('nan')
  with self.assertRaises(ValueError):prepare(self.candidate,self.output,self.approved,self.asr)
