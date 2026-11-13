"""Wiring checks only; native Vision/frame behavior requires the Apple probe."""
import pathlib, unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]
class VisualEvidenceTests(unittest.TestCase):
 def test_bounded_local_only_evidence_without_identity_claim(self):
  s=(ROOT/'VoiceMatrix/LocalVisualEvidence.swift').read_text()
  for text in ['import Vision','AVAssetImageGenerator','maximumSize','prefix(12)','prefix(8)','sourceSHA256','Task.checkCancellation()','cancelAllCGImageGeneration','No identity or speaking-character attribution','isSymbolicLink','250_000']:
   self.assertIn(text,s)
  for text in ['URLSession','removeItem','characterName =','URL(string:']:
   self.assertNotIn(text,s)
 def test_native_probe_and_pipeline_are_wired(self):
  project=(ROOT/'project.yml').read_text(); self.assertIn('VoiceMatrix/LocalVisualEvidence.swift',project)
  coordinator=(ROOT/'VoiceMatrix/LocalVideoStudio.swift').read_text()
  self.assertIn('LocalVisualEvidence.analyze(',coordinator)
  self.assertIn('visualEvidence',coordinator)
  self.assertIn('CancellationError',coordinator)
  view=(ROOT/'VoiceMatrix/LocalVideoStudioView.swift').read_text()
  self.assertIn('Visible text is not a verified character name',view)
  workflow=(ROOT/'.github/workflows/native-visual-evidence.yml').read_text()
  self.assertIn('probes/native-visual-evidence/Checks.swift',workflow)

 def test_paste_is_explicit_bounded_and_does_not_poll_clipboard(self):
  view=(ROOT/'VoiceMatrix/LocalVideoStudioView.swift').read_text()
  for text in ['PasteButton(payloadType: String.self)', 'values.count == 1', 'raw.utf8.count <= 16_384', 'LocalMediaURLPolicy.input(raw)', 'local-video-paste']:
   self.assertIn(text,view)
  self.assertNotIn('UIPasteboard',view)
  self.assertNotIn('hasStrings',view)
  self.assertIn('set -euo pipefail',(ROOT/'.github/workflows/native-visual-evidence.yml').read_text())
