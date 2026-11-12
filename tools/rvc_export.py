"""Private RVC artifact export, gated on hash-bound conversion/word evidence.

This is separate from F5 reference collections. It does not add an iPhone RVC
runtime, identify a character, establish likeness, or run pickle deserialization.
"""
import array
import hashlib
import io
import json
import math
import os
import pathlib
import re
import stat
import sys
import tempfile
import wave

UPSTREAM = '81eed5e8f68b6bed1789f682fe78cdd324495afc'
MAX_MODEL_BYTES = 512 * 1024 * 1024
MAX_INDEX_BYTES = 512 * 1024 * 1024
MAX_AUDIO_BYTES = 3 * 1024 * 1024


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_bound(path, maximum, expected=None):
    path = pathlib.Path(path)
    if path.is_symlink():
        raise ValueError('Linked artifacts are unsupported')
    with path.open('rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= maximum:
            raise ValueError('Artifact is empty or exceeds its bound')
        data = stream.read(maximum + 1)
    if len(data) != info.st_size or (expected is not None and sha(data) != expected):
        raise ValueError('Artifact checksum or size changed')
    return data


def audio_metrics(data):
    try:
        with wave.open(io.BytesIO(data), 'rb') as stream:
            rate = stream.getframerate()
            count = stream.getnframes()
            if (stream.getnchannels(), stream.getsampwidth(), stream.getcomptype()) != (1, 2, 'NONE'):
                raise ValueError('Use mono PCM16 audio')
            if rate not in (16000, 22050, 24000, 32000, 40000, 44100, 48000) or not .2 <= count / rate <= 30:
                raise ValueError('Conversion check audio must be 0.2–30 seconds')
            pcm = stream.readframes(count)
    except (wave.Error, EOFError) as error:
        raise ValueError('Invalid conversion WAV') from error
    if len(pcm) != count * 2:
        raise ValueError('Truncated conversion WAV')
    samples = array.array('h', pcm)
    if sys.byteorder != 'little':
        samples.byteswap()
    rms = math.sqrt(sum(value * value for value in samples) / count) / 32768
    clipped = sum(abs(value) >= 32767 for value in samples)
    if rms <= .0001 or clipped:
        raise ValueError('Conversion audio is silent or clipped')
    return dict(sampleRate=rate, seconds=count / rate, rms=rms, fullScaleSamples=clipped)


def _metadata(value):
    if not isinstance(value, dict) or set(value) != {'id', 'name', 'categories', 'source', 'permission'}:
        raise ValueError('Supply explicit model identity and provenance')
    if not isinstance(value['id'], str) or not re.fullmatch('[a-z0-9_-]{1,100}', value['id']):
        raise ValueError('Unsafe voice identifier')
    for field, limit in [('name', 200), ('source', 3000), ('permission', 3000)]:
        text = value[field]
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= limit or any(ord(c) < 32 for c in text):
            raise ValueError('Invalid voice metadata')
    categories = value['categories']
    if not isinstance(categories, list) or not 1 <= len(categories) <= 20 or any(
            not isinstance(item, str) or not 1 <= len(item.strip()) <= 100 or any(ord(c) < 32 for c in item)
            for item in categories):
        raise ValueError('Invalid voice categories')
    return dict(value)


def _proof(report):
    proof = json.loads(read_bound(report, 1024 * 1024))
    words = proof.get('wordcheck', {}) if isinstance(proof, dict) else {}
    gate = proof.get('effectiveTrainingData', {}) if isinstance(proof, dict) else {}
    if (not isinstance(proof, dict) or proof.get('schemaVersion') != 1 or
            proof.get('status') != 'conversion-checked-needs-review' or
            proof.get('sourceRevision') != UPSTREAM or proof.get('modelVersion') != 'v2' or
            proof.get('sampleRate') != 40000 or proof.get('featureDimensions') != 768 or
            type(proof.get('indexVectors')) is not int or proof['indexVectors'] < 1 or
            proof.get('audioPassed') is not True or not isinstance(words, dict) or
            words.get('passed') is not True or type(words.get('wordErrorRate')) not in (int, float) or
            not 0 <= words['wordErrorRate'] <= .1 or
            words.get('wavSHA256') != proof.get('outputSHA256') or
            not isinstance(gate, dict) or type(gate.get('gateVersion')) is not int or gate['gateVersion'] != 1 or
            gate.get('status') != 'passed' or gate.get('minimumActiveSeconds') != 60 or
            type(gate.get('activeLowerBoundSeconds')) not in (int, float) or
            not 60 <= gate['activeLowerBoundSeconds'] <= 1800 or
            not isinstance(gate.get('effectiveDatasetSHA256'), str) or
            not re.fullmatch('[0-9a-f]{64}', gate['effectiveDatasetSHA256'])):
        raise ValueError('Fresh conversion, index and independent word checks are required')
    for field in ('modelSHA256', 'indexSHA256', 'outputSHA256', 'trainingReportSHA256'):
        if not isinstance(proof.get(field), str) or not re.fullmatch('[0-9a-f]{64}', proof[field]):
            raise ValueError('Invalid conversion evidence digest')
    return proof


def export_folder(report, metadata, root, *, cancelled=lambda: False):
    """Copy the exact checked .pth/.index pair to a new private character folder.

    The report must be produced by the independent conversion checker, not a
    user-editable success toggle. Importing this format into the current native
    F5-only voice picker is intentionally unsupported.
    """
    from tools.master_voices import _publish_lock
    if cancelled():
        raise InterruptedError('RVC export cancelled')
    metadata = _metadata(metadata)
    proof = _proof(report)
    model = read_bound(proof['model'], MAX_MODEL_BYTES, proof['modelSHA256'])
    index = read_bound(proof['index'], MAX_INDEX_BYTES, proof['indexSHA256'])
    audio = read_bound(proof['output'], MAX_AUDIO_BYTES, proof['outputSHA256'])
    metrics = audio_metrics(audio)
    if metrics['sampleRate'] != proof['sampleRate']:
        raise ValueError('Conversion evidence sample rate changed')
    root = pathlib.Path(root).absolute()
    if any(path.is_symlink() for path in [root, *root.parents]):
        raise ValueError('Linked export destinations are unsupported')
    if (root / 'collection.json').exists():
        raise ValueError('Use a separate RVC folder; preserve the F5 reference collection')
    if cancelled():
        raise InterruptedError('RVC export cancelled')
    root.mkdir(parents=True, exist_ok=True)
    target = root / metadata['id']
    manifest = dict(metadata, schemaVersion=1, format='rvc-v2-pth-index',
                    status='conversion-checked-needs-review', modelVersion='v2',
                    sampleRate=40000, featureDimensions=768, indexVectors=proof['indexVectors'],
                    sourceRevision=UPSTREAM, modelFile='model.pth', indexFile='model.index',
                    modelSHA256=proof['modelSHA256'], indexSHA256=proof['indexSHA256'],
                    modelBytes=len(model), indexBytes=len(index),
                    validationAudioSHA256=proof['outputSHA256'],
                    wordErrorRate=proof['wordcheck']['wordErrorRate'],
                    trainingReportSHA256=proof['trainingReportSHA256'],
                    effectiveTrainingData=proof['effectiveTrainingData'],
                    identityVerified=False, likenessVerified=False,
                    nativeIPhoneRuntimeVerified=False)
    with _publish_lock(root / '.rvc-export.lock'):
        if target.exists() or target.is_symlink():
            raise FileExistsError('Existing RVC character folder was preserved')
        with tempfile.TemporaryDirectory(prefix='.rvc-export-', dir=root) as temporary:
            stage = pathlib.Path(temporary)
            files = {'model.pth': model, 'model.index': index,
                     'manifest.json': (json.dumps(manifest, indent=2, allow_nan=False) + '\n').encode()}
            for name, data in files.items():
                if cancelled():
                    raise InterruptedError('RVC export cancelled')
                with (stage / name).open('wb') as stream:
                    stream.write(data); stream.flush(); os.fsync(stream.fileno())
            if cancelled():
                raise InterruptedError('RVC export cancelled')
            if target.exists() or target.is_symlink():
                raise FileExistsError('Existing RVC character folder was preserved')
            stage.rename(target)
    return target
