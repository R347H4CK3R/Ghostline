"""Integration wiring checks, not neural or physical-device evidence."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
class LocalSimilarityIntegrationTests(unittest.TestCase):
 def test_diagnostic_follows_word_gate_and_never_becomes_likeness_gate(self):
  s=(ROOT/'VoiceMatrix/LocalVideoStudio.swift').read_text()
  gate=s.index('LocalStudioEvidence.wordErrorRate(expected: previewText')
  self.assertIn('similarityService.compare(',s[gate:])
  self.assertIn('previewEvidence.inputSHA256',s[gate:])
  self.assertIn('Similarity unavailable',s)
  self.assertIn('not identity or likeness verification',s)
 def test_pair_change_clears_diagnostic_and_ui_labels_numeric_limit(self):
  s=(ROOT/'VoiceMatrix/LocalVideoStudio.swift').read_text()
  self.assertIn('similarity = nil',s[s.index('mutating func selectReference'):s.index('@Published')])
  ui=(ROOT/'VoiceMatrix/LocalVideoStudioView.swift').read_text()
  self.assertIn('Recorded speaker similarity',ui)
  self.assertIn('not a likeness percentage',ui)

 def test_integrity_failures_do_not_become_optional_diagnostics(self):
  s=(ROOT/'VoiceMatrix/LocalVideoStudio.swift').read_text()
  self.assertIn('catch LocalVisualEvidence.Failure.sourceChanged { throw LocalError.source }',s)
  ui=(ROOT/'VoiceMatrix/LocalVideoStudioView.swift').read_text()
  self.assertIn('local.validatedSimilarity()',ui)

  self.assertIn("try await LocalVisualEvidence.verifySource(retained,sha256:expectedHash)",s)
