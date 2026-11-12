"""Private, fixed-shape CPU RVC synthesizer ONNX feasibility check, not iPhone support.

The only supported model is the pinned upstream v2/f0/40k architecture. A caller
must supply hash-bound conversion evidence and explicit synthetic-test provenance.
Nothing installs packages, downloads models, trains, publishes, or edits upstream.

Run only in a separate Python 3.12 export environment with torch==2.4.1+cpu,
numpy==1.26.4, scipy==1.13.1, onnx==1.17.0 and onnxruntime==1.24.2. These pins intentionally do
not change the upstream training environment. ONNX opset 17 / IR <=10 are below
ORT 1.24.2's supported ceiling, but only actual CPU inference earns parity.

Equations: upstream 81eed5e8f68b6bed1789f682fe78cdd324495afc,
infer/module/models.py:267-343, 388-400, 477-515, 646-678.
The adapter reuses trained layers; no weights or module methods are replaced.
Random calls are captured only around an original reference call in a dedicated
single-threaded Python child and restored in finally. Explicit random tensors,
not matching seeds, drive the adapter and exported graph.
"""
import argparse
import array
import contextlib
import importlib.metadata
import io
import json
import math
import os
import pathlib
import re
import socket
import subprocess
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from tools.rvc_export import (MAX_AUDIO_BYTES, MAX_INDEX_BYTES, MAX_MODEL_BYTES,
                              UPSTREAM, audio_metrics, read_bound, sha)
from tools.rvc_training import run_stage
from tools.rvc_validation import _speaker_config, _write, check_source

VERSIONS = {'torch': '2.4.1+cpu', 'numpy': '1.26.4', 'scipy': '1.13.1',
            'onnx': '1.17.0', 'onnxruntime': '1.24.2'}
OPSET = 17
FRAMES = 100
SAMPLES = 40000
CASES = ('voiced', 'unvoiced', 'mixed_pitch_edges', 'length_one', 'length_last')
INPUTS = ('phone', 'lengths', 'pitch', 'pitchf', 'speaker', 'latent_noise', 'phase_noise', 'excitation_noise')
SHAPES = {'phone': [1, FRAMES, 768], 'lengths': [1], 'pitch': [1, FRAMES],
          'pitchf': [1, FRAMES], 'speaker': [1], 'latent_noise': [1, 192, FRAMES],
          'phase_noise': [1, 1, 1], 'excitation_noise': [1, SAMPLES, 1],
          'original': [1, 1, SAMPLES], 'adapter': [1, 1, SAMPLES], 'ort': [1, 1, SAMPLES]}
THRESHOLDS = {'originalAdapter': {'maxAbs': 1e-6, 'rms': 1e-7},
              'originalORT': {'maxAbs': 2e-4, 'rms': 2e-5}}
CAPABILITIES = dict(hubert=False, pitchExtraction=False, retrieval=False, audioDSP=False,
                    endToEndConversion=False, dynamicShapes=False, coreML=False,
                    nativeIPhoneRuntime=False, identity=False, likeness=False)
MAX_ONNX_BYTES = 768 * 1024 * 1024
SOURCE_MODULES = ('models', 'modules', 'attentions', 'commons', 'transforms')


def _path(value):
    path = pathlib.Path(value).absolute()
    if path != path.resolve() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Linked or non-canonical paths are unsupported')
    return path


def _cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise InterruptedError('Portable feasibility check cancelled')


