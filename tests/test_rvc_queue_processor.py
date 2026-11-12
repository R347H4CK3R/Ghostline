"""Real SQLite/files/dataset/checker/export integration, mocked neural/acquisition only."""
import array
import contextlib
import hashlib
import importlib
import json
import pathlib
import random
import struct
import tempfile
import threading
import time
import unittest
import wave
from unittest import mock

from tools import rvc_request, rvc_training, rvc_validation
from tools.video_queue import VideoQueue


def digest(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def wav(path, seconds=1, rate=16000, seed=1):
    values = array.array('h', random.Random(seed).randbytes(int(seconds * rate) * 2))
    values = array.array('h', (value // 8 + 5000 for value in values))
    with wave.open(str(path), 'wb') as stream:
        stream.setparams((1, 2, rate, 0, 'NONE', 'none'))
        stream.writeframes(values.tobytes())


def effective_fixture(folder, source_count):
    from tools.rvc_preprocess import audit_preprocessed
    def float_wav(path, rate, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        pcm = struct.pack('<f', value) * int(rate * 3.7)
        fmt = struct.pack('<HHIIHH', 3, 1, rate, rate * 4, 4, 32)
        path.write_bytes(b'RIFF' + struct.pack('<I', 36 + len(pcm)) + b'WAVEfmt ' +
                         struct.pack('<I', 16) + fmt + b'data' + struct.pack('<I', len(pcm)) + pcm)
    def npy(path, shape, code, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        kind = '<i8' if code == 'q' else '<f4'
        header = repr(dict(descr=kind, fortran_order=False, shape=shape)).encode() + b'\n'
        count = shape[0] * (shape[1] if len(shape) > 1 else 1)
        path.write_bytes(b'\x93NUMPY\x01\x00' + struct.pack('<H', len(header)) + header + struct.pack('<'+code, value)*count)
    for index in range(18):
        stem = str(index % source_count) + '_' + str(index // source_count)
        for name, rate in [('0_gt_wavs', 40000), ('1_16k_wavs', 16000)]:
            float_wav(folder / name / (stem + '.wav'), rate, .1 + index*.001)
        npy(folder / '3_feature768' / (stem + '.npy'), (185, 768), 'f', .25)
        npy(folder / '2a_f0' / (stem + '.wav.npy'), (370,), 'q', 128)
        npy(folder / '2b-f0nsf' / (stem + '.wav.npy'), (370,), 'f', 180)
    return audit_preprocessed(folder, expected_sources=source_count, validate_features=True)


class Crash(BaseException):
    pass


class RVCQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = pathlib.Path(self.tmp.name).resolve()
        self.root = self.base / 'rvc'
        self.engine = self.base / 'engine'
        self.engine.mkdir()
        self.validation = self.base / 'original-validation.wav'
        wav(self.validation, seed=913)
        self.body = dict(schemaVersion=1, format='rvc-v2-pth-index',
                         requestID='b3e5fa2b-2b08-44ba-946a-299860f2e765',
                         videoURL='https://youtu.be/EAT0nWoEzJ8',
                         sourceUse=dict(decision='approved-private-rvc-training',
                                        record='Private training from permitted original test source.'))
        rvc_request.submit(self.root, self.body)
        self.database = self.root / 'rvc-queue.db'
        self.queue = VideoQueue(str(self.database))
        self.addCleanup(self.queue.close)
        self.acquired = 0
        self.trained = []
        self.converted = 0
        self.conversion_attempts = 0
        self.intervals = [(1, 0, 70), (2, 75, 145)]
        self.cancel = threading.Event()
        patch = mock.patch.object(rvc_validation, 'check_source')
        patch.start()
        self.addCleanup(patch.stop)

    @contextlib.contextmanager
    def acquire(self, url, *_args, **kwargs):
        self.assertEqual(url, 'https://www.youtube.com/watch?v=EAT0nWoEzJ8')
        self.acquired += 1
        with tempfile.TemporaryDirectory(dir=self.base) as directory:
            movie = pathlib.Path(directory).resolve() / 'download.mp4'
            wav(movie, seconds=150, seed=349)
            yield dict(privateMoviePath=str(movie), sourceSHA256=digest(movie),
                       videoID='EAT0nWoEzJ8')

    def analyze(self, audio, cancelled):
        self.assertTrue(pathlib.Path(audio).is_file())
        return dict(schemaVersion=1, engine='fixture', durationSeconds=150,
                    candidates=[dict(group=g, start=s, end=min(e, s+8)) for g,s,e in self.intervals],
                    memberIntervals=[dict(group=g,start=s,end=e) for g,s,e in self.intervals],
                    labelsVerified=False, speakerSeparated=False, overlapDetection='not-supported',
                    truncated=False, omitted=[], omittedCount=0)

    def prepare(self, *args, **kwargs):
        from tools.rvc_dataset_prepare import prepare
        return prepare(*args, acquire_source=self.acquire, **kwargs)

    def train(self, root, dataset, experiment, permission, **kwargs):
        self.assertIsInstance(kwargs['cancel'], threading.Event)
        self.assertFalse(kwargs['cancel'].is_set())
        root = pathlib.Path(root)
        folder = root / 'logs' / experiment
        folder.mkdir(parents=True, exist_ok=False)
        model = root / 'assets' / 'weights' / (experiment + '.pth')
        model.parent.mkdir(parents=True, exist_ok=True)
        model.write_bytes(('neural fixture ' + experiment).encode())
        index = folder / 'added_fixture.index'
        index.write_bytes(('neural index ' + experiment).encode())
        report = dict(status='trained-needs-independent-conversion-check',
                      experiment=experiment, epochs=kwargs['epochs'], sourceRevision=rvc_training.UPSTREAM,
                      completedStages=['preprocess','pitch','features','train','index'],
                      dataset=rvc_training.audit_dataset(dataset), permission=permission,
                      model=str(model), modelSHA256=digest(model), indices=[str(index)],
                      indexSHA256={str(index):digest(index)}, verified=False)
        report['effectiveDataset'] = effective_fixture(folder, len(report['dataset']['files']))
        (folder / 'voicematrix-training.json').write_text(json.dumps(report))
        self.trained.append(experiment)
        return report

    def neural(self, command, **kwargs):
        self.assertIsInstance(kwargs['cancel'], threading.Event)
        self.converted += 1
        model, index, source, output, result = map(pathlib.Path, command[-5:])
        with wave.open(str(source)) as stream:
            seconds = stream.getnframes() / stream.getframerate()
        wav(output, rate=40000, seconds=seconds, seed=490)
        result.write_text(json.dumps(dict(modelSHA256=digest(model), indexSHA256=digest(index),
                                         inputSHA256=digest(source), modelVersion='v2', sampleRate=40000,
                                         featureDimensions=768, indexVectors=42)))

    def conversion(self, *args, **kwargs):
        self.conversion_attempts += 1
        return rvc_validation.verify_conversion(*args, runner=self.neural, **kwargs)

    def words(self, audio, text):
        self.assertEqual(text, 'This original validation clip was held out.')
        return dict(passed=True, wordErrorRate=0, wavSHA256=digest(audio))

    def run_job(self, **kwargs):
        module = importlib.import_module('tools.rvc_queue_processor')
        config = dict(engine_root=self.engine, validation_wav=self.validation,
                      validation_text='This original validation clip was held out.',
                      validation_source='Separately recorded original held-out validation speech.',
                      verify_words=self.words, analyze=self.analyze, prepare_job=self.prepare,
                      train_job=self.train, conversion_job=self.conversion, epochs=1,
                      cancel=self.cancel, heartbeat_interval=.05)
        config.update(kwargs)
        return module.run_once(self.root, **config)

    def requeue(self):
        with self.queue.db:
            self.queue.db.execute("UPDATE jobs SET status='waiting'")
            self.queue.db.execute('UPDATE job_control SET next_attempt=0, token=NULL, lease_until=0')

    def rows(self):
        return [json.loads(row[0]) for row in self.queue.db.execute('SELECT state FROM rvc_groups ORDER BY group_id')]

    def test_anonymous_groups_export_real_checked_pair_sequentially_and_stay_review(self):
        result = self.run_job()
        self.assertEqual(result['status'], 'needs-review')
        self.assertEqual([row['status'] for row in result['groups']], ['exported-needs-review'] * 2)
        self.assertEqual(len(set(self.trained)), 2)
        self.assertEqual(self.acquired, 1)
        self.assertFalse(result['likenessVerified'])
        self.assertFalse(result['nativeIPhoneRuntimeVerified'])
        self.assertEqual(self.queue.export()['videos'][0]['status'], 'needs-review')
        for group in result['groups']:
            manifest = json.loads((self.root / 'voices' / group['id'] / 'manifest.json').read_text())
            self.assertEqual(manifest['format'], 'rvc-v2-pth-index')
            self.assertEqual(manifest['modelSHA256'], digest(self.root / 'voices' / group['id'] / 'model.pth'))
        self.assertNotIn('held out', json.dumps(result))
        self.assertNotIn(str(self.base), json.dumps(result))
        self.assertIsNone(self.run_job())

    def test_insufficient_group_is_persisted_without_training_or_redownload(self):
        self.intervals = [(1, 0, 20)]
        result = self.run_job()
        self.assertEqual(result['groups'][0]['status'], 'insufficient-data')
        self.assertEqual(result['reasonCode'], 'insufficient-data')
        self.assertEqual(self.trained, [])
        self.assertFalse((self.root / 'voices').exists())
        self.requeue()
        again = self.run_job()
        self.assertEqual(again['groups'], result['groups'])
        self.assertEqual(self.acquired, 1)

    def test_completed_groups_and_exports_survive_manual_requeue(self):
        first = self.run_job()
        self.requeue()
        second = self.run_job()
        self.assertEqual(first['groups'], second['groups'])
        self.assertEqual(len(self.trained), 2)
        self.assertEqual(self.converted, 2)
        self.assertEqual(self.acquired, 1)

    def test_failed_asr_has_no_publication_and_is_not_blindly_retrained(self):
        result = self.run_job(verify_words=lambda path, text:dict(passed=False, wordErrorRate=.5, wavSHA256=digest(path)))
        self.assertEqual(result['status'], 'needs-review')
        self.assertFalse((self.root / 'voices').exists())
        self.requeue()
        result = self.run_job()
        self.assertEqual(result['status'], 'needs-review')
        self.assertEqual(len(self.trained), 1)
        self.assertEqual(self.converted, 1)
        self.assertEqual(self.acquired, 1)
        self.assertFalse((self.root / 'voices').exists())

    def test_cancel_after_completed_training_retains_model_and_resumes_without_retraining(self):
        def stop(*args, **kwargs):
            result = self.train(*args, **kwargs)
            self.cancel.set()
            return result
        result = self.run_job(train_job=stop)
        self.assertEqual(result['status'], 'paused')
        self.assertEqual(len(self.trained), 1)
        self.assertEqual(self.converted, 0)
        self.cancel.clear()
        result = self.run_job()
        self.assertEqual(result['status'], 'needs-review')
        self.assertEqual(len(self.trained), 2)
        self.assertEqual(self.acquired, 1)

    def test_crash_after_durable_training_recovers_exact_report(self):
        def crash(*args, **kwargs):
            self.train(*args, **kwargs)
            raise Crash()
        with self.assertRaises(Crash):
            self.run_job(train_job=crash)
        with self.queue.db:
            self.queue.db.execute('UPDATE job_control SET lease_until=0')
        result = self.run_job()
        self.assertEqual(result['status'], 'needs-review')
        self.assertEqual(len(self.trained), 2)
        self.assertEqual(self.acquired, 1)

    def test_crash_after_conversion_recovers_checked_artifacts_without_rerunning(self):
        def crash(*args, **kwargs):
            self.conversion(*args, **kwargs)
            raise Crash()
        with self.assertRaises(Crash):
            self.run_job(conversion_job=crash)
        with self.queue.db:
            self.queue.db.execute('UPDATE job_control SET lease_until=0')
        result = self.run_job()
        self.assertEqual(result['status'], 'needs-review')
        self.assertEqual(len(self.trained), 2)
        self.assertEqual(self.converted, 2)

    def test_incomplete_training_is_retained_and_never_retried_automatically(self):
        def fail(root, dataset, experiment, permission, **kwargs):
            folder = pathlib.Path(root) / 'logs' / experiment
            folder.mkdir(parents=True)
            (folder / 'voicematrix-training.json').write_text('{"status":"failed"}')
            self.trained.append(experiment)
            raise RuntimeError('Private neural diagnostics')
        result = self.run_job(train_job=fail)
        self.assertEqual(result['status'], 'needs-review')
        self.requeue()
        self.run_job()
        self.assertEqual(len(self.trained), 1)
        self.assertTrue((self.engine / 'logs' / self.trained[0] / 'voicematrix-training.json').is_file())
        self.assertFalse((self.root / 'voices').exists())

    def test_training_report_cannot_redirect_to_an_external_model(self):
        external = self.base / 'unrelated-model.pth'
        external.write_bytes(b'preserved external model')
        def redirect(*args, **kwargs):
            report = self.train(*args, **kwargs)
            report['model'] = str(external)
            report['modelSHA256'] = digest(external)
            path = self.engine / 'logs' / report['experiment'] / 'voicematrix-training.json'
            path.write_text(json.dumps(report))
            return report
        result = self.run_job(train_job=redirect)
        self.assertEqual(result['status'], 'needs-review')
        self.assertEqual(self.converted, 0)
        self.assertEqual(external.read_bytes(), b'preserved external model')
        self.assertFalse((self.root / 'voices').exists())

    def test_lost_lease_cancels_neural_work_and_prevents_publication(self):
        def lose(*args, **kwargs):
            self.train(*args, **kwargs)
            with self.queue.db:
                self.queue.db.execute('UPDATE job_control SET lease_until=0')
            self.assertTrue(kwargs['cancel'].wait(2))
            raise InterruptedError('Lost worker')
        with self.assertRaisesRegex(ValueError, 'ownership'):
            self.run_job(train_job=lose)
        self.assertFalse((self.root / 'voices').exists())

    def test_external_cancel_reaches_running_neural_event(self):
        def stop(*args, **kwargs):
            self.cancel.set()
            self.assertTrue(kwargs['cancel'].wait(2))
            raise InterruptedError('Private source and transcript must not leak')
        result = self.run_job(train_job=stop)
        self.assertEqual(result['status'], 'paused')
        self.assertNotIn('transcript', json.dumps(result))
        self.assertFalse((self.root / 'voices').exists())

    def test_configured_recognizer_receives_cancellation_and_restores_prior_hook(self):
        prior = lambda: False
        observed = []
        def words(audio, text):
            self.cancel.set()
            deadline = time.monotonic() + 2
            while not words.job_cancelled() and time.monotonic() < deadline:
                time.sleep(.01)
            observed.append(words.job_cancelled())
            raise InterruptedError('Cancelled independent recognition')
        words.transcribe = lambda _audio: ''
        words.job_cancelled = prior
        result = self.run_job(verify_words=words)
        self.assertEqual(result['status'], 'paused')
        self.assertEqual(observed, [True])
        self.assertIs(words.job_cancelled, prior)
        self.assertFalse((self.root / 'voices').exists())

    def test_changed_model_digest_stops_before_conversion(self):
        def corrupt(*args, **kwargs):
            report = self.train(*args, **kwargs)
            pathlib.Path(report['model']).write_bytes(b'tampered')
            return report
        result = self.run_job(train_job=corrupt)
        self.assertEqual(result['status'], 'needs-review')
        self.assertEqual(self.converted, 0)
        self.assertFalse((self.root / 'voices').exists())

    def test_missing_effective_data_proof_is_rejected_before_conversion(self):
        def missing(*args, **kwargs):
            report = self.train(*args, **kwargs)
            report.pop('effectiveDataset')
            path = self.engine / 'logs' / report['experiment'] / 'voicematrix-training.json'
            path.write_text(json.dumps(report))
            return report
        result = self.run_job(train_job=missing)
        self.assertEqual(result['status'], 'needs-review')
        self.assertEqual(self.converted, 0)
        self.assertEqual(self.conversion_attempts, 0)
        self.assertFalse((self.root / 'voices').exists())

    def test_changed_effective_feature_bytes_are_rejected_before_conversion(self):
        def change(*args, **kwargs):
            report = self.train(*args, **kwargs)
            folder = self.engine / 'logs' / report['experiment']
            feature = next((folder / '3_feature768').glob('*.npy'))
            data = feature.read_bytes()
            feature.write_bytes(data[:-4] + struct.pack('<f', .75))
            return report
        result = self.run_job(train_job=change)
        self.assertEqual(result['status'], 'needs-review')
        self.assertEqual(self.converted, 0)
        self.assertEqual(self.conversion_attempts, 0)
        self.assertFalse((self.root / 'voices').exists())

    def test_unbound_word_proof_cannot_be_published(self):
        result = self.run_job(verify_words=lambda *_:dict(passed=True, wordErrorRate=0, wavSHA256='0'*64))
        self.assertEqual(result['status'], 'needs-review')
        self.assertFalse((self.root / 'voices').exists())

    def test_checked_conversion_must_bind_effective_gate_and_training_report(self):
        def corrupt(*args, **kwargs):
            path = self.conversion(*args, **kwargs)
            proof = json.loads(path.read_text())
            proof['trainingReportSHA256'] = '0' * 64
            path.write_text(json.dumps(proof))
            return path
        result = self.run_job(conversion_job=corrupt)
        self.assertEqual(result['status'], 'needs-review')
        self.assertFalse((self.root / 'voices').exists())

    def test_existing_conflicting_export_is_preserved(self):
        first = self.run_job()
        target = self.root / 'voices' / first['groups'][0]['id'] / 'model.pth'
        target.write_bytes(b'preserve conflicting existing model')
        self.requeue()
        result = self.run_job()
        self.assertEqual(result['status'], 'needs-review')
        self.assertEqual(target.read_bytes(), b'preserve conflicting existing model')
        self.assertEqual(len(self.trained), 2)

    def test_export_present_before_journal_commit_is_reused_after_verification(self):
        first = self.run_job()
        group = first['groups'][0]['id']
        state = self.rows()[0]
        state['status'] = 'checked'
        with self.queue.db:
            self.queue.db.execute('UPDATE rvc_groups SET state=? WHERE group_id=?', (json.dumps(state), group))
        self.requeue()
        result = self.run_job()
        self.assertEqual(result['groups'], first['groups'])
        self.assertEqual(len(self.trained), 2)
        self.assertEqual(self.converted, 2)

    def test_validation_bytes_must_not_be_a_training_clip(self):
        from tools.rvc_dataset_prepare import load_manifest
        request = rvc_request.validate(self.body)
        manifest_path = self.prepare(request, self.root / 'datasets', analyze=self.analyze)
        manifest = load_manifest(manifest_path, request=request)
        clip = manifest_path.parent / manifest['groups'][0]['trainingFiles'][0]['file']
        self.validation.write_bytes(clip.read_bytes())
        result = self.run_job()
        self.assertEqual(result['status'], 'needs-review')
        self.assertEqual(self.trained, [])
        self.assertFalse((self.root / 'voices').exists())

    def test_repeated_source_groups_fail_closed(self):
        self.intervals = [(1, 0, 70), (2, 0, 70)]
        result = self.run_job()
        self.assertEqual(result['status'], 'needs-review')
        self.assertEqual(self.trained, [])
        self.assertFalse((self.root / 'voices').exists())

    def test_later_group_is_rechecked_before_its_expensive_training_boundary(self):
        def change_next(*args, **kwargs):
            report = self.train(*args, **kwargs)
            if len(self.trained) == 1:
                manifest_path = next((self.root / 'datasets').glob('*/*/manifest.json'))
                manifest = json.loads(manifest_path.read_text())
                path = manifest_path.parent / manifest['groups'][1]['trainingFiles'][0]['file']
                raw = path.read_bytes()
                path.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
            return report
        result = self.run_job(train_job=change_next)
        self.assertEqual(result['status'], 'needs-review')
        self.assertEqual(len(self.trained), 1)
        self.assertEqual(result['groups'][1]['status'], 'needs-review')

    def test_changed_manifest_on_resume_is_reviewed_without_acquisition(self):
        self.run_job()
        path = next((self.root / 'datasets').glob('*/*/manifest.json'))
        value = json.loads(path.read_text())
        value['source']['sourceSHA256'] = '0'*64
        path.write_text(json.dumps(value))
        self.requeue()
        result = self.run_job()
        self.assertEqual(result['status'], 'needs-review')
        self.assertEqual(self.acquired, 1)
        self.assertEqual(len(self.trained), 2)

    def test_validation_configuration_cannot_change_during_resume(self):
        self.run_job()
        self.requeue()
        result = self.run_job(validation_text='Changed transcript is a new validation scope.')
        self.assertEqual(result['status'], 'needs-review')
        self.assertNotEqual(result['reasonCode'], 'technical-checks-only')
        self.assertEqual(self.converted, 2)


if __name__ == '__main__':
    unittest.main()
