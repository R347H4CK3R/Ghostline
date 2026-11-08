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

if __name__=='__main__':unittest.main()
