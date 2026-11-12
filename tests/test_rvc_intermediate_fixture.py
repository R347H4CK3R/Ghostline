import array
import json
import os
import stat
from unittest import mock
import pathlib
import tempfile
import unittest


class FixtureTests(unittest.TestCase):
    def setUp(self):
        from tools import rvc_intermediate_fixture as api
        self.api = api
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name).resolve()

    def test_tensor_round_trip_is_hash_bound_and_shapes_are_checked(self):
        writer = self.api.Capture(self.root)
        writer.add('hubert_features', array.array('f', [1.] * 768).tobytes(), [1, 1, 768], 'float32')
        self.assertEqual(writer.entries['hubert_features']['bytes'], 3072)
        writer.verify()
        (self.root / 'hubert_features.bin').write_bytes(b'x' * 3072)
        with self.assertRaises(ValueError): writer.verify()

    def test_bad_shapes_names_nonfinite_and_duplicates_fail(self):
        writer = self.api.Capture(self.root)
        for name, shape, dtype, raw in [('../audio', [1], 'float32', b'\0'*4),
                ('hubert_features', [1, 1, 256], 'float32', b'\0'*1024),
                ('audio_16k', [True], 'float32', b'\0'*4),
                ('audio_16k', [16001], 'float32', b'\0'*(16001*4)),
                ('audio_16k', [1], 'float32', array.array('f',[float('nan')]).tobytes())]:
            with self.subTest(name=name, shape=shape), self.assertRaises(ValueError): writer.add(name,raw,shape,dtype)
        writer.add('audio_16k', b'\0'*4, [1], 'float32')
        with self.assertRaises(ValueError): writer.add('audio_16k', b'\0'*4,[1],'float32')

    def test_completion_requires_every_real_stage_and_rejects_unknown_fields(self):
        writer = self.api.Capture(self.root)
        with self.assertRaises(ValueError): writer.complete()
        self.assertFalse((self.root/'fixture.json').exists())

    def test_reverification_rejects_metadata_path_and_dtype_replacements(self):
        writer = self.api.Capture(self.root)
        writer.add('audio_16k', b'\0' * 4, [1], 'float32')
        original = dict(writer.entries['audio_16k'])
        for field, value in [('file', '../elsewhere'), ('dtype', 'int16'), ('shape', [True]), ('bytes', True)]:
            writer.entries['audio_16k'] = dict(original, **{field: value})
            with self.subTest(field=field), self.assertRaises(ValueError): writer.verify()
        writer.entries['audio_16k'] = original
        writer.verify()

    def test_refuses_non_synthetic_before_reading_any_input(self):
        with self.assertRaises(ValueError):
            self.api.capture(self.root, self.root/'missing', self.root/'missing', self.root/'out',
                             proof_sha256='a'*64, source_sha256='b'*64, synthetic=False)
        self.assertFalse((self.root/'out').exists())

    def test_digest_bindings_are_required_before_io(self):
        for digest in (None, '', 'x'*64, True):
            with self.subTest(digest=digest), self.assertRaises(ValueError):
                self.api.capture(self.root/'upstream',self.root/'missing',self.root/'missing',self.root/'out',
                                 proof_sha256=digest,source_sha256='b'*64,synthetic=True)

    def test_tensor_contract_requires_exact_length_and_speaker_values(self):
        writer = self.api.Capture(self.root)
        shapes = {
            'audio_16k':[16000], 'filtered_audio':[16000], 'padded_audio':[48000], 'hubert_input':[1,48000],
            'hubert_features':[1,149,768], 'retrieval_scores':[149,8],
            'retrieval_ids':[149,8], 'retrieval_vectors':[149,8,768],
            'pitch_coarse':[1,298], 'pitch_hz':[1,298], 'synth_features':[1,298,768],
            'synth_lengths':[1], 'speaker':[1], 'latent_noise':[1,192,298],
            'phase_noise':[1,1,1], 'excitation_noise':[1,119200,1],
            'synth_output':[1,1,119200], 'final_pcm':[39200],
        }
        # Structural tensor fixtures only. This never claims neural execution.
        import math
        for name, shape in shapes.items():
            dtype = self.api.SPEC[name][0]
            fill = 1 if name in ('retrieval_scores','pitch_coarse') else 0
            if name == 'synth_lengths': fill = 297  # deliberate mismatch
            raw = array.array(self.api.CODES[dtype][0], [fill]*math.prod(shape)).tobytes()
            writer.add(name,raw,shape,dtype)
        with self.assertRaises(ValueError): writer.complete()

    def test_pinned_pitch_signature_rejects_added_optional_input(self):
        def pinned(self, x, p_len, f0_up_key, f0_method): pass
        def changed(self, x, p_len, f0_up_key, f0_method, inp_f0=None): pass
        contract = ('self','x','p_len','f0_up_key','f0_method')
        self.api.check_signature(pinned, contract)
        with self.assertRaises(ValueError): self.api.check_signature(changed, contract)

    @unittest.skipUnless(os.name == 'posix', 'POSIX permissions only; Windows ACL needs validation')
    def test_new_capture_directory_is_private_under_umask_022(self):
        folder = self.root / 'private-capture'
        proof = dict(inputSHA256='b'*64, model=str(self.root/'model'),
                     index=str(self.root/'index'), modelSHA256='c'*64, indexSHA256='d'*64)
        previous = os.umask(0o022)
        try:
            with mock.patch.object(self.api, 'read_bound', return_value=b'synthetic'), \
                 mock.patch.object(self.api, '_checked_proof', return_value=proof), \
                 mock.patch.object(self.api, 'audio_metrics', return_value={'seconds':1}), \
                 mock.patch.object(self.api, 'run_stage', side_effect=RuntimeError('stop before neural execution')):
                with self.assertRaises(RuntimeError):
                    self.api.capture(self.root/'upstream', self.root/'proof', self.root/'input', folder,
                                     proof_sha256='a'*64, source_sha256='b'*64, synthetic=True)
            self.assertEqual(stat.S_IMODE(folder.stat().st_mode), 0o700)
            self.assertEqual(json.loads((folder/'request.json').read_text())['root'], str(self.root/'upstream'))
            self.assertNotIn(str(self.root), (folder/'fixture.json').read_text())
        finally:
            os.umask(previous)

    def test_help_does_not_import_neural_packages(self):
        import subprocess, sys
        p=subprocess.run([sys.executable,'-m','tools.rvc_intermediate_fixture','--help'],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)

if __name__ == '__main__': unittest.main()
