"""Guard the UI boundary: automatic sync may refresh metadata, never import all audio."""
import pathlib, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class SelectiveVoiceWiringTests(unittest.TestCase):
 def test_automatic_sync_only_refreshes_catalog(self):
  source=(ROOT/'VoiceMatrix/CharacterLibraryView.swift').read_text()
  refresh=source.split('func syncVoices(',1)[1].split('func downloadVoice(',1)[0]
  self.assertIn('LaptopConnection.voiceCatalog',refresh)
  self.assertNotIn('store.importCollection',refresh)
  self.assertNotIn('LaptopConnection.syncVoices',source)
  self.assertIn('Date().timeIntervalSince(lastCatalogAttempt) < 60',source)
  automatic=source.split('func loadAndRefresh()',1)[1].split('func cancelSync()',1)[0]
  self.assertNotIn('importFolder(',automatic)
 def test_interrupted_refresh_can_retry_immediately_on_foreground(self):
  source=(ROOT/'VoiceMatrix/CharacterLibraryView.swift').read_text()
  lifecycle=source.split('func setApplicationActive(',1)[1].split('var engineAvailable',1)[0]
  self.assertIn('if syncing || !catalogReachable { lastCatalogAttempt = nil }',lifecycle)
  self.assertLess(lifecycle.index('lastCatalogAttempt = nil'),lifecycle.index('catalogReachable = false'))
  self.assertIn('if let interrupted = syncJob, interrupted.isCancelled { await interrupted.value }',lifecycle)
  self.assertIn('await loadAndRefresh()',lifecycle)
 def test_picker_shows_online_and_downloaded_states_without_deletion(self):
  source=(ROOT/'VoiceMatrix/CharacterLibraryView.swift').read_text()
  for text in ['Download for offline', 'Downloaded', 'Online required', 'storedVoiceBytes', 'library.availableProfiles']:
   self.assertIn(text,source)
  self.assertNotIn('role: .destructive',source)
 def test_selective_transport_is_bounded_and_rejects_redirects(self):
  source=(ROOT/'VoiceMatrix/VoiceCatalogConnection.swift').read_text()
  for text in ['VoiceFolderSync.bounded', 'withTaskCancellationHandler', 'completionHandler(nil)', 'response.url == endpoint', 'data.count < limit', 'waitsForConnectivity = false', 'VoiceSyncRemoteSnapshot', 'snapshot.newer(than: sequence, for: syncID)', 'activity.cancel(); pollSession.invalidateAndCancel()']:
   self.assertIn(text,source)
