import importlib.util,pathlib,sys,tempfile,unittest,subprocess,shutil
spec=importlib.util.spec_from_file_location('video_reference',pathlib.Path(__file__).parents[1]/'tools/video_reference.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class VideoReferenceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.retained=pathlib.Path(self.tmp.name).resolve()/"retained"
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
 def test_error_page_not_accepted_as_media_and_is_retained_for_diagnosis(self):
  touched=[]
  class FakeDownloader:
   def __init__(self,options):self.root=pathlib.Path(options['outtmpl']).parent;touched.append(self.root)
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def extract_info(self,*args,**kwargs):
    (self.root/'source.mp4').write_text('<html>Site Unavailable</html>')
    return dict(id='fixture',title='fixture',duration=10)
  with self.assertRaises(subprocess.CalledProcessError):
   with module.acquire('https://youtu.be/example',[dict(id='rick',start=0,end=5)],FakeDownloader,retention_root=self.retained):self.fail('Invalid media admitted')
  self.assertTrue(touched[0].exists())
 @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg required')
 def test_real_av_is_sliced_and_sources_retained(self):
  with tempfile.TemporaryDirectory() as temp:
   fixture=pathlib.Path(temp)/'fixture.mp4'
   subprocess.run([module.ffmpeg_path(),'-v','error','-f','lavfi','-i','color=c=purple:s=160x90:d=1','-f','lavfi','-i','sine=frequency=440:duration=1','-c:v','mpeg4','-c:a','aac','-shortest',str(fixture)],check=True,capture_output=True)
   class FakeDownloader:
    def __init__(self,options):self.root=pathlib.Path(options['outtmpl']).parent
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def extract_info(self,*args,**kwargs):
     shutil.copyfile(fixture,self.root/'source.mp4');return dict(id='fixture',title='fixture',duration=1)
   with module.acquire('https://youtu.be/example',[dict(id='rick',start=0,end=.6)],FakeDownloader,retention_root=self.retained) as result:
    path=pathlib.Path(result['segments'][0]['audioPath']);self.assertGreater(path.stat().st_size,44)
   self.assertTrue(path.exists())
 def test_split_av_fallback_and_mp4_merge_are_bounded(self):
  captured={}
  class Downloader:
   def __init__(self,options):captured.update(options)
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def extract_info(self,*args,**kwargs):return dict(id='fixture',title='fixture',duration=518)
  with tempfile.TemporaryDirectory() as temp:module.download_video('https://youtu.be/example',pathlib.Path(temp),'ffmpeg',Downloader)
  self.assertEqual(captured['format'],'best[ext=mp4][height<=480]/bestvideo[ext=mp4][height<=480][vcodec^=avc1]+bestaudio[ext=m4a][acodec^=mp4a]')
  self.assertEqual(captured['merge_output_format'],'mp4')
  self.assertEqual(captured['max_filesize'],268435456)
 def test_split_download_aggregate_bytes_cannot_exceed_limit(self):
  class Downloader:
   def __init__(self,options):self.options=options
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def extract_info(self,*args,**kwargs):
    hook=self.options['progress_hooks'][0]
    hook(dict(filename='source.f135.mp4',downloaded_bytes=700))
    hook(dict(filename='source.f135.mp4',downloaded_bytes=700))
    hook(dict(filename='source.f140.m4a',downloaded_bytes=400))
    return dict(id='fixture',title='fixture',duration=518)
  with tempfile.TemporaryDirectory() as temp:
   with self.assertRaises(ValueError):module.download_video('https://youtu.be/example',pathlib.Path(temp),'ffmpeg',Downloader,max_bytes=1024)
 def test_selected_stream_size_metadata_respects_aggregate_limit(self):
  captured={}
  class Downloader:
   def __init__(self,options):captured.update(options)
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def extract_info(self,*args,**kwargs):return dict(id='fixture',title='fixture',duration=518)
  with tempfile.TemporaryDirectory() as temp:module.download_video('https://youtu.be/example',pathlib.Path(temp),'ffmpeg',Downloader,max_bytes=1024)
  self.assertIsNotNone(captured['match_filter'](dict(duration=518,requested_formats=[dict(filesize=700),dict(filesize=400)])))
 @unittest.skipUnless(importlib.util.find_spec('yt_dlp'),'Uses installed yt-dlp selector without network')
 def test_real_selector_split_only_fixture_never_chooses_high_resolution(self):
  from yt_dlp import YoutubeDL
  captured={}
  class Downloader:
   def __init__(self,options):captured.update(options)
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def extract_info(self,*args,**kwargs):return dict(id='fixture',title='fixture',duration=518)
  with tempfile.TemporaryDirectory() as temp:module.download_video('https://youtu.be/example',pathlib.Path(temp),'ffmpeg',Downloader)
  formats=[dict(format_id='140',ext='m4a',acodec='mp4a.40.2',vcodec='none',url='https://invalid.example/audio'),dict(format_id='135',ext='mp4',height=480,acodec='none',vcodec='avc1.4D401F',url='https://invalid.example/video'),dict(format_id='137',ext='mp4',height=1080,acodec='none',vcodec='avc1.640028',url='https://invalid.example/high')]
  with YoutubeDL(dict(quiet=True)) as ydl:
   selector=ydl.build_format_selector(captured['format'])
   chosen=list(selector(dict(formats=formats,incomplete_formats=False)))
   self.assertEqual([f['format_id'] for f in chosen[0]['requested_formats']],['135','140'])
   highonly=[f for f in formats if f['format_id']!='135']
   self.assertEqual(list(selector(dict(formats=highonly,incomplete_formats=False))),[])
