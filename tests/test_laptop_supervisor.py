import json,pathlib,tempfile,unittest
from unittest.mock import patch
from tools.laptop_supervisor import tick

class SupervisorTests(unittest.TestCase):
 def test_pending_links_not_removed_without_pipeline(self):
  with tempfile.TemporaryDirectory() as d,patch('tools.laptop_supervisor.gaming',return_value=False):
   p=pathlib.Path(d);q=p/'video-queue.txt';q.write_text('Rick\thttps://youtu.be/EAT0nWoEzJ8\n')
   s=tick(p);self.assertEqual(s['pendingLines'],1);self.assertFalse(s['pipelineConnected']);self.assertIn('EAT0nWoEzJ8',q.read_text())
 def test_game_status_does_not_start_work(self):
  with tempfile.TemporaryDirectory() as d,patch('tools.laptop_supervisor.gaming',return_value=True):
   p=pathlib.Path(d);(p/'video-queue.txt').write_text('https://youtu.be/EAT0nWoEzJ8\n')
   self.assertEqual(tick(p)['status'],'paused-for-game')


class IntegratedSupervisorTests(unittest.TestCase):
 def test_api_queue_visible_without_file_lines(self):
  from tools.video_queue import VideoQueue
  with tempfile.TemporaryDirectory() as d,patch('tools.laptop_supervisor.gaming',return_value=False):
   p=pathlib.Path(d);q=VideoQueue(str(p/'queue.db'));q.add(['https://youtu.be/EAT0nWoEzJ8']);q.close()
   s=tick(p)
   self.assertEqual(s['pendingVideos'],1)
   self.assertEqual(s['status'],'waiting-for-pipeline-setup')
 def test_completed_file_entry_is_not_pending(self):
  from tools.video_queue import VideoQueue
  with tempfile.TemporaryDirectory() as d,patch('tools.laptop_supervisor.gaming',return_value=False):
   p=pathlib.Path(d);(p/'video-queue.txt').write_text('Rick\thttps://youtu.be/EAT0nWoEzJ8\n')
   tick(p);q=VideoQueue(str(p/'queue.db'));q.progress('EAT0nWoEzJ8',1,'completed');q.close()
   s=tick(p);self.assertEqual(s['pendingVideos'],0);self.assertEqual(s['completedVideos'],1)
 def test_bad_file_does_not_import_any_rows(self):
  from tools.video_queue import VideoQueue
  with tempfile.TemporaryDirectory() as d,patch('tools.laptop_supervisor.gaming',return_value=False):
   p=pathlib.Path(d);content='Rick\thttps://youtu.be/EAT0nWoEzJ8\ninvalid\n';(p/'video-queue.txt').write_text(content)
   s=tick(p);self.assertEqual(s['status'],'queue-import-error')
   q=VideoQueue(str(p/'queue.db'));self.assertEqual(q.export()['videos'],[]);q.close()
   self.assertEqual((p/'video-queue.txt').read_text(),content)
 def test_explicit_pause_survives_gaming_and_empty_queue(self):
  with tempfile.TemporaryDirectory() as d,patch('tools.laptop_supervisor.gaming',return_value=True):
   p=pathlib.Path(d);(p/'pause').touch();s=tick(p)
   self.assertEqual(s['status'],'paused');self.assertTrue(s['gamingDetected'])
 def test_game_detection_failure_is_safe(self):
  with tempfile.TemporaryDirectory() as d,patch('tools.laptop_supervisor.gaming',side_effect=TimeoutError):
   p=pathlib.Path(d);s=tick(p);self.assertEqual(s['status'],'paused-game-check-unavailable')

if __name__=='__main__':unittest.main()
