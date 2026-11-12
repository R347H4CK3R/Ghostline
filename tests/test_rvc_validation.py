"""Orchestration checks use explicit source/audit/neural boundaries.

Real effective audio and array admission is tested in test_rvc_preprocess and
test_rvc_queue_processor; fixture weights here are not neural evidence.
"""
import hashlib
import json
import pathlib
import tempfile
import unittest
import wave
from unittest import mock
from tools import rvc_validation as rv


def wav(path, rate=16000, seconds=1):
    with wave.open(str(path), 'wb') as stream:
        stream.setparams((1, 2, rate, 0, 'NONE', 'none'))
        stream.writeframes(b'\x00\x10' * int(rate * seconds))


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


class RVCValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name).resolve()
        self.source = self.root / 'input.wav'; wav(self.source)
        self.model = self.root / 'assets' / 'weights' / 'original.pth'
        self.model.parent.mkdir(parents=True); self.model.write_bytes(b'neural boundary fixture')
        self.index = self.root / 'logs' / 'original' / 'added.index'
        self.index.parent.mkdir(parents=True); self.index.write_bytes(b'index boundary fixture')
        self.effective = dict(status='ready-for-training', minimumActiveSeconds=60, activeLowerBoundSeconds=64, files=[])
        self.audit = mock.patch.object(rv, 'audit_preprocessed', return_value=self.effective)
        self.audit.start(); self.addCleanup(self.audit.stop)
        self.training = self.root / 'training.json'
        self.training.write_text(json.dumps(dict(status='trained-needs-independent-conversion-check',
            sourceRevision=rv.UPSTREAM, completedStages=['preprocess','pitch','features','train','index'],
            model=str(self.model),modelSHA256=sha(self.model),indices=[str(self.index)],
            indexSHA256={str(self.index):sha(self.index)},experiment='original',epochs=1,
            dataset={'files':[{'file':'source.wav','sha256':'1'*64}]}, effectiveDataset=self.effective)))
        self.patch = mock.patch.object(rv, 'check_source'); self.patch.start(); self.addCleanup(self.patch.stop)

    def run_check(self, runner=None, words=None):
        return rv.verify_conversion(self.root, self.training, self.source, self.root / 'check',
            expected_text='This is original test speech.', verify_words=words or self.words,
            runner=runner or self.neural_boundary)

    def words(self, path, expected):
        self.assertEqual(expected,'This is original test speech.')
        return dict(passed=True, wordErrorRate=0, wavSHA256=sha(path))

    def neural_boundary(self, command, **kwargs):
        model,index,source,output,result=map(pathlib.Path,command[-5:])
        wav(output,40000)
        result.write_text(json.dumps(dict(modelSHA256=sha(model),indexSHA256=sha(index),inputSHA256=sha(source),
            modelVersion='v2',sampleRate=40000,featureDimensions=768,indexVectors=42)))

    def test_real_output_and_words_are_hash_bound_before_success(self):
        path = self.run_check(); self.assertIsNotNone(path)
        report = json.loads(pathlib.Path(path).read_text())
        self.assertEqual(report['status'],'conversion-checked-needs-review')
        self.assertEqual(report['outputSHA256'],sha(pathlib.Path(report['output'])))
        self.assertFalse(report['physicalDeviceVerified']); self.assertFalse(report['likenessVerified'])

    def test_failed_or_unbound_wordcheck_cannot_become_exportable(self):
        with self.assertRaises(ValueError):
            self.run_check(words=lambda *_:dict(passed=True,wordErrorRate=0,wavSHA256='0'*64))
        report=json.loads((self.root/'check'/'conversion.json').read_text())
        self.assertEqual(report['status'],'failed')

    def test_empty_conversion_output_cannot_become_exportable(self):
        def empty(command,**kwargs):
            self.neural_boundary(command,**kwargs);pathlib.Path(command[-2]).write_bytes(b'')
        with self.assertRaises(ValueError): self.run_check(runner=empty)

    def test_incomplete_training_and_changed_index_stop_before_neural_execution(self):
        report=json.loads(self.training.read_text());report['completedStages']=['preprocess'];self.training.write_text(json.dumps(report))
        with self.assertRaises(ValueError):self.run_check()
        self.assertFalse((self.root/'check').exists())
        report['completedStages']=['preprocess','pitch','features','train','index'];self.training.write_text(json.dumps(report))
        self.index.write_bytes(b'changed')
        with self.assertRaises(ValueError):self.run_check()
        self.assertFalse((self.root/'check').exists())

    def test_changed_child_model_digest_rejected(self):
        def changed(command,**kwargs):
            self.neural_boundary(command,**kwargs)
            path=pathlib.Path(command[-1]);body=json.loads(path.read_text());body['modelSHA256']='0'*64;path.write_text(json.dumps(body))
        with self.assertRaises(ValueError):self.run_check(runner=changed)

    def test_existing_check_directory_is_not_overwritten(self):
        folder=self.root/'check';folder.mkdir();(folder/'original').write_text('preserved')
        with self.assertRaises(FileExistsError):self.run_check()
        self.assertEqual((folder/'original').read_text(),'preserved')

    def test_mutated_snapshot_after_conversion_is_rejected(self):
        def mutate(command, **kwargs):
            self.neural_boundary(command, **kwargs)
            pathlib.Path(command[-5]).write_bytes(b'new weights')
        with self.assertRaises(ValueError): self.run_check(runner=mutate)

    def test_changed_duration_and_rate_are_rejected(self):
        for rate, seconds in [(24000, 1), (40000, 2)]:
            with self.subTest(rate=rate, seconds=seconds):
                def altered(command, **kwargs):
                    self.neural_boundary(command, **kwargs)
                    wav(pathlib.Path(command[-2]), rate, seconds)
                with self.assertRaises(ValueError): self.run_check(runner=altered)
                import shutil
                shutil.rmtree(self.root / 'check')

    def test_cancellation_after_neural_stage_prevents_success(self):
        import threading
        cancel = threading.Event()
        def stopped(command, **kwargs):
            self.neural_boundary(command, **kwargs); cancel.set()
        with self.assertRaises(InterruptedError):
            rv.verify_conversion(self.root, self.training, self.source, self.root/'check',
                expected_text='This is original test speech.', verify_words=self.words,
                runner=stopped, cancel=cancel)
        self.assertEqual(json.loads((self.root/'check'/'conversion.json').read_text())['status'], 'cancelled')

    def test_changed_wav_during_wordcheck_is_rejected(self):
        def changed(path, expected):
            result=self.words(path, expected); wav(path, 40000, 2); return result
        with self.assertRaises(ValueError): self.run_check(words=changed)

    def test_infinite_and_boolean_word_error_rates_are_rejected(self):
        for value in (float('nan'), float('inf'), True, -.1, .11):
            with self.subTest(value=value):
                def invalid(path, expected):
                    return dict(passed=True, wordErrorRate=value, wavSHA256=sha(path))
                with self.assertRaises(ValueError): self.run_check(words=invalid)
                import shutil
                shutil.rmtree(self.root / 'check')

    def test_single_label_upstream_109_row_embedding_capacity_is_preserved(self):
        from types import SimpleNamespace
        config = [0] * 18
        config[-3:] = [109, 256, 40000]
        embedding = SimpleNamespace(ndim=2, shape=(109, 256))
        result = rv._speaker_config(config, embedding)
        self.assertEqual(result[-3:], [109, 256, 40000])
        self.assertIsNot(result, config)
        config[-3] = 1
        with self.assertRaises(ValueError): rv._speaker_config(config, embedding)

    def test_punctuation_only_transcript_is_rejected_before_output_creation(self):
        with self.assertRaises(ValueError):
            rv.verify_conversion(self.root, self.training, self.source, self.root/'check',
                expected_text='... !!!', verify_words=self.words, runner=self.neural_boundary)
        self.assertFalse((self.root/'check').exists())

    def test_old_or_changed_effective_dataset_cannot_reach_conversion(self):
        original=json.loads(self.training.read_text())
        for effective in (None, dict(self.effective,activeLowerBoundSeconds=59.9), dict(self.effective,files=['changed'])):
            changed=dict(original)
            if effective is None: changed.pop('effectiveDataset')
            else: changed['effectiveDataset']=effective
            self.training.write_text(json.dumps(changed))
            with self.assertRaises(ValueError):self.run_check()
            self.assertFalse((self.root/'check').exists())

    def test_model_from_another_experiment_cannot_borrow_data_proof(self):
        original=json.loads(self.training.read_text())
        copy=self.root/'other.pth';copy.write_bytes(self.model.read_bytes())
        original['model']=str(copy);self.training.write_text(json.dumps(original))
        with self.assertRaises(ValueError):self.run_check()
        self.assertFalse((self.root/'check').exists())

    def test_training_audio_is_not_a_heldout_input(self):
        original=json.loads(self.training.read_text())
        original['dataset']['files'][0]['sha256']=sha(self.source)
        self.training.write_text(json.dumps(original))
        with self.assertRaises(ValueError):self.run_check()
        self.assertFalse((self.root/'check').exists())
