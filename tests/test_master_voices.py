import tempfile,unittest
from tools.master_voices import scan,compare

class MasterTests(unittest.TestCase):
 def test_missing_files_are_reported_without_deletion(self):
  old={'voices':[{'id':'one','revision':'a'}]}
  with tempfile.TemporaryDirectory() as d:result=compare(old,scan(d))
  self.assertEqual(result['missing'],['one']);self.assertEqual(result['updated'],[])
 def test_updates_match_stable_id(self):
  old={'voices':[{'id':'one','revision':'a'}]}
  new={'status':'ready','voices':[{'id':'one','revision':'b'},{'id':'two','revision':'c'}]}
  self.assertEqual(compare(old,new),dict(added=['two'],updated=['one'],missing=[]))
 def test_invalid_collection_cannot_update(self):
  with self.assertRaises(ValueError):compare({},dict(status='needs-repair',voices=[]))

if __name__=='__main__':unittest.main()
