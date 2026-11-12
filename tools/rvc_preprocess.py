"""Bounded validation for the pinned RVC preprocessing adapter.

The effective-audio floor is an engineering admission check, not a quality or
speaker-identity claim. Overlap deductions are deliberately conservative.
"""
import array
import ast
import hashlib
import math
import pathlib
import struct
import sys
from fractions import Fraction

MAX_WAV_BYTES = 16 * 1024 * 1024
MAX_ARRAY_BYTES = 64 * 1024 * 1024
MINIMUM_ACTIVE_SECONDS = 60
OVERLAP_SECONDS = .3


def _read(path, limit):
    path = pathlib.Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Missing or linked output: ' + str(path))
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    if not data or len(data) > limit:
        raise ValueError('Empty or oversized output: ' + str(path))
    return data


def _float_wav(path, expected_rate):
    data = _read(path, MAX_WAV_BYTES)
    if (len(data) < 12 or data[:4] != b'RIFF' or data[8:12] != b'WAVE' or
            struct.unpack_from('<I', data, 4)[0] + 8 != len(data)):
        raise ValueError('Malformed float WAV: ' + str(path))
    offset = 12
    fmt = pcm = None
    while offset < len(data):
        if offset + 8 > len(data):
            raise ValueError('Truncated WAV chunk')
        name = data[offset:offset + 4]
        size = struct.unpack_from('<I', data, offset + 4)[0]
        start = offset + 8
        end = start + size
        if end > len(data):
            raise ValueError('Truncated WAV data')
        if name == b'fmt ':
            if fmt is not None or size < 16:
                raise ValueError('Invalid WAV format chunk')
            fmt = struct.unpack_from('<HHIIHH', data, start)
        elif name == b'data':
            if pcm is not None:
                raise ValueError('Duplicate WAV data chunk')
            pcm = data[start:end]
        offset = end + (size % 2)
    if offset != len(data) or fmt != (3, 1, expected_rate, expected_rate * 4, 4, 32):
        raise ValueError('Expected mono IEEE float32 WAV at ' + str(expected_rate))
    if not pcm or len(pcm) % 4:
        raise ValueError('Empty or misaligned float WAV')
    samples = array.array('f', pcm)
    if sys.byteorder != 'little':
        samples.byteswap()
    if any(not math.isfinite(value) or abs(value) >= 1 for value in samples):
        raise ValueError('Float WAV must be finite and unclipped')
    active_samples = 0
    frame_size = expected_rate // 50
    for start in range(0, len(samples), frame_size):
        frame = samples[start:start + frame_size]
        if sum(value * value for value in frame) / len(frame) > .01 ** 2:
            active_samples += len(frame)
    return dict(seconds=len(samples) / expected_rate, activeSeconds=active_samples / expected_rate,
                activeSamples=active_samples, sampleCount=len(samples), fileBytes=len(data),
                sha256=hashlib.sha256(data).hexdigest())


