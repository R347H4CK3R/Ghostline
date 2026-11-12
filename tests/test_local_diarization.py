"""Bundle byte/security tests plus source contracts; native inference is not asserted."""
import zipfile, shutil, subprocess, hashlib, importlib.util, json, pathlib, tempfile, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class LocalDiarizationTests(unittest.TestCase):
 def module(self):
  path=ROOT/'tools/bundle_diarization.py'
  self.assertTrue(path.exists(), 'Local-only hash-verified bundle stager is missing')
  spec=importlib.util.spec_from_file_location('bundle_diarization',path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
 def test_stage_rejects_corruption_and_never_replaces_existing_bytes(self):
  mod=self.module()
  with tempfile.TemporaryDirectory() as tmp:
   target=pathlib.Path(tmp).resolve()/'Diarization'; payload=b'approved'; lock={'files':{'NOTICE.md':{'size':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}}}
   with self.assertRaises(ValueError):mod.stage(target,lock,lambda p:b'corrupt!')
   self.assertFalse((target/'NOTICE.md').exists())
   mod.stage(target,lock,lambda p:payload)
   self.assertEqual((target/'NOTICE.md').read_bytes(),payload)
   (target/'NOTICE.md').write_bytes(b'existing')
   with self.assertRaises(ValueError):mod.stage(target,lock,lambda p:payload)
   self.assertEqual((target/'NOTICE.md').read_bytes(),b'existing')
 def test_stage_rejects_traversal_and_symlink(self):
  mod=self.module()
  with tempfile.TemporaryDirectory() as tmp:
   target=pathlib.Path(tmp).resolve()/'Diarization'; payload=b'x'; entry={'size':1,'sha256':hashlib.sha256(payload).hexdigest()}
   for path in ['../escape','/absolute','a/../../b','a\\b']:
    with self.assertRaises(ValueError):mod.stage(target,{'files':{path:entry}},lambda p:payload)
   target.mkdir(exist_ok=True);(target/'NOTICE.md').symlink_to(pathlib.Path(tmp).resolve()/'victim')
   with self.assertRaises(ValueError):mod.stage(target,{'files':{'NOTICE.md':entry}},lambda p:payload)
 def test_ipa_inspection_checks_exact_model_bytes(self):
  mod=self.module();payload=b'approved';lock={'files':{'NOTICE.md':{'size':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}}}
  with tempfile.TemporaryDirectory() as tmp:
   archive=pathlib.Path(tmp)/'candidate.ipa';prefix='Payload/VoiceMatrix.app/Diarization/'
   with zipfile.ZipFile(archive,'w') as out:
    out.writestr(prefix+'NOTICE.md',payload);out.writestr(prefix+'resource-lock.json',mod.LOCK.read_bytes())
   self.assertEqual(mod.inspect_ipa(archive,lock)['diarizationBundle'],'verified')
   with zipfile.ZipFile(archive,'w') as out:
    out.writestr(prefix+'NOTICE.md',b'corrupt!');out.writestr(prefix+'resource-lock.json',mod.LOCK.read_bytes())
   with self.assertRaises(ValueError):mod.inspect_ipa(archive,lock)
 def test_runtime_has_no_network_or_download_fallback(self):
  p=ROOT/'VoiceMatrix/LocalSpeakerDiarization.swift';self.assertTrue(p.exists(),'Native bundled-model adapter is missing');s=p.read_text()
  for forbidden in ['URLSession','prepareModels(', 'OfflineDiarizerModels.load(', 'removeItem'] :self.assertNotIn(forbidden,s)
  for required in ['initialize(models:', 'exclusiveSegments = false','segmentation.batchSize = 1','embedding.batchSize = 1','Task.checkCancellation()', 'SHA256','speakerWindows','CMSampleBufferGetPresentationTimeStamp','abs(timestamp - Double(samples.count)/16_000) <= 0.05']:self.assertIn(required,s)
 def test_real_model_silence_check_is_wired_not_claimed_by_source_tests(self):
  s=(ROOT/'.github/workflows/character-ui-smoke.yml').read_text()
  self.assertIn('python3 tools/bundle_diarization.py',s)
  self.assertEqual(s.count('-only-testing:VoiceMatrixTests/LocalSpeakerModelTests'),2)
 def test_positive_synthetic_speech_gate_is_test_bundle_only(self):
  config=(ROOT/'project.yml').read_text()
  sources=config.split('  VoiceMatrixTests:\n',1)[1].split('  VoiceMatrixUITests:\n',1)[0]
  self.assertIn('    - path: tests/fixtures/conversion-reference.wav\n      buildPhase: resources',sources)
  app=config.split('  VoiceMatrix:\n',1)[1].split('  VoiceMatrixTests:\n',1)[0]
  self.assertNotIn('tests/fixtures/conversion-reference.wav',app)
  native=(ROOT/'VoiceMatrixTests/LocalSpeakerModelTests.swift').read_text()
  for required in ['testBundledModelsDetectNeutralSyntheticSpeech','0840a3b08d2d438804e760afa54bc1c9cdf1c8b33bffdc1ab458be4ab3740cd2','XCTAssertFalse(result.segments.isEmpty','XCTAssertFalse(result.speakerWindows.isEmpty']:
   self.assertIn(required,native)
 def test_audio_timing_failure_is_distinct_and_actionable(self):
  s=(ROOT/'VoiceMatrix/LocalSpeakerDiarization.swift').read_text()
  self.assertIn('case .invalidTimeline:',s)
  self.assertIn('Export the media with a continuous audio track',s)
  self.assertIn('abs(timestamp - Double(samples.count)/16_000) <= 0.05 else { throw Failure.invalidTimeline }',s)
 def test_real_pipeline_uses_speaker_windows_and_retains_evidence(self):
  s=(ROOT/'VoiceMatrix/LocalVideoStudio.swift').read_text()
  for required in ['LocalSpeakerDiarization.analyze','analysisSHA256','for speaker in','Unidentified speaker','speakerWindows']:self.assertIn(required,s)
  self.assertNotIn('LocalStudioEvidence.windows(duration: duration)',s)
 @unittest.skipUnless(shutil.which('swiftc'),'Swift compiler required; native policy is not replaced by source checks')
 def test_real_swift_overlap_policy(self):
  with tempfile.TemporaryDirectory() as tmp:
   binary=pathlib.Path(tmp)/'speaker-policy'
   subprocess.run(['swiftc',str(ROOT/'VoiceMatrix/LocalSpeakerPolicy.swift'),str(ROOT/'tests/native/LocalSpeakerPolicyChecks.swift'),'-o',str(binary)],check=True,timeout=60)
   subprocess.run([str(binary)],check=True,timeout=10)
if __name__=='__main__':unittest.main()
