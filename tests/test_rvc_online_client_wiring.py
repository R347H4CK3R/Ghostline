"""Source-wiring regressions only; these do not compile or execute Swift/iOS."""
import pathlib,unittest
ROOT=pathlib.Path(__file__).parents[1]
class RVCClientWiringTests(unittest.TestCase):
 def test_observer_ownership_fences_stale_cleanup_and_updates(self):
  source=(ROOT/'VoiceMatrix/RVCOnlineStudio.swift').read_text(encoding='utf-8')
  self.assertIn('let observer = observation.begin()',source)
  self.assertIn('if observation.end(observer)',source)
  self.assertIn('while !Task.isCancelled && observation.owns(observer)',source)
  self.assertIn('if Task.isCancelled || !observation.owns(observer)',source)
 def test_destination_is_app_owned_and_upload_remains_explicit(self):
  app=(ROOT/'VoiceMatrix/App.swift').read_text(encoding='utf-8');view=(ROOT/'VoiceMatrix/RVCOnlineView.swift').read_text(encoding='utf-8')
  self.assertIn('@StateObject private var rvc = RVCOnlineStudio()',app)
  self.assertIn('.environmentObject(rvc)',app)
  self.assertIn('NavigationLink { RVCOnlineView() }',app)
  self.assertIn('Button { rvc.send(audio: audio) }',view)
  self.assertIn('Offline RVC and text-to-speech are unavailable',view)
 def test_controller_uses_safe_error_mapping(self):
  source=(ROOT/'VoiceMatrix/RVCOnlineStudio.swift').read_text(encoding='utf-8')
  self.assertNotIn('error.localizedDescription',source)
  self.assertEqual(source.count('RVCOnlineError.message(for: error)'),3)
