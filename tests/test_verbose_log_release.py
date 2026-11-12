"""The 0.4.9 publisher must be independently bound to fresh gate evidence."""
import importlib
from unittest import mock
from tests import test_workflow_log_release as historical
class VerboseReleaseTests(historical.WorkflowReleaseTests):
 def publisher(self):
  self.assertTrue((__import__('pathlib').Path(__file__).resolve().parents[1]/'tools/publish_voicematrix_049.py').is_file())
  return importlib.import_module('tools.publish_voicematrix_049')
 def test_release_identity_is_separate_from_previous_release(self):
  p=self.publisher()
  self.assertEqual(p.VERSION,'0.4.9')
  self.assertEqual(p.TAG,'voicematrix-v0.4.9')
  self.assertIn('.github/workflows/voicematrix-049-candidate.yml',p.REQUIRED_GATES)
  self.assertNotIn('.github/workflows/voicematrix-048-candidate.yml',p.REQUIRED_GATES)
