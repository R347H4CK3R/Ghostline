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


class NamedQueueTests(unittest.TestCase):
 def test_named_export_import_preserves_labels_and_deduplicates(self):
  q=VideoQueue(':memory:')
  result=q.import_text('\ufeffRick\thttps://youtu.be/EAT0nWoEzJ8\nhttps://www.youtube.com/watch?v=EAT0nWoEzJ8\n')
  self.assertEqual(result['added'],['EAT0nWoEzJ8'])
  self.assertEqual(q.export()['videos'][0]['name'],'Rick')
  q.close()
 def test_bad_named_list_is_atomic(self):
  q=VideoQueue(':memory:')
  with self.assertRaises(ValueError):q.import_text('Rick\thttps://youtu.be/EAT0nWoEzJ8\nBad\thttps://example.com\n')
  self.assertEqual(q.export()['videos'],[]);q.close()
 def test_import_is_durable_and_does_not_reset_status(self):
  with tempfile.TemporaryDirectory() as d:
   p=str(pathlib.Path(d)/'queue.db');q=VideoQueue(p)
   q.import_text('Rick\thttps://youtu.be/EAT0nWoEzJ8')
   q.progress('EAT0nWoEzJ8',1,'completed');q.close()
   q=VideoQueue(p);q.import_text('Rick\thttps://youtu.be/EAT0nWoEzJ8')
   self.assertEqual(q.export()['videos'][0]['status'],'completed');q.close()
 def test_import_does_not_reapply_unchanged_snapshot_over_api_label(self):
  q=VideoQueue(':memory:');text='Rick\thttps://youtu.be/EAT0nWoEzJ8'
  q.import_text(text)
  q.add_named([dict(name='Updated',url='https://youtu.be/EAT0nWoEzJ8')])
  q.import_text(text)
  self.assertEqual(q.export()['videos'][0]['name'],'Updated');q.close()
 def test_named_validation_precedes_any_write(self):
  q=VideoQueue(':memory:')
  with self.assertRaises(ValueError):q.add_named([dict(name='Rick',url='https://youtu.be/EAT0nWoEzJ8'),dict(name=3,url='https://youtu.be/EAT0nWoEzJ8')])
  self.assertEqual(q.export()['videos'],[]);q.close()

if __name__=='__main__':unittest.main()
