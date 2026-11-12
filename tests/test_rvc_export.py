"""File/evidence contract tests; fixture bytes are not neural models."""
import hashlib
import json
import pathlib
import tempfile
import unittest
import wave


def digest(data):
    return hashlib.sha256(data).hexdigest()


class RVCExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.model = self.root / 'original.pth'
        self.index = self.root / 'added_original.index'
        self.model.write_bytes(b'opaque tested model fixture')
        self.index.write_bytes(b'opaque tested index fixture')
        self.wav = self.root / 'converted.wav'
        with wave.open(str(self.wav), 'wb') as stream:
            stream.setparams((1, 2, 40000, 0, 'NONE', 'none'))
            stream.writeframes(b'\x00\x10' * 40000)
        self.evidence = {
            'schemaVersion': 1,
            'status': 'conversion-checked-needs-review',
            'sourceRevision': '81eed5e8f68b6bed1789f682fe78cdd324495afc',
            'model': str(self.model), 'modelSHA256': digest(self.model.read_bytes()),
            'index': str(self.index), 'indexSHA256': digest(self.index.read_bytes()),
            'output': str(self.wav), 'outputSHA256': digest(self.wav.read_bytes()),
            'modelVersion': 'v2', 'sampleRate': 40000,
            'featureDimensions': 768, 'indexVectors': 42,
            'audioPassed': True, 'wordcheck': {'passed': True, 'wordErrorRate': 0.0,
                'wavSHA256': digest(self.wav.read_bytes())},
            'identityVerified': False, 'likenessVerified': False,
            'physicalDeviceVerified': False,
            'trainingReportSHA256':'2'*64,
            'effectiveTrainingData':dict(gateVersion=1,status='passed',minimumActiveSeconds=60,activeLowerBoundSeconds=64,effectiveDatasetSHA256='3'*64),
        }
        self.report = self.root / 'conversion.json'
        self.report.write_text(json.dumps(self.evidence))
        self.metadata = dict(id='original-speaker', name='Original speaker',
            categories=['Original'], source='Synthetic test', permission='Original synthetic test')

    def export(self, **kwargs):
        from tools.rvc_export import export_folder
        return export_folder(self.report, self.metadata, self.root / 'RVCVoices', **kwargs)

    def test_export_preserves_exact_model_index_and_truthful_capabilities(self):
        result = self.export()
        self.assertIsNotNone(result, "A verified RVC export folder is required")
        folder = pathlib.Path(result)
        manifest = json.loads((folder / 'manifest.json').read_text())
        self.assertEqual((folder / 'model.pth').read_bytes(), self.model.read_bytes())
        self.assertEqual((folder / 'model.index').read_bytes(), self.index.read_bytes())
        self.assertEqual(manifest['format'], 'rvc-v2-pth-index')
        self.assertFalse(manifest['nativeIPhoneRuntimeVerified'])
        self.assertFalse(manifest['likenessVerified'])
        self.assertEqual(manifest['status'], 'conversion-checked-needs-review')
        self.assertEqual(sorted(x.name for x in folder.iterdir()), ['manifest.json', 'model.index', 'model.pth'])
        self.assertTrue(self.wav.exists())
        self.assertNotIn(str(self.root), (folder / 'manifest.json').read_text())

    def test_changed_weights_or_index_never_export(self):
        for file in (self.model, self.index):
            old = file.read_bytes()
            file.write_bytes(b'changed')
            with self.assertRaises(ValueError): self.export()
            self.assertFalse((self.root / 'RVCVoices' / 'original-speaker').exists())
            file.write_bytes(old)

    def test_missing_failed_or_unbound_conversion_proof_is_rejected(self):
        for update in ({'status': 'trained-needs-independent-conversion-check'},
                       {'effectiveTrainingData':{}}, {'trainingReportSHA256':'bad'},
                       {'effectiveTrainingData':dict(self.evidence['effectiveTrainingData'],activeLowerBoundSeconds=59.9)},
                       {'audioPassed': False}, {'featureDimensions': 256},
                       {'wordcheck': {'passed': True, 'wordErrorRate': 0, 'wavSHA256': '0' * 64}}):
            self.report.write_text(json.dumps(dict(self.evidence, **update)))
            with self.assertRaises(ValueError): self.export()
        self.assertFalse((self.root / 'RVCVoices' / 'original-speaker').exists())

    def test_existing_character_and_reference_collection_are_preserved(self):
        destination = self.root / 'RVCVoices' / 'original-speaker'
        destination.mkdir(parents=True)
        (destination / 'model.pth').write_bytes(b'original bytes')
        with self.assertRaises(FileExistsError): self.export()
        self.assertEqual((destination / 'model.pth').read_bytes(), b'original bytes')

    def test_unsafe_ids_and_symlink_destinations_are_rejected(self):
        for identifier in ('../old', '/old', 'old\\new'):
            self.metadata['id'] = identifier
            with self.assertRaises(ValueError): self.export()
        self.metadata['id'] = 'original-speaker'
        destination = self.root / 'RVCVoices'
        elsewhere = self.root / 'elsewhere'; elsewhere.mkdir()
        destination.symlink_to(elsewhere, target_is_directory=True)
        with self.assertRaises(ValueError): self.export()
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_cancelled_export_publishes_nothing(self):
        with self.assertRaises(InterruptedError): self.export(cancelled=lambda: True)
        self.assertFalse((self.root / 'RVCVoices').exists())

if __name__ == '__main__':
    unittest.main()
