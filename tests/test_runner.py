import importlib.util,sys,tempfile,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('runner',Path(__file__).parents[1]/'tools/run_native_tests.py')
r=importlib.util.module_from_spec(spec)
if spec.loader: spec.loader.exec_module(r)
class RunnerTests(unittest.TestCase):
 def test_successful_process(self):
  with tempfile.TemporaryDirectory() as p:
   self.assertEqual(r.run([sys.executable,'-c','print("completed")'],Path(p)/'run.log',5),0)
 def test_stalled_process_is_terminated(self):
  with tempfile.TemporaryDirectory() as p:
   self.assertEqual(r.run([sys.executable,'-c','import time;time.sleep(30)'],Path(p)/'run.log',0.1),124)

class HarvestTests(unittest.TestCase):
 def test_finds_qa_in_simulator_application_data(self):
  import json
  with tempfile.TemporaryDirectory() as p:
   root=Path(p); folder=root/'device/data/Containers/Data/Application/app/Documents/VoiceMatrix-QA';folder.mkdir(parents=True)
   report={'modelRevision':'pinned','profiles':[{'id':'a'}]}
   (folder/'voice-synthesis-results.json').write_text(json.dumps(report))
   (folder/'a.wav').write_bytes(b'0'*60)
   self.assertEqual(r.find_qa_folder(root,{'revision':'pinned','voices':[{'id':'a'}]}),folder)
 def test_rejects_incomplete_qa_folder(self):
  with tempfile.TemporaryDirectory() as p:
   with self.assertRaises(FileNotFoundError): r.find_qa_folder(Path(p),{'revision':'pinned','voices':[{'id':'a'}]})
