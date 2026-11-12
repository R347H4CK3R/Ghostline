"""Offline CPU conversion and independent word checks for a newly trained RVC pair.

Never publishes to the live voice catalog. A passing report checks conversion
functionality only, not character identity, likeness, or native iPhone support.
"""
import argparse
import json
import os
import pathlib
import re
import subprocess
import sys

# Direct execution of the isolated child still needs our standard-library helpers.
if __package__ in (None, ''):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from tools.rvc_export import (MAX_AUDIO_BYTES, MAX_INDEX_BYTES, MAX_MODEL_BYTES,
                              UPSTREAM, audio_metrics, read_bound, sha)
from tools.rvc_preprocess import audit_preprocessed


def check_source(root):
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root,
                                       text=True, timeout=10).strip()
    dirty = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'],
                                    cwd=root, text=True, timeout=10).strip()
    if revision != UPSTREAM or dirty:
        raise ValueError('Use the clean pinned RVC source revision')


def _write(path, value):
    temporary = path.with_suffix('.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    temporary.replace(path)


def verify_conversion(root, training_report, input_wav, output_dir, *, expected_text,
                      verify_words, python=sys.executable, cancel=None, timeout=600,
                      runner=None):
    """Validate snapshots of trained artifacts, run real conversion, then run ASR.

    The callable word verifier must independently transcribe the emitted audio
    and bind its result to that exact WAV. Test doubles belong only in tests.
    All inputs stay private; failures retain diagnostics in a new directory.
    """
    from tools.rvc_training import run_stage
    root = pathlib.Path(root).resolve()
    if cancel and cancel.is_set():
        raise InterruptedError('RVC conversion cancelled')
    check_source(root)
    training_bytes = read_bound(training_report, 1024 * 1024)
    report = json.loads(training_bytes)
    if (not isinstance(report, dict) or report.get('sourceRevision') != UPSTREAM or
            report.get('status') != 'trained-needs-independent-conversion-check' or
            report.get('completedStages') != ['preprocess', 'pitch', 'features', 'train', 'index'] or
            not isinstance(report.get('indices'), list) or len(report['indices']) != 1 or
            not isinstance(report.get('indexSHA256'), dict) or
            type(report.get('epochs')) is not int or not 1 <= report['epochs'] <= 1200):
        raise ValueError('Completed training and one indexed model are required')
    experiment = report.get('experiment')
    dataset = report.get('dataset')
    effective = report.get('effectiveDataset')
    if (not isinstance(experiment, str) or not re.fullmatch('[a-z0-9_-]{1,80}', experiment) or
            not isinstance(dataset, dict) or not isinstance(dataset.get('files'), list) or
            not dataset['files'] or any(not isinstance(row, dict) for row in dataset['files']) or
            not isinstance(effective, dict) or effective.get('status') != 'ready-for-training' or
            effective.get('minimumActiveSeconds') != 60 or
            type(effective.get('activeLowerBoundSeconds')) not in (int, float) or
            not 60 <= effective['activeLowerBoundSeconds'] <= 1800):
        raise ValueError('Verified effective training data is required')
    exp = root / 'logs' / experiment
    if (not isinstance(report.get('model'), str) or not isinstance(report['indices'][0], str) or
            pathlib.Path(report['model']).absolute() != root / 'assets' / 'weights' / (experiment + '.pth') or
            pathlib.Path(report['indices'][0]).absolute().parent != exp or exp.resolve() != exp):
        raise ValueError('Artifacts do not belong to the checked training experiment')
    if audit_preprocessed(exp, expected_sources=len(dataset['files']), validate_features=True) != effective:
        raise ValueError('Effective training data changed after training')
    gate = dict(gateVersion=1, status='passed', minimumActiveSeconds=60,
                activeLowerBoundSeconds=effective['activeLowerBoundSeconds'],
                effectiveDatasetSHA256=sha(json.dumps(effective, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()))
    if (not callable(verify_words) or not isinstance(expected_text, str) or
            not 1 <= len(expected_text.strip()) <= 4000 or not re.search('[a-z0-9]', expected_text.lower())):
        raise ValueError('An independent word verifier and held-out transcript are required')
    model_digest = report.get('modelSHA256')
    index_digest = report['indexSHA256'].get(report['indices'][0])
    if any(not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value)
           for value in (model_digest, index_digest)):
        raise ValueError('Missing artifact digests')
    model = read_bound(report['model'], MAX_MODEL_BYTES, model_digest)
    index = read_bound(report['indices'][0], MAX_INDEX_BYTES, index_digest)
    source = read_bound(input_wav, MAX_AUDIO_BYTES)
    if sha(source) in {row.get('sha256') for row in dataset['files']}:
        raise ValueError('Validation must use held-out audio, not a training file')
    input_metrics = audio_metrics(source)
    folder = pathlib.Path(output_dir).absolute()
    if folder.resolve() != folder:
        raise ValueError('Linked conversion destinations are unsupported')
    folder.mkdir(parents=True, exist_ok=False)
    destination = folder / 'conversion.json'
    state = dict(schemaVersion=1, status='checking', sourceRevision=UPSTREAM,
                 modelSHA256=model_digest, indexSHA256=index_digest,
                 trainingReportSHA256=sha(training_bytes), effectiveTrainingData=gate,
                 inputSHA256=sha(source), physicalDeviceVerified=False,
                 identityVerified=False, likenessVerified=False)
    _write(destination, state)
    try:
        model_path = folder / 'model.pth'
        index_path = folder / 'model.index'
        source_path = folder / 'input.wav'
        output_path = folder / 'converted.wav'
        result_path = folder / 'neural-result.json'
        for path, data in ((model_path, model), (index_path, index), (source_path, source)):
            path.write_bytes(data)
        del model, index, source
        env = dict(os.environ, HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                   CUDA_VISIBLE_DEVICES='', OMP_NUM_THREADS='2', RVC_CUDA_GRAPH='0')
        command = [str(python), str(pathlib.Path(__file__).resolve()), '--child', str(root),
                   *map(str, (model_path, index_path, source_path, output_path, result_path))]
        with (folder / 'conversion.log').open('wb') as log:
            (runner or run_stage)(command, cwd=root, env=env, log=log, timeout=timeout, cancel=cancel)
        if cancel and cancel.is_set():
            raise InterruptedError('RVC conversion cancelled')
        neural = json.loads(read_bound(result_path, 1024 * 1024))
        if (not isinstance(neural, dict) or neural.get('modelVersion') != 'v2' or
                neural.get('sampleRate') != 40000 or neural.get('featureDimensions') != 768 or
                type(neural.get('indexVectors')) is not int or neural['indexVectors'] < 1 or
                any(neural.get(field) != state[field]
                    for field in ('modelSHA256', 'indexSHA256', 'inputSHA256'))):
            raise ValueError('Neural result does not match the checked artifacts')
        # Reject replacements after inference as well as mismatched child evidence.
        read_bound(model_path, MAX_MODEL_BYTES, model_digest)
        read_bound(index_path, MAX_INDEX_BYTES, index_digest)
        read_bound(source_path, MAX_AUDIO_BYTES, state['inputSHA256'])
        output = read_bound(output_path, MAX_AUDIO_BYTES)
        metrics = audio_metrics(output)
        if metrics['sampleRate'] != 40000 or abs(metrics['seconds'] - input_metrics['seconds']) > .25:
            raise ValueError('Converted audio rate or duration changed')
        output_digest = sha(output)
        words = verify_words(output_path, expected_text)
        if (not isinstance(words, dict) or words.get('passed') is not True or
                type(words.get('wordErrorRate')) not in (int, float) or
                not 0 <= words['wordErrorRate'] <= .1 or words.get('wavSHA256') != output_digest):
            raise ValueError('Independent transcription did not pass for this conversion')
        read_bound(output_path, MAX_AUDIO_BYTES, output_digest)
        if cancel and cancel.is_set():
            raise InterruptedError('RVC conversion cancelled')
        state.update(status='conversion-checked-needs-review', model=str(model_path),
                     index=str(index_path), output=str(output_path), outputSHA256=output_digest,
                     modelVersion='v2', sampleRate=40000, featureDimensions=768,
                     indexVectors=neural['indexVectors'], audioPassed=True, audio=metrics,
                     wordcheck=words)
        _write(destination, state)
    except Exception as error:
        state.update(status='cancelled' if isinstance(error, InterruptedError) else 'failed', error=str(error))
        _write(destination, state)
        raise
    return destination


def _speaker_config(config, embedding):
    # The upstream single-label trainer retains a 109-row embedding table.
    # Table capacity is not the number of identities in this training dataset.
    if (embedding is None or embedding.ndim != 2 or
            not 1 <= embedding.shape[0] <= 1024 or not 1 <= embedding.shape[1] <= 1024 or
            config[-3] != embedding.shape[0] or config[-2] != embedding.shape[1]):
        raise ValueError('Invalid or inconsistent speaker embedding table')
    return list(config)


def _child(root, model_path, index_path, source_path, output_path, result_path):
    """The expensive boundary: pinned upstream CPU neural inference, no downloads."""
    import fractions
    import io
    import socket
    from types import SimpleNamespace
    def offline(*_args, **_kwargs):
        raise RuntimeError('Network disabled during RVC conversion checks')
    socket.socket.connect = offline
    socket.socket.connect_ex = offline
    socket.create_connection = offline
    root = pathlib.Path(root).resolve()
    check_source(root)
    # Both projects use a tools namespace package. Include both search roots.
    sys.path.insert(0, str(root))
    import tools
    if str(root / 'tools') not in tools.__path__:
        tools.__path__.append(str(root / 'tools'))
    import faiss
    import numpy as np
    import scipy.signal
    import soundfile as sf
    import torch
    torch.set_num_threads(2)
    torch.manual_seed(347)
    faiss.omp_set_num_threads(2)
    model_bytes = read_bound(model_path, MAX_MODEL_BYTES)
    index_bytes = read_bound(index_path, MAX_INDEX_BYTES)
    input_bytes = read_bound(source_path, MAX_AUDIO_BYTES)
    audio_metrics(input_bytes)
    state = torch.load(io.BytesIO(model_bytes), map_location='cpu', weights_only=True)
    if not isinstance(state, dict) or state.get('version') != 'v2' or state.get('f0') != 1:
        raise ValueError('Expected a v2 pitch-aware RVC model')
    weights = state.get('weight')
    config = state.get('config')
    if (not isinstance(weights, dict) or not weights or not isinstance(config, (list, tuple)) or len(config) != 18 or
            any(not isinstance(value, torch.Tensor) or not torch.isfinite(value).all() for value in weights.values())):
        raise ValueError('Invalid model architecture or tensors')
    config = _speaker_config(config, weights.get('emb_g.weight'))
    if config[-1] not in (40000, '40k') or state.get('sr') not in (40000, '40k'):
        raise ValueError('Expected a 40 kHz model')
    index = faiss.deserialize_index(np.frombuffer(index_bytes, dtype=np.uint8).copy())
    if index.d != 768 or not index.is_trained or index.ntotal < 1:
        raise ValueError('Expected a populated trained 768-dimensional index')
    # Upstream uses all reconstructed vectors at inference; reject invalid data.
    for start in range(0, index.ntotal, 1024):
        if not np.isfinite(index.reconstruct_n(start, min(1024, index.ntotal - start))).all():
            raise ValueError('Index contains nonfinite features')
    from infer.hubert import load_hubert_model
    from infer.module.models import SynthesizerTrnMs768NSFsid
    from infer.vc.pipeline import Pipeline
    net = SynthesizerTrnMs768NSFsid(*config, is_half=False)
    del net.enc_q
    missing, unexpected = net.load_state_dict(weights, strict=False)
    if missing or any(not key.startswith('enc_q.') for key in unexpected):
        raise ValueError('Checkpoint architecture mismatch')
    net.eval().float()
    hubert = load_hubert_model('cpu', False)
    signal, rate = sf.read(io.BytesIO(input_bytes), dtype='float32')
    ratio = fractions.Fraction(16000, rate)
    signal = scipy.signal.resample_poly(signal, ratio.numerator, ratio.denominator)
    converter = Pipeline(40000, SimpleNamespace(x_pad=1, x_query=6, x_center=38, x_max=41,
                                               is_half=False, device='cpu'))
    with torch.inference_mode():
        converted = converter.pipeline(hubert, net, 0, signal.copy(), [0, 0, 0], 0, 'pm',
                                       str(index_path), .75, 1, 40000, 0, 1, 'v2', .33)
    if converted.dtype != np.int16 or not np.isfinite(converted).all():
        raise ValueError('Invalid converted samples')
    sf.write(output_path, converted, 40000, subtype='PCM_16')
    audio_metrics(read_bound(output_path, MAX_AUDIO_BYTES))
    _write(pathlib.Path(result_path), dict(modelSHA256=sha(model_bytes), indexSHA256=sha(index_bytes),
           inputSHA256=sha(input_bytes), modelVersion='v2', sampleRate=40000,
           featureDimensions=768, indexVectors=int(index.ntotal)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--child', nargs=6, metavar=('ROOT', 'MODEL', 'INDEX', 'INPUT', 'OUTPUT', 'RESULT'), required=True)
    args = parser.parse_args()
    _child(*args.child)
