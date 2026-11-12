import json,pathlib,tempfile,unittest,wave,hashlib,time,sys,weakref,gc
from tools.video_queue import VideoQueue
from tools import queue_processor

class ProcessorTests(unittest.TestCase):
 def test_idle_model_cache_reuses_then_releases_heavy_reference(self):
  self.assertTrue(hasattr(queue_processor,'LazyModel'),'Releasable model cache is missing')
  class Resource:pass
  allocations=[]
  def factory():allocations.append(True);return Resource()
  cache=queue_processor.LazyModel(factory);model=cache();reference=weakref.ref(model)
  self.assertIs(cache(),model);del model;cache.release();gc.collect()
  self.assertIsNone(reference());cache();self.assertEqual(len(allocations),2)
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name);self.specs=self.root/'specs';self.specs.mkdir()
  self.q=VideoQueue(str(self.root/'queue.db'));self.q.add(['https://youtu.be/EAT0nWoEzJ8'])
  self.audio=self.specs/'reference.wav'
  with wave.open(str(self.audio),'wb') as w:w.setparams((1,2,24000,0,'NONE','not compressed'));w.writeframes(b'\x00\x10'*24000)
  self.spec=dict(schemaVersion=1,videoURL='https://youtu.be/EAT0nWoEzJ8',profiles=[dict(referenceFile='reference.wav',referenceSHA256=hashlib.sha256(self.audio.read_bytes()).hexdigest(),metadata=dict(id='synthetic-original',name='Original fixture',categories=['Animation','Fantasy'],source='Synthetic fixture',permission='Original synthetic fixture',referenceText='A reference sentence.'))])
  self.path=self.specs/'EAT0nWoEzJ8.json';self.path.write_text(json.dumps(self.spec))
 def tearDown(self):self.q.close();self.tmp.cleanup()
 def run_job(self,**kwargs):
  self.assertTrue(hasattr(queue_processor,'run_once'),'Prepared queue processor is missing')
  verify=kwargs.pop('verify',lambda wav,text:dict(passed=True,wordErrorRate=0,wavSHA256=hashlib.sha256(wav.read_bytes()).hexdigest()))
  return queue_processor.run_once(self.root/'queue.db',self.specs,self.root/'work',self.root/'Voices',model_factory=lambda:object(),synthesize=self.synth,verify=verify,retry_delay=0,**kwargs)
 def synth(self,pack,text,out,model):
  # Only neural inference is substituted. Packs, queue, files and publisher are real.
  with wave.open(str(out),'wb') as w:w.setparams((1,2,24000,0,'NONE','not compressed'));w.writeframes(b'\x00\x08'*24000)
  return dict(file=str(out))
 def test_workflow_tracks_actual_stages_without_claiming_completion(self):
  from tools.workflow_activity import snapshot
  self.run_job()
  stages=[e['stage'] for e in snapshot(self.root/'queue.db')['videos'][0]['events']]
  self.assertEqual(stages,['received','claimed','references_checking','model_loading','synthesizing','audio_checking','words_checking','publishing','needs_review'])
 def test_failed_synthesis_has_no_later_checks_or_publication_event(self):
  from tools.workflow_activity import snapshot
  def fail(*args):raise RuntimeError('private voice path and transcript')
  self.synth=fail;self.run_job()
  snapshot=snapshot(self.root/'queue.db');events=snapshot['videos'][0]['events']
  self.assertEqual([e['stage'] for e in events][-2:],['synthesizing','retry'])
  self.assertNotIn('private voice',json.dumps(snapshot))
 def test_real_pack_and_native_folder_publish_but_job_waits_for_review(self):
  r=self.run_job();self.assertEqual(r['status'],'needs-review')
  self.assertEqual(r['profiles'][0]['id'],'synthetic-original')
  self.assertFalse(r['physicalDeviceVerified']);self.assertFalse(r['likenessVerified'])
  self.assertTrue((self.root/'Voices/synthetic-original/reference.wav').exists())
  self.assertEqual(self.q.export()['videos'][0]['status'],'needs-review')
  self.assertEqual(len(self.q.export()['videos']),1)
 def test_missing_spec_keeps_job_for_review_without_allocating_model(self):
  self.path.unlink();r=self.run_job();self.assertEqual(r['status'],'awaiting-preparation')
  self.assertIn('prepared',r['reason'].lower());self.assertFalse((self.root/'Voices').exists())
 def test_changed_reference_hash_fails_without_publishing(self):
  self.spec['profiles'][0]['referenceSHA256']='0'*64;self.path.write_text(json.dumps(self.spec))
  r=self.run_job();self.assertEqual(r['status'],'retry');self.assertFalse((self.root/'Voices').exists())
 def test_failed_wordcheck_does_not_publish_and_stops_after_four_attempts(self):
  original=self.synth
  def failure(*args):raise ValueError('Independent generated-word check failed')
  self.synth=failure
  for _ in range(4):r=self.run_job()
  self.assertEqual(r['status'],'failed');self.assertIn('Independent',r['reason'])
  self.assertIsNone(self.run_job());self.assertFalse((self.root/'Voices').exists())
 def test_game_pause_does_not_claim_or_allocate(self):
  self.assertIsNone(self.run_job(paused=lambda:True));self.assertEqual(self.q.export()['videos'][0]['attempts'],0)
 def test_path_traversal_is_rejected(self):
  self.spec['profiles'][0]['referenceFile']='../outside.wav';self.path.write_text(json.dumps(self.spec))
  self.assertEqual(self.run_job()['status'],'retry');self.assertFalse((self.root/'Voices').exists())
 def test_pause_after_inference_resumes_same_attempt_without_publishing(self):
  paused=[False];original=self.synth
  def synth(*args):original(*args);paused[0]=True
  self.synth=synth
  r=self.run_job(paused=lambda:paused[0]);self.assertEqual(r['status'],'paused')
  self.assertFalse((self.root/'Voices').exists())
  self.synth=original;paused[0]=False;r=self.run_job()
  self.assertEqual(r['status'],'needs-review');self.assertEqual(r['attempt'],1)
 def test_failed_recognition_result_is_retained_and_does_not_publish(self):
  r=self.run_job(verify=lambda wav,text:dict(passed=False,wordErrorRate=.25,wavSHA256=hashlib.sha256(wav.read_bytes()).hexdigest()))
  self.assertEqual(r['status'],'retry');self.assertEqual(r['profiles'][0]['wordcheck']['wordErrorRate'],.25)
  self.assertFalse((self.root/'Voices').exists())
 def test_expired_owner_cannot_enter_publication(self):
  original=self.synth
  def synth(*args):
   original(*args)
   with self.q.db:self.q.db.execute('UPDATE job_control SET lease_until=0')
  self.synth=synth
  with self.assertRaises(ValueError):self.run_job()
  self.assertFalse((self.root/'Voices').exists())
 def test_cancelled_recognizer_child_is_stopped(self):
  start=time.monotonic()
  with self.assertRaises(InterruptedError):
   queue_processor.checked_process([sys.executable,'-c','import time;time.sleep(20)'],timeout=30,cancelled=lambda:True)
  self.assertLess(time.monotonic()-start,5)

if __name__=='__main__':unittest.main()