def _checked_proof(raw):
    proof = json.loads(raw)
    if not isinstance(proof, dict):
        raise ValueError('A conversion proof object is required')
    words = proof.get('wordcheck')
    required = dict(schemaVersion=1, status='conversion-checked-needs-review',
                    sourceRevision=UPSTREAM, modelVersion='v2', sampleRate=40000,
                    featureDimensions=768, audioPassed=True)
    if (any(proof.get(k) != v or type(proof.get(k)) is not type(v) for k, v in required.items()) or
            type(proof.get('indexVectors')) is not int or not 1 <= proof['indexVectors'] <= 174762 or
            not isinstance(words, dict) or words.get('passed') is not True or
            type(words.get('wordErrorRate')) not in (int, float) or not 0 <= words['wordErrorRate'] <= .1 or
            words.get('wavSHA256') != proof.get('outputSHA256')):
        raise ValueError('Fresh v2/40k conversion and independent word evidence are required')
    gate = proof.get('effectiveTrainingData')
    if (not isinstance(gate, dict) or
            type(gate.get('gateVersion')) is not int or gate['gateVersion'] != 1 or
            gate.get('status') != 'passed' or
            type(gate.get('minimumActiveSeconds')) not in (int, float) or
            gate['minimumActiveSeconds'] != 60 or
            type(gate.get('activeLowerBoundSeconds')) not in (int, float) or
            not 60 <= gate['activeLowerBoundSeconds'] <= 1800 or
            not isinstance(gate.get('effectiveDatasetSHA256'), str) or
            not re.fullmatch('[0-9a-f]{64}', gate['effectiveDatasetSHA256']) or
            not isinstance(proof.get('trainingReportSHA256'), str) or
            not re.fullmatch('[0-9a-f]{64}', proof['trainingReportSHA256'])):
        raise ValueError('Passing effective-training data and bound training report are required')
    for key in ('model', 'index', 'output'):
        if (not isinstance(proof.get(key), str) or not isinstance(proof.get(key + 'SHA256'), str) or
                not re.fullmatch('[0-9a-f]{64}', proof[key + 'SHA256'])):
            raise ValueError('Invalid conversion artifact binding')
    return proof


def error_metrics(expected, actual):
    """Measured scalar errors, rejecting nonfinite, empty or mismatched arrays."""
    if not len(expected) or len(expected) != len(actual):
        raise ValueError('Empty or mismatched parity tensors')
    errors = []
    for left, right in zip(expected, actual):
        if isinstance(left, bool) or isinstance(right, bool) or not math.isfinite(left) or not math.isfinite(right):
            raise ValueError('Nonfinite or non-numeric parity tensor')
        errors.append(abs(float(left) - float(right)))
    result = dict(count=len(errors), maxAbs=max(errors), rms=math.sqrt(math.fsum(x*x for x in errors) / len(errors)))
    if not math.isfinite(result['rms']) or not math.isfinite(result['maxAbs']):
        raise ValueError('Nonfinite parity error')
    return result


def _within(metrics, stage):
    if any(metrics[key] > limit for key, limit in THRESHOLDS[stage].items()):
        raise ValueError(stage + ' numerical parity exceeded fixed thresholds: ' + str(metrics))


