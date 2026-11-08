"""Source regressions only; native UI/runtime checks still require Apple tooling."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
class NoStockCandidateSourceTests(unittest.TestCase):
    def test_intentionally_empty_stock_manifest_is_not_rejected(self):
        self.assertNotIn('!manifest.voices.isEmpty', (ROOT/'VoiceMatrix/Catalog.swift').read_text())
    def test_home_speech_opens_character_speech_not_empty_stock_picker(self):
        source=(ROOT/'VoiceMatrix/App.swift').read_text()
        self.assertIn('NavigationLink { CharacterLibraryView() } label: { HomeCard(title: "MAKE CHARACTER SPEECH"',source)
    def test_empty_stock_status_points_to_character_folder(self):
        source=(ROOT/'VoiceMatrix/SpeechEngine.swift').read_text()
        self.assertIn('if voices.isEmpty { status = "Stock voices removed. Open My Character Folder to test your imported voices." }',source)
if __name__=='__main__':unittest.main()
