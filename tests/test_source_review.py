import copy,json,pathlib,re,tempfile,threading,unittest,urllib.request,urllib.error
from tools.queue_transport import create_server
from tools.video_queue import VideoQueue

class SourceReviewTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=pathlib.Path(self.temp.name)
  q=VideoQueue(str(self.root/'queue.db'));q.add(['https://youtu.be/SYNTHETIC03']);q.close()
  self.server=create_server(self.root,'s'*48);self.addCleanup(self.server.server_close)
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.addCleanup(self.server.shutdown)
  self.url='http://127.0.0.1:'+str(self.server.server_port)
  self.recipe=dict(schemaVersion=1,videoURL='https://youtu.be/SYNTHETIC03',referenceUseReview=dict(decision='approved-local-processing',reviewer='Fixture creator',record='Original synthetic fixture'),segments=[dict(id='original-fixture',name='Original fixture',start=0,end=.7,labelStatus='original-speaker-reviewed',categories=['Original'],source='Synthetic AV',permission='Original fixture',referenceText='A reference sentence.')])
 def request(self,path,data=None,auth=True,csrf=None):
  headers={'Authorization':'Bearer '+'s'*48} if auth else {}
  if data is not None:headers['Content-Type']='application/json'
  if csrf is not None:headers['X-VoiceMatrix-Review']=csrf
  req=urllib.request.Request(self.url+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
  try:
   with urllib.request.urlopen(req) as r:return r.status,r.read(),dict(r.headers)
  except urllib.error.HTTPError as r:return r.code,r.read(),dict(r.headers)
 def token(self):
  status,body,headers=self.request('/review');self.assertEqual(status,200)
  self.assertIn('no-store',headers['Cache-Control']);self.assertIn("default-src 'none'",headers['Content-Security-Policy'])
  return re.search(rb'const csrf="([a-zA-Z0-9_-]+)"',body).group(1).decode()
 def test_authenticated_form_and_csrf_required(self):
  self.assertEqual(self.request('/review',auth=False)[0],401)
  token=self.token();self.assertEqual(self.request('/review',self.recipe)[0],403)
  self.assertEqual(self.request('/review',self.recipe,auth=False,csrf=token)[0],401)
  self.assertFalse((self.root/'recipes/SYNTHETIC03.json').exists())
 def test_review_link_accepts_only_canonical_video_selection(self):
  self.assertEqual(self.request('/review?video=SYNTHETIC03')[0],200)
  self.assertEqual(self.request('/review?video=../bad')[0],400)
  self.assertEqual(self.request('/review?video=SYNTHETIC03&video=SYNTHETIC04')[0],400)
 def test_initial_review_saved_in_actual_processor_recipe_format(self):
  self.assertEqual(self.request('/review',self.recipe,csrf=self.token())[0],200)
  saved=json.loads((self.root/'recipes/SYNTHETIC03.json').read_text());self.assertEqual(saved,self.recipe)
  from tools.video_prepare import validate_recipe
  self.assertEqual(validate_recipe(saved,transcribe_available=True)[0],'SYNTHETIC03')
  q=VideoQueue(str(self.root/'queue.db'));self.assertEqual(q.export()['videos'][0]['status'],'waiting');q.close()
 def test_unknown_video_and_invalid_review_do_not_write(self):
  token=self.token()
  for transform in [lambda r:r.update(videoURL=None),lambda r:r.update(videoURL='https://youtu.be/UNKNOWN0001'),lambda r:r['referenceUseReview'].update(record=''),lambda r:r['segments'][0].update(labelStatus='uncertain'),lambda r:r['segments'][0].update(start=True),lambda r:r['segments'].append(copy.deepcopy(r['segments'][0]))]:
   r=copy.deepcopy(self.recipe);transform(r);self.assertEqual(self.request('/review',r,csrf=token)[0],400)
  self.assertFalse((self.root/'recipes/SYNTHETIC03.json').exists())
 def test_existing_recipe_is_never_silently_replaced(self):
  token=self.token();self.assertEqual(self.request('/review',self.recipe,csrf=token)[0],200)
  path=self.root/'recipes/SYNTHETIC03.json';old=path.read_bytes();self.recipe['segments'][0]['name']='Changed'
  self.assertEqual(self.request('/review',self.recipe,csrf=token)[0],409);self.assertEqual(path.read_bytes(),old)
 def test_terminal_or_already_prepared_job_cannot_receive_false_initial_review(self):
  token=self.token();q=VideoQueue(str(self.root/'queue.db'))
  for state in ['failed','needs-review','completed','processing']:
   with q.db:q.db.execute('UPDATE jobs SET status=?',(state,))
   self.assertEqual(self.request('/review',self.recipe,csrf=token)[0],400)
  with q.db:q.db.execute("UPDATE jobs SET status='waiting'")
  q.close();(self.root/'specifications').mkdir();(self.root/'specifications/SYNTHETIC03.json').write_text('{}')
  self.assertEqual(self.request('/review',self.recipe,csrf=token)[0],409)
  self.assertFalse((self.root/'recipes/SYNTHETIC03.json').exists())
 def test_saved_http_review_is_consumed_by_actual_video_preparer(self):
  import shutil,subprocess
  from tools.video_prepare import prepare
  self.assertEqual(self.request('/review',self.recipe,csrf=self.token())[0],200)
  fixture=self.root/'fixture.mp4'
  subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=purple:s=160x90:d=1','-f','lavfi','-i','sine=frequency=440:duration=1','-c:v','mpeg4','-c:a','aac','-shortest',str(fixture)],check=True,capture_output=True)
  class Downloader:
   def __init__(self,o):self.root=pathlib.Path(o['outtmpl']).parent
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def extract_info(self,*args,**kwargs):shutil.copyfile(fixture,self.root/'source.mp4');return dict(id='SYNTHETIC03',title='Synthetic fixture',duration=1)
  output=prepare(self.root/'recipes/SYNTHETIC03.json',self.root/'specifications',downloader_factory=Downloader)
  result=json.loads(output.read_text());self.assertEqual(result['profiles'][0]['metadata']['name'],'Original fixture')
  self.assertFalse(result['provenance']['likenessVerified']);self.assertTrue((self.root/'specifications'/result['profiles'][0]['referenceFile']).is_file())
