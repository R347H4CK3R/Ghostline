"""Source-contract checks, not evidence of iPhone inference or native compilation."""
import pathlib, shutil, subprocess, tempfile, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class LocalStudioSourceTests(unittest.TestCase):
 def read(self,path):return (ROOT/path).read_text(encoding='utf8')
 def test_recognition_requires_local_engine_and_has_bounded_cancellation(self):
  s=self.read('VoiceMatrix/OnDeviceTranscription.swift')
  for text in ['supportsOnDeviceRecognition','requiresOnDeviceRecognition = true','seconds(45)','withTaskCancellationHandler','guard token == run','task?.cancel()']:self.assertIn(text,s)
  self.assertNotIn('requiresOnDeviceRecognition = false',s)
 def test_pipeline_never_contacts_companion_or_deletes_retained_work(self):
  s=self.read('VoiceMatrix/LocalVideoStudio.swift')
  for text in ['LaptopConnection','URLSession','removeItem','shutil','trainedModel": true']:self.assertNotIn(text,s)
  for text in ['sourceSHA256','importLocalGeneratedCollection','wordErrorRate','<= 0.1','keepWarm: false','Task.detached','thermalState']:self.assertIn(text,s)
 def test_log_refresh_is_separate_from_last_activity(self):
  s=self.read('VoiceMatrix/LocalVideoStudioView.swift')
  for text in ['by: 1','Last actual update:','timeIntervalSince(job.updated) >= 30','not a failure declaration','No laptop or server fallback','one usable reference']:self.assertIn(text,s)
 def test_native_verification_is_wired_not_merely_stored(self):
  s=self.read('.github/workflows/character-ui-smoke.yml')
  for target in ['VoiceMatrixTests/LocalVideoAudioTests','VoiceMatrixTests/LocalStudioEvidenceTests','VoiceMatrixUITests/LocalVideoStudioUITests']:self.assertGreaterEqual(s.count('-only-testing:'+target),2)
 @unittest.skipUnless(shutil.which('swiftc'),'Swift compiler required; source checks cannot replace it')
 def test_real_swift_evidence_policy(self):
  with tempfile.TemporaryDirectory() as directory:
   binary=pathlib.Path(directory)/'local-evidence'
   subprocess.run(['swiftc',str(ROOT/'VoiceMatrix/LocalStudioEvidence.swift'),str(ROOT/'tests/native/LocalStudioEvidenceChecks.swift'),'-o',str(binary)],check=True,timeout=60)
   subprocess.run([str(binary)],check=True,timeout=10)
