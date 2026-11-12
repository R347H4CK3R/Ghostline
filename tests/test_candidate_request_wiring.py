import pathlib,unittest
ROOT=pathlib.Path(__file__).parents[1]
class CandidateRequestWiringTests(unittest.TestCase):
 def test_explicit_request_and_native_receipt_checks_are_present(self):
  model=ROOT/'VoiceMatrix/VideoCandidateRequest.swift'
  self.assertTrue(model.exists())
  source=model.read_text();self.assertIn('approved-private-candidates',source);self.assertIn('validateReceipt',source)
  view=(ROOT/'VoiceMatrix/VideoQueueView.swift').read_text();self.assertIn('Request voice candidates',view);self.assertIn('sourceUseApproved',view)
  connection=(ROOT/'VoiceMatrix/LaptopConnection.swift').read_text();self.assertIn('appendingPathComponent("requests")',connection);self.assertIn('validateReceipt',connection)
 def test_new_fixed_stages_are_supported_on_both_sides(self):
  from tools.workflow_activity import MESSAGES
  swift=(ROOT/'VoiceMatrix/VideoWorkflow.swift').read_text()
  for stage in ['candidate_requested','speaker_analyzing','temporary_media_removed']:
   self.assertIn(stage,MESSAGES);self.assertIn('"'+stage+'"',swift)
