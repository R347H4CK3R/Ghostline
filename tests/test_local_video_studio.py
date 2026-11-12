"""Source-contract checks, not evidence of iPhone inference or native compilation."""
import pathlib, shutil, subprocess, tempfile, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class LocalStudioSourceTests(unittest.TestCase):
 def read(self,path):return (ROOT/path).read_text(encoding='utf8')
 def test_recognition_requires_local_engine_and_has_bounded_cancellation(self):
  s=self.read('VoiceMatrix/OnDeviceTranscription.swift')
  for text in ['AsrModels.loadLocal(','parallelChunkConcurrency: 1','seconds(45)','withTaskCancellationHandler','self.token == run','worker.cancel()','manager.cleanup()']:self.assertIn(text,s)
  self.assertNotIn('import Speech',s)
  self.assertNotIn('downloadAndLoad',s)
 def test_pipeline_never_contacts_companion_or_deletes_retained_work(self):
  s=self.read('VoiceMatrix/LocalVideoStudio.swift')
  for text in ['LaptopConnection','URLSession','removeItem','shutil','trainedModel": true']:self.assertNotIn(text,s)
  for text in ['sourceSHA256','importLocalGeneratedCollection','wordErrorRate','<= 0.1','keepWarm: false','Task.detached','thermalState']:self.assertIn(text,s)
 def test_local_failed_generation_is_retained_without_changing_legacy_default(self):
  self.assertIn('preserveIncomplete: true',self.read('VoiceMatrix/LocalVideoStudio.swift'))
  engine=self.read('VoiceMatrix/F5ReferenceEngine.swift')
  self.assertIn('preserveIncomplete: Bool = false',engine)
  self.assertIn('!completed && !preserveIncomplete',engine)
 def test_local_owner_cancels_optional_catalog_and_fences_import(self):
  library=self.read('VoiceMatrix/CharacterLibraryView.swift')
  self.assertIn('func beginLocalGeneration()',library)
  self.assertIn('localGenerationOwner == owner',library)
  self.assertIn('syncJob?.cancel()',library)
  self.assertIn('library.endLocalGeneration(libraryOwner)',self.read('VoiceMatrix/LocalVideoStudio.swift'))
 def test_memory_and_thermal_signals_request_safe_stop(self):
  app=self.read('VoiceMatrix/App.swift')
  self.assertIn('localVideo.memoryWarning()',app)
  self.assertIn('localVideo.thermalChanged()',app)
  self.assertIn('Stopping for memory',self.read('VoiceMatrix/LocalVideoStudio.swift'))
 def test_log_refresh_is_separate_from_last_activity(self):
  s=self.read('VoiceMatrix/LocalVideoStudioView.swift')
  for text in ['by: 1','Last actual update:','timeIntervalSince(job.updated) >= 30','not a failure declaration','No laptop or server fallback','groups speakers']:self.assertIn(text,s)
 def test_native_verification_is_wired_not_merely_stored(self):
  s=self.read('.github/workflows/character-ui-smoke.yml')
  for target in ['VoiceMatrixTests/LocalVideoAudioTests','VoiceMatrixTests/LocalStudioEvidenceTests','VoiceMatrixUITests/LocalVideoStudioUITests']:self.assertGreaterEqual(s.count('-only-testing:'+target),2)
 @unittest.skipUnless(shutil.which('swiftc'),'Swift compiler required; source checks cannot replace it')
 def test_real_swift_evidence_policy(self):
  with tempfile.TemporaryDirectory() as directory:
   binary=pathlib.Path(directory)/'local-evidence'
   subprocess.run(['swiftc',str(ROOT/'VoiceMatrix/LocalStudioEvidence.swift'),str(ROOT/'tests/native/LocalStudioEvidenceChecks.swift'),'-o',str(binary)],check=True,timeout=60)
   subprocess.run([str(binary)],check=True,timeout=10)
