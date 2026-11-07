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
