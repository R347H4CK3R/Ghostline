import pathlib,tempfile,unittest
from tools.video_queue import VideoQueue

class QueueTests(unittest.TestCase):
 def test_link_variants_are_one_job(self):
  q=VideoQueue(':memory:');r=q.add(['https://youtu.be/EAT0nWoEzJ8','https://www.youtube.com/live/EAT0nWoEzJ8','https://www.youtube.com/watch?v=EAT0nWoEzJ8'])
  self.assertEqual(len(r['added']),1);self.assertEqual(len(r['duplicates']),2);q.close()
 def test_claim_is_exclusive_across_connections(self):
  with tempfile.TemporaryDirectory() as d:
   p=str(pathlib.Path(d)/'queue.db');a=VideoQueue(p);b=VideoQueue(p)
   a.add(['https://youtu.be/EAT0nWoEzJ8']);self.assertIsNotNone(a.claim());self.assertIsNone(b.claim());a.close();b.close()
 def test_invalid_list_does_not_partially_import(self):
  q=VideoQueue(':memory:')
  with self.assertRaises(ValueError):q.add(['https://youtu.be/EAT0nWoEzJ8','https://example.com/'])
  self.assertEqual(q.export()['videos'],[]);q.close()

if __name__=='__main__':unittest.main()
