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
  self.assertIn("expected_build='2'",text)
  self.assertIn("--expected-build 2",text)
  self.assertNotIn('0.4.8',text)
  self.assertIn('MARKETING_VERSION: 0.4.9',(ROOT/'project.yml').read_text())
  self.assertIn("CURRENT_PROJECT_VERSION: '2'",(ROOT/'project.yml').read_text())
 def test_queue_recovery_installs_media_fixture_dependency(self):
  text=(ROOT/'.github/workflows/queue-recovery.yml').read_text()
  self.assertIn('choco install ffmpeg',text)
  self.assertIn('apt-get install -y ffmpeg',text)
 def test_candidate_config_retriggers_every_same_source_gate(self):
  for name in ['character-ui-smoke','native-app','native-queue','native-character-folder','queue-processor','queue-recovery']:
   self.assertIn('.github/workflows/voicematrix-049-candidate.yml',(ROOT/f'.github/workflows/{name}.yml').read_text(),name)
 def test_cross_platform_full_suite_has_expanded_bounded_budget(self):
  source=(ROOT/'.github/workflows/queue-processor.yml').read_text()
  self.assertIn('timeout-minutes: 20',source)
