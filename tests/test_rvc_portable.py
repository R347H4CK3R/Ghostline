"""Source-only admission/report tests. Fixture bytes are NOT neural models.

No test fabricates a successful ONNX export or successful neural parity report.
Only the isolated export/runtime process is replaced in orchestration tests.
"""
import hashlib
import importlib.util
import json
import math
import pathlib
import subprocess
import sys
import tempfile
import threading
import unittest
import wave
from unittest import mock


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PortableAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('tools.rvc_portable'),
                             'The bounded portable feasibility adapter is missing')
        from tools import rvc_portable
        self.api = rvc_portable
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name).resolve()
        self.upstream = self.root / 'upstream'; self.upstream.mkdir()
        self.model = self.root / 'model.pth'; self.model.write_bytes(b'not a neural model')
        self.index = self.root / 'model.index'; self.index.write_bytes(b'not a neural index')
        self.audio = self.root / 'converted.wav'
        with wave.open(str(self.audio), 'wb') as stream:
            stream.setparams((1, 2, 40000, 0, 'NONE', 'none'))
            stream.writeframes(b'\x00\x10' * 40000)
        self.proof = self.root / 'conversion.json'
        self.body = dict(schemaVersion=1, status='conversion-checked-needs-review',
                         sourceRevision='81eed5e8f68b6bed1789f682fe78cdd324495afc',
                         model=str(self.model), modelSHA256=digest(self.model),
                         index=str(self.index), indexSHA256=digest(self.index),
                         output=str(self.audio), outputSHA256=digest(self.audio),
                         modelVersion='v2', sampleRate=40000, featureDimensions=768,
                         indexVectors=42, audioPassed=True,
                         trainingReportSHA256='2'*64,
                         effectiveTrainingData=dict(gateVersion=1,status='passed',minimumActiveSeconds=60,activeLowerBoundSeconds=64,effectiveDatasetSHA256='3'*64),
                         wordcheck=dict(passed=True, wordErrorRate=0,
                                        wavSHA256=digest(self.audio)))
        self.rebind()
        self.destination = self.root / 'private-portable-check'

    def rebind(self):
        self.proof.write_text(json.dumps(self.body))
        self.proof_hash = digest(self.proof)
        self.provenance = dict(kind='synthetic-test-fixture',
                               modelSHA256=digest(self.model),
                               conversionProofSHA256=self.proof_hash,
                               source='Original generated engineering fixture',
                               permission='Authorized synthetic fixture')

    def export(self, **kwargs):
        return self.api.export_synthesizer(
            self.upstream, self.proof, self.destination,
            proof_sha256=self.proof_hash, synthetic_provenance=self.provenance, **kwargs)

    def report(self):
        return json.loads((self.destination / 'portable.json').read_text())

    def test_effective_training_gate_and_report_digest_are_required(self):
        mutations = [
            ('missing gate', lambda p: p.pop('effectiveTrainingData')),
            ('missing report digest', lambda p: p.pop('trainingReportSHA256')),
            ('invalid report digest', lambda p: p.update(trainingReportSHA256='not-a-hash')),
            ('non-object gate', lambda p: p.update(effectiveTrainingData=[])),
        ]
        for field, values in {
            'gateVersion': [None, True, 1.0, 2],
            'status': [None, 'failed'],
            'minimumActiveSeconds': [None, True, '60', 59, 61],
            'activeLowerBoundSeconds': [None, True, '64', 40.195, 59.999, 1801, math.nan, math.inf],
            'effectiveDatasetSHA256': [None, '3' * 63, 'G' * 64],
        }.items():
            for value in values:
                mutations.append((field + '=' + repr(value),
                                  lambda p, k=field, v=value: p['effectiveTrainingData'].update({k: v})))
        for label, mutate in mutations:
            proof = json.loads(json.dumps(self.body))
            mutate(proof)
            with self.subTest(case=label), self.assertRaises(ValueError):
                self.api._checked_proof(json.dumps(proof))

    def test_valid_effective_training_boundary_is_admitted(self):
        for seconds in (60, 60.0, 1800):
            self.body['effectiveTrainingData']['activeLowerBoundSeconds'] = seconds
            self.assertEqual(self.api._checked_proof(json.dumps(self.body)), self.body)

    def test_proof_mutation_and_unbound_synthetic_provenance_prevent_creation(self):
        self.proof.write_text('{}')
        with self.assertRaises(ValueError): self.export()
        self.assertFalse(self.destination.exists())
        self.rebind()
        for key, value in [('kind', 'character'), ('modelSHA256', '0' * 64),
                           ('conversionProofSHA256', '0' * 64), ('permission', '')]:
            old = self.provenance[key]; self.provenance[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): self.export()
            self.provenance[key] = old
        self.assertFalse(self.destination.exists())

    def test_failed_proof_or_changed_artifacts_never_reach_export(self):
        for key, value in [('audioPassed', False), ('sampleRate', 24000),
                           ('status', 'trained-needs-independent-conversion-check')]:
            old = self.body[key]; self.body[key] = value; self.rebind()
            with self.subTest(key=key), self.assertRaises(ValueError): self.export()
            self.body[key] = old
        self.rebind()
        for artifact in (self.model, self.index, self.audio):
            old = artifact.read_bytes(); artifact.write_bytes(b'changed')
            with self.subTest(path=artifact.name), self.assertRaises(ValueError): self.export()
            artifact.write_bytes(old)
        self.assertFalse(self.destination.exists())

    def test_linked_ancestors_upstream_and_f5_destinations_are_rejected(self):
        elsewhere = self.root / 'elsewhere'; elsewhere.mkdir()
        link = self.root / 'linked'; link.symlink_to(elsewhere, target_is_directory=True)
        for folder in (link / 'out', self.upstream / 'out'):
            self.destination = folder
            with self.assertRaises(ValueError): self.export()
            self.assertFalse(folder.exists())
        (elsewhere / 'collection.json').write_text('{}')
        self.destination = elsewhere / 'out'
        with self.assertRaises(ValueError): self.export()
        self.assertFalse(self.destination.exists())

    def test_existing_destination_is_preserved(self):
        self.destination.mkdir(); sentinel = self.destination / 'kept'
        sentinel.write_bytes(b'preserve')
        with self.assertRaises(FileExistsError): self.export()
        self.assertEqual(sentinel.read_bytes(), b'preserve')

    def test_invalid_timeout_and_pre_cancel_do_not_create_outputs(self):
        for timeout in (True, 0, -1, math.inf, math.nan, 1801):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                self.export(timeout=timeout)
        cancel = threading.Event(); cancel.set()
        with self.assertRaises(InterruptedError): self.export(cancel=cancel)
        self.assertFalse(self.destination.exists())

    def test_external_failure_records_failure_without_portability_claim(self):
        with mock.patch.object(self.api, 'run_stage', side_effect=RuntimeError('export operator unsupported')):
            with self.assertRaisesRegex(RuntimeError, 'unsupported'): self.export()
        report = self.report()
        self.assertEqual(report['status'], 'failed')
        self.assertFalse(report['synthesizerParityVerified'])
        self.assertTrue(all(value is False for value in report['capabilities'].values()))
        self.assertEqual(digest(self.destination / 'model.pth'), digest(self.model))

    def test_cancel_after_child_cannot_publish_success(self):
        cancel = threading.Event()
        def stop(*args, **kwargs): cancel.set()
        with mock.patch.object(self.api, 'run_stage', side_effect=stop):
            with self.assertRaises(InterruptedError): self.export(cancel=cancel)
        self.assertEqual(self.report()['status'], 'cancelled')

    def test_incomplete_or_unbound_child_success_is_rejected(self):
        def malformed(*args, **kwargs):
            (self.destination / 'child-result.json').write_text(json.dumps(
                dict(status='synthesizer-parity-checked', modelSHA256='0' * 64)))
        with mock.patch.object(self.api, 'run_stage', side_effect=malformed):
            with self.assertRaises(ValueError): self.export()
        self.assertEqual(self.report()['status'], 'failed')
        self.assertFalse(self.report()['synthesizerParityVerified'])

    def test_replaced_snapshot_is_rejected_before_reading_child_claims(self):
        def replace(*args, **kwargs):
            (self.destination / 'model.pth').write_bytes(b'changed')
        with mock.patch.object(self.api, 'run_stage', side_effect=replace):
            with self.assertRaises(ValueError): self.export()
        self.assertEqual(self.report()['status'], 'failed')

    def test_import_and_help_never_load_neural_packages(self):
        script = """import sys
class Deny:
 def find_spec(self, fullname, *args):
  if fullname.split('.')[0] in {'torch','numpy','onnx','onnxruntime'}:
   raise RuntimeError('Neural import during help')
sys.meta_path.insert(0,Deny())
import runpy
sys.argv=['tools.rvc_portable','--help']
runpy.run_module('tools.rvc_portable',run_name='__main__')
"""
        result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


class PortableMetricTests(unittest.TestCase):
    def metrics(self, expected, actual):
        from tools.rvc_portable import error_metrics
        return error_metrics(expected, actual)

    def test_measures_actual_max_and_rms_error(self):
        result = self.metrics([0., .5], [.001, .498])
        self.assertAlmostEqual(result['maxAbs'], .002)
        self.assertAlmostEqual(result['rms'], math.sqrt(.0000025))
        self.assertEqual(result['count'], 2)

    def test_empty_length_mismatch_and_nonfinite_outputs_fail(self):
        for left, right in [([], []), ([0.], []), ([0.], [math.nan]),
                            ([math.inf], [0.]), ([False], [0.])]:
            with self.subTest(left=left, right=right), self.assertRaises(ValueError):
                self.metrics(left, right)

    def test_waveform_reopen_is_bound_to_the_manifest_hash(self):
        from tools import rvc_portable
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory).resolve() / 'original.f32'
            path.write_bytes(b'\x00\x00\x80\x3f')
            original_hash = digest(path)
            path.write_bytes(b'\x00\x00\x00\x00')
            with self.assertRaises(ValueError):
                rvc_portable.read_waveform(path, original_hash)


if __name__ == '__main__':
    unittest.main()