def audit_preprocessed(experiment, *, expected_sources=None, validate_features=False):
    experiment = pathlib.Path(experiment)
    gt = sorted((experiment / '0_gt_wavs').glob('*.wav'))
    low = sorted((experiment / '1_16k_wavs').glob('*.wav'))
    if not gt or len(gt) > 10000 or [p.name for p in gt] != [p.name for p in low]:
        raise ValueError('Preprocessing requires matching nonempty 40k and 16k WAV outputs')
    if expected_sources is not None:
        import re
        if type(expected_sources) is not int or expected_sources < 1:
            raise ValueError('Invalid expected source count')
        matches = [re.fullmatch(r'(0|[1-9][0-9]*)_(0|[1-9][0-9]*)\.wav', path.name) for path in gt]
        if any(match is None for match in matches) or {int(match[1]) for match in matches} != set(range(expected_sources)):
            raise ValueError('Missing or unexpected preprocessed source outputs')
        for source_index in range(expected_sources):
            chunks = sorted(int(match[2]) for match in matches if int(match[1]) == source_index)
            if chunks != list(range(len(chunks))):
                raise ValueError('Incomplete preprocessed chunk sequence')
    rows, excluded = [], []
    lower = Fraction(0)
    for high_path, low_path in zip(gt, low):
        high = _float_wav(high_path, 40000)
        low_metrics = _float_wav(low_path, 16000)
        if abs(high['seconds'] - low_metrics['seconds']) > .002:
            raise ValueError('Resampled WAV duration mismatch')
        if validate_features:
            arrays = validate_arrays(experiment / '3_feature768' / (high_path.stem + '.npy'),
                                     experiment / '2a_f0' / (high_path.name + '.npy'),
                                     experiment / '2b-f0nsf' / (high_path.name + '.npy'))
        sampler_length = high['fileBytes'] // 1200 # pinned loader: bytes // (3 * hop400)
        if not 100 < sampler_length <= 900:
            excluded.append(dict(file=high_path.name, reason='outside-pinned-sampler-buckets', samplerLength=sampler_length))
            continue
        active = min(Fraction(high['activeSamples'], 40000), Fraction(low_metrics['activeSamples'], 16000))
        row = dict(file=high_path.name, seconds=high['seconds'], activeSeconds=float(active),
                   sha256=high['sha256'], resampledSHA256=low_metrics['sha256'], samplerLength=sampler_length)
        trim = Fraction(0)
        if validate_features:
            # Pinned get_labels repeats HuBERT frames twice and caps at900;
            # get_audio_text_pair trims audio to min(label, spectrogram) frames.
            frames = min(arrays['featureRows'] * 2, 900, high['sampleCount'] // 400)
            if arrays['pitchRows'] < frames:
                raise ValueError('Pitch arrays do not cover retained training frames')
            trim = max(Fraction(0), Fraction(high['sampleCount'], 40000) - Fraction(frames, 100))
            row.update(arrays, trainingFrames=frames, trimmedTailSeconds=float(trim))
        contribution = max(Fraction(0), active - Fraction(3, 10) - trim)
        row['activeLowerBoundSeconds'] = float(contribution)
        lower += contribution
        rows.append(row)
    ready = 'ready-for-training' if validate_features else 'ready-for-features'
    return dict(status=ready if lower >= MINIMUM_ACTIVE_SECONDS else 'insufficient-effective-data',
                minimumActiveSeconds=MINIMUM_ACTIVE_SECONDS, fileCount=len(gt),
                retainedFileCount=len(rows), excludedFileCount=len(excluded), expectedSourceCount=expected_sources,
                seconds=sum(row['seconds'] for row in rows), activeSeconds=sum(row['activeSeconds'] for row in rows),
                activeLowerBoundSeconds=float(lower), maximumOverlapSecondsPerOutput=OVERLAP_SECONDS,
                overlapRule='Subtract 0.3 seconds per sampler-eligible output plus possible feature trimming; floor each contribution at zero.',
                excludedFiles=excluded, files=rows)


def _npy(path):
    data = _read(path, MAX_ARRAY_BYTES)
    if len(data) < 10 or data[:6] != b'\x93NUMPY' or data[6:8] not in (b'\x01\x00', b'\x02\x00', b'\x03\x00'):
        raise ValueError('Invalid NPY header')
    length_size = 2 if data[6] == 1 else 4
    start = 8 + length_size
    if len(data) < start:
        raise ValueError('Truncated NPY header')
    length = int.from_bytes(data[8:start], 'little')
    if not 0 < length <= 65536 or start + length > len(data):
        raise ValueError('Unbounded or truncated NPY header')
    try:
        header = ast.literal_eval(data[start:start + length].decode('utf-8'))
    except (ValueError, SyntaxError, UnicodeError, RecursionError) as error:
        raise ValueError('Invalid NPY header') from error
    if (not isinstance(header, dict) or set(header) != {'descr', 'fortran_order', 'shape'} or
            header['fortran_order'] is not False or not isinstance(header['shape'], tuple) or
            not 1 <= len(header['shape']) <= 2 or
            any(type(size) is not int or not 0 < size <= 1000000 for size in header['shape'])):
        raise ValueError('Unsupported NPY layout')
    kinds = {'<f4': ('f', 4), '<f8': ('d', 8), '<i8': ('q', 8), '<i4': ('i', 4)}
    if not isinstance(header['descr'], str) or header['descr'] not in kinds:
        raise ValueError('Unsupported NPY dtype; object arrays are forbidden')
    code, width = kinds[header['descr']]
    count = math.prod(header['shape'])
    payload = data[start + length:]
    if count * width != len(payload):
        raise ValueError('Truncated or extra NPY data')
    values = array.array(code, payload)
    if sys.byteorder != 'little':
        values.byteswap()
    if any(not math.isfinite(value) for value in values):
        raise ValueError('NPY values must be finite')
    return header['shape'], header['descr'], values, hashlib.sha256(data).hexdigest()


def validate_arrays(feature_path, f0_path, nsf_path):
    feature_shape, feature_type, features, feature_hash = _npy(feature_path)
    pitch_shape, pitch_type, pitch, pitch_hash = _npy(f0_path)
    nsf_shape, nsf_type, nsf, nsf_hash = _npy(nsf_path)
    if len(feature_shape) != 2 or feature_shape[1] != 768 or feature_type not in ('<f4', '<f8'):
        raise ValueError('Expected nonempty 768-dimensional floating features')
    if (len(pitch_shape) != 1 or pitch_shape != nsf_shape or
            pitch_type not in ('<i4', '<i8') or nsf_type not in ('<f4', '<f8') or
            any(value < 1 or value > 255 for value in pitch) or any(value < 0 for value in nsf)):
        raise ValueError('Invalid corresponding pitch arrays')
    return dict(featureSHA256=feature_hash, f0SHA256=pitch_hash, f0nsfSHA256=nsf_hash,
                featureRows=feature_shape[0], pitchRows=pitch_shape[0])


PINNED_SOURCE_SHA256 = 'f8405e93dc1ed2f08d895cf09daf14df210ffc50520d3a84358af6edc8e68c97'
TRANSFORM = 'rvc-81eed5e-tail-write-before-index-increment-v1'


def build_preprocess(raw_source):
    """Move exactly one pinned AST statement, without editing the checkout."""
    normalized = raw_source.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n')
    digest = hashlib.sha256(normalized.encode('utf-8')).hexdigest()
    if digest != PINNED_SOURCE_SHA256:
        raise ValueError('Pinned preprocess source hash mismatch; no transform applied')
    tree = ast.parse(normalized)
    try:
        klass = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'PreProcess')
        method = next(node for node in klass.body if isinstance(node, ast.FunctionDef) and node.name == 'pipeline')
        body = method.body[0].body
        loops = [(index, node) for index, node in enumerate(body) if isinstance(node, ast.For)]
        if len(loops) != 1:
            raise ValueError('Unexpected slice loop count')
        index, loop = loops[0]
        if ast.unparse(loop.target) != 'audio' or ast.unparse(loop.iter) != 'self.slicer.slice(audio)':
            raise ValueError('Unexpected slice loop')
        write = body[index + 1]
        if ast.unparse(write) != 'self.norm_write(tmp_audio, output_key, idx1)':
            raise ValueError('Unexpected tail write')
        chunk_loop = loop.body[1]
        branch = chunk_loop.body[2]
        if (not isinstance(chunk_loop, ast.While) or not isinstance(branch, ast.If) or
                [ast.unparse(node) for node in branch.orelse] != ['tmp_audio = audio[start:]', 'idx1 += 1', 'break']):
            raise ValueError('Unexpected tail branch')
        # The only AST edit: relocate the existing write before the existing
        # increment. Increment-after-write preserves unique sequential names.
        branch.orelse.insert(1, write)
        del body[index + 1]
    except (StopIteration, IndexError, AttributeError) as error:
        raise ValueError('Pinned preprocessing AST structure mismatch') from error
    ast.fix_missing_locations(tree)
    return tree, dict(transform=TRANSFORM, rawSourceSHA256=hashlib.sha256(raw_source).hexdigest(),
                      normalizedSourceSHA256=digest,
                      transformedASTSHA256=hashlib.sha256(ast.dump(tree).encode()).hexdigest())


def main(argv=None):
    import argparse
    import json
    parser = argparse.ArgumentParser(description='Guarded pinned RVC tail-write repair; leaves upstream unchanged')
    for name in ('root', 'dataset', 'experiment'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args(argv)
    root = pathlib.Path(args.root).resolve()
    source_path = root / 'train/preprocess.py'
    tree, provenance = build_preprocess(_read(source_path, 65536))
    experiment = pathlib.Path(args.experiment).resolve()
    provenance.update(adapterSHA256=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
                      sourceFile=str(source_path), sourceModified=False)
    target = experiment / 'voicematrix-preprocess-adapter.json'
    target.write_text(json.dumps(provenance, indent=2) + '\n', encoding='utf-8')
    # Root comes before the launcher directory; never put root/train first.
    sys.path.insert(0, str(root))
    sys.argv = [str(source_path), str(pathlib.Path(args.dataset).resolve()), '40000', '2',
                str(experiment), 'True', '3.7']
    namespace = dict(__name__='__main__', __package__='train', __file__=str(source_path))
    exec(compile(tree, str(source_path), 'exec'), namespace)


if __name__ == '__main__':
    main()
