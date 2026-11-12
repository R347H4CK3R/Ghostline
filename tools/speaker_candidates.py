"""Offline anonymous voice candidates, not character identification or separation.

Run in a separate CPU process. No assets, Python, or YAML are fetched at inference.
The only supported neural backend is the hash-pinned ECAPA + Silero ONNX bundle.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import stat
import tempfile
import wave

RATE = 16000
MAX_SECONDS = 1800
MAX_GROUPS = 32
MAX_WINDOWS = 512
MAX_REGIONS = 3600
MAX_OMITTED = 128
MAX_RESULT_BYTES = 128 * 1024
MODEL_SHA256 = '0575cb64845e6b9a10db9bcb74d5ac32b326b8dc90352671d345e2ee3d0126a2'
MODEL_REVISION = '0f99f2d0ebe89ac095bcc5903c4dd8f72b367286'
# silero-vad 6.2.3 official PyPI wheel, data/silero_vad.onnx (MIT).
VAD_SHA256 = '1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3'


def _cancel(cancelled):
    if cancelled():
        raise InterruptedError('Speaker analysis cancelled')


def _verified_bytes(path, expected, maximum):
    path = pathlib.Path(path)
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode) or not 0 < st.st_size <= maximum:
        raise ValueError('Invalid local model file')
    with path.open('rb') as stream:
        data = stream.read(maximum + 1)
    if len(data) != st.st_size or hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('Local model checksum mismatch')
    return data


def load_local_encoder(checkpoint, vad_checkpoint=None):
    """Load only fixed verified weights. Never evaluate model-supplied YAML/code."""
    import io
    checkpoint = pathlib.Path(checkpoint)
    weights = _verified_bytes(checkpoint, MODEL_SHA256, 90_000_000)
    vad_checkpoint = pathlib.Path(vad_checkpoint or checkpoint.with_name('silero_vad.onnx'))
    vad_bytes = _verified_bytes(vad_checkpoint, VAD_SHA256, 10_000_000)
    import torch
    from speechbrain.lobes.features import Fbank
    from speechbrain.processing.features import InputNormalization
    from speechbrain.lobes.models.ECAPA_TDNN import ECAPA_TDNN
    from silero_vad.utils_vad import OnnxWrapper
    torch.set_num_threads(2)
    # This module is intended for a fresh dedicated process, not the F5 process.
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:
        pass  # A caller may have already initialized the same process's pool.
    state = torch.load(io.BytesIO(weights), map_location='cpu', weights_only=True)
    if not isinstance(state, dict) or not state or any(
            not isinstance(k, str) or not torch.is_tensor(v) for k, v in state.items()):
        raise ValueError('Embedding checkpoint must contain only a tensor state dict')
    encoder = ECAPA_TDNN(
        input_size=80, channels=[1024, 1024, 1024, 1024, 3072],
        kernel_sizes=[5, 3, 3, 3, 1], dilations=[1, 2, 3, 4, 1],
        attention_channels=128, lin_neurons=192)
    encoder.load_state_dict(state, strict=True)
    encoder.eval()
    return LocalEncoder(
        encoder, Fbank(n_mels=80),
        InputNormalization(norm_type='sentence', std_norm=False),
        _load_verified_vad(vad_bytes, OnnxWrapper))


def _load_verified_vad(data, factory):
    # The upstream wrapper requires a filename. Load a private snapshot rather
    # than reopening the caller's mutable path after its checksum was verified.
    with tempfile.TemporaryDirectory(prefix='voicematrix-vad-') as directory:
        path = pathlib.Path(directory) / 'silero_vad.onnx'
        path.write_bytes(data)
        return factory(str(path), force_onnx_cpu=True)


class LocalEncoder:
    def __init__(self, encoder, features, normalization, vad):
        self.encoder = encoder
        self.features = features
        self.normalization = normalization
        self.vad = vad

    def speech_regions(self, audio, cancelled):
        import torch
        from silero_vad.utils_vad import get_speech_timestamps
        _cancel(cancelled)
        with torch.inference_mode():
            regions = get_speech_timestamps(
                torch.from_numpy(audio), self.vad, sampling_rate=RATE,
                min_speech_duration_ms=400, min_silence_duration_ms=250,
                max_speech_duration_s=30, speech_pad_ms=0,
                progress_tracking_callback=lambda _percent: _cancel(cancelled))
        return [(r['start'], r['end']) for r in regions]

    def embed(self, audio):
        import torch
        with torch.inference_mode():
            signal = torch.from_numpy(audio.copy()).unsqueeze(0)
            lengths = torch.ones(1)
            features = self.normalization(self.features(signal), lengths)
            embedding = self.encoder(features, lengths).reshape(-1)
            return embedding.cpu().numpy()


def _read_audio(path):
    import numpy as np
    path = pathlib.Path(path)
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_size > RATE * MAX_SECONDS * 2 + 65536:
        raise ValueError('Audio must be a regular bounded PCM WAV file')
    try:
        with wave.open(str(path), 'rb') as wav:
            frames = wav.getnframes()
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype()) != (1, 2, RATE, 'NONE'):
                raise ValueError('Use 16 kHz mono PCM16 WAV')
            if not 0 < frames <= MAX_SECONDS * RATE:
                raise ValueError('Audio must contain at most 30 minutes')
            pcm = wav.readframes(frames)
            if len(pcm) != frames * 2:
                raise ValueError('Truncated audio')
    except (wave.Error, EOFError) as error:
        raise ValueError('Invalid PCM WAV') from error
    return np.frombuffer(pcm, dtype='<i2').astype(np.float32) / 32768.0


def _unit(vector):
    import numpy as np
    vector = np.asarray(vector, dtype=np.float32)
    if vector.ndim != 1 or not 1 < len(vector) <= 4096 or not np.isfinite(vector).all():
        raise ValueError('Invalid speaker embedding')
    norm = float(np.linalg.norm(vector))
    if norm < 1e-8:
        raise ValueError('Empty speaker embedding')
    return vector / norm


def analyze(path_16k_mono_pcm16, model, cancelled=lambda: False):
    """Return up to 32 tentative representatives (3–12 s), with no identity claim.

    `model` implements speech_regions(float32_audio, cancelled) and embed(window).
    Scores are heuristic embedding stability, not confidence probabilities.
    This method never modifies the source, existing voices, or model files.
    """
    import numpy as np
    from sklearn.cluster import AgglomerativeClustering
    _cancel(cancelled)
    audio = _read_audio(path_16k_mono_pcm16)
    _cancel(cancelled)
    report = {
        'schemaVersion': 1, 'engine': 'speechbrain-ecapa-silero',
        'status': 'no-candidates', 'durationSeconds': round(len(audio) / RATE, 6),
        'candidates': [], 'memberIntervals': [],
        'labelsVerified': False, 'speakerSeparated': False,
        'overlapDetection': 'not-supported', 'truncated': False, 'groupLimitExceeded': False,
        'limits': {'maxSeconds': MAX_SECONDS, 'maxGroups': MAX_GROUPS,
                   'maxWindows': MAX_WINDOWS, 'maxRegions': MAX_REGIONS,
                   'minimumCandidateSeconds': 3, 'maximumCandidateSeconds': 12},
        'omitted': [], 'omittedCount': 0,
        'warnings': ['Tentative voice groups only; some speakers may be missed or merged.',
                     'Overlapping speech and background music are not separated.'],
    }
    def omit(reason, start=None, end=None):
        report['omittedCount'] += 1
        if len(report['omitted']) < MAX_OMITTED:
            row = {'reason': reason}
            if start is not None:
                row.update(start=round(start / RATE, 6), end=round(end / RATE, 6))
            report['omitted'].append(row)
    regions = []
    previous_end = 0
    for region_index, region in enumerate(model.speech_regions(audio, cancelled)):
        _cancel(cancelled)
        if region_index >= MAX_REGIONS:
            report['truncated'] = True
            omit('region-limit')
            break
        if not isinstance(region, (tuple, list)) or len(region) != 2:
            raise ValueError('Invalid speech region')
        start, end = region
        if (isinstance(start, bool) or isinstance(end, bool) or
                not isinstance(start, (int, np.integer)) or not isinstance(end, (int, np.integer)) or
                not previous_end <= start < end <= len(audio)):
            raise ValueError('Invalid or overlapping speech regions')
        start, end = int(start), int(end)
        previous_end = end
        regions.append((start, end))
    windows = []
    examined = 0
    stop = False
    for start, end in regions:
        _cancel(cancelled)
        if end - start < 3 * RATE:
            omit('speech-too-short', start, end)
            continue
        # Eight-second windows with a six-second stride. Endpoints stay inside VAD speech.
        position = start
        while position + 3 * RATE <= end:
            _cancel(cancelled)
            if examined >= MAX_WINDOWS:
                report['truncated'] = True
                omit('window-limit')
                stop = True
                break
            finish = min(position + 8 * RATE, end)
            segment = audio[position:finish]
            examined += 1
            if float(np.mean(np.abs(segment) >= 32760 / 32768)) > .001:
                omit('clipped-window', position, finish)
            elif float(np.mean(segment * segment)) < 1e-6:
                omit('quiet-window', position, finish)
            else:
                full = _unit(model.embed(segment))
                _cancel(cancelled)
                middle = len(segment) // 2
                left = _unit(model.embed(segment[:middle]))
                _cancel(cancelled)
                right = _unit(model.embed(segment[middle:]))
                _cancel(cancelled)
                if full.shape != left.shape or full.shape != right.shape:
                    raise ValueError('Inconsistent speaker embedding dimensions')
                stability = min(float(full @ left), float(full @ right), float(left @ right))
                if stability < .65:
                    omit('unstable-voice-window', position, finish)
                else:
                    windows.append({'start': position, 'end': finish, 'vector': full,
                                    'score': round(min(1.0, stability), 6)})
            if finish == end:
                break
            position += 6 * RATE
        if stop:
            break
    report['analyzedWindows'] = examined
    if not windows:
        return report
    _cancel(cancelled)
    vectors = np.stack([r['vector'] for r in windows])
    if len(windows) == 1:
        labels = np.zeros(1, dtype=int)
    else:
        labels = AgglomerativeClustering(
            n_clusters=None, metric='cosine', linkage='complete',
            distance_threshold=.30).fit_predict(vectors)
    _cancel(cancelled)
    clusters = {}
    for window, label in zip(windows, labels):
        clusters.setdefault(int(label), []).append(window)
    # First occurrence gives deterministic anonymous numbering within this source only.
    ordered = sorted(clusters.values(), key=lambda members: members[0]['start'])
    for index, members in enumerate(ordered):
        _cancel(cancelled)
        if index >= MAX_GROUPS:
            report['groupLimitExceeded'] = True
            omit('group-limit', members[0]['start'], members[-1]['end'])
            report['truncated'] = True
            continue
        representative = max(members, key=lambda r: (r['score'], r['end'] - r['start'], -r['start']))
        report['candidates'].append({
            'start': round(representative['start'] / RATE, 6),
            'end': round(representative['end'] / RATE, 6), 'group': index + 1,
            'confidence': None, 'score': representative['score'],
            'uncertainty': ['label-unverified', 'overlap-not-assessed', 'grouping-not-calibrated'],
            'supportingWindows': len(members),
        })
        # These original VAD-window timestamps are tentative group membership,
        # not separated or identity-verified speech. Downstream dataset builders
        # must union within groups and remove cross-group timestamp conflicts.
        # MAX_WINDOWS bounds this list globally, not per group.
        report['memberIntervals'].extend({
            'group': index + 1, 'start': round(member['start'] / RATE, 6),
            'end': round(member['end'] / RATE, 6),
        } for member in members)
    report['status'] = 'candidates'
    return report


def write_result(output, result):
    data = json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
    if len(data) > MAX_RESULT_BYTES:
        raise ValueError('Analysis result exceeds 128 KiB')
    output = pathlib.Path(output)
    if output.is_symlink():
        raise ValueError('Result path must not be a symlink')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, prefix='.speaker-result-', delete=False) as stream:
            temporary = pathlib.Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        # Hard-link publication is atomic and fails if the destination exists,
        # including if another process creates it after our checks.
        os.link(temporary, output)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audio', required=True)
    parser.add_argument('--checkpoint', required=True)
    parser.add_argument('--vad-checkpoint')
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    try:
        if os.path.lexists(args.output):
            raise FileExistsError('Analysis output must be a new file')
        vad_path = args.vad_checkpoint or pathlib.Path(args.checkpoint).with_name('silero_vad.onnx')
        protected = [pathlib.Path(p).resolve() for p in (args.audio, args.checkpoint, vad_path)]
        if pathlib.Path(args.output).resolve() in protected:
            raise ValueError('Output must not overwrite an input or model')
        model = load_local_encoder(args.checkpoint, args.vad_checkpoint)
        result = analyze(args.audio, model)
        result['modelRevision'] = MODEL_REVISION
        result['modelSHA256'] = MODEL_SHA256
        result['vadSHA256'] = VAD_SHA256
        write_result(args.output, result)
        return 0
    except (OSError, ValueError, RuntimeError, ImportError) as error:
        import sys
        print('Speaker analysis failed: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
