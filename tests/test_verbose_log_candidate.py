"""Require a fresh 0.4.9 package and evidence identity, never reused 0.4.8 output."""
import pathlib
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class VerboseCandidateTests(unittest.TestCase):
 def test_candidate_has_fresh_version_and_exact_source_verification(self):
  path=ROOT/'.github/workflows/voicematrix-049-candidate.yml'
  self.assertTrue(path.is_file(),'Fresh 0.4.9 candidate workflow missing')
  text=path.read_text()
  self.assertIn("branches: ['candidate/voicematrix-0.4.9']",text)
  self.assertIn('VoiceMatrix-0.4.9-character-test.ipa',text)
  self.assertIn("os.environ['GITHUB_SHA'],'0.4.9'",text)
  self.assertNotIn('0.4.8',text)
  self.assertIn('MARKETING_VERSION: 0.4.9',(ROOT/'project.yml').read_text())
  self.assertIn("CURRENT_PROJECT_VERSION: '1'",(ROOT/'project.yml').read_text())
