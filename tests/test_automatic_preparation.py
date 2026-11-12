import contextlib,hashlib,json,pathlib,shutil,subprocess,tempfile,unittest,wave
from unittest import mock
from tools.video_prepare import ReviewRequired

@unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg fixture required')
class AutomaticPreparationTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.temp.name);self.specs=self.root/'specifications';self.movie=None
  self.body=dict(schemaVersion=1,requestID='b3e5fa2b-2b08-44ba-946a-299860f2e765',videoURL='https://youtu.be/EAT0nWoEzJ8',displayName='Not an identity',sourceUse=dict(decision='approved-private-candidates',record='Synthetic original test'))
  self.analysis=dict(schemaVersion=1,engine='speechbrain-ecapa-silero',labelsVerified=False,speakerSeparated=False,candidates=[dict(start=0,end=3,group=1,uncertainty=['unreviewed-speaker-group'])],truncated=False,omitted=[])
 def tearDown(self):self.temp.cleanup()
 @contextlib.contextmanager
 def source(self,*args,**kwargs):
  with tempfile.TemporaryDirectory(dir=self.root) as directory:
   movie=pathlib.Path(directory)/'source.mp4';self.movie=movie
   subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=4','-c:a','aac',str(movie)],check=True)
   yield dict(privateMoviePath=str(movie),videoID='EAT0nWoEzJ8',sourceSHA256=hashlib.sha256(movie.read_bytes()).hexdigest(),duration=4)
 def run_prepare(self,transcribe=None,**kwargs):
  from tools.automatic_prepare import prepare
  return prepare(self.body,self.specs,analyze=lambda path,cancelled:self.analysis,transcribe=transcribe or (lambda path:'This is an original synthetic fixture.'),acquire_source=self.source,**kwargs)
 def test_real_extraction_publishes_anonymous_spec_and_removes_movie(self):
  stages=[];path=self.run_prepare(activity=lambda stage,*args:stages.append(stage));spec=json.loads(path.read_text())
  self.assertFalse(self.movie.exists());self.assertEqual(len(spec['profiles']),1);row=spec['profiles'][0]
  self.assertEqual(row['metadata']['name'],'Speaker 01 (unreviewed)');self.assertNotIn('Not an identity',row['metadata']['name'])
  self.assertTrue((self.specs/row['referenceFile']).exists());self.assertEqual(row['referenceTranscriptStatus'],'automatic-needs-review')
  self.assertFalse(spec['provenance']['identityVerified']);self.assertFalse(spec['provenance']['trainedRVC'])
  self.assertIn('temporary_media_removed',stages)
 def test_no_usable_candidates_retains_queue_review_boundary_and_cleans_movie(self):
  self.analysis['candidates']=[]
  with self.assertRaises(ReviewRequired):self.run_prepare()
  self.assertFalse(self.movie.exists());self.assertFalse((self.specs/'EAT0nWoEzJ8.json').exists())
 def test_invalid_overlap_or_duplicate_group_is_not_published(self):
  self.analysis['candidates'].append(dict(start=1,end=4,group=1,uncertainty=[]))
  with self.assertRaises(ValueError):self.run_prepare()
  self.assertFalse(self.movie.exists());self.assertFalse((self.specs/'EAT0nWoEzJ8.json').exists())
 def test_lost_owner_cannot_commit_and_does_not_touch_existing_voice(self):
  old=self.root/'Voices'/'old.wav';old.parent.mkdir();old.write_bytes(b'preserved')
  def denied(operation):raise ValueError('Lost worker ownership')
  with self.assertRaises(ValueError):self.run_prepare(commit=denied)
  self.assertFalse((self.specs/'EAT0nWoEzJ8.json').exists());self.assertEqual(old.read_bytes(),b'preserved');self.assertFalse(self.movie.exists())
 def test_cancelled_operation_cannot_publish(self):
  with self.assertRaises(InterruptedError):self.run_prepare(cancelled=lambda:True)
  self.assertFalse((self.specs/'EAT0nWoEzJ8.json').exists())
 def test_existing_spec_is_preserved(self):
  self.specs.mkdir();path=self.specs/'EAT0nWoEzJ8.json';path.write_bytes(b'existing')
  with self.assertRaises(FileExistsError):self.run_prepare()
  self.assertEqual(path.read_bytes(),b'existing')

 def test_interrupted_directory_copy_cannot_strand_a_partial_final_revision(self):
  # Simulate a filesystem interruption in the old non-atomic directory copy.
  # An atomic publication may avoid that operation altogether; either way the
  # source must produce a complete spec on this run or the next retry.
  def interrupted_copy(source,target,*args,**kwargs):
   target=pathlib.Path(target);target.mkdir()
   first=next(pathlib.Path(source).iterdir())
   (target/first.name).write_bytes(b'partial')
   raise OSError('Interrupted reference publication')
  with mock.patch('tools.automatic_prepare.shutil.copytree',side_effect=interrupted_copy):
   try:path=self.run_prepare()
   except OSError:path=None
  if path is None:path=self.run_prepare()
  spec=json.loads(path.read_text());row=spec['profiles'][0]
  saved=self.specs/row['referenceFile']
  self.assertEqual(hashlib.sha256(saved.read_bytes()).hexdigest(),row['referenceSHA256'])
  self.assertFalse(self.movie.exists())

 def test_analysis_evidence_is_retained_and_source_hash_linked(self):
  self.analysis['memberIntervals']=[dict(group=1,start=0,end=3)]
  self.analysis['privatePath']='/do/not/copy'
  spec=json.loads(self.run_prepare().read_text())
  self.assertIn('analysisEvidence',spec['provenance'])
  evidence=spec['provenance']['analysisEvidence']
  self.assertEqual(evidence['sourceSHA256'],spec['provenance']['sourceSHA256'])
  self.assertEqual(evidence['memberIntervals'],[dict(group=1,start=0,end=3)])
  self.assertNotIn('privatePath',evidence)
  self.assertFalse(evidence['cleanSpeechVerified'])
  canonical=json.dumps(evidence,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
  self.assertEqual(spec['provenance']['analysisEvidenceSHA256'],hashlib.sha256(canonical).hexdigest())

 def test_explicit_music_annotations_need_review_with_retained_evidence(self):
  self.analysis['memberIntervals']=[dict(group=1,start=0,end=3)]
  with self.assertRaises(ReviewRequired):self.run_prepare(transcribe=lambda _: '♪ These are three words ♪')
  self.assertFalse((self.specs/'EAT0nWoEzJ8.json').exists())
  proofs=list((self.specs/'candidate-reviews'/'EAT0nWoEzJ8').glob('*.json'))
  self.assertEqual(len(proofs),1)
  proof=json.loads(proofs[0].read_text())
  self.assertEqual(proof['candidateOutcomes'][0]['reason'],'explicit-non-speech-annotation')
  self.assertEqual(proof['candidateOutcomes'][0]['status'],'review-needed')
  self.assertEqual(proof['analysisEvidence']['memberIntervals'],[dict(group=1,start=0,end=3)])
  self.assertFalse(self.movie.exists())

 def test_review_artifact_obeys_owner_and_cancellation(self):
  def denied(operation):raise ValueError('Owner lost')
  with self.assertRaises(ValueError):self.run_prepare(transcribe=lambda _: '[Music] these are words',commit=denied)
  self.assertEqual(list(self.specs.rglob('*.json')),[])
  stopped=[False]
  def transcript(_):stopped[0]=True;return '[Music] these are words'
  with self.assertRaises(InterruptedError):self.run_prepare(transcribe=transcript,cancelled=lambda:stopped[0])
  self.assertEqual(list(self.specs.rglob('*.json')),[])

 def test_mixed_candidates_retain_review_needed_group_outcomes(self):
  self.analysis['candidates'].append(dict(group=2,start=1,end=4))
  self.analysis['memberIntervals']=[dict(group=1,start=0,end=3),dict(group=2,start=1,end=4)]
  def transcript(path):return '[Singing] words need review' if 'speaker-01' in path.name else 'This is a spoken test.'
  spec=json.loads(self.run_prepare(transcribe=transcript).read_text())
  self.assertEqual(len(spec['profiles']),1)
  outcomes=spec['provenance']['candidateOutcomes']
  self.assertEqual([(x['group'],x['status']) for x in outcomes],[(1,'review-needed'),(2,'eligible-unreviewed')])
  self.assertEqual(spec['provenance']['candidateCounts'],dict(total=2,eligibleUnreviewed=1,reviewNeeded=1))
  self.assertEqual(len(spec['provenance']['analysisEvidence']['memberIntervals']),2)
  self.assertFalse(spec['profiles'][0]['candidateEvidence']['suitability']['cleanSpeechVerified'])

 def test_cancel_arriving_inside_accepted_commit_does_not_publish(self):
  stopped=[False]
  def commit(operation):stopped[0]=True;operation()
  with self.assertRaises(InterruptedError):self.run_prepare(commit=commit,cancelled=lambda:stopped[0])
  self.assertFalse((self.specs/'EAT0nWoEzJ8.json').exists())

 def test_competing_final_spec_cannot_be_overwritten_at_atomic_publish(self):
  import os
  original_replace,original_link=os.replace,os.link
  output=(self.specs/'EAT0nWoEzJ8.json').resolve()
  def compete(operation):
   def wrapped(source,destination,*args,**kwargs):
    if pathlib.Path(destination)==output:output.write_bytes(b'operator-owned-spec')
    return operation(source,destination,*args,**kwargs)
   return wrapped
  with mock.patch('tools.automatic_prepare.os.replace',compete(original_replace)),mock.patch('tools.automatic_prepare.os.link',compete(original_link)):
   with self.assertRaises(FileExistsError):self.run_prepare()
  self.assertEqual(output.read_bytes(),b'operator-owned-spec')
