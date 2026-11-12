import pathlib,tempfile,unittest,wave
from tools.rvc_training import audit_dataset,training_commands,prepare_filelist

class TrainingTests(unittest.TestCase):
 def test_short_clip_does_not_qualify_for_training(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d).resolve()/'voice.wav'
   with wave.open(str(p),'wb') as w:w.setparams((1,2,24000,0,'NONE','none'));w.writeframes(b'\0\x10'*24000)
   report=audit_dataset(d)
   self.assertEqual(report['status'],'insufficient-data');self.assertEqual(report['uniqueSeconds'],1)
 def test_exactly_sixty_active_seconds_meets_floor(self):
  with tempfile.TemporaryDirectory() as d:
   for index,rate in enumerate((16000,24000)):
    p=pathlib.Path(d).resolve()/f'voice{index}.wav'
    with wave.open(str(p),'wb') as w:w.setparams((1,2,rate,0,'NONE','none'));w.writeframes(bytes([index,16])*(rate*30))
   report=audit_dataset(d)
   self.assertEqual(report['status'],'ready-for-training');self.assertEqual(report['uniqueSeconds'],60)
 def test_duplicates_not_counted_twice(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d).resolve()/'one.wav'
   with wave.open(str(p),'wb') as w:w.setparams((1,2,24000,0,'NONE','none'));w.writeframes(b'\0\x10'*24000)
   (p.parent/'two.wav').write_bytes(p.read_bytes());r=audit_dataset(d)
   self.assertEqual(r['uniqueSeconds'],1);self.assertEqual(len(r['duplicates']),1)
 def test_train_invokes_real_upstream_stages(self):
  cmds=training_commands('/rvc','/data','test-voice','python',20)
  modules={'pitch':'train.dataset.extract_f0','features':'train.dataset.extract_hubert_feature','index':'train.train_index'}
  for stage,module in modules.items():
   with self.subTest(stage=stage):self.assertEqual(cmds[stage][:3],['python','-m',module])
  self.assertEqual(pathlib.Path(cmds['preprocess'][1]).name,'rvc_preprocess.py')
  self.assertEqual(cmds['preprocess'][2],'--root');self.assertIn('--dataset',cmds['preprocess'])
  self.assertEqual(pathlib.Path(cmds['train'][1]).name,'rvc_train_cpu.py')
  self.assertEqual(cmds['train'][2],'--root');self.assertIn('--',cmds['train'])
  self.assertIn('-sw',cmds['train'])
  self.assertEqual(cmds['index'][3:],['test-voice','v2','assets/indices','2','single'])
 def test_unsafe_experiment_rejected(self):
  with self.assertRaises(ValueError):training_commands('/rvc','/data','../bad','python',20)
 def test_missing_extracted_features_block_filelist(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d).resolve();(p/'0_gt_wavs').mkdir();(p/'0_gt_wavs'/'one.wav').write_bytes(b'x')
   with self.assertRaises(ValueError):prepare_filelist(p)

if __name__=='__main__':unittest.main()
