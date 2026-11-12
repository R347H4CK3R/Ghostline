"""CLI routing tests mock neural training, conversion and independent ASR boundaries."""
import contextlib
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from tools import voice_studio


class RVCCLITests(unittest.TestCase):
 def invoke(self,args):
  output=io.StringIO()
  with contextlib.redirect_stdout(output):voice_studio.main(args)
  return json.loads(output.getvalue())
 def train_args(self):return ['train-rvc','--root','rvc','--dataset','dataset','--experiment','voice','--permission','authorized']
 def verify_args(self):return ['verify-rvc','--root','rvc','--training-report','training.json','--input','heldout.wav','--output','checks','--text','A held-out sentence.','--whisper-cli','whisper-cli','--whisper-model','whisper.bin']
 def test_train_defaults_route_runtime_and_timeout(self):
  with mock.patch('tools.rvc_training.train',return_value={'verified':False}) as train:
   self.assertEqual(self.invoke(self.train_args()),{'verified':False})
  train.assert_called_once_with('rvc','dataset','voice','authorized',epochs=200,python=sys.executable,stage_timeout=21600)
 def test_train_overrides_route_to_training(self):
  with mock.patch('tools.rvc_training.train',return_value={}) as train:
   self.invoke(self.train_args()+['--epochs','1','--python','isolated-python','--stage-timeout','12.5'])
  train.assert_called_once_with('rvc','dataset','voice','authorized',epochs=1,python='isolated-python',stage_timeout=12.5)
 def test_verify_routes_independent_asr_and_options(self):
  verifier=mock.Mock()
  with mock.patch('tools.queue_processor.recognizer',return_value=verifier) as recognizer, mock.patch('tools.rvc_validation.verify_conversion',return_value=pathlib.Path('checks/conversion.json')) as verify:
   result=self.invoke(self.verify_args()+['--python','isolated-python','--timeout','123'])
  recognizer.assert_called_once_with('whisper-cli','whisper.bin')
  verify.assert_called_once_with('rvc','training.json','heldout.wav','checks',expected_text='A held-out sentence.',verify_words=verifier,python='isolated-python',timeout=123)
  self.assertEqual(result,{'report':'checks/conversion.json'})
 def test_verify_defaults(self):
  with mock.patch('tools.queue_processor.recognizer') as recognizer, mock.patch('tools.rvc_validation.verify_conversion',return_value='report') as verify:
   self.invoke(self.verify_args())
  self.assertEqual(verify.call_args.kwargs['python'],sys.executable)
  self.assertEqual(verify.call_args.kwargs['timeout'],600)
 def test_export_reads_metadata_and_does_not_publish(self):
  with tempfile.TemporaryDirectory() as d:
   metadata=pathlib.Path(d).resolve()/'meta.json';value={'name':'Example'};metadata.write_text(json.dumps(value))
   with mock.patch('tools.rvc_export.export_folder',return_value=pathlib.Path('private/voice')) as export, mock.patch('tools.master_voices.publish') as publish:
    self.assertEqual(self.invoke(['export-rvc','--report','conversion.json','--metadata',str(metadata),'--output','private']),{'folder':'private/voice'})
   export.assert_called_once_with('conversion.json',value,'private');publish.assert_not_called()
 def test_stage_errors_exit_cleanly(self):
  for error in [ValueError('invalid'),OSError('missing'),RuntimeError('failed'),subprocess.CalledProcessError(1,['child']),subprocess.TimeoutExpired(['child'],1)]:
   with self.subTest(error=type(error).__name__),mock.patch('tools.rvc_training.train',side_effect=error),contextlib.redirect_stderr(io.StringIO()) as stderr:
    with self.assertRaises(SystemExit) as raised:voice_studio.main(self.train_args())
    self.assertEqual(raised.exception.code,2);self.assertNotIn('Traceback',stderr.getvalue())
 def test_missing_arguments_do_not_start_asr(self):
  with mock.patch('tools.queue_processor.recognizer') as recognizer,contextlib.redirect_stderr(io.StringIO()):
   with self.assertRaises(SystemExit):voice_studio.main(['verify-rvc','--root','rvc'])
   recognizer.assert_not_called()
 def test_help_never_loads_neural_packages(self):
  script="""import importlib.abc,sys
class BlockNeural(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname.split('.')[0] in {'torch','faiss','f5_tts','transformers'}:raise RuntimeError('Neural import during help: '+fullname)
sys.meta_path.insert(0,BlockNeural())
from tools.voice_studio import main
main(sys.argv[1:])
"""
  for args in [['--help'],['train-rvc','--help'],['verify-rvc','--help'],['export-rvc','--help']]:
   with self.subTest(args=args):
    result=subprocess.run([sys.executable,'-c',script,*args],text=True,capture_output=True,timeout=10)
    self.assertEqual(result.returncode,0,result.stderr)
 def test_failed_recognizer_setup_stops_before_conversion(self):
  with mock.patch('tools.queue_processor.recognizer',side_effect=ValueError('Independent recognizer model checksum failed')),mock.patch('tools.rvc_validation.verify_conversion') as verify,contextlib.redirect_stderr(io.StringIO()) as stderr:
   with self.assertRaises(SystemExit) as raised:voice_studio.main(self.verify_args())
  self.assertEqual(raised.exception.code,2);verify.assert_not_called()
  self.assertIn('checksum failed',stderr.getvalue())
 def test_invalid_export_metadata_stops_before_export(self):
  with tempfile.TemporaryDirectory() as d:
   metadata=pathlib.Path(d).resolve()/'meta.json';metadata.write_text('{invalid')
   with mock.patch('tools.rvc_export.export_folder') as export,contextlib.redirect_stderr(io.StringIO()):
    with self.assertRaises(SystemExit) as raised:voice_studio.main(['export-rvc','--report','conversion.json','--metadata',str(metadata),'--output','private'])
   self.assertEqual(raised.exception.code,2);export.assert_not_called()
