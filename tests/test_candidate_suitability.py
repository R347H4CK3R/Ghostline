import copy,hashlib,json,math,tempfile,pathlib,unittest,os
from tools import automatic_prepare

class SuitabilityTests(unittest.TestCase):
 def helper(self,name):
  self.assertTrue(callable(getattr(automatic_prepare,name,None)),name+' must be implemented')
  return getattr(automatic_prepare,name)
 def analysis(self):return dict(schemaVersion=1,engine='speechbrain-ecapa-silero',labelsVerified=False,speakerSeparated=False,durationSeconds=10,candidates=[dict(group=1,start=0,end=3)],memberIntervals=[dict(group=1,start=0,end=3)],truncated=False)
 def evidence(self,a):return self.helper('analysis_evidence')(a,'a'*64,'EAT0nWoEzJ8',10,10)
 def test_bounds_accept_32_groups_and_512_unique_intervals(self):
  a=self.analysis();a['durationSeconds']=1800;a['candidates']=[dict(group=i,start=0,end=3) for i in range(1,33)]
  a['memberIntervals']=[dict(group=i%32+1,start=i*3,end=i*3+3) for i in range(512)]
  result=self.helper('analysis_evidence')(a,'a'*64,'EAT0nWoEzJ8',1800,1800)
  self.assertEqual(len(result['memberIntervals']),512);self.assertEqual(len(result['candidates']),32)
  a['memberIntervals'].append(dict(group=1,start=1600,end=1603))
  with self.assertRaises(ValueError):self.helper('analysis_evidence')(a,'a'*64,'EAT0nWoEzJ8',1800,1800)
  a=self.analysis();a['candidates']=[dict(group=i,start=0,end=3) for i in range(1,34)]
  with self.assertRaises(ValueError):self.evidence(a)
 def test_bad_intervals_rejected(self):
  for interval in [dict(group=True,start=0,end=3),dict(group=2,start=0,end=3),dict(group=1,start=float('nan'),end=3),dict(group=1,start=0,end=float('inf')),dict(group=1,start=False,end=3),dict(group=1,start=-1,end=3),dict(group=1,start=8,end=11),dict(group=1,start=7.01,end=10.01)]:
   with self.subTest(interval=interval):
    a=self.analysis();a['memberIntervals']=[interval]
    with self.assertRaises(ValueError):self.evidence(a)
  a=self.analysis();a['memberIntervals']*=2
  with self.assertRaises(ValueError):self.evidence(a)
 def test_source_and_measured_durations_are_bound(self):
  for duration in (True,float('nan'),9,11):
   a=self.analysis();a['durationSeconds']=duration
   with self.assertRaises(ValueError):self.evidence(a)
  with self.assertRaises(ValueError):self.helper('analysis_evidence')(self.analysis(),'bad','EAT0nWoEzJ8',10,10)
  with self.assertRaises(ValueError):self.helper('analysis_evidence')(self.analysis(),'a'*64,'EAT0nWoEzJ8',5,10)
 def test_projection_does_not_copy_private_unknown_fields(self):
  a=self.analysis();a['token']='private';a['memberIntervals'][0]['path']='/private'
  e=self.evidence(a);self.assertNotIn('private',json.dumps(e));self.assertFalse(e['cleanSpeechVerified']);self.assertFalse(e['overlapAssessed'])
 def test_transcript_annotation_cases_are_review_flags_not_music_claims(self):
  for text in ('♪ some audible words here ♪','♫ some audible words here','[Music] some audible words here','some words [applause] end','(singing softly) some audible words here','â™ª some audible words here'):
   with self.subTest(text=text):
    out=self.helper('screen_transcript')(text);self.assertEqual(out['status'],'review-needed');self.assertEqual(out['reason'],'explicit-non-speech-annotation');self.assertFalse(out['cleanSpeechVerified'])
 def test_no_annotation_never_claims_clean_and_counts_are_recorded(self):
  out=self.helper('screen_transcript')('These are three words.')
  self.assertEqual(out['wordCount'],4);self.assertEqual(out['characterCount'],22)
  self.assertEqual(out['status'],'eligible-unreviewed');self.assertFalse(out['cleanSpeechVerified'])
  for text in (None,'one two','x'*3001):
   self.assertEqual(self.helper('screen_transcript')(text)['status'],'review-needed')
 def test_missing_declared_duration_is_not_invented(self):
  evidence=self.helper('analysis_evidence')(self.analysis(),'a'*64,'EAT0nWoEzJ8',None,10)
  self.assertIsNone(evidence['declaredSourceDurationSeconds'])
  self.assertEqual(evidence['decodedDurationSeconds'],10)

 def test_source_padding_tolerated_but_material_mismatch_rejected(self):
  self.helper('analysis_evidence')(self.analysis(),'a'*64,'EAT0nWoEzJ8',10.03,10)
  self.helper('analysis_evidence')(self.analysis(),'a'*64,'EAT0nWoEzJ8',9.99,10)
  a=self.analysis();a['candidates']=[dict(group=1,start=7,end=10)];a['memberIntervals']=[dict(group=1,start=7,end=10)]
  evidence=self.helper('analysis_evidence')(a,'a'*64,'EAT0nWoEzJ8',9.1,10)
  self.assertEqual(evidence['decodedDurationSeconds'],10)
  self.assertEqual(evidence['declaredSourceDurationSeconds'],9.1)
  with self.assertRaises(ValueError):self.helper('analysis_evidence')(self.analysis(),'a'*64,'EAT0nWoEzJ8',15,10)

class ReviewArtifactTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=pathlib.Path(self.temp.name)
  self.evidence=dict(sourceSHA256='a'*64,memberIntervals=[],cleanSpeechVerified=False)
  self.outcomes=[dict(group=1,status='review-needed',reason='explicit-non-speech-annotation')]
 def save(self,**kwargs):
  return automatic_prepare._review_artifact(self.root,'EAT0nWoEzJ8','b3e5fa2b-2b08-44ba-946a-299860f2e765',self.evidence,self.outcomes,kwargs.get('cancelled',lambda:False),kwargs.get('commit'))
 def test_content_hash_idempotence_and_new_revision(self):
  path=self.save();before=path.read_bytes();self.assertEqual(path.stem,hashlib.sha256(before).hexdigest())
  self.assertEqual(path,self.save());self.assertEqual(path.read_bytes(),before)
  self.outcomes[0]['reason']='insufficient-transcribed-speech';other=self.save()
  self.assertNotEqual(path,other);self.assertEqual(path.read_bytes(),before)
 def test_existing_conflict_preserved(self):
  path=self.save();path.write_bytes(b'existing changed by operator')
  with self.assertRaises(FileExistsError):self.save()
  self.assertEqual(path.read_bytes(),b'existing changed by operator')
 @unittest.skipIf(os.name=='nt','Creating symlinks can require Windows elevation')
 def test_linked_parent_and_destination_rejected(self):
  outside=self.root/'outside';outside.mkdir();(self.root/'candidate-reviews').symlink_to(outside,target_is_directory=True)
  with self.assertRaises(ValueError):self.save()
  (self.root/'candidate-reviews').unlink();path=self.save();path.unlink();target=self.root/'target';target.write_bytes(b'preserve');path.symlink_to(target)
  with self.assertRaises(ValueError):self.save()
  self.assertEqual(target.read_bytes(),b'preserve')
 def test_cancel_at_owned_operation_prevents_any_final_artifact(self):
  stopped=[False]
  def commit(operation):stopped[0]=True;operation()
  with self.assertRaises(InterruptedError):self.save(cancelled=lambda:stopped[0],commit=commit)
  self.assertEqual(list(self.root.rglob('*.json')),[])
 @unittest.skipIf(os.name=='nt','Creating symlinks can require Windows elevation')
 def test_racing_linked_destination_is_not_accepted_as_existing_evidence(self):
  import os
  from unittest import mock
  path=self.save();data=path.read_bytes();path.unlink();target=self.root/'external';target.write_bytes(data)
  def competing_link(source,destination):pathlib.Path(destination).symlink_to(target);raise FileExistsError()
  with mock.patch('tools.automatic_prepare.os.link',competing_link):
   with self.assertRaises((ValueError,FileExistsError)):self.save()
  self.assertEqual(target.read_bytes(),data)
