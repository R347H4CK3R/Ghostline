import pathlib, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class LocalPipelineDiagnosticTests(unittest.TestCase):
 def test_exact_coordinator_and_real_library_are_used(self):
  s=(ROOT/'probes/native-local-studio/Diagnostic.swift').read_text()
  for term in ['LocalVideoStudio(', 'CharacterLibrary(', 'AudioStore(', 'SpeechStudio()', 'studio.start(', 'studio.resume(', 'studio.cancel()', 'reloaded.speak(', 'recognizer.transcribe(', 'wer<=0.1', 'studio.current?.completed == true', 'physicalIPhoneVerified = false', 'likenessVerified = false']:
   self.assertIn(term,s)
  self.assertNotIn('mock',s.lower())
 def test_native_network_denied_gate(self):
  s=(ROOT/'.github/workflows/local-pipeline-diagnostic.yml').read_text()
  for term in ['(deny network*)', '/usr/bin/say', 'bundle_asr.py','bundle_diarization.py','LocalStudioDiagnostic','workflow_call:']:
   self.assertIn(term,s)
 def test_defaults_keep_iphone_paths_and_engines(self):
  s=(ROOT/'VoiceMatrix/LocalVideoStudio.swift').read_text()
  self.assertIn('root: URL? = nil',s)
  self.assertIn('speakerBundle: URL? = Bundle.main.url',s)
  self.assertIn('private let engine = F5ReferenceEngine(idleRetention: .zero)',s)
  model=(ROOT/'VoiceMatrix/CharacterLibrary.swift').read_text()
  self.assertIn('profiles = try await store.importCollection',model)
  self.assertIn('supportRoot: URL? = nil',model)

 def test_aggregate_requires_actual_pipeline(self):
  s=(ROOT/'.github/workflows/voicematrix-049-candidate.yml').read_text()
  self.assertIn('uses: ./.github/workflows/local-pipeline-diagnostic.yml',s)
  self.assertIn('needs: [resolve, ipa, speech, conversion, bundled-asr, local-pipeline]',s)
