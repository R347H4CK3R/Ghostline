import contextlib,hashlib,json,pathlib,shutil,subprocess,tempfile,unittest,threading,concurrent.futures,time,os,sys
from unittest.mock import patch
from tools import video_prepare
from tools.video_queue import VideoQueue
from tools.queue_processor import run_once
from tools.master_voices import _publish_lock
from tools.video_reference import acquire

class PreparationTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.temp.name).resolve();self.recipes=self.root/'recipes';self.recipes.mkdir();self.specs=self.root/'specs';self.specs.mkdir()
  self.recipe=dict(schemaVersion=1,videoURL='https://youtu.be/SYNTHETIC03',referenceUseReview=dict(decision='approved-local-processing',reviewer='Fixture creator',record='Original synthetic AV fixture'),segments=[dict(id='original-fixture',start=0,end=.7,labelStatus='original-speaker-reviewed',name='Original fixture',categories=['Animation','Fantasy'],source='Synthetic AV fixture',permission='Original synthetic fixture',referenceText='A reference sentence.')])
  self.path=self.recipes/'SYNTHETIC03.json';self.save()
 def save(self):self.path.write_text(json.dumps(self.recipe))
 def tearDown(self):self.temp.cleanup()
 def prepare(self,**kwargs):
  self.assertTrue(hasattr(video_prepare,'prepare'),'Video reference preparer is missing')
  return video_prepare.prepare(self.path,self.specs,**kwargs)
 def test_uncertain_label_never_downloads(self):
  self.recipe['segments'][0]['labelStatus']='uncertain';self.save()
  self.assertTrue(hasattr(video_prepare,'ReviewRequired'),'Review gate missing')
  with self.assertRaises(video_prepare.ReviewRequired):self.prepare(downloader_factory=lambda _:self.fail('Unreviewed label downloaded'))
 def test_missing_permission_record_never_downloads(self):
  self.recipe['referenceUseReview']['record']='';self.save()
  self.assertTrue(hasattr(video_prepare,'ReviewRequired'),'Review gate missing')
  with self.assertRaises(video_prepare.ReviewRequired):self.prepare(downloader_factory=lambda _:self.fail('Unreviewed source downloaded'))
 @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg required')
 def test_real_video_to_prepared_spec_and_queue_native_folder(self):
  fixture=self.root/'fixture.mp4'
  subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=purple:s=160x90:d=1','-f','lavfi','-i','sine=frequency=440:duration=1','-c:v','mpeg4','-c:a','aac','-shortest',str(fixture)],check=True,capture_output=True)
  sources=[]
  class Downloader:
   def __init__(self,options):self.root=pathlib.Path(options['outtmpl']).parent;sources.append(self.root)
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def extract_info(self,*args,**kwargs):shutil.copyfile(fixture,self.root/'source.mp4');return dict(id='SYNTHETIC03',title='Synthetic fixture',duration=1)
  self.recipe['segments'][0].pop('referenceText');self.save()
  result=self.prepare(downloader_factory=Downloader,transcribe=lambda _: 'A reference sentence.')
  self.assertTrue(result.is_file());spec=json.loads(result.read_text());row=spec['profiles'][0]
  reference=self.specs/row['referenceFile'];self.assertEqual(hashlib.sha256(reference.read_bytes()).hexdigest(),row['referenceSHA256'])
  self.assertTrue(sources[0].exists());self.assertFalse(spec['provenance']['likenessVerified'])
  q=VideoQueue(str(self.root/'queue.db'));q.add([self.recipe['videoURL']])
  def synth(pack,text,out,model):shutil.copyfile(reference,out)
  result.unlink()
  def verify(wav,text):return dict(passed=True,wordErrorRate=0,wavSHA256=hashlib.sha256(wav.read_bytes()).hexdigest())
  verify.transcribe=lambda _: 'A reference sentence.'
  prepare_job=lambda *args,**kwargs:video_prepare.prepare(*args,**kwargs,downloader_factory=Downloader)
  report=run_once(self.root/'queue.db',self.specs,self.root/'work',self.root/'Voices',model_factory=lambda:object(),synthesize=synth,verify=verify,recipe_directory=self.recipes,prepare_job=prepare_job)
  from tools.workflow_activity import snapshot
  stages=[e['stage'] for e in snapshot(self.root/'queue.db')['videos'][0]['events']]
  self.assertEqual(stages[:7],['received','claimed','preparation_started','media_checking','extracting','transcribing','preparation_ready'])
  self.assertEqual(len(sources),1) # The verified original was reused, not downloaded again.
  self.assertEqual(len(sources),1);self.assertTrue(all(p.exists() for p in sources))
  self.assertEqual(report['status'],'needs-review');self.assertTrue((self.root/'Voices/original-fixture/reference.wav').exists());q.close()
 def test_whole_pipeline_waits_then_automatically_retries_when_spec_arrives(self):
  import wave
  q=VideoQueue(str(self.root/'queue.db'));q.add([self.recipe['videoURL']]);kwargs=dict(model_factory=lambda:object(),synthesize=lambda *args:self.fail('No model before preparation'),verify=lambda *args:{})
  report=run_once(self.root/'queue.db',self.specs,self.root/'work',self.root/'Voices',**kwargs)
  self.assertEqual(report['status'],'awaiting-preparation');self.assertEqual(q.export()['videos'][0]['attempts'],1)
  audio=self.specs/'reference.wav'
  with wave.open(str(audio),'wb') as w:w.setparams((1,2,24000,0,'NONE','not compressed'));w.writeframes(b'\x00\x10'*24000)
  segment=self.recipe['segments'][0];metadata={k:segment[k] for k in ['id','name','categories','source','permission','referenceText']}
  (self.specs/'SYNTHETIC03.json').write_text(json.dumps(dict(schemaVersion=1,videoURL=self.recipe['videoURL'],profiles=[dict(referenceFile='reference.wav',referenceSHA256=hashlib.sha256(audio.read_bytes()).hexdigest(),metadata=metadata)])))
  report=run_once(self.root/'queue.db',self.specs,self.root/'work',self.root/'Voices',model_factory=lambda:object(),synthesize=lambda p,t,out,m:shutil.copyfile(audio,out),verify=lambda wav,text:dict(passed=True,wordErrorRate=0,wavSHA256=hashlib.sha256(wav.read_bytes()).hexdigest()))
  self.assertEqual(report['status'],'needs-review');self.assertEqual(report['attempt'],1);q.close()
 def test_busy_preparer_does_not_spend_quality_retries(self):
  q=VideoQueue(str(self.root/'queue.db'));q.add([self.recipe['videoURL']])
  with _publish_lock(self.specs/'.SYNTHETIC03.prepare.lock'):
   report=run_once(self.root/'queue.db',self.specs,self.root/'work',self.root/'Voices',model_factory=lambda:self.fail('Model allocated while busy'),verify=lambda *args:{},recipe_directory=self.recipes,retry_delay=0)
  self.assertEqual(report['status'],'paused');self.assertEqual(q.claim()['attempt'],1);q.close()
 def test_lost_owner_cancels_preparation_before_specification_commit(self):
  q=VideoQueue(str(self.root/'queue.db'));q.add([self.recipe['videoURL']]);started=threading.Event();observed=[]
  def prepare_job(*args,cancelled,**kwargs):
   started.set();deadline=time.monotonic()+8
   while time.monotonic()<deadline:
    if cancelled():observed.append(True);raise InterruptedError('Lost preparation owner cancelled')
    time.sleep(.01)
   self.fail('Stale preparation was not cancelled')
  with concurrent.futures.ThreadPoolExecutor(1) as pool:
   future=pool.submit(run_once,self.root/'queue.db',self.specs,self.root/'work',self.root/'Voices',model_factory=lambda:self.fail('Stale model allocated'),verify=lambda *args:{},recipe_directory=self.recipes,prepare_job=prepare_job)
   self.assertTrue(started.wait(2))
   with q.db:q.db.execute('UPDATE job_control SET lease_until=0')
   new=q.claim();self.assertEqual(new['attempt'],2)
   with self.assertRaises(ValueError):future.result(timeout=10)
  self.assertEqual(observed,[True]);self.assertEqual(q.export()['videos'][0]['status'],'processing');self.assertFalse((self.specs/'SYNTHETIC03.json').exists());q.close()
 @contextlib.contextmanager
 def child_downloader(self,fixture=None,delay=0):
  # Only external network acquisition is replaced; the real child and FFmpeg run.
  fake=self.root/'fake-downloader';fake.mkdir(exist_ok=True)
  (fake/'yt_dlp.py').write_text('import pathlib,os,shutil,time\nclass YoutubeDL:\n def __init__(self,o):self.root=pathlib.Path(o["outtmpl"]).parent\n def __enter__(self):return self\n def __exit__(self,*a):pass\n def extract_info(self,*a,**kw):\n  pathlib.Path(os.environ["VM_TEST_MARKER"]).write_text(str(self.root))\n  time.sleep(float(os.environ["VM_TEST_DELAY"]))\n  shutil.copyfile(os.environ["VM_TEST_FIXTURE"],self.root/"source.mp4")\n  return dict(id="SYNTHETIC03",title="Original synthetic fixture",duration=1)\n')
  marker=self.root/'child-root.txt';old=list(sys.path)
  values=dict(PYTHONPATH=str(fake)+os.pathsep+os.environ.get('PYTHONPATH',''),VM_TEST_MARKER=str(marker),VM_TEST_DELAY=str(delay),VM_TEST_FIXTURE=str(fixture or self.root/'unused.mp4'))
  try:
   sys.path.insert(0,str(fake))
   with patch.dict(os.environ,values):yield marker
  finally:sys.path[:]=old
 def test_real_downloader_child_has_deadline_and_retains_interrupted_download(self):
  started=time.monotonic()
  with self.child_downloader(delay=20) as marker:
   with self.assertRaises(TimeoutError):
    with acquire(self.recipe['videoURL'],self.recipe['segments'],max_download_seconds=3,retention_root=self.root/"retained-sources"):self.fail('Slow download admitted')
   self.assertTrue(marker.is_file());self.assertTrue(pathlib.Path(marker.read_text()).exists())
  self.assertLess(time.monotonic()-started,8)
 @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg required')
 def test_production_child_path_decodes_and_prepares_actual_video(self):
  fixture=self.root/'child-fixture.mp4'
  subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=purple:s=160x90:d=1','-f','lavfi','-i','sine=frequency=440:duration=1','-c:v','mpeg4','-c:a','aac','-shortest',str(fixture)],check=True,capture_output=True)
  with self.child_downloader(fixture) as marker:
   result=self.prepare();spec=json.loads(result.read_text())
   self.assertEqual(len(spec['profiles']),1);self.assertTrue(pathlib.Path(marker.read_text()).exists())
 def test_provisional_transcript_status_survives_in_native_folder(self):
  # The earlier whole pipeline checks exercise automatic ASR. This schema field
  # must never become a fabricated human approval during pack export.
  import wave
  from tools.voice_pack import export_reference_pack,validate_pack
  audio=self.root/'status.wav'
  with wave.open(str(audio),'wb') as w:w.setparams((1,2,24000,0,'NONE','not compressed'));w.writeframes(b'\x00\x10'*24000)
  m={k:self.recipe['segments'][0][k] for k in ['id','name','categories','source','permission','referenceText']};m['referenceTranscriptStatus']='automatic-needs-review'
  pack=export_reference_pack(audio,m,self.root/'status.vmpack')
  self.assertEqual(validate_pack(pack)['referenceTranscriptStatus'],'automatic-needs-review')
 def test_oversized_download_is_rejected_and_retained_before_decoding(self):
  roots=[]
  class Downloader:
   def __init__(self,o):self.root=pathlib.Path(o['outtmpl']).parent;roots.append(self.root)
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def extract_info(self,*args,**kwargs):
    (self.root/'source.mp4').write_bytes(b'x'*2048)
    return dict(id='SYNTHETIC03',title='Oversize fixture',duration=1)
  with self.assertRaisesRegex(ValueError,'byte limit'):
   with acquire(self.recipe['videoURL'],self.recipe['segments'],Downloader,max_bytes=1024,retention_root=self.root/"retained-sources"):self.fail('Oversized source admitted')
  self.assertTrue(roots[0].exists())
 @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg required')
 def test_failed_replacement_preserves_previous_specification_and_reference(self):
  fixture=self.root/'rollback-fixture.mp4'
  subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=purple:s=160x90:d=1','-f','lavfi','-i','sine=frequency=440:duration=1','-c:v','mpeg4','-c:a','aac','-shortest',str(fixture)],check=True,capture_output=True)
  with self.child_downloader(fixture):output=self.prepare()
  previous=output.read_bytes();row=json.loads(previous)['profiles'][0];reference=(self.specs/row['referenceFile']).read_bytes()
  self.recipe['segments'][0]['name']='Changed candidate';self.save()
  bad=self.root/'bad-video.mp4';bad.write_text('<html>Unavailable</html>')
  retained=next((self.root/'retained-sources').rglob('source.mp4'));retained.write_bytes(b'corrupted cached source')
  with self.child_downloader(bad):
   with self.assertRaisesRegex(ValueError,'Retained source changed'):self.prepare()
  self.assertEqual(retained.read_bytes(),b'corrupted cached source')
  self.assertEqual(output.read_bytes(),previous);self.assertEqual((self.specs/row['referenceFile']).read_bytes(),reference)
