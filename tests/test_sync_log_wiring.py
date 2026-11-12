import pathlib,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class SyncLogWiringTests(unittest.TestCase):
 def test_progress_is_emitted_after_hash_validation_and_native_commit(self):
  sync=(ROOT/'VoiceMatrix/VoiceFolderSync.swift').read_text()
  self.assertIn('progress(.catalogValidated',sync)
  self.assertLess(sync.index('digest(bytes) == file.sha256'),sync.index('progress(.fileValidated'))
  library=((ROOT/'VoiceMatrix/CharacterLibraryView.swift').read_text() + (ROOT/'VoiceMatrix/CharacterLibrary.swift').read_text())
  self.assertLess(library.index('store.importCollection(at: temporary)'),library.index('recordSync(.completed'))
  self.assertIn('recordSync(.unchanged)',library)
 def test_phone_never_marks_receipt_at_request_start(self):
  source=(ROOT/'VoiceMatrix/LaptopConnection.swift').read_text()
  self.assertIn('X-VoiceMatrix-Sync-ID',source)
  self.assertIn('VoiceSyncRemoteSnapshot',source)
  self.assertLess(source.index('let (stream, response)'),source.index('progress(.laptopResponded)'))
 def test_terminal_sync_cannot_be_replaced_by_a_late_stop(self):
  source=((ROOT/'VoiceMatrix/CharacterLibraryView.swift').read_text() + (ROOT/'VoiceMatrix/CharacterLibrary.swift').read_text())
  self.assertIn('if progress.isTerminal || progress == .stopping { syncCanStop = false }',source)
  self.assertIn('func cancelSync() { guard syncCanStop else { return }',source)
  self.assertIn('guard syncing, syncCanStop, syncRunID == run',source)
 def test_log_is_accessible_and_bounded(self):
  source=((ROOT/'VoiceMatrix/CharacterLibraryView.swift').read_text() + (ROOT/'VoiceMatrix/CharacterLibrary.swift').read_text())
  self.assertIn('Live sync log',source);self.assertIn('syncEvents.count > 200',source)
