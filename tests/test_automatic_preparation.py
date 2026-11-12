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
 def run_prepare(self,**kwargs):
  from tools.automatic_prepare import prepare
  return prepare(self.body,self.specs,analyze=lambda path,cancelled:self.analysis,transcribe=lambda path:'This is an original synthetic fixture.',acquire_source=self.source,**kwargs)
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
