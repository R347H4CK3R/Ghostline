"""Packaging checks use tiny synthetic bytes, never model execution or private media."""
import hashlib
import io
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

class BundleASRTests(unittest.TestCase):
    def lock(self, data=b'model-fixture'):
        return {'schemaVersion': 1, 'revision': 'a'*40, 'files': {
            'Encoder.mlmodelc/weights/weight.bin': {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}}}
    def test_stage_streams_verified_bytes_and_reuses_exact_files(self):
        from tools.bundle_asr import stage
        with tempfile.TemporaryDirectory() as directory:
            data=b'model-fixture'; lock=self.lock(data); seen=[]
            def fetch(path):
                seen.append(path); return io.BytesIO(data)
            stage(directory, lock, fetch)
            stage(directory, lock, lambda _: self.fail('Exact verified file should not be downloaded again'))
            self.assertEqual(seen, ['Encoder.mlmodelc/weights/weight.bin'])
            self.assertEqual((pathlib.Path(directory)/seen[0]).read_bytes(), data)
    def test_bad_bytes_never_become_a_loadable_model(self):
        from tools.bundle_asr import stage
        for data in [b'', b'wrong', b'model-fixture-extra', b'model-fixturf']:
            with self.subTest(data=data), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(ValueError): stage(directory,self.lock(),lambda _:io.BytesIO(data))
                self.assertFalse((pathlib.Path(directory)/'Encoder.mlmodelc/weights/weight.bin').exists())
    def test_existing_mismatch_is_preserved(self):
        from tools.bundle_asr import stage
        with tempfile.TemporaryDirectory() as directory:
            target=pathlib.Path(directory)/'Encoder.mlmodelc/weights/weight.bin'; target.parent.mkdir(parents=True); target.write_bytes(b'keep-existing')
            with self.assertRaises(ValueError): stage(directory,self.lock(),lambda _:self.fail('Do not replace'))
            self.assertEqual(target.read_bytes(), b'keep-existing')
    def test_traversal_and_symlinks_are_rejected(self):
        from tools.bundle_asr import stage
        with tempfile.TemporaryDirectory() as directory:
            for name in ['../outside','/outside','a/../outside','a//x','a\\x']:
                lock=self.lock(); lock['files']={name:next(iter(lock['files'].values()))}
                with self.assertRaises(ValueError):stage(directory,lock,lambda _:io.BytesIO(b'model-fixture'))
            (pathlib.Path(directory)/'Encoder.mlmodelc').symlink_to(pathlib.Path(directory),target_is_directory=True)
            with self.assertRaises(ValueError):stage(directory,self.lock(),lambda _:io.BytesIO(b'model-fixture'))
    def test_runtime_is_local_only_and_releases_models_on_every_outcome(self):
        source=(ROOT/'VoiceMatrix/OnDeviceTranscription.swift').read_text()
        for forbidden in ['import Speech','SFSpeechRecognizer','URLSession','downloadAndLoad','loadWithAutoRecovery','AsrModels.load(']: self.assertNotIn(forbidden,source)
        for required in ['AsrModels.loadLocal(', 'version: .v3','encoderPrecision: .int8V2','parallelChunkConcurrency: 1','manager.cleanup()', 'withTaskCancellationHandler','worker.cancel()', 'seconds(45)']: self.assertIn(required,source)
    def test_model_manifest_and_runtime_hash_are_bound(self):
        lock_path=ROOT/'tools/asr-resource-lock.json'; raw=lock_path.read_bytes(); lock=json.loads(raw)
        self.assertEqual(lock['schemaVersion'],1)
        self.assertRegex(lock['revision'],r'^[a-f0-9]{40}$')
        self.assertEqual(lock['repository'],'FluidInference/parakeet-tdt-0.6b-v3-coreml')
        self.assertIn('JointDecisionv3.mlmodelc/weights/weight.bin',lock['files'])
        self.assertIn('Encoder_v2.mlmodelc/weights/weight.bin',lock['files'])
        self.assertNotIn('Encoder.mlmodelc/weights/weight.bin',lock['files'])
        self.assertEqual(len(lock['files']),20)
        self.assertNotIn('JointDecision.mlmodelc/weights/weight.bin',lock['files'])
        self.assertIn(hashlib.sha256(raw).hexdigest(),(ROOT/'VoiceMatrix/BundledASRAssets.swift').read_text())
        total=sum(item['size'] for item in lock['files'].values())
        self.assertGreater(total,400_000_000);self.assertLess(total,700_000_000)

    def test_confidence_cannot_use_sdk_fallback(self):
        source=(ROOT/'VoiceMatrix/OnDeviceTranscription.swift').read_text()
        self.assertIn('let timings = result.tokenTimings',source)
        self.assertIn('BundledASRPolicy.admittedTokenMean',source)
        self.assertNotIn('result.confidence >=',source)
        self.assertIn('inputSHA256',source)
        self.assertIn('transcriptSHA256',source)

    def test_native_token_evidence_policy(self):
        import shutil, subprocess
        compiler=shutil.which('swiftc')
        if not compiler: self.skipTest('Swift unavailable; real token-evidence policy not executed')
        with tempfile.TemporaryDirectory() as directory:
            binary=pathlib.Path(directory)/'asr-policy'
            subprocess.run([compiler,str(ROOT/'VoiceMatrix/BundledASRPolicy.swift'),str(ROOT/'tests/native/BundledASRPolicyChecks.swift'),'-o',str(binary)],check=True,timeout=60)
            subprocess.run([str(binary)],check=True,timeout=10)

    def test_placeholder_matches_runtime_packaging_allowance(self):
        from tools import bundle_asr
        import zipfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            root=pathlib.Path(directory); lock=self.lock(); manifest=root/'lock.json'
            manifest.write_text(json.dumps(lock)); archive=root/'app.ipa'
            prefix='Payload/VoiceMatrix.app/ParakeetASR/'
            for placeholder in [b'',b'unexpected']:
                with zipfile.ZipFile(archive,'w') as out:
                    out.writestr(prefix+'Encoder.mlmodelc/weights/weight.bin',b'model-fixture')
                    out.writestr(prefix+'resource-lock.json',manifest.read_bytes())
                    out.writestr(prefix+'.gitkeep',placeholder)
                    for notice in (ROOT/'VoiceMatrix/Resources/ParakeetNotices').iterdir():
                        out.writestr('Payload/VoiceMatrix.app/ParakeetNotices/'+notice.name,notice.read_bytes())
                with patch.object(bundle_asr,'LOCK',manifest):
                    if placeholder:
                        with self.assertRaises(ValueError):bundle_asr.inspect_ipa(archive,lock)
                    else:self.assertEqual(bundle_asr.inspect_ipa(archive,lock)['asrBundle'],'verified')

    def test_full_ipa_and_ui_workflows_include_asr_gates(self):
        workflow=(ROOT/'.github/workflows/voicematrix-049-candidate.yml').read_text()
        self.assertIn('needs: [resolve, ipa, speech, conversion, bundled-asr]', workflow)
        self.assertIn('uses: ./.github/workflows/bundled-asr-diagnostic.yml', workflow)
        self.assertIn('  workflow_call:', (ROOT/'.github/workflows/bundled-asr-diagnostic.yml').read_text())
        self.assertIn('python3 tools/bundle_asr.py\n',workflow)
        self.assertIn('python3 tools/bundle_asr.py --inspect-ipa VoiceMatrix-0.4.9-character-test.ipa',workflow)
        ui=(ROOT/'.github/workflows/character-ui-smoke.yml').read_text()
        self.assertEqual(ui.count('-only-testing:VoiceMatrixTests/BundledASRTests'),2)
        source=(ROOT/'VoiceMatrix/LocalVideoStudio.swift').read_text()
        self.assertIn('transcription-evidence-',source)
        self.assertIn('preview-asr-evidence-',source)

    def test_native_diagnostic_uses_actual_known_words_and_no_network(self):
        workflow=(ROOT/'.github/workflows/bundled-asr-diagnostic.yml').read_text()
        diagnostic=(ROOT/'probes/native-asr/Diagnostic.swift').read_text()
        self.assertIn('(deny network*)',workflow)
        self.assertIn('  push:',workflow)
        self.assertIn("'VoiceMatrix/OnDeviceTranscription.swift'",workflow)
        self.assertIn("'tools/asr-resource-lock.json'",workflow)
        self.assertIn('try await transcriber.transcribe',diagnostic)
        self.assertIn('guard wer <= 0.1',diagnostic)
        self.assertIn('transcriber.lastEvidence',diagnostic)
        self.assertIn('fullLocalPipelineVerified = false',diagnostic)
        self.assertNotIn('mocks',diagnostic)

    def test_stream_reads_are_bounded_even_for_large_assets(self):
        from tools.bundle_asr import stage, CHUNK
        class BoundedStream(io.BytesIO):
            def read(self, count=-1):
                if not 0 < count <= CHUNK: raise AssertionError('Unbounded model read')
                return super().read(count)
        data=b'x'*(CHUNK*2+13)
        with tempfile.TemporaryDirectory() as directory:
            stage(directory,self.lock(data),lambda _:BoundedStream(data))

    def test_notices_and_asset_selection_are_packaged(self):
        project=(ROOT/'project.yml').read_text()
        self.assertIn('VoiceMatrix/Resources/ParakeetASR',project)
        self.assertIn('VoiceMatrix/Resources/ParakeetNotices',project)
        notices=(ROOT/'VoiceMatrix/Resources/ParakeetNotices/ATTRIBUTION.txt').read_text()
        self.assertIn('Apache 2.0. See the FluidAudio repository for details and usage guidance.',notices)
        self.assertIn('CC-BY-4.0',notices)
        self.assertTrue((ROOT/'VoiceMatrix/Resources/ParakeetNotices/CC-BY-4.0.txt').stat().st_size > 10000)
        self.assertTrue((ROOT/'VoiceMatrix/Resources/ParakeetNotices/FluidAudio-APACHE-2.0.txt').stat().st_size > 10000)

    def test_packaging_without_required_notices_fails(self):
        from tools import bundle_asr
        import zipfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            root=pathlib.Path(directory);lock=self.lock();manifest=root/'lock.json';manifest.write_text(json.dumps(lock));archive=root/'app.ipa'
            prefix='Payload/VoiceMatrix.app/ParakeetASR/'
            with zipfile.ZipFile(archive,'w') as out:
                out.writestr(prefix+'Encoder.mlmodelc/weights/weight.bin',b'model-fixture')
                out.writestr(prefix+'resource-lock.json',manifest.read_bytes())
            with patch.object(bundle_asr,'LOCK',manifest):
                with self.assertRaises(ValueError):bundle_asr.inspect_ipa(archive,lock)

    def test_source_identity_is_rechecked_after_sdk_reopens_audio(self):
        source=(ROOT/'VoiceMatrix/OnDeviceTranscription.swift').read_text()
        self.assertIn('matching: inputSHA256',source)
        self.assertLess(source.index('manager.transcribe(file'),source.index('matching: inputSHA256'))
        self.assertLess(source.index('matching: inputSHA256'),source.index('let evidence = Evidence'))
