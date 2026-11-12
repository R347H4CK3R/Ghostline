"""Real PCM/file orchestration; acquisition and anonymous neural analysis are fixtures."""
import array
import contextlib
import copy
import hashlib
import json
import os
import pathlib
import shutil
import tempfile
import unittest
import wave
from unittest import mock

try:
    from tools import rvc_dataset_prepare as dataset
except ImportError:
    dataset = None


def write_source(path, seconds=80, *, silent_after=None, repeated=False):
    with wave.open(str(path), 'wb') as stream:
        stream.setparams((1, 2, 16000, 0, 'NONE', 'none'))
        for second in range(seconds):
            if silent_after is not None and second >= silent_after:
                pcm = b'\0\0' * 16000
            else:
                frequency = 7 if repeated else second + 7
                values = array.array('h', ((i * frequency % 6000) - 3000 for i in range(16000)))
                if os.sys.byteorder != 'little':
                    values.byteswap()
                pcm = values.tobytes()
            stream.writeframes(pcm)


def analysis(groups, duration=80):
    return dict(schemaVersion=1, engine='fixture-boundary', status='candidates',
                durationSeconds=duration, candidates=[dict(group=g, start=spans[0][0],
                end=min(spans[0][0] + 8, spans[0][1]), confidence=None, score=.8,
                supportingWindows=len(spans), uncertainty=['label-unverified'])
                for g, spans in groups.items()],
                memberIntervals=[dict(group=g, start=a, end=b)
                                 for g, spans in groups.items() for a, b in spans],
                labelsVerified=False, speakerSeparated=False, overlapDetection='not-supported',
                truncated=False, omitted=[], omittedCount=0)


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(dataset, 'The source-only RVC dataset preparer is missing')
        if not shutil.which('ffmpeg'):
            self.skipTest('Local ffmpeg is required for real fixture extraction')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.output = self.root / 'datasets'
        self.source = self.root / 'original.wav'
        write_source(self.source)
        self.request = dict(schemaVersion=1, format='rvc-v2-pth-index',
                            requestID='e23e8d36-a086-4660-a017-367444016be0',
                            videoURL='https://www.youtube.com/watch?v=SYNTHETIC03',
                            sourceUse=dict(decision='approved-private-rvc-training', record='Owned synthetic audio'))
        self.acquisitions = []
        self.events = []

    @contextlib.contextmanager
    def acquire(self, url, segments, **kwargs):
        self.assertEqual(url, self.request['videoURL'])
        self.assertLessEqual(kwargs['max_duration'], 1800)
        self.assertLessEqual(kwargs['max_bytes'], 268435456)
        with tempfile.TemporaryDirectory(dir=self.root, prefix='acquired-') as temporary:
            movie = pathlib.Path(temporary) / 'source.mp4'
            shutil.copyfile(self.source, movie)
            self.acquisitions.append(movie)
            yield dict(privateMoviePath=str(movie), sourceURL=url, title='Fixture source',
                       videoID='SYNTHETIC03', sourceSHA256=hashlib.sha256(movie.read_bytes()).hexdigest(),
                       segments=[], authorizedLikeness=False)

    def prepare(self, report=None, **kwargs):
        report = report or analysis({1: [(0, 75)]})
        def analyze(path, *, cancelled):
            with wave.open(str(path)) as stream:
                self.assertEqual((stream.getframerate(), stream.getnchannels(), stream.getsampwidth()), (16000, 1, 2))
                self.assertLessEqual(stream.getnframes(), 1800 * 16000)
            if cancelled():
                raise InterruptedError('Cancelled fixture analysis')
            return copy.deepcopy(report)
        path = dataset.prepare(self.request, self.output, analyze=analyze, acquire_source=self.acquire,
                               activity=lambda *event: self.events.append(event), **kwargs)
        return path, dataset.load_manifest(path, request=self.request)

    def test_admits_real_disjoint_audio_and_reserves_held_out_before_sixty_second_floor(self):
        path, manifest = self.prepare()
        group = manifest['groups'][0]
        self.assertEqual(group['status'], 'ready-for-training')
        self.assertEqual(group['uniqueSeconds'], 72)
        self.assertEqual(group['heldOutAudit']['uniqueSeconds'], 3)
        self.assertEqual(group['minimumSeconds'], 60)
        self.assertFalse(manifest['trained'])
        self.assertFalse(manifest['labelsVerified'])
        self.assertFalse(manifest['speakerSeparated'])
        self.assertFalse(manifest['likenessVerified'])
        self.assertEqual(manifest['overlapDetection'], 'not-supported')
        self.assertEqual(manifest['source']['sourceUse'], self.request['sourceUse'])
        self.assertIn('synthetic03', group['id'])
        self.assertNotIn('character', group)
        rows = group['trainingFiles'] + group['heldOutFiles']
        self.assertEqual(sum(r['end'] - r['start'] for r in rows), 75)
        ordered = sorted(rows, key=lambda r: r['start'])
        self.assertTrue(all(left['end'] <= right['start'] for left, right in zip(ordered, ordered[1:])))
        for row in rows:
            file = path.parent / row['file']
            self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(), row['sha256'])
            self.assertEqual(file.stat().st_size, row['bytes'])
            with wave.open(str(file)) as stream:
                self.assertEqual((stream.getframerate(), stream.getnchannels(), stream.getsampwidth()), (40000, 1, 2))
                self.assertAlmostEqual(stream.getnframes() / 40000, row['end'] - row['start'])
        self.assertTrue(all(not movie.exists() for movie in self.acquisitions))
        self.assertEqual(list(self.output.rglob('*.mp4')), [])
        if os.name != 'nt':
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)

    def test_completed_manifest_reuses_audited_audio_without_reacquisition_or_analysis(self):
        path, _ = self.prepare(analysis({1: [(0, 30)]}))
        again = dataset.prepare(self.request, self.output,
                                analyze=lambda *a, **kw: self.fail('Analysis repeated'),
                                acquire_source=lambda *a, **kw: self.fail('Source downloaded again'))
        self.assertEqual(again, path)
        self.assertEqual(dataset.load_manifest(path)['groups'][0]['status'], 'insufficient-data')

    def test_overlap_is_unioned_within_group_and_conflicts_excluded_from_every_group(self):
        _, manifest = self.prepare(analysis({1: [(0, 50), (25, 75)], 2: [(65, 80)]}))
        first, second = manifest['groups']
        self.assertEqual(first['uniqueSeconds'], 62)
        self.assertEqual(second['uniqueSeconds'], 2)
        self.assertEqual(second['status'], 'insufficient-data')
        rows = [row for g in manifest['groups'] for role in ('trainingFiles', 'heldOutFiles') for row in g[role]]
        self.assertTrue(all(row['end'] <= 65 or row['start'] >= 75 for row in rows))
        self.assertIn('ambiguous-group-overlap', [row['reason'] for row in manifest['omitted']])

    def test_sixty_total_seconds_does_not_meet_training_floor_after_held_out(self):
        _, manifest = self.prepare(analysis({1: [(0, 60)]}))
        self.assertEqual(manifest['groups'][0]['status'], 'insufficient-data')
        self.assertEqual(manifest['groups'][0]['uniqueSeconds'], 57)

    def test_exactly_sixty_active_training_seconds_meets_floor(self):
        _, manifest = self.prepare(analysis({1: [(0, 63)]}))
        self.assertEqual(manifest['groups'][0]['uniqueSeconds'], 60)
        self.assertEqual(manifest['groups'][0]['status'], 'ready-for-training')

    def test_fractional_vad_boundary_keeps_exact_three_second_held_out_ready_and_cached(self):
        path, manifest = self.prepare(analysis({1: [(0, 65.472)]}))
        group = manifest['groups'][0]
        self.assertEqual(group['uniqueSeconds'], 62.472)
        held_out = group['heldOutFiles'][0]
        self.assertEqual((held_out['start'], held_out['end']), (62.472, 65.472))
        with wave.open(str(path.parent / held_out['file'])) as stream:
            self.assertEqual(stream.getnframes(), 120000)
        self.assertEqual(group['status'], 'ready-for-training')
        self.assertNotIn('insufficient-held-out-data', [row['reason'] for row in manifest['omitted']])
        reused = dataset.prepare(self.request, self.output,
                                 analyze=lambda *a, **kw: self.fail('Fractional-boundary analysis repeated'),
                                 acquire_source=lambda *a, **kw: self.fail('Fractional-boundary source redownloaded'))
        self.assertEqual(reused, path)
        self.assertEqual(dataset.load_manifest(reused, request=self.request)['groups'][0]['status'],
                         'ready-for-training')

    def test_held_out_one_sample_below_three_seconds_does_not_meet_floor(self):
        spans = [(index * 3.5, index * 3.5 + 2.999975) for index in range(22)]
        path, manifest = self.prepare(analysis({1: spans}))
        group = manifest['groups'][0]
        self.assertGreaterEqual(group['uniqueSeconds'], 60)
        with wave.open(str(path.parent / group['heldOutFiles'][0]['file'])) as stream:
            self.assertEqual(stream.getnframes(), 119999)
        self.assertEqual(group['status'], 'insufficient-data')
        self.assertIn('insufficient-held-out-data', [row['reason'] for row in manifest['omitted']])

    def test_only_tiny_exclusive_fragments_cannot_claim_a_three_second_held_out(self):
        write_source(self.source, seconds=126)
        _, manifest = self.prepare(analysis({1: [(start, start + 1) for start in range(0, 126, 2)]}, duration=126))
        self.assertGreaterEqual(manifest['groups'][0]['uniqueSeconds'], 60)
        self.assertEqual(manifest['groups'][0]['status'], 'insufficient-data')
        self.assertIn('insufficient-held-out-data', [row['reason'] for row in manifest['omitted']])

    def test_silence_and_duplicate_content_never_inflate_active_seconds(self):
        write_source(self.source, silent_after=50)
        _, manifest = self.prepare()
        self.assertEqual(manifest['groups'][0]['status'], 'insufficient-data')
        self.assertLess(manifest['groups'][0]['uniqueSeconds'], 51)
        self.request['requestID'] = 'f23e8d36-a086-4660-a017-367444016be0'
        write_source(self.source, repeated=True)
        _, repeated = self.prepare(analysis({1: [(0, 33)], 2: [(40, 73)]}))
        hashes = [r['pcmSHA256'] for g in repeated['groups'] for key in ('trainingFiles', 'heldOutFiles') for r in g[key]]
        self.assertEqual(len(hashes), len(set(hashes)))
        self.assertIn('duplicate-pcm-content', [r['reason'] for r in repeated['omitted']])

    def test_invalid_authorization_report_and_source_never_publish(self):
        original = copy.deepcopy(self.request)
        self.request['sourceUse']['record'] = ''
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(self.acquisitions, [])
        self.request = original
        for report in [analysis({1: [(0, 81)]}), analysis({1: [(0, float('nan'))]}),
                       analysis({1: [(0, 5)] * 513}), analysis({n: [(0, 5)] for n in range(1, 34)})]:
            with self.subTest(report=repr(report)[:60]), self.assertRaises(ValueError):
                self.prepare(report)
        self.assertEqual(list(self.output.rglob('manifest.json')), [])
        self.assertTrue(all(not movie.exists() for movie in self.acquisitions))

    def test_malformed_member_group_fails_cleanly_and_empty_analysis_is_cached(self):
        bad = analysis({1: [(0, 5)]})
        bad['memberIntervals'][0]['group'] = []
        with self.assertRaises(ValueError):
            self.prepare(bad)
        path, empty = self.prepare(analysis({}))
        self.assertEqual(empty['groups'], [])
        self.assertEqual(dataset.prepare(self.request, self.output,
                                        analyze=lambda *a, **kw: self.fail('Empty analysis repeated'),
                                        acquire_source=lambda *a, **kw: self.fail('Empty source redownloaded')), path)

    def test_group_limit_analysis_does_not_use_unknown_dropped_group_members(self):
        report = analysis({1: [(0, 75)]})
        report.update(truncated=True, omitted=[dict(reason='group-limit', start=65, end=80)], omittedCount=1)
        _, manifest = self.prepare(report)
        # The analyzer could omit more dropped-group spans than fit its omission
        # list. A group-limit report therefore cannot safely admit any dataset.
        self.assertEqual(manifest['groups'][0]['status'], 'insufficient-data')
        self.assertEqual(manifest['groups'][0]['trainingFiles'], [])
        self.assertIn('analysis-group-limit', [row['reason'] for row in manifest['omitted']])

    def test_changed_source_hash_and_cancellation_inside_acquisition_leave_no_snapshot(self):
        original = self.acquire
        @contextlib.contextmanager
        def mismatch(*args, **kwargs):
            with original(*args, **kwargs) as source:
                source['sourceSHA256'] = '0' * 64
                yield source
        self.acquire = mismatch
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.prepare()
        self.acquire = original
        stopped = False
        @contextlib.contextmanager
        def interrupt(*args, **kwargs):
            nonlocal stopped
            with original(*args, **kwargs) as source:
                stopped = True
                yield source
        self.acquire = interrupt
        with self.assertRaises(InterruptedError):
            self.prepare(cancelled=lambda: stopped)
        self.assertTrue(all(not movie.exists() for movie in self.acquisitions))
        self.assertEqual(list(self.output.rglob('manifest.json')), [])

    def test_cancellation_and_stale_commit_remove_temporary_source_without_publishing(self):
        with self.assertRaises(InterruptedError):
            self.prepare(cancelled=lambda: True)
        self.assertEqual(self.acquisitions, [])
        def stale(operation):
            published = [p for p in self.output.rglob('manifest.json')
                         if not p.parent.name.startswith('.')]
            self.assertEqual(published, [])
            raise InterruptedError('Lease expired')
        with self.assertRaises(InterruptedError):
            self.prepare(commit=stale)
        self.assertTrue(all(not movie.exists() for movie in self.acquisitions))
        self.assertEqual(list(self.output.rglob('*.wav')), [])
        self.assertEqual(list(self.output.rglob('manifest.json')), [])

    def test_existing_outputs_survive_new_revision_and_changed_cache_is_rejected(self):
        old_path, old = self.prepare()
        old_bytes = old_path.read_bytes()
        self.request['requestID'] = 'f23e8d36-a086-4660-a017-367444016be0'
        new_path, _ = self.prepare()
        self.assertNotEqual(new_path, old_path)
        self.assertEqual(old_path.read_bytes(), old_bytes)
        audio = new_path.parent / old['groups'][0]['trainingFiles'][0]['file']
        audio.write_bytes(b'corrupted WAV')
        with self.assertRaises(ValueError):
            dataset.prepare(self.request, self.output,
                            analyze=lambda *a, **kw: self.fail('Corruption redownloaded'),
                            acquire_source=lambda *a, **kw: self.fail('Corruption redownloaded'))

    def test_linked_output_or_manifest_audio_is_rejected(self):
        real = self.root / 'real'
        real.mkdir()
        self.output.symlink_to(real, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(self.acquisitions, [])
        self.output.unlink()
        path, manifest = self.prepare()
        row = manifest['groups'][0]['trainingFiles'][0]
        audio = path.parent / row['file']
        original = self.root / 'preserve.wav'
        audio.rename(original)
        audio.symlink_to(original)
        with self.assertRaises(ValueError):
            dataset.load_manifest(path)

    def test_unlisted_snapshot_files_and_resealed_overlapping_timestamps_are_rejected(self):
        path, manifest = self.prepare()
        extra = path.parent / 'unlisted.wav'
        extra.write_bytes(b'not part of the audited snapshot')
        with self.assertRaises(ValueError):
            dataset.load_manifest(path)
        extra.unlink()
        group = manifest['groups'][0]
        row = group['heldOutFiles'][0]
        row['start'], row['end'] = 0, 3
        unsigned = {k: v for k, v in manifest.items() if k != 'revision'}
        manifest['revision'] = hashlib.sha256(json.dumps(unsigned, sort_keys=True, ensure_ascii=False,
                                                         allow_nan=False, separators=(',', ':')).encode()).hexdigest()
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'overlap'):
            dataset.load_manifest(path)

    def test_extraction_file_budget_is_reported_and_existing_outputs_are_never_replaced(self):
        with mock.patch.object(dataset, 'MAX_FILES', 2):
            path, manifest = self.prepare()
        self.assertEqual(len(list(path.parent.rglob('*.wav'))), 2)
        self.assertEqual(manifest['groups'][0]['status'], 'insufficient-data')
        self.assertIn('output-file-or-byte-limit', [row['reason'] for row in manifest['omitted']])
        original = path.read_bytes()
        self.request['requestID'] = 'f23e8d36-a086-4660-a017-367444016be0'
        def concurrent(operation):
            request_hash = hashlib.sha256(json.dumps(self.request, sort_keys=True, ensure_ascii=False,
                                                     allow_nan=False, separators=(',', ':')).encode()).hexdigest()
            target = self.output / 'SYNTHETIC03' / request_hash
            target.mkdir()
            (target / 'keep.txt').write_text('preserve')
            operation()
        with self.assertRaises(FileExistsError):
            self.prepare(commit=concurrent)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual([p.read_text() for p in self.output.rglob('keep.txt')], ['preserve'])

    def test_group_and_total_limits_are_explicit_and_manifest_is_bounded(self):
        with mock.patch.object(dataset, 'MAX_GROUP_SECONDS', 65), mock.patch.object(dataset, 'MAX_TOTAL_SECONDS', 70):
            _, manifest = self.prepare(analysis({1: [(0, 70)], 2: [(70, 80)]}))
        self.assertLessEqual(sum(row['end'] - row['start'] for g in manifest['groups']
                                 for key in ('trainingFiles', 'heldOutFiles') for row in g[key]), 70)
        reasons = [row['reason'] for row in manifest['omitted']]
        self.assertIn('group-duration-limit', reasons)
        self.assertIn('total-duration-limit', reasons)
        self.assertLessEqual(len(json.dumps(manifest).encode()), 512 * 1024)


if __name__ == '__main__':
    unittest.main()
