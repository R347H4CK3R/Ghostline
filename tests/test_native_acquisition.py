"""Source-contract checks; real Swift behavior runs in native XCTest, not Python."""
import pathlib, unittest, shutil, subprocess, tempfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
class NativeAcquisitionTests(unittest.TestCase):
 def test_actual_studio_wires_download_before_analysis(self):
  s=(ROOT/'VoiceMatrix/LocalVideoStudio.swift').read_text()
  self.assertIn('LocalMediaAcquisition.acquire',s)
  self.assertIn('func startURL',s)
 def test_transport_is_bounded_and_rejects_redirects(self):
  p=ROOT/'VoiceMatrix/LocalMediaAcquisition.swift';self.assertTrue(p.exists(),'bounded native acquisition is missing')
  s=p.read_text()
  for x in ['willPerformHTTPRedirection','LocalMediaURLPolicy.validate','httpCookieStorage = nil','urlCredentialStorage = nil','maximumBytes','didReceive data: Data','withTaskCancellationHandler']:
   self.assertIn(x,s)
  for x in ['URLSession.shared','YouTubeKit','bypassAgeGate','has_verified','racyCheckOk']:
   self.assertNotIn(x,s)
 def test_page_cap_and_merge_reservation_are_explicit(self):
  s=(ROOT/'VoiceMatrix/LocalMediaAcquisition.swift').read_text()
  self.assertIn('min(4_000_000, try remainingBudget(folder:folder, reserveForMerge:false))',s)
  self.assertIn('reserveForMerge:receipt.parts.count == 2, completedSourceBytes:downloaded',s)
  self.assertIn('byteBudget(retained:retained,free:free',s)
 def test_archive_redirect_uses_same_provider_policy(self):
  s=(ROOT/'VoiceMatrix/LocalMediaAcquisition.swift').read_text()
  self.assertIn('LocalMediaURLPolicy.validateRedirect',s)
 @unittest.skipUnless(shutil.which('swiftc'),'Swift compiler required; source checks do not replace native policy execution')
 def test_real_swift_url_parser_budget_policy(self):
  with tempfile.TemporaryDirectory() as tmp:
   binary=pathlib.Path(tmp)/'acquisition-policy'
   subprocess.run(['swiftc',str(ROOT/'VoiceMatrix/LocalMediaURLPolicy.swift'),str(ROOT/'tests/native/LocalMediaURLPolicyChecks.swift'),'-o',str(binary)],check=True,timeout=60)
   subprocess.run([str(binary)],check=True,timeout=10)
 def test_native_behavior_gate_wired(self):
  s=(ROOT/'.github/workflows/character-ui-smoke.yml').read_text()
  self.assertEqual(s.count('-only-testing:VoiceMatrixTests/LocalMediaAcquisitionTests'),2)

 def test_retention_scan_fails_closed(self):
  s=(ROOT/'VoiceMatrix/LocalMediaAcquisition.swift').read_text()
  self.assertIn('static func retainedBytes',s)
  self.assertIn('guard let entries=',s)
  self.assertIn('errorHandler:',s)
  self.assertIn('guard !scanFailed',s)
  self.assertIn('let size=v.fileSize',s)
  self.assertIn('addingReportingOverflow',s)

  self.assertIn('let retained = try LocalMediaAcquisition.retainedBytes(root: root)', (ROOT/'VoiceMatrix/LocalVideoStudio.swift').read_text())

 def test_transfer_digest_does_not_override_nsobject_hash(self):
  s=(ROOT/'VoiceMatrix/LocalMediaAcquisition.swift').read_text().split('final class Transfer:',1)[1]
  self.assertNotIn('hash=SHA256()',s)
  self.assertIn('contentHash=SHA256()',s)
  self.assertIn('contentHash.update(data:data)',s)
  self.assertIn('contentHash.finalize()',s)