def export_synthesizer(root, proof_path, output_dir, *, proof_sha256,
                       synthetic_provenance, python=sys.executable, cancel=None, timeout=600):
    """Create a new private diagnostic directory; return its report only on parity.

    synthetic_provenance is an explicit declaration, not inferred speaker identity:
    kind=synthetic-test-fixture, modelSHA256, conversionProofSHA256, source, permission.
    Source-only/unit tests cannot establish neural success. A passing result still
    supports only synthetic input tensors, one shape and speaker ID zero.
    """
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 1800:
        raise ValueError('Timeout must be finite and between zero and 1800 seconds')
    _cancel(cancel)
    if not isinstance(proof_sha256, str) or not re.fullmatch('[0-9a-f]{64}', proof_sha256):
        raise ValueError('Supply the previously verified conversion proof hash')
    root, proof_path, folder = _path(root), _path(proof_path), _path(output_dir)
    if not root.is_dir() or folder == root or root in folder.parents:
        raise ValueError('Keep portable outputs outside the upstream checkout')
    if any((p / 'collection.json').exists() for p in (folder, *folder.parents)):
        raise ValueError('Keep portable outputs separate from F5 collections')
    raw = read_bound(proof_path, 1024 * 1024, proof_sha256)
    proof = _checked_proof(raw)
    provenance = synthetic_provenance
    if (not isinstance(provenance, dict) or set(provenance) != {
            'kind', 'modelSHA256', 'conversionProofSHA256', 'source', 'permission'} or
            provenance['kind'] != 'synthetic-test-fixture' or
            provenance['modelSHA256'] != proof['modelSHA256'] or
            provenance['conversionProofSHA256'] != proof_sha256 or
            any(not isinstance(provenance[k], str) or not 1 <= len(provenance[k].strip()) <= 3000
                for k in ('source', 'permission'))):
        raise ValueError('Hash-bound explicit synthetic-test provenance is required')
    model = read_bound(_path(proof['model']), MAX_MODEL_BYTES, proof['modelSHA256'])
    read_bound(_path(proof['index']), MAX_INDEX_BYTES, proof['indexSHA256'])
    if audio_metrics(read_bound(_path(proof['output']), MAX_AUDIO_BYTES, proof['outputSHA256']))['sampleRate'] != 40000:
        raise ValueError('Conversion evidence sample rate changed')
    _cancel(cancel)
    folder.mkdir(exist_ok=False)
    state = dict(schemaVersion=1, status='checking', sourceRevision=UPSTREAM,
                 conversionProofSHA256=proof_sha256, modelSHA256=proof['modelSHA256'],
                 synthesizerParityVerified=False, capabilities=dict(CAPABILITIES),
                 syntheticProvenance=dict(provenance), plannedVersions=dict(VERSIONS),
                 opset=OPSET, frameCount=FRAMES, thresholds=THRESHOLDS)
    report_path = folder / 'portable.json'
    _write(report_path, state)
    try:
        (folder / 'model.pth').write_bytes(model)
        del model
        (folder / 'conversion-proof.json').write_bytes(raw)
        request = dict(root=str(root), modelSHA256=proof['modelSHA256'],
                       conversionProofSHA256=proof_sha256)
        request_path = folder / 'request.json'
        _write(request_path, request)
        request_hash = sha(read_bound(request_path, 65536))
        env = dict(os.environ, HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                   CUDA_VISIBLE_DEVICES='', OMP_NUM_THREADS='2', MKL_NUM_THREADS='2',
                   RVC_CUDA_GRAPH='0', PYTHONDONTWRITEBYTECODE='1')
        env.pop('PYTHONPATH', None)
        command = [str(python), '-I', str(pathlib.Path(__file__).resolve()),
                   '--child', str(request_path), request_hash]
        with (folder / 'export.log').open('wb') as log:
            run_stage(command, cwd=folder, env=env, log=log, timeout=timeout, cancel=cancel)
        _cancel(cancel)
        read_bound(folder / 'model.pth', MAX_MODEL_BYTES, proof['modelSHA256'])
        read_bound(folder / 'conversion-proof.json', 1024 * 1024, proof_sha256)
        read_bound(request_path, 65536, request_hash)
        result = json.loads(read_bound(folder / 'child-result.json', 1024 * 1024))
        _validate_result(folder, result, request)
        _cancel(cancel)
        state.update(status='synthesizer-parity-checked', synthesizerParityVerified=True,
                     result=result)
        _write(report_path, state)
    except BaseException as error:
        state.update(status='cancelled' if isinstance(error, (InterruptedError, KeyboardInterrupt)) else 'failed',
                     synthesizerParityVerified=False, error=str(error), errorType=type(error).__name__)
        _write(report_path, state)
        raise
    return report_path


def _dtype(name):
    return '<i8' if name in ('lengths', 'pitch', 'speaker') else '<f4'


def _tensor_path(case, name):
    return case + '/' + name + ('.i64' if _dtype(name) == '<i8' else '.f32')


def read_waveform(path, expected_sha256):
    """Decode exactly the hash-verified bytes used for a numerical comparison."""
    raw = read_bound(_path(path), SAMPLES * 4, expected_sha256)
    if len(raw) != SAMPLES * 4:
        raise ValueError('Unexpected waveform tensor length')
    values = array.array('f', raw)
    if sys.byteorder != 'little': values.byteswap()
    return values


