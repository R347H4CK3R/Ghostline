import json,pathlib,sys,tempfile,unittest,subprocess
class CandidateEngineTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name)
 def tearDown(self):self.tmp.cleanup()
 def factory(self,code):
  from tools.candidate_engine import analyzer
  script=self.root/'speaker_candidates.py';script.write_text(code)
  return analyzer(sys.executable,self.root/'ecapa.ckpt',self.root/'vad.onnx',script=script)
 def test_child_result_is_read_after_success_and_scratch_is_removed(self):
  fn=self.factory("import json,pathlib,sys\nout=pathlib.Path(sys.argv[sys.argv.index('--output')+1]);out.write_text(json.dumps({'schemaVersion':1,'candidates':[]}))\n")
  self.assertEqual(fn(self.root/'audio.wav',lambda:False)['candidates'],[])
 def test_oversized_or_failed_child_is_rejected(self):
  for code in ["raise SystemExit(2)","import pathlib,sys\npathlib.Path(sys.argv[sys.argv.index('--output')+1]).write_text(' '*150000)"]:
   fn=self.factory(code)
   with self.assertRaises((ValueError,subprocess.CalledProcessError)):fn(self.root/'audio.wav',lambda:False)
 def test_cancellation_is_honored_before_start(self):
  fn=self.factory("raise RuntimeError('must not start')")
  with self.assertRaises(InterruptedError):fn(self.root/'audio.wav',lambda:True)

 def test_default_backend_is_packaged_as_runnable_cli(self):
  from tools import candidate_engine
  script=pathlib.Path(candidate_engine.__file__).with_name('speaker_candidates.py')
  result=subprocess.run([sys.executable,str(script),'--help'],capture_output=True,text=True)
  self.assertEqual(result.returncode,0,result.stderr)
