"""Tiny subprocess fixtures only: no neural training or upstream dependencies."""
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
from tools import rvc_training as rvc


class StageTests(unittest.TestCase):
 def run_stage(self, code, timeout=2, cancel=None):
  with tempfile.TemporaryDirectory() as d, open(os.devnull, 'wb') as log:
   return rvc.run_stage([sys.executable, '-c', code], cwd=d, env=os.environ.copy(), log=log, timeout=timeout, cancel=cancel)
 def test_failure_is_reported(self):
  with self.assertRaises(subprocess.CalledProcessError):self.run_stage('raise SystemExit(7)')
 def test_timeout_is_bounded(self):
  start=time.monotonic()
  with self.assertRaises(TimeoutError):self.run_stage('import time; time.sleep(60)', timeout=.15)
  self.assertLess(time.monotonic()-start,5)
 def test_cancel_is_bounded(self):
  event=threading.Event();timer=threading.Timer(.15,event.set);timer.start()
  try:
   with self.assertRaises(InterruptedError):self.run_stage('import time; time.sleep(60)', cancel=event)
  finally:timer.cancel()
 def test_invalid_timeout_never_launches(self):
  for timeout in (0,-1,float('inf'),float('nan')):
   with self.subTest(timeout=timeout), self.assertRaises(ValueError):self.run_stage('pass',timeout=timeout)
 def test_descendant_cannot_outlive_cancel(self):
  with tempfile.TemporaryDirectory() as d:
   marker=pathlib.Path(d).resolve()/'escaped'
   descendant="import time,pathlib; time.sleep(1.5); pathlib.Path(%r).write_text('alive')" % str(marker)
   if os.name!='nt':descendant="import signal; signal.signal(signal.SIGTERM,signal.SIG_IGN); "+descendant
   code="import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',%r]); time.sleep(60)" % descendant
   event=threading.Event();timer=threading.Timer(.3,event.set);timer.start()
   try:
    with self.assertRaises(InterruptedError):self.run_stage(code,cancel=event)
    time.sleep(1.6);self.assertFalse(marker.exists(),'descendant survived cancellation')
   finally:timer.cancel()

 @unittest.skipUnless(os.name=='nt','Windows Job Object needs native Windows')
 def test_windows_descendant_cannot_outlive_successful_leader(self):
  with tempfile.TemporaryDirectory() as d:
   marker=pathlib.Path(d).resolve()/'escaped'
   descendant="import time,pathlib; time.sleep(1.5); pathlib.Path(%r).write_text('alive')" % str(marker)
   self.run_stage("import subprocess,sys; subprocess.Popen([sys.executable,'-c',%r])" % descendant)
   time.sleep(1.6);self.assertFalse(marker.exists())

 def test_windows_job_sets_kill_on_close_before_assignment(self):
  import ctypes
  api=mock.MagicMock();api.CreateJobObjectW.return_value=123
  with mock.patch.object(ctypes,'WinDLL',return_value=api,create=True):
   job=rvc._WindowsJob()
   try:
    api.SetInformationJobObject.assert_called_once()
    args=api.SetInformationJobObject.call_args.args
    self.assertEqual(args[:2],(123,9))
    self.assertEqual(args[2]._obj.BasicLimitInformation.LimitFlags,0x2000)
   finally:job.close()
 @unittest.skipUnless(os.name=='nt','Windows Job Object needs native Windows')
 def test_windows_descendant_dies_when_runner_owner_is_killed(self):
  with tempfile.TemporaryDirectory() as d:
   ready=pathlib.Path(d).resolve()/'ready';marker=pathlib.Path(d).resolve()/'escaped'
   descendant="import time,pathlib;pathlib.Path(%r).write_text('ready');time.sleep(2);pathlib.Path(%r).write_text('alive')" % (str(ready),str(marker))
   worker="import os,sys;from tools.rvc_training import run_stage;run_stage([sys.executable,'-c',%r],cwd=%r,env=os.environ.copy(),log=open(os.devnull,'wb'),timeout=30)" % (descendant,d)
   with subprocess.Popen([sys.executable,'-c',worker],cwd=pathlib.Path(rvc.__file__).resolve().parent.parent) as owner:
    try:
     deadline=time.monotonic()+10
     while not ready.exists() and owner.poll() is None and time.monotonic()<deadline:time.sleep(.05)
     self.assertTrue(ready.exists(),'descendant did not reach readiness gate')
     owner.kill();owner.wait(timeout=5)
     time.sleep(2.2);self.assertFalse(marker.exists(),'job survived abrupt owner exit')
    finally:
     if owner.poll() is None:owner.kill();owner.wait(timeout=5)