def _validate_result(folder, result, request):
    """Re-hash all evidence and independently recompute reported waveform errors."""
    if (not isinstance(result, dict) or result.get('schemaVersion') != 1 or
            result.get('status') != 'synthesizer-parity-checked' or
            result.get('sourceRevision') != UPSTREAM or
            any(result.get(k) != request[k] for k in ('modelSHA256', 'conversionProofSHA256')) or
            result.get('versions') != VERSIONS or result.get('provider') != 'CPUExecutionProvider' or
            result.get('opset') != OPSET or type(result.get('irVersion')) is not int or
            not 1 <= result['irVersion'] <= 10 or result.get('capabilities') != CAPABILITIES or
            any(value is not False for value in result['capabilities'].values()) or
            result.get('thresholds') != THRESHOLDS or not isinstance(result.get('cases'), dict) or
            set(result['cases']) != set(CASES) or not isinstance(result.get('artifacts'), dict) or
            not isinstance(result.get('sourceFiles'), dict) or
            set(result['sourceFiles']) != {name + '.py' for name in SOURCE_MODULES}):
        raise ValueError('Incomplete or incompatible portable result')
    for name, expected in result['sourceFiles'].items():
        if not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected):
            raise ValueError('Invalid pinned source snapshot hash')
        read_bound(_path(folder / 'source' / 'infer' / 'module' / name), 1024 * 1024, expected)
    expected_files = {'synthesizer.onnx'} | {_tensor_path(c, n) for c in CASES for n in SHAPES}
    if set(result['artifacts']) != expected_files:
        raise ValueError('Missing or unexpected parity artifacts')
    for name, metadata in result['artifacts'].items():
        if (not isinstance(metadata, dict) or type(metadata.get('bytes')) is not int or
                not isinstance(metadata.get('sha256'), str) or not re.fullmatch('[0-9a-f]{64}', metadata['sha256'])):
            raise ValueError('Invalid artifact metadata')
        raw = read_bound(_path(folder / name), MAX_ONNX_BYTES if name.endswith('.onnx') else 1024*1024,
                         metadata['sha256'])
        if len(raw) != metadata['bytes']:
            raise ValueError('Artifact byte count changed')
        if name != 'synthesizer.onnx':
            tensor = name.split('/')[1].split('.')[0]
            dtype, shape = _dtype(tensor), SHAPES[tensor]
            if metadata.get('dtype') != dtype or metadata.get('shape') != shape or len(raw) != math.prod(shape) * (8 if dtype == '<i8' else 4):
                raise ValueError('Invalid fixed-shape tensor metadata')
    for case in CASES:
        if not isinstance(result['cases'][case], dict) or set(result['cases'][case]) != set(THRESHOLDS):
            raise ValueError('Missing or unexpected case comparisons')
        outputs = {}
        for name in ('original', 'adapter', 'ort'):
            relative = _tensor_path(case, name)
            outputs[name] = read_waveform(folder / relative, result['artifacts'][relative]['sha256'])
        for stage, actual in [('originalAdapter', 'adapter'), ('originalORT', 'ort')]:
            measured = error_metrics(outputs['original'], outputs[actual])
            claimed = result['cases'][case].get(stage)
            if (not isinstance(claimed, dict) or claimed != measured or
                    type(claimed.get('count')) is not int or
                    any(type(claimed.get(key)) not in (int, float) for key in ('maxAbs', 'rms'))):
                raise ValueError('Claimed parity errors do not match golden tensor bytes')
            _within(measured, stage)


@contextlib.contextmanager
def _capture_random(torch):
    """Only used within the dedicated child, never in an app/training process."""
    original_normal, original_uniform = torch.randn_like, torch.rand
    calls = []
    def normal(*args, **kwargs):
        value = original_normal(*args, **kwargs)
        calls.append(('normal', value.detach().clone()))
        return value
    def uniform(*args, **kwargs):
        value = original_uniform(*args, **kwargs)
        calls.append(('uniform', value.detach().clone()))
        return value
    try:
        torch.randn_like, torch.rand = normal, uniform
        yield calls
    finally:
        torch.randn_like, torch.rand = original_normal, original_uniform


