"""Source contracts; native diagnostics separately execute real Swift/models."""
import pathlib,unittest,shutil,subprocess,tempfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
class SimilarityTests(unittest.TestCase):
 def test_service_is_local_bounded_and_hash_bound(self):
  p=ROOT/'VoiceMatrix/SpeakerSimilarityService.swift'
  self.assertTrue(p.exists(),'Native similarity service is missing')
  s=p.read_text()
  for word in ['referenceSHA256','generatedSHA256','modelRevision','makeManager','embedSpans','Task.checkCancellation','maximumSeconds: 30','SHA256','likenessVerified = false']:
   self.assertIn(word,s)
  for word in ['downloadAndLoad','prepareModels(', 'URLSession','removeItem','likenessPercent']:
   self.assertNotIn(word,s)
 def test_snapshot_bound_precedes_copy_and_native_recovery_is_exercised(self):
  s=(ROOT/'VoiceMatrix/SpeakerSimilarityService.swift').read_text()
  self.assertLess(s.index('contains(source.count)'),s.index('let data=Data(source)'))
  probe=(ROOT/'probes/native-similarity/Diagnostic.swift').read_text()
  for text in ['missing-model-bundle','cancellationRecoveryVerified','await iterator.next()','prefixed.dropFirst()']:
   self.assertIn(text,probe)
 @unittest.skipUnless(shutil.which('swiftc'),'Swift unavailable; no native behavior claim')
 def test_native_similarity_math(self):
  with tempfile.TemporaryDirectory() as tmp:
   exe=pathlib.Path(tmp)/'policy'
   subprocess.run(['swiftc',str(ROOT/'VoiceMatrix/SpeakerSimilarityPolicy.swift'),str(ROOT/'tests/native/SpeakerSimilarityChecks.swift'),'-o',str(exe)],check=True,timeout=60)
   subprocess.run([str(exe)],check=True,timeout=20)
