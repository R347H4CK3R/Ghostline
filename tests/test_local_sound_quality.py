"""Local quality source contracts; real Apple inference is a separate native gate."""
import pathlib,shutil,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class LocalSoundQualityTests(unittest.TestCase):
 def read(self,name):
  p=ROOT/name;self.assertTrue(p.exists(),f'Missing local quality implementation: {name}');return p.read_text()
 def test_adapter_is_local_cancelable_bounded_and_label_checked(self):
  s=self.read('VoiceMatrix/LocalSoundQuality.swift')
  for text in ['SNClassifySoundRequest(classifierIdentifier: .version1)','knownClassifications','cancelAnalysis()','withTaskCancellationHandler','seconds(30)','128','classification(forIdentifier:'] :self.assertIn(text,s)
  for text in ['URLSession','download','removeItem']:self.assertNotIn(text,s)
 def test_pipeline_retains_screening_before_any_transcription_or_f5(self):
  s=self.read('VoiceMatrix/LocalVideoStudio.swift')
  self.assertIn('LocalSoundQuality.analyze',s)
  self.assertLess(s.index('LocalSoundQuality.analyze'),s.index('transcriber.transcribe(reference)'))
  self.assertLess(s.index('LocalSoundQuality.analyze'),s.index('engine.load(localBundle: bundle)'))
  for text in ['quality-','quality.decision.admitted','Candidate needs review','sourceSHA256']:self.assertIn(text,s)
 def test_resume_cannot_skip_new_quality_policy_and_actual_voice_names_are_logged(self):
  s=self.read('VoiceMatrix/LocalVideoStudio.swift')
  self.assertIn('qualityPolicyVersions?[speaker.speaker] == LocalSoundQualityPolicy.version',s)
  self.assertIn('Added \(savedProfile.name) (ID \(savedProfile.id))',s)
  self.assertIn('Reused \(existing.name) (ID \(existing.id))',s)
  self.assertIn('Library now contains \(library.profiles.count) voices',s)
  self.assertLess(s.index('try await library.importLocalGeneratedCollection'),s.index('guard let savedProfile = library.profiles.first'))
 def test_expanded_native_suite_has_bounded_capacity_without_removed_tests(self):
  s=self.read('.github/workflows/character-ui-smoke.yml')
  self.assertIn('timeout-minutes: 60',s)
  self.assertIn('-only-testing:VoiceMatrixTests/LocalSpeakerModelTests',s)
 def test_native_classifier_tests_are_wired(self):
  s=self.read('.github/workflows/character-ui-smoke.yml')
  for target in ['LocalSoundQualityTests','LocalSoundQualityPolicyTests']:
   self.assertEqual(s.count('-only-testing:VoiceMatrixTests/'+target),2)
 @unittest.skipUnless(shutil.which('swiftc'),'Swift compiler unavailable; source checks do not replace policy execution')
 def test_swift_independent_scores_and_coverage_policy(self):
  with tempfile.TemporaryDirectory() as tmp:
   binary=pathlib.Path(tmp)/'sound-quality'
   subprocess.run(['swiftc',str(ROOT/'VoiceMatrix/LocalSoundQualityPolicy.swift'),str(ROOT/'tests/native/LocalSoundQualityChecks.swift'),'-o',str(binary)],check=True,timeout=60)
   subprocess.run([str(binary)],check=True,timeout=10)
if __name__=='__main__':unittest.main()
