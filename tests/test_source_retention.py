import contextlib,json,pathlib,shutil,subprocess,tempfile,unittest
from tools.video_reference import acquire,ffmpeg_path

@unittest.skipUnless(shutil.which('ffmpeg'),'real FFmpeg fixture')
class RetentionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=pathlib.Path(self.tmp.name).resolve();self.store=self.root/'retained';self.fixture=self.root/'fixture.mp4';self.calls=0
  subprocess.run([ffmpeg_path(),'-v','error','-f','lavfi','-i','color=c=purple:s=160x90:d=1','-f','lavfi','-i','sine=frequency=440:duration=1','-c:v','mpeg4','-c:a','aac','-shortest',str(self.fixture)],check=True,capture_output=True)
 def factory(self,options):
  owner=self
  class Downloader:
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def extract_info(self,*a,**kw):
    owner.calls+=1;shutil.copyfile(owner.fixture,pathlib.Path(options['outtmpl']).parent/'source.mp4');return dict(id='abcdefghijk',title='synthetic',duration=1)
  return Downloader()
 def acquire(self,**kw):return acquire('https://youtu.be/abcdefghijk',[dict(id='sample',start=0,end=.6)],self.factory,retention_root=self.store,**kw)
 def test_success_and_restart_reuse_without_cleanup(self):
  with self.acquire() as first:pass
  self.assertTrue(pathlib.Path(first['privateMoviePath']).is_file());self.assertTrue(pathlib.Path(first['segments'][0]['audioPath']).is_file());self.assertFalse(first['cleanupEligible'])
  with self.acquire() as second:pass
  self.assertEqual(self.calls,1);self.assertEqual(first['sourceSHA256'],second['sourceSHA256'])
 def test_consumer_failure_and_cancellation_retain_source(self):
  for error in (RuntimeError,InterruptedError):
   with self.assertRaises(error):
    with self.acquire() as result:raise error('interrupted')
   self.assertTrue(pathlib.Path(result['privateMoviePath']).is_file());self.assertTrue(pathlib.Path(result['segments'][0]['audioPath']).is_file())
 def test_corrupt_cache_is_not_silently_replaced(self):
  with self.acquire() as result:pass
  path=pathlib.Path(result['privateMoviePath']);path.write_bytes(b'corrupted')
  with self.assertRaises(ValueError):
   with self.acquire():pass
  self.assertEqual(self.calls,1);self.assertEqual(path.read_bytes(),b'corrupted')
 def test_root_required_and_symlink_rejected(self):
  with self.assertRaises(ValueError):
   with acquire('https://youtu.be/abcdefghijk',[dict(id='sample',start=0,end=.6)],self.factory):pass
  link=self.root/'linked'
  try:link.symlink_to(self.root,target_is_directory=True)
  except OSError:self.skipTest('symlinks unavailable')
  with self.assertRaises(ValueError):
   with acquire('https://youtu.be/abcdefghijk',[dict(id='sample',start=0,end=.6)],self.factory,retention_root=link):pass
 def test_failed_partial_download_retained(self):
  def bad(options):
   root=pathlib.Path(options['outtmpl']).parent
   class Downloader:
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def extract_info(self,*a,**kw):(root/'source.part').write_bytes(b'partial');raise RuntimeError('failed')
   return Downloader()
  with self.assertRaises(RuntimeError):
   with acquire('https://youtu.be/abcdefghijk',[dict(id='sample',start=0,end=.6)],bad,retention_root=self.store):pass
  self.assertEqual([p.read_bytes() for p in self.store.rglob('source.part')],[b'partial'])

 def test_quota_refusal_preserves_old_data(self):
  from unittest.mock import patch
  with self.acquire() as result:pass
  old=pathlib.Path(result['privateMoviePath']).read_bytes()
  with patch('tools.source_retention.MAX_STORE_BYTES',1),self.assertRaises(ValueError):
   with self.acquire():pass
  self.assertEqual(pathlib.Path(result['privateMoviePath']).read_bytes(),old)
 def test_concurrent_writer_denied_without_touching_source(self):
  from tools.master_voices import PublishBusy
  with self.acquire() as result:
   with self.assertRaises(PublishBusy):
    with self.acquire():pass
  self.assertTrue(pathlib.Path(result['privateMoviePath']).exists())

class LegacyRetentionGuardTests(unittest.TestCase):
 def test_legacy_worker_refuses_before_imports_or_filesystem_changes(self):
  import os,sys
  script=pathlib.Path(__file__).resolve().parents[1]/'tools'/'full_cast_video_worker.py'
  with tempfile.TemporaryDirectory() as directory:
   root=pathlib.Path(directory);sentinel=root/'source.mp4';sentinel.write_bytes(b'preserve original')
   result=subprocess.run([sys.executable,str(script)],env={**os.environ,'VOICEMATRIX_CAST_JOB':str(root)},capture_output=True,text=True)
   self.assertNotEqual(result.returncode,0)
   self.assertIn('disabled pending verified-delivery retention',result.stderr)
   self.assertEqual(sentinel.read_bytes(),b'preserve original')
   self.assertEqual([p.name for p in root.iterdir()],['source.mp4'])

class ReparseRetentionGuardTests(unittest.TestCase):
 def test_windows_reparse_attribute_is_rejected(self):
  from tools.source_retention import reject_reparse
  from types import SimpleNamespace
  with self.assertRaises(ValueError):reject_reparse(SimpleNamespace(st_mode=0o40700,st_file_attributes=0x400))
  reject_reparse(SimpleNamespace(st_mode=0o40700,st_file_attributes=0))
  reject_reparse(SimpleNamespace(st_mode=0o40700))
 @unittest.skipUnless(__import__('os').name=='nt','Windows junction integration')
 def test_junction_root_is_rejected_without_writes(self):
  from tools.source_retention import real_directory
  with tempfile.TemporaryDirectory() as directory:
   root=pathlib.Path(directory).resolve();target=root/'target';target.mkdir();link=root/'junction'
   result=subprocess.run(['cmd','/c','mklink','/J',str(link),str(target)],capture_output=True)
   if result.returncode:self.skipTest('junction creation unavailable')
   try:
    with self.assertRaises(ValueError):real_directory(link/'new-child')
    self.assertEqual(list(target.iterdir()),[])
   finally:link.rmdir()
