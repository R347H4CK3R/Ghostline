import hashlib,json,pathlib,tempfile,unittest,wave
from tools.video_request import submit
from tools.queue_processor import run_once
from tools.video_queue import VideoQueue
from tools.workflow_activity import snapshot

class CandidateQueueTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name);self.specs=self.root/'specifications';self.specs.mkdir()
  submit(self.root,dict(schemaVersion=1,requestID='b3e5fa2b-2b08-44ba-946a-299860f2e765',videoURL='https://youtu.be/EAT0nWoEzJ8',displayName='',sourceUse=dict(decision='approved-private-candidates',record='Original fixture')))
 def tearDown(self):self.tmp.cleanup()
 def prepare(self,request,root,*,analyze,transcribe,activity,cancelled,commit):
  self.assertEqual(request['sourceUse']['record'],'Original fixture');self.assertTrue(callable(analyze));self.assertTrue(callable(transcribe))
  audio=root/'original.wav'
  with wave.open(str(audio),'wb') as f:f.setparams((1,2,24000,0,'NONE','not compressed'));f.writeframes(b'\x00\x10'*24000)
  spec=dict(schemaVersion=1,videoURL=request['videoURL'],profiles=[dict(referenceFile='original.wav',referenceSHA256=hashlib.sha256(audio.read_bytes()).hexdigest(),metadata=dict(id='source-fixture',name='Speaker 01 (unreviewed)',categories=['Unreviewed'],source='Original fixture',permission='Original fixture',referenceText='This is a test.'))])
  path=root/'EAT0nWoEzJ8.json';commit(lambda:path.write_text(json.dumps(spec)));return path
 def run_job(self,**kwargs):
  def verify(audio,text):return dict(passed=True,wordErrorRate=0,wavSHA256=hashlib.sha256(audio.read_bytes()).hexdigest())
  verify.transcribe=lambda audio:'Test original speech.'
  def synth(pack,text,path,model):
   with wave.open(str(path),'wb') as f:f.setparams((1,2,24000,0,'NONE','not compressed'));f.writeframes(b'\x00\x10'*24000)
  return run_once(self.root/'queue.db',self.specs,self.root/'work',self.root/'Voices',model_factory=lambda:object(),verify=verify,synthesize=synth,**kwargs)
 def test_explicit_request_prepares_without_manual_recipe_and_preserves_review(self):
  result=self.run_job(automatic_job=self.prepare,candidate_analyzer=lambda *args:None)
  self.assertEqual(result['status'],'needs-review');self.assertTrue((self.root/'Voices/source-fixture/reference.wav').exists())
  stages=[x['stage'] for x in snapshot(self.root/'queue.db','EAT0nWoEzJ8')['videos'][0]['events']]
  self.assertIn('preparation_started',stages);self.assertIn('preparation_ready',stages);self.assertEqual(stages[-1],'needs_review')
 def test_no_candidates_waits_for_new_review_without_repeating_downloads(self):
  from tools.video_prepare import ReviewRequired
  calls=[]
  def unusable(*args,**kwargs):calls.append(True);raise ReviewRequired('No usable speech candidates')
  for _ in range(2):
   result=self.run_job(automatic_job=unusable,candidate_analyzer=lambda *args:None)
   self.assertEqual(result['status'],'awaiting-preparation')
  self.assertEqual(len(calls),1)
 def test_explicit_reviewed_recipe_takes_priority_over_automatic_request(self):
  folder=self.root/'recipes';folder.mkdir();recipe=folder/'EAT0nWoEzJ8.json';recipe.write_text(json.dumps(dict(videoURL='https://youtu.be/EAT0nWoEzJ8')))
  prepared=[]
  def manual(path,root,**kwargs):
   prepared.append(True)
   return self.prepare(dict(videoURL='https://youtu.be/EAT0nWoEzJ8',sourceUse=dict(record='Original fixture')),root,analyze=lambda *args:None,**kwargs)
  def unexpected(*args,**kwargs):raise AssertionError('Automatic request ignored reviewed recipe')
  result=self.run_job(automatic_job=unexpected,candidate_analyzer=lambda *args:None,recipe_directory=folder,prepare_job=manual)
  self.assertEqual(result['status'],'needs-review');self.assertEqual(len(prepared),1)
 def test_reviewed_recipe_can_resume_after_no_automatic_candidates(self):
  from tools.video_prepare import ReviewRequired
  def unusable(*args,**kwargs):raise ReviewRequired('No usable speech candidates')
  self.assertEqual(self.run_job(automatic_job=unusable,candidate_analyzer=lambda *args:None)['status'],'awaiting-preparation')
  folder=self.root/'recipes';folder.mkdir();(folder/'EAT0nWoEzJ8.json').write_text(json.dumps(dict(videoURL='https://youtu.be/EAT0nWoEzJ8')))
  def manual(path,root,**kwargs):
   return self.prepare(dict(videoURL='https://youtu.be/EAT0nWoEzJ8',sourceUse=dict(record='Original fixture')),root,analyze=lambda *args:None,**kwargs)
  result=self.run_job(automatic_job=unusable,candidate_analyzer=lambda *args:None,recipe_directory=folder,prepare_job=manual)
  self.assertEqual(result['status'],'needs-review');self.assertTrue((self.root/'Voices/source-fixture/reference.wav').is_file())
 def test_missing_runtime_can_resume_when_configured(self):
  self.assertEqual(self.run_job()['status'],'awaiting-preparation')
  result=self.run_job(automatic_job=self.prepare,candidate_analyzer=lambda *args:None)
  self.assertEqual(result['status'],'needs-review')
 def test_missing_analyzer_pauses_explicitly_without_model_or_publication(self):
  result=self.run_job();self.assertEqual(result['status'],'awaiting-preparation');self.assertIn('speaker',result['reason'].lower());self.assertFalse((self.root/'Voices').exists())
