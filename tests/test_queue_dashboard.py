import json,pathlib,tempfile,threading,unittest,urllib.request
from unittest.mock import patch
from tools.laptop_supervisor import tick
from tools.video_queue import VideoQueue
from tools.queue_transport import create_server

URL='https://youtu.be/EAT0nWoEzJ8'
class DashboardTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name)
  self.game=patch('tools.laptop_supervisor.gaming',return_value=False);self.game.start()
 def tearDown(self):self.game.stop();self.tmp.cleanup()
 def test_app_post_reaches_pending_text_and_real_stage_is_escaped(self):
  server=create_server(self.root,'x'*48);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:
   body=json.dumps({'videos':[{'url':URL,'name':'<script>Rick</script>'}]}).encode()
   req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/queue',data=body,headers={'Authorization':'Bearer '+'x'*48})
   with urllib.request.urlopen(req) as response:self.assertEqual(response.status,200)
   q=VideoQueue(str(self.root/'queue.db'));job=q.claim();q.progress(job['id'],.37,token=job['token']);q.close()
   state=tick(self.root)
   self.assertEqual(state['videos'][0]['progress'],.37)
   self.assertIn(URL,(self.root/'video-queue.txt').read_text())
   html=(self.root/'Progress.html').read_text();self.assertIn('37%',html);self.assertIn('&lt;script&gt;',html);self.assertNotIn('<script>',html)
  finally:server.shutdown();server.server_close();thread.join()
 def test_text_input_reaches_worker_queue_and_review_never_clears_link(self):
  path=self.root/'video-queue.txt';path.write_text('Rick\t'+URL+'\n')
  tick(self.root);q=VideoQueue(str(self.root/'queue.db'));job=q.claim()
  self.assertIsNotNone(job);q.review_with(job['id'],job['token'],lambda:None);q.close()
  state=tick(self.root);self.assertEqual(state['videos'][0]['status'],'needs-review')
  self.assertEqual(state['videos'][0]['name'],'Rick');self.assertIn(URL,path.read_text())
 def test_invalid_file_does_not_partially_import(self):
  path=self.root/'video-queue.txt';original=URL+'\nnot-a-link\n';path.write_text(original)
  state=tick(self.root);self.assertEqual(state['status'],'queue-input-error')
  q=VideoQueue(str(self.root/'queue.db'));self.assertEqual(q.export()['videos'],[]);q.close();self.assertEqual(path.read_text(),original)
 def test_repeat_keeps_existing_text_bytes_and_canonical_deduplication(self):
  path=self.root/'video-queue.txt';original='# keep this comment\nRick\thttps://www.youtube.com/live/EAT0nWoEzJ8';path.write_text(original)
  tick(self.root);tick(self.root)
  self.assertEqual(path.read_text(),original)
  q=VideoQueue(str(self.root/'queue.db'));self.assertEqual(len(q.export()['videos']),1);q.close()
 def test_append_after_nonterminated_line_preserves_both_entries(self):
  path=self.root/'video-queue.txt';path.write_text('# existing comment')
  q=VideoQueue(str(self.root/'queue.db'));q.add([URL]);q.close()
  tick(self.root);self.assertEqual(path.read_text(),'# existing comment\n\t'+URL+'\n')

 def test_hash_prefixed_app_name_round_trips_without_duplicate_lines(self):
  q=VideoQueue(str(self.root/'queue.db'));q.add([URL])
  with q.db:
   q.db.execute('CREATE TABLE names (video_id TEXT PRIMARY KEY,name TEXT NOT NULL)')
   q.db.execute('INSERT INTO names VALUES (?,?)',('EAT0nWoEzJ8','#Rick'))
  q.close();tick(self.root);original=(self.root/'video-queue.txt').read_bytes();tick(self.root)
  self.assertEqual((self.root/'video-queue.txt').read_bytes(),original)
 def test_monitor_can_read_its_own_large_mirror(self):
  urls=['https://youtu.be/'+str(n).zfill(11) for n in range(1001)]
  q=VideoQueue(str(self.root/'queue.db'));q.add(urls);q.close()
  self.assertEqual(len(tick(self.root)['videos']),1001)
  self.assertEqual(len(tick(self.root)['videos']),1001)
 def test_bad_pending_file_does_not_hide_existing_processing_job(self):
  q=VideoQueue(str(self.root/'queue.db'));q.add([URL]);job=q.claim();q.progress(job['id'],.37,token=job['token']);q.close()
  (self.root/'video-queue.txt').write_text('bad line')
  state=tick(self.root);self.assertEqual(state['status'],'queue-input-error')
  self.assertEqual(state['videos'][0]['progress'],.37)
  self.assertIn('37%',(self.root/'Progress.html').read_text())

if __name__=='__main__':unittest.main()
