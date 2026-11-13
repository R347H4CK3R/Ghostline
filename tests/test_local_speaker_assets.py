import pathlib, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class SpeakerAssetIntegrationTests(unittest.TestCase):
 def test_completed_speakers_keep_independent_receipts(self):
  src=(ROOT/'VoiceMatrix/LocalVideoStudio.swift').read_text()
  self.assertIn('struct SpeakerAssets: Codable',src)
  self.assertIn('var speakerAssets: [String:SpeakerAssets]?',src)
  self.assertEqual(src.count('recordSpeakerAssets(speaker.speaker,'),2)
  self.assertIn('func speakerAssetURL(',src)
  self.assertIn('Self.hash(bytes) == expected',src)
 def test_ui_exposes_each_speaker_not_just_last_attempt(self):
  src=(ROOT/'VoiceMatrix/LocalVideoStudioView.swift').read_text()
  self.assertIn('local.speakerAssetURL(speaker, preview: false)',src)
  self.assertIn('local.speakerAssetURL(speaker, preview: true)',src)
  self.assertIn('Preview-only reference; not a trained RVC model',src)
 def test_failed_selection_cannot_leave_previous_speaker_playing(self):
  src=(ROOT/'VoiceMatrix/LocalVideoStudioView.swift').read_text()
  self.assertEqual(src.count('audio.stop()\n                                    if let url=local.speakerAssetURL'),2)
