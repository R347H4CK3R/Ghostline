import pathlib,tempfile,unittest,wave
from tools.rvc_training import audit_dataset,training_commands,prepare_filelist

class TrainingTests(unittest.TestCase):
 def test_short_clip_does_not_qualify_for_training(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'voice.wav'
   with wave.open(str(p),'wb') as w:w.setparams((1,2,24000,0,'NONE','none'));w.writeframes(b'\0\x10'*24000)
   report=audit_dataset(d)
   self.assertEqual(report['status'],'insufficient-data');self.assertEqual(report['uniqueSeconds'],1)
 def test_duplicates_not_counted_twice(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'one.wav'
   with wave.open(str(p),'wb') as w:w.setparams((1,2,24000,0,'NONE','none'));w.writeframes(b'\0\x10'*24000)
   (p.parent/'two.wav').write_bytes(p.read_bytes());r=audit_dataset(d)
   self.assertEqual(r['uniqueSeconds'],1);self.assertEqual(len(r['duplicates']),1)
 def test_train_invokes_real_upstream_stages(self):
  cmds=training_commands('/rvc','/data','test-voice','python',20)
  self.assertEqual(cmds['train'][:2],['python','train/train.py']);self.assertIn('-sw',cmds['train'])
  self.assertEqual(cmds['index'][1],'train/train_index.py')
 def test_unsafe_experiment_rejected(self):
  with self.assertRaises(ValueError):training_commands('/rvc','/data','../bad','python',20)
 def test_missing_extracted_features_block_filelist(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d);(p/'0_gt_wavs').mkdir();(p/'0_gt_wavs'/'one.wav').write_bytes(b'x')
   with self.assertRaises(ValueError):prepare_filelist(p)

if __name__=='__main__':unittest.main()
