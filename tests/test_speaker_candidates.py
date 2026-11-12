"""Fast orchestration tests use fixed embeddings, never claim neural accuracy."""
import contextlib
import io
import json
import math
import pathlib
import struct
import tempfile
import unittest
import wave
from unittest import mock
try:
    import numpy as np
except ImportError:
    np = None

try:
    from tools import speaker_candidates as sc
except ImportError:
    sc = None


class FixtureModel:
    """Boundary double: neural regions/embeddings are deliberately controlled."""
    def __init__(self, regions, embeddings):
        self.regions = regions
        self.embeddings = iter(embeddings)

    def speech_regions(self, audio, cancelled):
        if cancelled():
            raise InterruptedError('Analysis cancelled')
        return self.regions

    def embed(self, audio):
        return np.asarray(next(self.embeddings), dtype=np.float32)


def write_wav(path, seconds=8, rate=16000, channels=1, width=2, silent=False):
    samples = np.zeros(round(seconds * rate), dtype='<i2') if silent else (
        np.sin(np.arange(round(seconds * rate)) * .08) * 4000).astype('<i2')
    with wave.open(str(path), 'wb') as w:
        w.setparams((channels, width, rate, 0, 'NONE', 'none'))
        w.writeframes(samples.tobytes())


class SpeakerCandidateTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(sc, 'The anonymous speaker-candidate component is missing')
        if np is None and self._testMethodName not in ('test_checkpoint_hash_rejected_before_any_neural_loading', 'test_cli_output_is_atomic_json_and_bounded', 'test_cli_protects_default_vad_input', 'test_existing_voice_output_is_never_overwritten', 'test_vad_loader_uses_verified_bytes_and_removes_private_copy'):
            self.skipTest('Optional speaker-engine NumPy dependency is not installed')
        if self._testMethodName.startswith('test_') and self._testMethodName not in ('test_checkpoint_hash_rejected_before_any_neural_loading', 'test_cli_output_is_atomic_json_and_bounded', 'test_cli_protects_default_vad_input', 'test_existing_voice_output_is_never_overwritten', 'test_vad_loader_uses_verified_bytes_and_removes_private_copy'):
            import importlib.util
            if importlib.util.find_spec('sklearn') is None:
                self.skipTest('Optional speaker-engine scikit-learn dependency is not installed')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = pathlib.Path(self.tmp.name) / 'input.wav'

    def test_same_voice_regions_yield_one_tentative_representative(self):
        write_wav(self.path, seconds=10)
        # Two 4-second separated turns, each full/left/right embedding agrees.
        model = FixtureModel([(0, 64000), (96000, 160000)], [[1, 0]] * 6)
        report = sc.analyze(self.path, model)
        self.assertEqual(report['status'], 'candidates')
        self.assertEqual(len(report['candidates']), 1)
        row = report['candidates'][0]
        self.assertEqual(row['group'], 1)
        self.assertGreaterEqual(row['end'] - row['start'], 3)
        self.assertLessEqual(row['end'] - row['start'], 12)
        self.assertIsNone(row['confidence'])
        self.assertIn('overlap-not-assessed', row['uncertainty'])
        self.assertFalse(report['labelsVerified'])
        self.assertFalse(report['speakerSeparated'])
        self.assertEqual(report['overlapDetection'], 'not-supported')
        self.assertFalse(report['truncated'])

    def test_distinct_embeddings_keep_different_anonymous_groups(self):
        write_wav(self.path, seconds=10)
        model = FixtureModel([(0, 64000), (96000, 160000)], [[1, 0]] * 3 + [[0, 1]] * 3)
        rows = sc.analyze(self.path, model)['candidates']
        self.assertEqual([r['group'] for r in rows], [1, 2])
        self.assertEqual([(r['start'], r['end']) for r in rows], [(0, 4), (6, 10)])

    def test_member_intervals_retain_original_windows_without_changing_candidates(self):
        write_wav(self.path, seconds=20)
        report = sc.analyze(self.path, FixtureModel([(0, 320000)], [[1, 0]] * 9))
        self.assertEqual(report.get('memberIntervals'), [
            {'group': 1, 'start': 0.0, 'end': 8.0},
            {'group': 1, 'start': 6.0, 'end': 14.0},
            {'group': 1, 'start': 12.0, 'end': 20.0},
        ])
        self.assertEqual(report['candidates'][0], {
            'start': 0.0, 'end': 8.0, 'group': 1, 'confidence': None,
            'score': 1.0, 'uncertainty': ['label-unverified', 'overlap-not-assessed',
                                      'grouping-not-calibrated'], 'supportingWindows': 3,
        })

    def test_bounded_member_intervals_and_result_at_window_limit(self):
        write_wav(self.path, seconds=60)
        # Exercise the limit cheaply without loading any neural model.
        with mock.patch.object(sc, 'MAX_WINDOWS', 8):
            report = sc.analyze(self.path, FixtureModel([(0, 960000)], [[1, 0]] * 24))
        self.assertEqual(len(report.get('memberIntervals', [])), 8)
        self.assertTrue(report['truncated'])
        self.assertLessEqual(len(json.dumps(report).encode()), 128 * 1024)

    def test_changes_within_window_are_omitted_instead_of_false_clean_claim(self):
        write_wav(self.path, seconds=4)
        model = FixtureModel([(0, 64000)], [[1, 1], [1, 0], [0, 1]])
        report = sc.analyze(self.path, model)
        self.assertEqual(report['candidates'], [])
        self.assertIn('unstable-voice-window', [r['reason'] for r in report['omitted']])

    def test_no_speech_is_empty_without_synthetic_speaker(self):
        write_wav(self.path, silent=True)
        report = sc.analyze(self.path, FixtureModel([], []))
        self.assertEqual(report['status'], 'no-candidates')
        self.assertEqual(report['candidates'], [])

    def test_short_speech_is_omitted(self):
        write_wav(self.path, seconds=2)
        report = sc.analyze(self.path, FixtureModel([(0, 32000)], []))
        self.assertEqual(report['candidates'], [])
        self.assertEqual(report['omitted'][0]['reason'], 'speech-too-short')

    def test_clipping_is_omitted_before_embedding(self):
        with wave.open(str(self.path), 'wb') as w:
            w.setparams((1, 2, 16000, 0, 'NONE', 'none'))
            w.writeframes(b'\xff\x7f' * 64000)
        report = sc.analyze(self.path, FixtureModel([(0, 64000)], []))
        self.assertEqual(report['candidates'], [])
        self.assertEqual(report['omitted'][0]['reason'], 'clipped-window')

    def test_invalid_format_truncation_and_overlong_header_rejected(self):
        for rate, channels, width in [(8000, 1, 2), (16000, 2, 2), (16000, 1, 1)]:
            write_wav(self.path, rate=rate, channels=channels, width=width)
            with self.assertRaises(ValueError):
                sc.analyze(self.path, FixtureModel([], []))
        write_wav(self.path)
        data = self.path.read_bytes()
        self.path.write_bytes(data[:-20])
        with self.assertRaises(ValueError):
            sc.analyze(self.path, FixtureModel([], []))
        data = bytearray(data)
        struct.pack_into('<I', data, 40, 1801 * 16000 * 2)
        self.path.write_bytes(data)
        with self.assertRaises(ValueError):
            sc.analyze(self.path, FixtureModel([], []))

    def test_cancelled_analysis_does_not_return_partial_success(self):
        write_wav(self.path)
        with self.assertRaises(InterruptedError):
            sc.analyze(self.path, FixtureModel([], []), cancelled=lambda: True)

    def test_nan_and_zero_embeddings_rejected(self):
        write_wav(self.path, seconds=4)
        for vector in [[math.nan, 1], [0, 0]]:
            with self.assertRaises(ValueError):
                sc.analyze(self.path, FixtureModel([(0, 64000)], [vector]))

    def test_regions_outside_audio_and_overlapping_regions_rejected(self):
        write_wav(self.path, seconds=4)
        for regions in [[(-1, 50000)], [(0, 64001)], [(0, 50000), (40000, 60000)]]:
            with self.assertRaises(ValueError):
                sc.analyze(self.path, FixtureModel(regions, []))

    def test_more_than_32_groups_are_omitted_not_merged(self):
        write_wav(self.path, seconds=35 * 5)
        regions = [(i * 80000, i * 80000 + 64000) for i in range(35)]
        vectors = [v for row in np.eye(35) for v in [row, row, row]]
        report = sc.analyze(self.path, FixtureModel(regions, vectors))
        self.assertEqual(len(report['candidates']), 32)
        self.assertTrue(report['truncated'])
        self.assertTrue(report.get('groupLimitExceeded'))
        self.assertEqual(sum(x['reason'] == 'group-limit' for x in report['omitted']), 3)

    def test_checkpoint_hash_rejected_before_any_neural_loading(self):
        bad = pathlib.Path(self.tmp.name) / 'embedding_model.ckpt'
        bad.write_bytes(b'not a checkpoint')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            sc.load_local_encoder(bad)

    def test_cli_protects_default_vad_input(self):
        self.path.write_bytes(b'input-must-not-be-opened')
        checkpoint = pathlib.Path(self.tmp.name) / 'embedding_model.ckpt'
        vad = checkpoint.with_name('silero_vad.onnx')
        vad.write_bytes(b'preserve-vad')
        model = FixtureModel([], [])
        with mock.patch.object(sc, 'load_local_encoder', return_value=model):
            with contextlib.redirect_stderr(io.StringIO()):
                code = sc.main(['--audio', str(self.path), '--checkpoint', str(checkpoint), '--output', str(vad)])
        self.assertEqual(code, 1)
        self.assertEqual(vad.read_bytes(), b'preserve-vad')

    def test_existing_voice_output_is_never_overwritten(self):
        target = pathlib.Path(self.tmp.name) / 'saved-voice.wav'
        target.write_bytes(b'original-voice')
        with self.assertRaises(FileExistsError):
            sc.write_result(target, {'status': 'no-candidates', 'candidates': []})
        self.assertEqual(target.read_bytes(), b'original-voice')

    def test_vad_loader_uses_verified_bytes_and_removes_private_copy(self):
        # Replacing a path after validation must not change the bytes opened by ONNX.
        seen = []
        paths = []
        def open_model(path, force_onnx_cpu):
            paths.append(pathlib.Path(path))
            seen.append(pathlib.Path(path).read_bytes())
            return 'loaded'
        self.assertEqual(sc._load_verified_vad(b'verified-vad', open_model), 'loaded')
        self.assertEqual(seen, [b'verified-vad'])
        self.assertFalse(paths[0].exists())

    def test_cli_output_is_atomic_json_and_bounded(self):
        target = pathlib.Path(self.tmp.name) / 'result.json'
        sc.write_result(target, {'status': 'no-candidates', 'candidates': []})
        self.assertEqual(json.loads(target.read_text())['candidates'], [])
        previous = target.read_bytes()
        with self.assertRaises(ValueError):
            sc.write_result(target, {'bad': 'x' * 131073})
        self.assertEqual(target.read_bytes(), previous)
        with self.assertRaises(ValueError):
            sc.write_result(target, {'bad': float('nan')})
        self.assertEqual(target.read_bytes(), previous)


if __name__ == '__main__':
    unittest.main()