class WindowsJobDrainTests(unittest.TestCase):
 def setUp(self):
  import ctypes
  self.ctypes=ctypes;self.api=mock.MagicMock();self.api.CreateJobObjectW.return_value=123
  patch=mock.patch.object(ctypes,'WinDLL',return_value=self.api,create=True);patch.start();self.addCleanup(patch.stop)
  self.job=rvc._WindowsJob()
 def test_close_drains_all_processes_before_closing_handle(self):
  remaining=iter([3,1,0]);observed=[]
  def query(handle,kind,pointer,size,returned):
   self.assertEqual((handle,kind,size),(123,1,48))
   self.assertEqual(type(pointer._obj).ActiveProcesses.offset,40)
   self.api.CloseHandle.assert_not_called()
   count=next(remaining);pointer._obj.ActiveProcesses=count;observed.append(count);return 1
  self.api.QueryInformationJobObject.side_effect=query
  with mock.patch.object(rvc.time,'sleep'):self.job.close()
  self.assertEqual(observed,[3,1,0]);self.api.CloseHandle.assert_called_once_with(123)
  self.assertIsNone(self.job.handle)
 def test_query_failure_is_reported_and_handle_closed(self):
  self.api.QueryInformationJobObject.return_value=0
  with mock.patch.object(self.ctypes,'get_last_error',return_value=5,create=True),mock.patch.object(self.ctypes,'WinError',return_value=OSError('query denied'),create=True):
   with self.assertRaisesRegex(OSError,'query denied'):self.job.close()
  self.api.CloseHandle.assert_called_once_with(123);self.assertIsNone(self.job.handle)
 def test_drain_timeout_is_bounded_and_reported(self):
  def query(handle,kind,pointer,size,returned):pointer._obj.ActiveProcesses=1;return 1
  self.api.QueryInformationJobObject.side_effect=query
  with mock.patch.object(rvc.time,'monotonic',side_effect=[10,16]),mock.patch.object(rvc.time,'sleep'):
   with self.assertRaisesRegex(TimeoutError,'Windows.*process'):self.job.close()
  self.api.CloseHandle.assert_called_once_with(123);self.assertIsNone(self.job.handle)


class DatasetSnapshotTests(unittest.TestCase):
 def test_audit_hash_matches_audio_actually_inspected(self):
  import wave
  with tempfile.TemporaryDirectory() as d:
   path=pathlib.Path(d).resolve()/'voice.wav'
   with wave.open(str(path),'wb') as writer:
    writer.setparams((1,2,16000,0,'NONE','none'));writer.writeframes(b'\x00\x10'*16000)
   original=path.read_bytes();real_open=wave.open
   def replace_after_open(*args,**kwargs):
    reader=real_open(*args,**kwargs)
    replacement=path.with_suffix('.tmp');replacement.write_bytes(b'replaced');replacement.replace(path)
    return reader
   with mock.patch.object(rvc.wave,'open',side_effect=replace_after_open):report=rvc.audit_dataset(d)
   self.assertEqual(report['files'][0]['sha256'],hashlib.sha256(original).hexdigest())
 def test_mutated_audio_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   source=pathlib.Path(d).resolve()/'source';source.mkdir();(source/'voice.wav').write_bytes(b'changed')
   with self.assertRaisesRegex(ValueError,'changed'):
    rvc.snapshot_dataset(source,pathlib.Path(d).resolve()/'snapshot',{'files':[{'file':'voice.wav','sha256':hashlib.sha256(b'original').hexdigest()}]})
 def test_only_audited_bytes_reach_preprocess(self):
  with tempfile.TemporaryDirectory() as d:
   source=pathlib.Path(d).resolve()/'source';source.mkdir();(source/'voice.wav').write_bytes(b'audited');(source/'other.mp3').write_bytes(b'not audited')
   target=pathlib.Path(d).resolve()/'snapshot'
   rvc.snapshot_dataset(source,target,{'files':[{'file':'voice.wav','sha256':hashlib.sha256(b'audited').hexdigest()}]})
   (source/'voice.wav').write_bytes(b'changed')
   self.assertEqual(list(target.iterdir()),[target/'voice.wav']);self.assertEqual((target/'voice.wav').read_bytes(),b'audited')


class TrainingSafetyTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=pathlib.Path(self.tmp.name).resolve();self.exp=self.root/'logs'/'voice'
  for name in ['configs/v1/40k.json','assets/pretrained_v2/f0G40k.pth','assets/pretrained_v2/f0D40k.pth','assets/hubert_base/config.json','assets/hubert_base/preprocessor_config.json','assets/hubert_base/weights.bin']:
   p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'fixture')
  self.model=self.root/'assets/weights/voice.pth';self.model.parent.mkdir(parents=True)
  dataset=self.root/'dataset';dataset.mkdir();(dataset/'voice.wav').write_bytes(b'fixture')
  self.report=dict(status='ready-for-training',files=[dict(file='voice.wav',sha256=hashlib.sha256(b'fixture').hexdigest())])
  self.audit=mock.patch.object(rvc,'audit_dataset',return_value=self.report);self.audit.start();self.addCleanup(self.audit.stop)
  self.git=mock.patch.object(rvc.subprocess,'check_output',side_effect=lambda cmd,**kw:rvc.UPSTREAM+'\n' if 'rev-parse' in cmd else '');self.git.start();self.addCleanup(self.git.stop)
  self.commands=mock.patch.object(rvc,'training_commands',return_value={'index':[sys.executable,'-c','pass']});self.commands.start();self.addCleanup(self.commands.stop)
 def train(self):return rvc.train(self.root,self.root/'dataset','voice','fixture permission')
 def test_existing_weight_preserved_without_logs(self):
  self.model.write_bytes(b'original')
  with self.assertRaises(FileExistsError):self.train()
  self.assertEqual(self.model.read_bytes(),b'original');self.assertFalse(self.exp.exists())
 def test_existing_external_index_preserved_without_logs(self):
  index=self.root/'assets/indices/added_IVF1_Flat_nprobe_1_voice_v2.index';index.parent.mkdir();index.write_bytes(b'original')
  with self.assertRaises(FileExistsError):self.train()
  self.assertEqual(index.read_bytes(),b'original');self.assertFalse(self.exp.exists())
 def output_stage(self,model=b'model',index=b'index'):
  def execute(*args,**kwargs):
   self.model.write_bytes(model);(self.exp/'added_fixture.index').write_bytes(index)
  return execute
 def test_empty_outputs_rejected(self):
  for model,index in [(b'',b'index'),(b'model',b'')]:
   with self.subTest(model=model,index=index):
    with mock.patch.object(rvc,'run_stage',create=True,side_effect=self.output_stage(model,index)):
     with self.assertRaisesRegex(ValueError,'empty'):self.train()
    self.assertEqual(json.loads((self.exp/'voicematrix-training.json').read_text())['status'],'failed')
    import shutil
    shutil.rmtree(self.exp);self.model.unlink()
 def test_model_and_index_hashes_recorded_without_verification_claim(self):
  with mock.patch.object(rvc,'run_stage',create=True,side_effect=self.output_stage()):state=self.train()
  self.assertFalse(state['verified'])
  self.assertEqual(state['modelSHA256'],hashlib.sha256(b'model').hexdigest())
  self.assertEqual(state['indexSHA256'],{str(self.exp/'added_fixture.index'):hashlib.sha256(b'index').hexdigest()})
 def test_dirty_tracked_source_rejected(self):
  self.git.stop()
  with mock.patch.object(rvc.subprocess,'check_output',side_effect=[rvc.UPSTREAM+'\n',' M train/train.py\n']):
   with self.assertRaisesRegex(ValueError,'modified'):self.train()
  self.assertFalse(self.exp.exists())

 def test_missing_hubert_preprocessor_config_blocks_launch(self):
  (self.root/'assets/hubert_base/preprocessor_config.json').unlink()
  with self.assertRaisesRegex(ValueError,'preprocessor_config'):
   self.train()
  self.assertFalse(self.exp.exists())
 def test_real_timeout_persists_failed_report(self):
  self.commands.stop()
  with mock.patch.object(rvc,'training_commands',return_value={'preprocess':[sys.executable,'-c','import time;time.sleep(60)']}):
   with self.assertRaises(TimeoutError):rvc.train(self.root,self.root/'dataset','voice','fixture permission',stage_timeout=.1)
  state=json.loads((self.exp/'voicematrix-training.json').read_text())
  self.assertEqual(state['status'],'failed');self.assertEqual(state['completedStages'],[])
 def test_cancel_persists_cancelled_report(self):
  event=threading.Event();event.set()
  with self.assertRaises(InterruptedError):rvc.train(self.root,self.root/'dataset','voice','fixture permission',cancel=event)
  state=json.loads((self.exp/'voicematrix-training.json').read_text())
  self.assertEqual(state['status'],'cancelled');self.assertEqual(state['completedStages'],[])

 def test_output_directory_symlinks_rejected_before_experiment_creation(self):
  for relative in ('assets/weights','assets/indices','logs'):
   with self.subTest(relative=relative):
    path=self.root/relative;outside=self.root/('outside-'+path.name);outside.mkdir()
    if path.exists():path.rmdir()
    try:path.symlink_to(outside,target_is_directory=True)
    except (OSError,NotImplementedError):self.skipTest('Directory symlinks unavailable')
    try:
     with self.assertRaisesRegex(ValueError,'redirect'):self.train()
     self.assertFalse(self.exp.exists())
    finally:path.unlink();path.mkdir()
 def test_nested_stage_imports_root_without_inheriting_pythonpath(self):
  # Match upstream's nested script entry point, without importing neural packages.
  (self.root/'train').mkdir();(self.root/'infer').mkdir()
  (self.root/'infer/__init__.py').write_text('')
  (self.root/'infer/audio.py').write_text('VALUE = "root package"\n')
  (self.root/'train/preprocess.py').write_text(
   'import os,pathlib\nfrom infer.audio import VALUE\n'
   'assert VALUE == "root package"\n'
   'assert os.environ["PYTHONPATH"] == str(pathlib.Path.cwd())\n'
   'pathlib.Path("assets/weights/voice.pth").write_bytes(b"model")\n'
   'pathlib.Path("logs/voice/added_fixture.index").write_bytes(b"index")\n')
  unrelated=self.root/'unrelated';unrelated.mkdir()
  self.commands.stop()
  with mock.patch.dict(os.environ,{'PYTHONPATH':str(unrelated)}),mock.patch.object(rvc,'training_commands',return_value={'preprocess':[sys.executable,'train/preprocess.py']}):
   with self.assertRaisesRegex(ValueError,'matching'):self.train()
  self.assertEqual(self.model.read_bytes(),b'model')

 def test_module_launch_avoids_sibling_train_py_shadowing_package(self):
  self.commands.stop()
  (self.root/'train/dataset').mkdir(parents=True)
  (self.root/'train/dataset/train.py').write_text('raise RuntimeError("sibling train.py shadowed the train package")\n')
  (self.root/'train/dataset/slicer2.py').write_text('class Slicer: pass\n')
  (self.root/'train/dataset/extract_f0.py').write_text(
   'from train.dataset.slicer2 import Slicer\n'
   'import pathlib\npathlib.Path("module-import-ok").write_text(Slicer.__name__)\n')
  command=rvc.training_commands(self.root,self.root/'dataset','voice',sys.executable,1)['pitch']
  with (self.root/'fixture.log').open('wb') as log:
   rvc.run_stage(command,cwd=self.root,env=dict(os.environ,PYTHONPATH=str(self.root)),log=log,timeout=5)
  self.assertEqual((self.root/'module-import-ok').read_text(),'Slicer')
 def test_effective_floor_blocks_pitch_after_preprocessing(self):
  from tests.test_rvc_preprocess import float_wav
  self.commands.stop()
  stages={'preprocess':['fixture'],'pitch':['must-not-run']}
  def stage(command,**kwargs):
   self.assertEqual(command,['fixture'])
   for folder,rate in [('0_gt_wavs',40000),('1_16k_wavs',16000)]:float_wav(self.exp/folder/'0_0.wav',rate,1)
  with mock.patch.object(rvc,'training_commands',return_value=stages),mock.patch.object(rvc,'run_stage',side_effect=stage) as run:
   with self.assertRaisesRegex(ValueError,'effective'):self.train()
  self.assertEqual(run.call_count,1)
  state=json.loads((self.exp/'voicematrix-training.json').read_text())
  self.assertEqual(state['status'],'failed')
  self.assertLess(state['preprocessingDataset']['activeLowerBoundSeconds'],60)
 def test_invalid_feature_arrays_never_enter_filelist(self):
  from tests.test_rvc_preprocess import float_wav
  float_wav(self.exp/'0_gt_wavs/0_0.wav')
  for folder,name in [('3_feature768','0_0.npy'),('2a_f0','0_0.wav.npy'),('2b-f0nsf','0_0.wav.npy')]:
   p=self.exp/folder/name;p.parent.mkdir();p.write_bytes(b'nonempty but invalid')
  with self.assertRaisesRegex(ValueError,'NPY'):rvc.prepare_filelist(self.exp)
  self.assertFalse((self.exp/'filelist.txt').exists())
 def test_complete_pipeline_records_only_effectively_admitted_filelist(self):
  from tests.test_rvc_preprocess import float_wav,npy
  from tools.rvc_preprocess import TRANSFORM,PINNED_SOURCE_SHA256
  self.commands.stop()
  commands={name:[name] for name in ['preprocess','pitch','features','train','index']}
  def execute(command,**kwargs):
   stage=command[0]
   if stage=='preprocess':
    for i in range(19):
     for folder,rate in [('0_gt_wavs',40000),('1_16k_wavs',16000)]:float_wav(self.exp/folder/f'0_{i}.wav',rate,3.7 if i<18 else .5)
    (self.exp/'voicematrix-preprocess-adapter.json').write_text(json.dumps(dict(transform=TRANSFORM,normalizedSourceSHA256=PINNED_SOURCE_SHA256,sourceModified=False)))
   elif stage=='features':
    for i in range(19):
     frames=370 if i<18 else 50
     npy(self.exp/'3_feature768'/f'0_{i}.npy',(frames//2,768))
     npy(self.exp/'2a_f0'/f'0_{i}.wav.npy',(frames,),'<i8',100)
     npy(self.exp/'2b-f0nsf'/f'0_{i}.wav.npy',(frames,),'<f4',150)
   elif stage=='train':
    rows=(self.exp/'filelist.txt').read_text().splitlines()
    self.assertEqual(len(rows),18);self.assertFalse(any('0_18.' in row for row in rows))
    self.model.write_bytes(b'model')
    from tools.rvc_train_cpu import MODE,PINNED_SOURCE_SHA256 as TRAIN_SHA
    (self.exp/'voicematrix-train-adapter.json').write_text(json.dumps(dict(mode=MODE,normalizedSourceSHA256=TRAIN_SHA,sourceModified=False)))
   elif stage=='index':(self.exp/'added_fixture.index').write_bytes(b'index')
  with mock.patch.object(rvc,'training_commands',return_value=commands),mock.patch.object(rvc,'run_stage',side_effect=execute):state=self.train()
  self.assertEqual(state['effectiveDataset']['status'],'ready-for-training')
  self.assertEqual(state['effectiveDataset']['retainedFileCount'],18)
  self.assertEqual(state['effectiveDataset']['excludedFileCount'],1)
  self.assertEqual(state['effectiveDataset']['activeLowerBoundSeconds'],61.2)
  self.assertEqual(state['completedStages'],list(commands));self.assertFalse(state['verified'])
 def test_missing_model_stops_before_index_and_train_completion(self):
  self.commands.stop()
  with mock.patch.object(rvc,'training_commands',return_value={'train':['train'],'index':['index']}),mock.patch('tools.rvc_preprocess.audit_preprocessed',return_value={'status':'ready-for-training','files':[]}),mock.patch.object(rvc,'prepare_filelist'),mock.patch.object(rvc,'run_stage') as stage:
   with self.assertRaisesRegex(ValueError,'empty'):self.train()
  stage.assert_called_once()
  state=json.loads((self.exp/'voicematrix-training.json').read_text())
  self.assertEqual(state['completedStages'],[]);self.assertEqual(state['status'],'failed')