def _adapter(torch, net):
    """Exact no-skip/no-resample upstream inference equations; fixed f0 model."""
    F = torch.nn.functional
    class ExplicitNoiseSynthesizer(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.net = net

        def forward(self, phone, lengths, pitch, pitchf, speaker,
                    latent_noise, phase_noise, excitation_noise):
            g = self.net.emb_g(speaker).unsqueeze(-1)
            m, logs, mask = self.net.enc_p(phone, pitch, lengths)
            z_p = (m + torch.exp(logs) * latent_noise * 0.66666) * mask
            z = self.net.flow(z_p, mask, g=g, reverse=True) * mask
            dec = self.net.dec
            sine = dec.m_source.l_sin_gen
            f0 = pitchf[:, None].transpose(1, 2)
            rad = f0 / sine.sampling_rate * torch.arange(1, dec.upp + 1, device=f0.device)
            rad2 = torch.fmod(rad[..., -1:].float() + 0.5, 1.0) - 0.5
            accumulator = rad2.cumsum(dim=1).fmod(1.0).to(f0)
            rad = rad + F.pad(accumulator, (0, 0, 1, -1))
            rad = rad.reshape(f0.shape[0], -1, 1)
            harmonics = torch.arange(1, sine.dim + 1, device=f0.device).reshape(1, 1, -1)
            rad = torch.multiply(rad, harmonics)
            # Upstream zeroes the fundamental phase after drawing it. No mutation
            # here: an explicit mask preserves that exact phase-input contract.
            phase_mask = (torch.arange(sine.dim, device=f0.device) != 0).to(f0).reshape(1, 1, -1)
            waves = torch.sin(2 * math.pi * (rad + phase_noise * phase_mask)) * sine.sine_amp
            uv = torch.ones_like(f0) * (f0 > sine.voiced_threshold)
            uv = F.interpolate(uv.transpose(2, 1), scale_factor=float(dec.upp), mode='nearest').transpose(2, 1)
            noise_amp = uv * sine.noise_std + (1 - uv) * sine.sine_amp / 3
            waves = waves * uv + noise_amp * excitation_noise
            source = dec.m_source.l_tanh(dec.m_source.l_linear(waves.to(dec.m_source.l_linear.weight.dtype)))
            source = source.transpose(1, 2)
            x = dec.conv_pre(z) + dec.cond(g)
            for i, (ups, noise_conv) in enumerate(zip(dec.ups, dec.noise_convs)):
                x = ups(F.leaky_relu(x, dec.lrelu_slope)) + noise_conv(source)
                summed = None
                for j in range(dec.num_kernels):
                    value = dec.resblocks[i * dec.num_kernels + j](x)
                    summed = value if summed is None else summed + value
                x = summed / dec.num_kernels
            return torch.tanh(dec.conv_post(F.leaky_relu(x)))
    return ExplicitNoiseSynthesizer().eval()


def _save_tensor(folder, case, name, tensor, artifacts):
    import numpy as np
    value = tensor.detach().cpu().numpy() if hasattr(tensor, 'detach') else tensor
    if (list(value.shape) != SHAPES[name] or not np.isfinite(value).all() or
            value.dtype.kind != ('i' if _dtype(name) == '<i8' else 'f') or
            value.dtype.itemsize != (8 if _dtype(name) == '<i8' else 4)):
        raise ValueError('Unexpected or nonfinite tensor: ' + name)
    value = np.asarray(value, dtype=_dtype(name), order='C')
    raw = value.tobytes()
    relative = _tensor_path(case, name)
    path = folder / relative
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(raw)
    artifacts[relative] = dict(bytes=len(raw), sha256=sha(raw), shape=list(value.shape), dtype=_dtype(name))


def _load_pinned_modules(root, folder):
    """Execute Git-object snapshots, never worktree bytecode/extension shadows.

    Files are retained for auditing; execution and inspect/torchscript source lookup
    use the same in-memory bytes. Only this five-module import closure is allowed.
    """
    import importlib.abc
    import importlib.util
    import linecache
    if any(name == 'infer' or name.startswith('infer.') for name in sys.modules):
        raise ValueError('Inference namespace was already imported')
    directory = folder / 'source' / 'infer' / 'module'
    directory.mkdir(parents=True, exist_ok=False)
    source, digests = {'infer': b'', 'infer.module': b''}, {}
    for name in SOURCE_MODULES:
        relative = 'infer/module/' + name + '.py'
        raw = subprocess.check_output(['git', 'show', UPSTREAM + ':' + relative], cwd=root, timeout=10)
        if not 0 < len(raw) <= 1024 * 1024:
            raise ValueError('Invalid pinned source object size')
        (directory / (name + '.py')).write_bytes(raw)
        source['infer.module.' + name] = raw
        digests[name + '.py'] = sha(raw)
    class SnapshotLoader(importlib.abc.MetaPathFinder, importlib.abc.Loader):
        def find_spec(self, fullname, path=None, target=None):
            if fullname in source:
                return importlib.util.spec_from_loader(fullname, self, is_package=fullname in ('infer', 'infer.module'))
            if fullname.startswith('infer.'):
                raise ImportError('Outside the pinned inference import closure: ' + fullname)
            return None
        def create_module(self, spec): return None
        def exec_module(self, module):
            name = module.__name__
            filename = str(folder / 'source' / (name.replace('.', '/') + '.py'))
            raw = source[name]
            module.__file__ = filename
            linecache.cache[filename] = (len(raw), None, raw.decode('utf-8').splitlines(True), filename)
            exec(compile(raw, filename, 'exec'), module.__dict__)
    sys.meta_path.insert(0, SnapshotLoader())
    from infer.module.models import SynthesizerTrnMs768NSFsid
    return SynthesizerTrnMs768NSFsid, digests


def _child(request_path, request_sha256):
    """Actual neural/export boundary. Never invoked by ordinary unit tests."""
    # -I intentionally ignores PYTHON* environment variables, including the
    # parent's PYTHONDONTWRITEBYTECODE. Set this explicitly before upstream imports.
    sys.dont_write_bytecode = True
    def offline(*args, **kwargs):
        raise RuntimeError('Network disabled during portable feasibility checks')
    socket.socket.connect = offline
    socket.socket.connect_ex = offline
    socket.create_connection = offline
    request_path = _path(request_path)
    request = json.loads(read_bound(request_path, 65536, request_sha256))
    root, folder = _path(request['root']), request_path.parent
    check_source(root)
    if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all', '--', 'infer'],
                               cwd=root, text=True, timeout=10).strip():
        raise ValueError('Inference source contains untracked or modified files')
    if sys.version_info[:2] != (3, 12):
        raise ValueError('Use the separate pinned Python 3.12 export environment')
    versions = {name: importlib.metadata.version(name) for name in VERSIONS}
    if versions != VERSIONS:
        raise ValueError('Export package versions differ from pinned contract: ' + str(versions))
    # No imported package may auto-fetch weights. Only local checkpoint tensors
    # and pinned inference layers are used; HuBERT/RMVPE are deliberately absent.
    import numpy as np
    import torch
    import onnx
    import onnxruntime as ort
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    SynthesizerTrnMs768NSFsid, source_digests = _load_pinned_modules(root, folder)
    raw = read_bound(folder / 'model.pth', MAX_MODEL_BYTES, request['modelSHA256'])
    checkpoint = torch.load(io.BytesIO(raw), map_location='cpu', weights_only=True)
    del raw
    if not isinstance(checkpoint, dict) or checkpoint.get('version') != 'v2' or checkpoint.get('f0') != 1 or checkpoint.get('sr') not in (40000, '40k'):
        raise ValueError('Expected v2/f0/40k checkpoint')
    config, weights = checkpoint.get('config'), checkpoint.get('weight')
    if (not isinstance(config, (list, tuple)) or len(config) != 18 or not isinstance(weights, dict) or not weights or
            any(not isinstance(t, torch.Tensor) or not torch.isfinite(t).all() for t in weights.values())):
        raise ValueError('Malformed checkpoint tensors or configuration')
    config = _speaker_config(config, weights.get('emb_g.weight'))
    expected = [1025, 32, 192, 192, 768, 2, 6, 3, 0, '1', [3, 7, 11],
                [[1, 3, 5]] * 3, [10, 10, 2, 2], 512, [16, 16, 4, 4]]
    if config[:15] != expected or config[-2] != 256 or config[-1] not in (40000, '40k'):
        raise ValueError('Only the pinned fixed 40k architecture is admitted')
    net = SynthesizerTrnMs768NSFsid(*config, is_half=False)
    del net.enc_q
    missing, unexpected = net.load_state_dict(weights, strict=False)
    if missing or any(not key.startswith('enc_q.') for key in unexpected):
        raise ValueError('Checkpoint architecture mismatch')
    net.eval().float()
    del checkpoint, weights
    if net.dec.upp != 400 or net.dec.m_source.l_sin_gen.dim != 1:
        raise ValueError('Unsupported excitation or upsampling architecture')
    adapter = _adapter(torch, net)
    artifacts, cases, vectors = {}, {}, []
    for index, case in enumerate(CASES):
        # Seeds merely create reproducible fixture inputs. Parity itself uses the
        # captured actual random tensors from the original call, not seed matching.
        generator = torch.Generator(device='cpu').manual_seed(347 + index)
        phone = torch.randn((1, FRAMES, 768), generator=generator) * .1
        pitchf = torch.full((1, FRAMES), 220., dtype=torch.float32)
        length = FRAMES
        if case == 'unvoiced': pitchf.zero_()
        if case == 'mixed_pitch_edges':
            pitchf[:, FRAMES // 2:] = 0
            pitchf[:, 0], pitchf[:, -1] = 50., 1100.
        if case == 'length_one': length = 1
        if case == 'length_last': length = FRAMES - 1
        mel = 1127 * torch.log(1 + pitchf / 700)
        lower, upper = 1127 * math.log(1 + 50 / 700), 1127 * math.log(1 + 1100 / 700)
        pitch = torch.round(torch.clamp((mel - lower) * 254 / (upper - lower) + 1, 1, 255)).long()
        args = (phone, torch.tensor([length], dtype=torch.int64), pitch, pitchf,
                torch.tensor([0], dtype=torch.int64))
        with torch.no_grad(), _capture_random(torch) as draws:
            original = net.infer(*args)[0].detach().clone()
        if [kind for kind, value in draws] != ['normal', 'uniform', 'normal']:
            raise ValueError('Upstream random-call contract changed')
        explicit = args + tuple(value for kind, value in draws)
        for name, value in zip(INPUTS, explicit):
            _save_tensor(folder, case, name, value, artifacts)
        with torch.no_grad(): output = adapter(*explicit).detach()
        _save_tensor(folder, case, 'original', original, artifacts)
        _save_tensor(folder, case, 'adapter', output, artifacts)
        measured = error_metrics(original.flatten().tolist(), output.flatten().tolist())
        cases[case] = dict(originalAdapter=measured)
        _write(folder / 'progress.json', dict(stage='original-adapter', cases=cases))
        _within(measured, 'originalAdapter')
        vectors.append((explicit, original))
    # No export may occur until every original-vs-adapter fixture passed.
    model_path = folder / 'synthesizer.onnx'
    with torch.no_grad():
        torch.onnx.export(adapter, vectors[0][0], str(model_path), export_params=True,
                          opset_version=OPSET, input_names=list(INPUTS), output_names=['audio'],
                          dynamic_axes=None, do_constant_folding=True, dynamo=False)
    # One immutable snapshot supplies checker, digest and runtime, closing file
    # replacement races between graph validation and ORT session creation.
    model_bytes = read_bound(model_path, MAX_ONNX_BYTES)
    graph = onnx.load_model_from_string(model_bytes)
    if not 1 <= graph.ir_version <= 10 or [(o.domain, o.version) for o in graph.opset_import] != [('', OPSET)]:
        raise ValueError('Unexpected ONNX IR/opset contract')
    onnx.checker.check_model(graph, full_check=True)
    forbidden = {'RandomNormal', 'RandomNormalLike', 'RandomUniform', 'RandomUniformLike', 'Bernoulli', 'Multinomial'}
    if (any(node.domain not in ('', 'ai.onnx') or node.op_type in forbidden or node.attribute and
            any(a.type in (onnx.AttributeProto.GRAPH, onnx.AttributeProto.GRAPHS) for a in node.attribute)
            for node in graph.graph.node) or any(t.external_data for t in graph.graph.initializer)):
        raise ValueError('Random/custom/control-flow/external-data ONNX is outside this bounded check')
    artifacts['synthesizer.onnx'] = dict(bytes=len(model_bytes), sha256=sha(model_bytes))
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2; options.inter_op_num_threads = 1
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    session = ort.InferenceSession(model_bytes, sess_options=options, providers=['CPUExecutionProvider'])
    del model_bytes
    if session.get_providers() != ['CPUExecutionProvider'] or [i.name for i in session.get_inputs()] != list(INPUTS):
        raise ValueError('ORT provider or explicit-input contract changed')
    for case, (explicit, original) in zip(CASES, vectors):
        for info, name in zip(session.get_inputs(), INPUTS):
            if info.shape != SHAPES[name] or info.type != ('tensor(int64)' if _dtype(name) == '<i8' else 'tensor(float)'):
                raise ValueError('ORT input shape or dtype differs from fixed contract')
        output = session.run(['audio'], {name: value.numpy() for name, value in zip(INPUTS, explicit)})[0]
        _save_tensor(folder, case, 'ort', output, artifacts)
        measured = error_metrics(original.flatten().tolist(), output.flatten().tolist())
        cases[case]['originalORT'] = measured
        _write(folder / 'progress.json', dict(stage='onnx-cpu', cases=cases))
        _within(measured, 'originalORT')
    check_source(root)
    result = dict(schemaVersion=1, status='synthesizer-parity-checked', sourceRevision=UPSTREAM,
                  modelSHA256=request['modelSHA256'], conversionProofSHA256=request['conversionProofSHA256'],
                  versions=versions, provider='CPUExecutionProvider', opset=OPSET,
                  irVersion=int(graph.ir_version), capabilities=dict(CAPABILITIES),
                  thresholds=THRESHOLDS, cases=cases, artifacts=artifacts, sourceFiles=source_digests)
    _validate_result(folder, result, request)
    _write(folder / 'child-result.json', result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--child', nargs=2, metavar=('REQUEST', 'SHA256'), required=True)
    arguments = parser.parse_args()
    _child(*arguments.child)
