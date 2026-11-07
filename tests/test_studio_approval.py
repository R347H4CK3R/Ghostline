import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
from approve_studio_catalog import approve
class StudioApprovalTests(unittest.TestCase):
 def setUp(self):
  self.lock=dict(revision='pinned',requiresVoiceConversionChecks=True,files=[dict(path='a.json'),dict(path='b.json'),dict(path='model.bin')],voices=[dict(id=n,path=n+'.json',sha256=n*64,engine='phonon31m',category='Everyday Voices',categories=['Everyday Voices','Original Voices']) for n in ['a','b']])
  self.qa=dict(inferenceFingerprint='f'*64,modelRevision='pinned',profiles=[],conversionChecks=[],additionalEnglishChecks=[])
  self.asr=dict(inferenceFingerprint='f'*64,profiles=[])
  for name in ['a','b']:
   row=dict(id=name,embeddingSHA256=name*64,audioSHA256='c'*64,audioSeconds=1.5,elapsedSeconds=1,nonSilentWAVDecoded=True)
   self.qa['profiles'].append(row)
   self.qa['conversionChecks'].append(dict(row,file='vc-'+name+'.wav',referenceText='Test words'))
   for mode in ['baseline','voice-conversion']:
    self.asr['profiles'].append(dict(id=name,check=mode,audioSHA256='c'*64,wordErrorRate=0,rms=.1,fullScaleSampleFraction=0,passed=True))
 def test_approved_profiles_and_overlapping_categories_count_once(self):
  lock,summary=approve(self.lock,self.qa,self.asr)
  self.assertEqual(len(lock['voices']),2)
  self.assertEqual(summary['categories'],{'Everyday Voices':2,'Original Voices':2})
 def test_failed_conversion_removes_voice_and_its_asset(self):
  r=self.asr['profiles'][1];r.update(wordErrorRate=.5,passed=False)
  lock,summary=approve(self.lock,self.qa,self.asr)
  self.assertEqual([v['id'] for v in lock['voices']],['b'])
  self.assertEqual([f['path'] for f in lock['files']],['b.json','model.bin'])
 def test_missing_check_rejected(self):
  self.asr['profiles'].pop()
  with self.assertRaises(ValueError):approve(self.lock,self.qa,self.asr)
 def test_repeated_check_rejected(self):
  self.asr['profiles'].append(copy.deepcopy(self.asr['profiles'][0]))
  with self.assertRaises(ValueError):approve(self.lock,self.qa,self.asr)
 def test_changed_audio_rejected(self):
  self.asr['profiles'][0]['audioSHA256']='0'*64
  with self.assertRaises(ValueError):approve(self.lock,self.qa,self.asr)
 def test_changed_inference_rejected(self):
  self.asr['inferenceFingerprint']='0'*64
  with self.assertRaises(ValueError):approve(self.lock,self.qa,self.asr)
 def test_inconsistent_pass_flag_rejected(self):
  self.asr['profiles'][0]['wordErrorRate']=.5
  with self.assertRaises(ValueError):approve(self.lock,self.qa,self.asr)
 def test_nonfinite_measurement_rejected(self):
  self.asr['profiles'][0]['rms']=float('nan')
  with self.assertRaises(ValueError):approve(self.lock,self.qa,self.asr)
