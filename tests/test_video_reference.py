import importlib.util,pathlib,sys,tempfile,unittest,subprocess,shutil
spec=importlib.util.spec_from_file_location('video_reference',pathlib.Path(__file__).parents[1]/'tools/video_reference.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class VideoReferenceTests(unittest.TestCase):
 def test_non_youtube_and_credential_urls_rejected(self):
  for url in ['file:///tmp/source','https://youtube.com.evil.test/video','https://user:secret@youtube.com/watch?v=test','http://youtube.com/watch?v=test']:
   with self.assertRaises(ValueError):module.validate_request(url,[dict(id='rick',start=0,end=5)])
 def test_invalid_segments_rejected(self):
  for segment in [dict(id='../rick',start=0,end=5),dict(id='rick',start=-1,end=5),dict(id='rick',start=5,end=0),dict(id='rick',start=0,end=16),dict(id='rick',start=float('nan'),end=5)]:
   with self.assertRaises(ValueError):module.validate_request('https://youtu.be/example',[segment])
 def test_duplicates_and_empty_segments_rejected(self):
  row=dict(id='rick',start=0,end=5)
  for rows in [[],[row,row]]:
   with self.assertRaises(ValueError):module.validate_request('https://youtu.be/example',rows)
 @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg required')
 def test_error_page_not_accepted_as_media_and_is_deleted(self):
  touched=[]
  class FakeDownloader:
   def __init__(self,options):self.root=pathlib.Path(options['outtmpl']).parent;touched.append(self.root)
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def extract_info(self,*args,**kwargs):
    (self.root/'source.mp4').write_text('<html>Site Unavailable</html>')
    return dict(id='fixture',title='fixture',duration=10)
  with self.assertRaises(subprocess.CalledProcessError):
   with module.acquire('https://youtu.be/example',[dict(id='rick',start=0,end=5)],FakeDownloader):self.fail('Invalid media admitted')
  self.assertFalse(touched[0].exists())
 @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg required')
 def test_real_av_is_sliced_and_temporary_sources_removed(self):
  with tempfile.TemporaryDirectory() as temp:
   fixture=pathlib.Path(temp)/'fixture.mp4'
   subprocess.run([module.ffmpeg_path(),'-v','error','-f','lavfi','-i','color=c=purple:s=160x90:d=1','-f','lavfi','-i','sine=frequency=440:duration=1','-c:v','mpeg4','-c:a','aac','-shortest',str(fixture)],check=True,capture_output=True)
   class FakeDownloader:
    def __init__(self,options):self.root=pathlib.Path(options['outtmpl']).parent
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def extract_info(self,*args,**kwargs):
     shutil.copyfile(fixture,self.root/'source.mp4');return dict(id='fixture',title='fixture',duration=1)
   with module.acquire('https://youtu.be/example',[dict(id='rick',start=0,end=.6)],FakeDownloader) as result:
    path=pathlib.Path(result['segments'][0]['audioPath']);self.assertGreater(path.stat().st_size,44)
   self.assertFalse(path.exists())
