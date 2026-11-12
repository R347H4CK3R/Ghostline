import copy,hashlib,json,pathlib,shutil,subprocess,tempfile,unittest
from tools.video_queue import VideoQueue
from tools.queue_processor import run_once

class InspectionTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=pathlib.Path(self.temp.name).resolve()
  self.request=dict(schemaVersion=1,videoURL='https://youtu.be/SYNTHETIC03',decision='approved-local-inspection',reviewer='Fixture creator',record='Original synthetic AV fixture')
  folder=self.root/'inspections';folder.mkdir();self.path=folder/'SYNTHETIC03.json';self.path.write_text(json.dumps(self.request))
 def inspector(self):
  from tools import source_inspection
  return source_inspection.inspect_source
 def fixture(self):
  movie=self.root/'fixture.mp4'
  subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=purple:s=160x90:d=5','-f','lavfi','-i','sine=frequency=440:sample_rate=16000:duration=5','-af',"volume=volume=0:enable='not(between(t,1,2)+between(t,3,4))'",'-c:v','mpeg4','-c:a','aac','-shortest',str(movie)],check=True,capture_output=True)
  calls=[]
  class Downloader:
   def __init__(self,options):self.root=pathlib.Path(options['outtmpl']).parent;calls.append(self.root)
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def extract_info(self,*args,**kwargs):shutil.copyfile(movie,self.root/'source.mp4');return dict(id='SYNTHETIC03',title='Synthetic fixture',duration=5)
  return Downloader,calls
 def test_no_explicit_inspection_use_record_never_downloads(self):
  self.request['record']='';self.path.write_text(json.dumps(self.request))
  with self.assertRaises(ValueError):self.inspector()(self.path,self.root,downloader_factory=lambda _:self.fail('Unreviewed source downloaded'))
 def test_actual_audio_activity_proposals_are_unlabeled_hash_bound_and_cached(self):
  factory,calls=self.fixture();result=self.inspector()(self.path,self.root,downloader_factory=factory)
  self.assertEqual(result['status'],'needs-source-review');self.assertGreaterEqual(len(result['segments']),2)
  self.assertFalse(result['speakerSeparated']);self.assertFalse(result['likenessVerified'])
  for segment in result['segments']:
   self.assertEqual(segment['labelStatus'],'uncertain');self.assertTrue(.5<=segment['end']-segment['start']<=15)
   audio=self.root/'proposals/SYNTHETIC03'/result['revision']/segment['file'];self.assertEqual(hashlib.sha256(audio.read_bytes()).hexdigest(),segment['sha256'])
  self.assertTrue(all(path.exists() for path in calls))
  self.inspector()(self.path,self.root,downloader_factory=lambda _:self.fail('Unchanged inspection downloaded again'))
 def test_same_owned_queue_worker_inspects_without_allocating_synthesis_model(self):
  factory,calls=self.fixture();q=VideoQueue(str(self.root/'queue.db'));q.add([self.request['videoURL']])
  report=run_once(self.root/'queue.db',self.root/'specifications',self.root/'separate-work',self.root/'Voices',model_factory=lambda:self.fail('Inspection loaded F5'),verify=lambda *args:{},recipe_directory=self.root/'recipes',inspection_job=lambda *args,**kw:self.inspector()(*args,**kw,downloader_factory=factory))
  self.assertEqual(report['status'],'awaiting-preparation');self.assertEqual(q.export()['videos'][0]['attempts'],1)
  from tools.workflow_activity import snapshot
  stages=[e['stage'] for e in snapshot(self.root/'queue.db')['videos'][0]['events']]
  self.assertEqual(stages,['received','claimed','inspection_started','download_started','download_finished','media_checking','extracting','inspection_analyzing','inspection_ready','awaiting_preparation'])
  self.assertTrue((self.root/'proposals/SYNTHETIC03/index.json').is_file());self.assertFalse((self.root/'Voices').exists());q.close()
 def test_inspection_cancellation_keeps_private_master_unchanged(self):
  factory,_=self.fixture()
  with self.assertRaises(InterruptedError):self.inspector()(self.path,self.root,cancelled=lambda:True,downloader_factory=factory)
  self.assertFalse((self.root/'proposals/SYNTHETIC03/index.json').exists())

 def test_request_video_cannot_change_the_owned_job(self):
  with self.assertRaisesRegex(ValueError,'match queued video'):self.inspector()(self.path,self.root,expected_video='SYNTHETIC04',downloader_factory=lambda _:self.fail('Wrong source downloaded'))
 def test_stale_worker_cannot_publish_private_proposal_index(self):
  factory,_=self.fixture();q=VideoQueue(str(self.root/'queue.db'));q.add([self.request['videoURL']]);job=q.claim()
  def commit(operation):
   with q.db:q.db.execute('UPDATE job_control SET lease_until=0')
   q.claim()
   return q.owned_call(job['id'],job['token'],operation)
  with self.assertRaises(ValueError):self.inspector()(self.path,self.root,downloader_factory=factory,commit=commit)
  self.assertFalse((self.root/'proposals/SYNTHETIC03/index.json').exists());q.close()
 def test_reviewed_source_binding_rejects_changed_download_before_transcription(self):
  from tools.video_prepare import prepare,ReviewRequired
  from tools.source_review import save_initial_review
  factory,_=self.fixture();proposal=self.inspector()(self.path,self.root,downloader_factory=factory)
  q=VideoQueue(str(self.root/'queue.db'));q.add([self.request['videoURL']]);q.close()
  row=proposal['segments'][0]
  recipe=dict(schemaVersion=1,videoURL=self.request['videoURL'],inspectionRevision=proposal['revision'],inspectedSourceSHA256=proposal['sourceSHA256'],referenceUseReview=dict(decision='approved-local-processing',reviewer='Fixture creator',record='Original fixture'),segments=[dict(id='fixture',name='Original fixture',categories=['Original'],source='Original fixture',permission='Original fixture',start=row['start'],end=row['end'],labelStatus='original-speaker-reviewed')])
  save_initial_review(self.root,recipe)
  # A review bound to different source bytes must fail before transcription,
  # even though the real original video is now retained and reused.
  recipe_path=self.root/'recipes/SYNTHETIC03.json'
  saved=json.loads(recipe_path.read_text());saved['inspectedSourceSHA256']='0'*64;recipe_path.write_text(json.dumps(saved))
  with self.assertRaisesRegex(ReviewRequired,'Source bytes changed'):
   prepare(self.root/'recipes/SYNTHETIC03.json',self.root/'specifications',downloader_factory=factory,transcribe=lambda _:self.fail('Changed source transcribed'))
  self.assertFalse((self.root/'specifications/SYNTHETIC03.json').exists())
 def test_authenticated_preview_is_hash_bound_and_rejects_corruption(self):
  import threading,urllib.request,urllib.error
  from tools.queue_transport import create_server
  factory,_=self.fixture();proposal=self.inspector()(self.path,self.root,downloader_factory=factory)
  server=create_server(self.root,'s'*48);threading.Thread(target=server.serve_forever,daemon=True).start()
  try:
   row=proposal['segments'][0];url='http://127.0.0.1:'+str(server.server_port)+'/inspection/SYNTHETIC03/'+proposal['revision']+'/'+row['file']
   with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(url)
   self.assertEqual(e.exception.code,401)
   request=urllib.request.Request(url,headers={'Authorization':'Bearer '+'s'*48})
   with urllib.request.urlopen(request) as response:self.assertEqual(hashlib.sha256(response.read()).hexdigest(),row['sha256'])
   (self.root/'proposals/SYNTHETIC03'/proposal['revision']/row['file']).write_bytes(b'corrupt')
   with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(request)
   self.assertEqual(e.exception.code,409)
  finally:server.shutdown();server.server_close()

 def test_linked_inspection_request_parent_is_rejected_before_download(self):
  import os
  real=self.root/'real-inspections';real.mkdir();request=real/'SYNTHETIC03.json';request.write_text(json.dumps(self.request));alias=self.root/'linked-inspections'
  if os.name=='nt':subprocess.run(['cmd','/c','mklink','/J',str(alias),str(real)],check=True,capture_output=True)
  else:alias.symlink_to(real,target_is_directory=True)
  try:
   with self.assertRaises(ValueError):self.inspector()(alias/request.name,self.root,downloader_factory=lambda _:self.fail('Linked request downloaded'))
  finally:
   if os.name=='nt':alias.rmdir()
   else:alias.unlink()
