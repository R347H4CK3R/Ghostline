"""CPU launch tests stub the neural module, never train a model."""
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock
from tools import rvc_train_cpu as cpu


class CPULaunchTests(unittest.TestCase):
 def module(self):
  return SimpleNamespace(hps=SimpleNamespace(gpus='',model_dir='experiment'),
    torch=SimpleNamespace(cuda=SimpleNamespace(is_available=lambda:False)),
    mp=SimpleNamespace(set_start_method=mock.Mock()),utils=SimpleNamespace(get_logger=mock.Mock(return_value='logger')),
    run=mock.Mock(),main=mock.Mock(side_effect=AssertionError('DDP main must not run')))
 def test_direct_cpu_run_never_enters_ddp_or_changes_port(self):
  module=self.module()
  with mock.patch.dict(os.environ,{'MASTER_PORT':'unchanged'}):
   cpu.run_cpu(module)
   self.assertEqual(os.environ['MASTER_PORT'],'unchanged')
  module.mp.set_start_method.assert_called_once_with('spawn',force=True)
  module.run.assert_called_once_with(0,1,module.hps,'logger',False)
  module.main.assert_not_called()
 def test_training_exception_propagates(self):
  module=self.module();module.run.side_effect=RuntimeError('optimizer failure')
  with self.assertRaisesRegex(RuntimeError,'optimizer failure'):cpu.run_cpu(module)
 def test_visible_gpu_or_gpu_argument_is_rejected(self):
  for gpu_arg,available in [('0',False),('',True)]:
   with self.subTest(gpu_arg=gpu_arg,available=available):
    module=self.module();module.hps.gpus=gpu_arg;module.torch.cuda.is_available=lambda:available
    with self.assertRaisesRegex(ValueError,'CPU'):cpu.run_cpu(module)
    module.run.assert_not_called()
 def test_mismatched_source_never_executes(self):
  with tempfile.TemporaryDirectory() as d:
   root=pathlib.Path(d).resolve();(root/'train').mkdir();(root/'train/train.py').write_text('raise AssertionError("must not execute")')
   with self.assertRaisesRegex(ValueError,'source hash'):cpu.load_training_module(root,['-e','voice','-g',''])
 def test_source_registered_and_arguments_preserved_without_running_main(self):
  # A tiny exact-byte fixture replaces only the expensive upstream module body.
  raw=b'import sys\nseen=list(sys.argv)\nif __name__ == "__main__": raise AssertionError("main entered")\n'
  with tempfile.TemporaryDirectory() as d:
   root=pathlib.Path(d).resolve();(root/'train').mkdir();source=root/'train/train.py';source.write_bytes(raw)
   original_path=list(sys.path);original_argv=list(sys.argv)
   saved={key:sys.modules.get(key) for key in ('train','train.train')}
   try:
    for key in saved:sys.modules.pop(key,None)
    with mock.patch.object(cpu,'PINNED_SOURCE_SHA256',hashlib.sha256(raw).hexdigest()):
     module,proof=cpu.load_training_module(root,['-e','voice','-g','','-te','1'])
    self.assertEqual(module.seen,[str(source),'-e','voice','-g','','-te','1'])
    self.assertIs(sys.modules['train.train'],module);self.assertEqual(module.__name__,'train.train')
    self.assertEqual(source.read_bytes(),raw);self.assertFalse(proof['sourceModified'])
   finally:
    sys.path[:]=original_path;sys.argv[:]=original_argv
    for key,value in saved.items():
     if value is None:sys.modules.pop(key,None)
     else:sys.modules[key]=value
 def test_entrypoint_failure_has_nonzero_process_exit(self):
  code="from types import SimpleNamespace;from tools.rvc_train_cpu import run_cpu;from unittest.mock import Mock;m=SimpleNamespace(hps=SimpleNamespace(gpus=''),torch=SimpleNamespace(cuda=SimpleNamespace(is_available=lambda:False)),mp=SimpleNamespace(set_start_method=Mock()),utils=SimpleNamespace(get_logger=lambda p:None));m.hps.model_dir='fixture';m.run=lambda *a:(_ for _ in ()).throw(RuntimeError('fixture failure'));run_cpu(m)"
  result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=10)
  self.assertNotEqual(result.returncode,0);self.assertIn('fixture failure',result.stderr)
