"""Bounded original-source datasets for a separate RVC queue, never model training.

prepare returns an immutable manifest path; load_manifest verifies that durable
snapshot without downloading again. File paths are relative to manifest.parent.
Each request hash names a new private revision directory; a new requestID asks
for a new snapshot while leaving earlier snapshots unchanged.
The caller supplies an authorized validated request and a bounded local analyzer.
Anonymous grouping is neither character identification nor speech separation.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
import pathlib
import re
import shutil
import stat
import tempfile
import wave

from tools.master_voices import _publish_lock, _sync_directory
from tools.process_control import checked_process
from tools.rvc_training import audit_dataset
from tools.video_queue import video_id
from tools.video_reference import acquire, ffmpeg_path

RATE = 40000
ANALYSIS_RATE = 16000
MAX_VIDEO_SECONDS = 1800
MAX_DOWNLOAD_BYTES = 268435456
MAX_GROUP_SECONDS = 300
MAX_TOTAL_SECONDS = 900
MAX_FILE_SECONDS = 15
MAX_FILES = 512
MAX_OUTPUT_BYTES = 80 * 1024 * 1024
MAX_MANIFEST_BYTES = 512 * 1024
MAX_ANALYSIS_BYTES = 128 * 1024
MAX_GROUPS = 32
MAX_INTERVALS = 512
MAX_OMITTED = 128
MINIMUM_SECONDS = 60
HELD_OUT_SECONDS = 3


def _json(value):
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                          separators=(',', ':')).encode('utf8')
    except (TypeError, ValueError, OverflowError, RecursionError) as error:
        raise ValueError('Expected finite JSON data') from error


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _cancel(cancelled):
    if cancelled():
        raise InterruptedError('RVC dataset preparation cancelled')


def _real(path):
    path = pathlib.Path(path).absolute()
    if any(p.is_symlink() or getattr(p, 'is_junction', lambda: False)()
           for p in (path, *path.parents)):
        raise ValueError('Linked dataset paths are unsupported')
    return path


def _read(path, maximum):
    path = _real(path)
    if not stat.S_ISREG(path.stat().st_mode) or not 0 < path.stat().st_size <= maximum:
        raise ValueError('Invalid or oversized dataset file')
    with path.open('rb') as stream:
        data = stream.read(maximum + 1)
    if not 0 < len(data) <= maximum:
        raise ValueError('Dataset file exceeds byte limit')
    return data


def _request(request):
    if not isinstance(request, dict):
        raise ValueError('Expected validated RVC request')
    raw = _json(request)
    if len(raw) > 16384:
        raise ValueError('RVC request exceeds 16 KiB')
    identifier = request.get('requestID')
    if not isinstance(identifier, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', identifier):
        raise ValueError('Invalid request ID')
    url = request.get('videoURL')
    if not isinstance(url, str) or len(url) > 2048:
        raise ValueError('Invalid video URL')
    source_use = request.get('sourceUse')
    if (not isinstance(source_use, dict) or not isinstance(source_use.get('record'), str)
            or not source_use['record'].strip() or len(source_use['record']) > 3000):
        raise ValueError('Authorized source-use record is required')
    return video_id(url), _hash(raw)


def _number(value, maximum):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not 0 <= value <= maximum):
        raise ValueError('Invalid dataset interval')
    return value


def _pcm(raw, rate, maximum_seconds):
    try:
        with wave.open(io.BytesIO(raw)) as stream:
            frames = stream.getnframes()
            if ((stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getcomptype())
                    != (1, 2, rate, 'NONE') or not 0 < frames <= rate * maximum_seconds):
                raise ValueError('Expected bounded mono PCM16 WAV')
            pcm = stream.readframes(frames)
            if len(pcm) != frames * 2:
                raise ValueError('Truncated dataset WAV')
    except (wave.Error, EOFError) as error:
        raise ValueError('Invalid dataset WAV') from error
    return pcm


def _wave_info(path, rate):
    path = _real(path)
    if not stat.S_ISREG(path.stat().st_mode) or path.stat().st_size > rate * MAX_VIDEO_SECONDS * 2 + 65536:
        raise ValueError('Decoded source exceeds limits')
    try:
        with wave.open(str(path)) as stream:
            if ((stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getcomptype())
                    != (1, 2, rate, 'NONE') or not 0 < stream.getnframes() <= rate * MAX_VIDEO_SECONDS):
                raise ValueError('Decoded source format or duration exceeds limits')
            frames = stream.getnframes()
            stream.setpos(frames - 1)
            if len(stream.readframes(1)) != 2:
                raise ValueError('Truncated decoded source')
            return frames
    except (wave.Error, EOFError) as error:
        raise ValueError('Invalid decoded source') from error


def _intervals(report, frames):
    if not isinstance(report, dict) or len(_json(report)) > MAX_ANALYSIS_BYTES:
        raise ValueError('Analyzer result exceeds 128 KiB')
    if (report.get('labelsVerified') is not False or report.get('speakerSeparated') is not False
            or report.get('overlapDetection') != 'not-supported'):
        raise ValueError('Analyzer must report tentative unseparated groups')
    candidates, members = report.get('candidates'), report.get('memberIntervals')
    if not isinstance(candidates, list) or len(candidates) > MAX_GROUPS:
        raise ValueError('Analyzer group limit exceeded')
    if not isinstance(members, list) or len(members) > MAX_INTERVALS:
        raise ValueError('Analyzer member intervals missing or exceed limit')
    if (not isinstance(report.get('omitted', []), list)
            or len(report.get('omitted', [])) > MAX_OMITTED
            or any(not isinstance(row, dict) for row in report.get('omitted', []))):
        raise ValueError('Invalid analyzer omissions')
    groups = {}
    for row in candidates:
        group = row.get('group') if isinstance(row, dict) else None
        if isinstance(group, bool) or not isinstance(group, int) or not 1 <= group <= MAX_GROUPS or group in groups:
            raise ValueError('Invalid anonymous group')
        groups[group] = []
    for row in members:
        if (not isinstance(row, dict) or isinstance(row.get('group'), bool)
                or not isinstance(row.get('group'), int) or row['group'] not in groups):
            raise ValueError('Unknown member group')
        # Convert inward to original decoded PCM frames. Never extend an interval
        # to collect additional audio or to meet the admission floor.
        start = math.ceil(_number(row.get('start'), frames / RATE) * RATE)
        end = math.floor(_number(row.get('end'), frames / RATE) * RATE)
        if not 0 <= start < end <= frames:
            raise ValueError('Invalid member interval')
        groups[row['group']].append((start, end))
    return groups


def _exclusive(groups, omit):
    # Sweep line counts each group once even if its own analysis windows overlap.
    events = {}
    for group, intervals in groups.items():
        for start, end in intervals:
            events.setdefault(start, []).append((group, 1))
            events.setdefault(end, []).append((group, -1))
    output = {group: [] for group in groups}
    counts = {}
    previous = None
    for position, changes in sorted(events.items()):
        owners = [group for group, count in counts.items() if count > 0]
        if previous is not None and previous < position:
            if len(owners) == 1:
                intervals = output[owners[0]]
                if intervals and intervals[-1][1] == previous:
                    intervals[-1] = (intervals[-1][0], position)
                else:
                    intervals.append((previous, position))
            elif len(owners) > 1:
                omit('ambiguous-group-overlap', start=previous / RATE, end=position / RATE)
        for group, change in changes:
            counts[group] = counts.get(group, 0) + change
        previous = position
    return output


def _limited(intervals, budget, reason, group, omit):
    selected = []
    for start, end in intervals:
        stop = min(end, start + max(0, budget))
        if stop > start:
            selected.append((start, stop))
            budget -= stop - start
        if stop < end:
            omit(reason, group=group, start=stop / RATE, end=end / RATE)
    return selected


def _write(path, data):
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    if os.name != 'nt':
        path.chmod(0o600)


def _audit_rows(directory, rows, omit, group, cancelled):
    _cancel(cancelled)
    audit = audit_dataset(directory)
    admitted = {row['file']: row for row in audit['files']}
    for row in list(rows):
        name = pathlib.PurePosixPath(row['file']).name
        if name not in admitted:
            (directory / name).unlink()
            rows.remove(row)
            omit('audio-audit-rejected', group=group, start=row['start'], end=row['end'])
        else:
            if admitted[name]['sha256'] != row['sha256']:
                raise ValueError('Dataset changed during audit')
            row['activeSeconds'] = admitted[name]['activeSeconds']
    # Persist only admitted exact files; rejection reasons remain in omissions.
    if audit['duplicates'] or audit['rejected']:
        audit = audit_dataset(directory)
    _cancel(cancelled)
    return audit


def _create_groups(stage, decoded, intervals, source, omit, cancelled):
    seen_pcm = set()
    total_frames = 0
    output_bytes = 0
    file_count = 0
    groups = []
    with wave.open(str(decoded)) as original:
        for group, spans in sorted(intervals.items()):
            _cancel(cancelled)
            spans = _limited(spans, MAX_GROUP_SECONDS * RATE, 'group-duration-limit', group, omit)
            spans = _limited(spans, MAX_TOTAL_SECONDS * RATE - total_frames, 'total-duration-limit', group, omit)
            total_frames += sum(end - start for start, end in spans)
            identifier = 'rvc-' + source['videoID'].lower() + '-' + source['sourceSHA256'][:12] + '-group-' + str(group).zfill(2)
            training = 'groups/' + identifier + '/training'
            held_out = 'groups/' + identifier + '/held-out'
            (stage / training).mkdir(parents=True, mode=0o700)
            (stage / held_out).mkdir(mode=0o700)
            row = dict(id=identifier, group=group, status='insufficient-data',
                       trainingDirectory=training, heldOutDirectory=held_out,
                       trainingFiles=[], heldOutFiles=[], minimumSeconds=MINIMUM_SECONDS)
            file_frames = {}
            reserve = []
            # Last sufficiently long disjoint span is a held-out source segment.
            if spans:
                index = next((i for i in range(len(spans) - 1, -1, -1)
                              if spans[i][1] - spans[i][0] >= HELD_OUT_SECONDS * RATE), len(spans) - 1)
                start, end = spans[index]
                boundary = max(start, end - HELD_OUT_SECONDS * RATE)
                reserve = [(boundary, end)]
                spans[index:index + 1] = [(start, boundary)] if boundary > start else []
            else:
                omit('no-unambiguous-intervals', group=group)
            # Reserve held-out contents first as well as timestamps. A repeated
            # source recording may never put an identical PCM clip into training.
            for key, directory, selected in [('heldOutFiles', held_out, reserve),
                                              ('trainingFiles', training, spans)]:
                for start, end in selected:
                    while start < end:
                        _cancel(cancelled)
                        stop = min(end, start + MAX_FILE_SECONDS * RATE)
                        if stop - start < RATE // 2:
                            omit('fragment-too-short', group=group, start=start / RATE, end=stop / RATE)
                            break
                        if file_count >= MAX_FILES or output_bytes + (stop - start) * 2 + 44 > MAX_OUTPUT_BYTES:
                            omit('output-file-or-byte-limit', group=group, start=start / RATE, end=end / RATE)
                            break
                        original.setpos(start)
                        pcm = original.readframes(stop - start)
                        if len(pcm) != (stop - start) * 2:
                            raise ValueError('Source audio changed during extraction')
                        digest = _hash(pcm + str(RATE).encode())
                        if digest in seen_pcm:
                            omit('duplicate-pcm-content', group=group, start=start / RATE, end=stop / RATE)
                            start = stop
                            continue
                        seen_pcm.add(digest)
                        memory = io.BytesIO()
                        with wave.open(memory, 'wb') as stream:
                            stream.setparams((1, 2, RATE, 0, 'NONE', 'none'))
                            stream.writeframes(pcm)
                        data = memory.getvalue()
                        relative = directory + '/clip-' + str(len(row[key])).zfill(4) + '.wav'
                        _write(stage / relative, data)
                        file_frames[relative] = stop - start
                        row[key].append(dict(file=relative, sha256=_hash(data), pcmSHA256=digest,
                                             start=start / RATE, end=stop / RATE, bytes=len(data)))
                        output_bytes += len(data)
                        file_count += 1
                        start = stop
            row['audit'] = _audit_rows(stage / training, row['trainingFiles'], omit, group, cancelled)
            row['heldOutAudit'] = _audit_rows(stage / held_out, row['heldOutFiles'], omit, group, cancelled)
            row['uniqueSeconds'] = row['audit']['uniqueSeconds']
            # Timing is serialized in seconds, but subtraction at fractional
            # VAD boundaries can round an exact three seconds just below three.
            # Admit using the actual extracted integer PCM frame count instead.
            held_out_ready = any(file_frames[r['file']] >= HELD_OUT_SECONDS * RATE
                                 for r in row['heldOutFiles'])
            if not held_out_ready:
                omit('insufficient-held-out-data', group=group)
            if row['audit']['status'] == 'ready-for-training' and held_out_ready:
                row['status'] = 'ready-for-training'
            else:
                omit('insufficient-data', group=group, activeTrainingSeconds=row['uniqueSeconds'])
            groups.append(row)
    return groups


def load_manifest(path, *, request=None, cancelled=lambda: False):
    """Read and re-audit a durable snapshot; corruption never triggers a download."""
    _cancel(cancelled)
    path = _real(path)
    try:
        manifest = json.loads(_read(path, MAX_MANIFEST_BYTES))
    except (json.JSONDecodeError, UnicodeError) as error:
        raise ValueError('Invalid dataset manifest') from error
    if not isinstance(manifest, dict):
        raise ValueError('Invalid dataset manifest')
    unsigned = {key: value for key, value in manifest.items() if key != 'revision'}
    if manifest.get('revision') != _hash(_json(unsigned)):
        raise ValueError('Dataset revision checksum mismatch')
    if (manifest.get('schemaVersion') != 1 or manifest.get('kind') != 'rvc-source-dataset'
            or any(manifest.get(key) is not False for key in ('trained', 'labelsVerified', 'speakerSeparated', 'likenessVerified'))
            or manifest.get('overlapDetection') != 'not-supported'):
        raise ValueError('Invalid dataset schema or claims')
    source = manifest.get('source', {})
    if (not isinstance(source, dict) or not isinstance(source.get('sourceSHA256'), str)
            or not re.fullmatch(r'[a-f0-9]{64}', source['sourceSHA256'])
            or not isinstance(manifest.get('requestSHA256'), str)
            or not re.fullmatch(r'[a-f0-9]{64}', manifest['requestSHA256'])):
        raise ValueError('Invalid dataset provenance')
    _request(dict(requestID=manifest.get('requestID'), videoURL=source.get('videoURL'), sourceUse=source.get('sourceUse')))
    if video_id(source['videoURL']) != source.get('videoID'):
        raise ValueError('Dataset video provenance mismatch')
    if request is not None:
        identifier, digest = _request(request)
        if (digest != manifest['requestSHA256'] or request['requestID'] != manifest['requestID']
                or source['videoID'] != identifier or request['sourceUse'] != source['sourceUse']):
            raise ValueError('Dataset does not match the authorized request')
    groups = manifest.get('groups')
    if not isinstance(groups, list) or len(groups) > MAX_GROUPS:
        raise ValueError('Invalid dataset group count')
    if {entry.name for entry in path.parent.iterdir()} != ({'manifest.json', 'groups'} if groups else {'manifest.json'}):
        raise ValueError('Unlisted dataset snapshot files')
    pcm_hashes, numbers, paths, intervals = set(), set(), set(), []
    group_ids = set()
    total_bytes = 0
    for group in groups:
        _cancel(cancelled)
        if not isinstance(group, dict):
            raise ValueError('Invalid dataset group')
        number = group.get('group')
        if isinstance(number, bool) or not isinstance(number, int) or not 1 <= number <= MAX_GROUPS or number in numbers:
            raise ValueError('Invalid dataset group number')
        numbers.add(number)
        expected_id = 'rvc-' + source['videoID'].lower() + '-' + source['sourceSHA256'][:12] + '-group-' + str(number).zfill(2)
        if group.get('id') != expected_id or group.get('minimumSeconds') != MINIMUM_SECONDS:
            raise ValueError('Invalid anonymous dataset identity or floor')
        group_ids.add(expected_id)
        if {entry.name for entry in _real(path.parent / 'groups' / expected_id).iterdir()} != {'training', 'held-out'}:
            raise ValueError('Unlisted group files')
        group_seconds = 0
        held_out_ready = False
        for key, directory_key, suffix, audit_key in [
                ('trainingFiles', 'trainingDirectory', 'training', 'audit'),
                ('heldOutFiles', 'heldOutDirectory', 'held-out', 'heldOutAudit')]:
            expected_dir = 'groups/' + expected_id + '/' + suffix
            if group.get(directory_key) != expected_dir:
                raise ValueError('Unsafe dataset directory')
            directory = _real(path.parent / expected_dir)
            rows = group.get(key)
            if not directory.is_dir() or not isinstance(rows, list) or len(rows) > MAX_FILES:
                raise ValueError('Invalid dataset audio list')
            files = set()
            for row in rows:
                _cancel(cancelled)
                if not isinstance(row, dict):
                    raise ValueError('Invalid dataset audio record')
                relative = row.get('file')
                if not isinstance(relative, str) or not re.fullmatch(re.escape(expected_dir) + r'/clip-[0-9]{4}\.wav', relative) or relative in paths:
                    raise ValueError('Unsafe or repeated dataset path')
                if len(paths) >= MAX_FILES:
                    raise ValueError('Dataset file limit exceeded')
                paths.add(relative)
                files.add(pathlib.PurePosixPath(relative).name)
                raw = _read(path.parent / relative, RATE * MAX_FILE_SECONDS * 2 + 65536)
                pcm = _pcm(raw, RATE, MAX_FILE_SECONDS)
                if key == 'heldOutFiles' and len(pcm) // 2 >= HELD_OUT_SECONDS * RATE:
                    held_out_ready = True
                digest = _hash(pcm + str(RATE).encode())
                if _hash(raw) != row.get('sha256') or digest != row.get('pcmSHA256') or len(raw) != row.get('bytes'):
                    raise ValueError('Dataset audio checksum mismatch')
                if digest in pcm_hashes:
                    raise ValueError('Repeated dataset PCM content')
                pcm_hashes.add(digest)
                start = _number(row.get('start'), MAX_VIDEO_SECONDS)
                end = _number(row.get('end'), MAX_VIDEO_SECONDS)
                if not start < end or abs((end - start) * RATE - len(pcm) // 2) > .001:
                    raise ValueError('Dataset timestamp/audio duration mismatch')
                intervals.append((start, end))
                group_seconds += end - start
                total_bytes += len(raw)
                if total_bytes > MAX_OUTPUT_BYTES:
                    raise ValueError('Dataset byte limit exceeded')
            if {file.name for file in directory.iterdir()} != files:
                raise ValueError('Unlisted dataset files')
            audit = audit_dataset(directory)
            if audit != group.get(audit_key) or audit['rejected'] or audit['duplicates']:
                raise ValueError('Dataset audit changed')
            admitted = {row['file']: row for row in audit['files']}
            if any(row.get('activeSeconds') != admitted[pathlib.PurePosixPath(row['file']).name]['activeSeconds'] for row in rows):
                raise ValueError('Dataset activity audit mismatch')
        if group_seconds > MAX_GROUP_SECONDS + .0001:
            raise ValueError('Dataset group duration exceeds limit')
        ready = group['audit']['status'] == 'ready-for-training' and held_out_ready
        if group.get('uniqueSeconds') != group['audit']['uniqueSeconds'] or group.get('status') != ('ready-for-training' if ready else 'insufficient-data'):
            raise ValueError('Dataset admission status mismatch')
    ordered = sorted(intervals)
    if groups and {entry.name for entry in _real(path.parent / 'groups').iterdir()} != group_ids:
        raise ValueError('Unlisted dataset groups')
    if any(left[1] > right[0] for left, right in zip(ordered, ordered[1:])):
        raise ValueError('Dataset source intervals overlap')
    if len(paths) > MAX_FILES or total_bytes > MAX_OUTPUT_BYTES or sum(end - start for start, end in ordered) > MAX_TOTAL_SECONDS + .0001:
        raise ValueError('Dataset total limits exceeded')
    _cancel(cancelled)
    return manifest


def prepare(request, output_root, *, analyze, acquire_source=acquire,
            cancelled=lambda: False, activity=lambda *args: None, commit=None):
    """Collect and audit original audio once. commit(operation) fences publication.

    analyze(path_16k_mono_pcm16, *, cancelled) must return the bounded anonymous
    speaker_candidates report with memberIntervals. No models are loaded here.
    Existing snapshots, including insufficient-data results, are never replaced.
    """
    identifier, request_hash = _request(request)
    request = json.loads(_json(request))  # Freeze mutable caller input.
    _cancel(cancelled)
    root = _real(output_root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = _real(root / identifier)
    destination.mkdir(exist_ok=True, mode=0o700)
    target = _real(destination / request_hash)
    with _publish_lock(destination / ('.' + request_hash + '.lock')):
        if target.exists():
            load_manifest(target / 'manifest.json', request=request, cancelled=cancelled)
            activity('rvc_dataset_reused')
            return target / 'manifest.json'
        stage = pathlib.Path(tempfile.mkdtemp(prefix='.preparing-', dir=destination))
        omissions = []
        omitted_count = 0
        def omit(reason, **details):
            nonlocal omitted_count
            omitted_count += 1
            if len(omissions) < MAX_OMITTED:
                omissions.append(dict(reason=reason, **details))
        try:
            url = 'https://www.youtube.com/watch?v=' + identifier
            activity('rvc_dataset_preparing')
            with acquire_source(url, [dict(id='rvc-probe', start=0, end=.5)],
                                cancelled=cancelled, activity=activity, max_duration=MAX_VIDEO_SECONDS,
                                max_bytes=MAX_DOWNLOAD_BYTES, max_download_seconds=300) as acquired:
                _cancel(cancelled)
                if acquired.get('videoID') != identifier:
                    raise ValueError('Acquired source does not match requested video')
                movie = _real(acquired['privateMoviePath'])
                if not stat.S_ISREG(movie.stat().st_mode) or not 0 < movie.stat().st_size <= MAX_DOWNLOAD_BYTES:
                    raise ValueError('Source exceeds download byte limit')
                with movie.open('rb') as stream:
                    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                if digest != acquired.get('sourceSHA256'):
                    raise ValueError('Acquired source checksum mismatch')
                source = dict(videoURL=url, videoID=identifier, sourceSHA256=digest, sourceUse=request['sourceUse'])
                with tempfile.TemporaryDirectory(prefix='.decoding-', dir=destination) as scratch:
                    decoded = pathlib.Path(scratch) / 'original-40k.wav'
                    analysis_audio = pathlib.Path(scratch) / 'analysis-16k.wav'
                    ffmpeg = ffmpeg_path()
                    for output, rate in [(decoded, RATE), (analysis_audio, ANALYSIS_RATE)]:
                        _cancel(cancelled)
                        checked_process([ffmpeg, '-v', 'error', '-threads', '1', '-i', str(movie),
                                         '-t', str(MAX_VIDEO_SECONDS + .02), '-fs', str(rate * MAX_VIDEO_SECONDS * 2 + 65536),
                                         '-map', '0:a:0', '-vn', '-ac', '1', '-ar', str(rate), '-c:a', 'pcm_s16le', str(output)],
                                        timeout=120, cancelled=cancelled)
                        _wave_info(output, rate)
                    frames = _wave_info(decoded, RATE)
                    activity('rvc_dataset_analyzing')
                    report = analyze(analysis_audio, cancelled=cancelled)
                    grouped = _intervals(report, frames)
                    # Omitted group members are unavailable, so their potential
                    # timestamp conflicts cannot be safely subtracted. Fail
                    # closed rather than train from falsely exclusive audio.
                    if (report.get('groupLimitExceeded')
                            or any(row.get('reason') == 'group-limit' for row in report.get('omitted', []))
                            or ('groupLimitExceeded' not in report and report.get('truncated') and len(grouped) == MAX_GROUPS)):
                        grouped = {group: [] for group in grouped}
                        omit('analysis-group-limit')
                    spans = _exclusive(grouped, omit)
                    activity('rvc_dataset_extracting', 0, len(grouped))
                    groups = _create_groups(stage, decoded, spans, source, omit, cancelled)
            # The acquisition context has deleted its MP4 before publication.
            manifest = dict(schemaVersion=1, kind='rvc-source-dataset', requestID=request['requestID'],
                            requestSHA256=request_hash, source=source, groups=groups,
                            trained=False, labelsVerified=False, speakerSeparated=False,
                            overlapDetection='not-supported', likenessVerified=False,
                            analysis=dict(sha256=_hash(_json(report)), engine=report.get('engine'),
                                          truncated=bool(report.get('truncated')), omitted=report.get('omitted', [])[:MAX_OMITTED],
                                          omittedCount=report.get('omittedCount', 0)),
                            limits=dict(maxVideoSeconds=MAX_VIDEO_SECONDS, maxDownloadBytes=MAX_DOWNLOAD_BYTES,
                                        maxGroups=MAX_GROUPS, maxIntervals=MAX_INTERVALS, maxGroupSeconds=MAX_GROUP_SECONDS,
                                        maxTotalSeconds=MAX_TOTAL_SECONDS, maxFileSeconds=MAX_FILE_SECONDS,
                                        maxFiles=MAX_FILES, maxOutputBytes=MAX_OUTPUT_BYTES, minimumTrainingSeconds=60,
                                        heldOutSeconds=HELD_OUT_SECONDS),
                            omitted=omissions, omittedCount=omitted_count,
                            warnings=['Tentative source-specific groups may merge or miss speakers.',
                                      'Timestamp conflicts are excluded; simultaneous speakers and music are not separated.',
                                      'Sixty active training seconds is an admission floor, not a likeness or quality guarantee.'])
            manifest['revision'] = _hash(_json(manifest))
            data = _json(manifest)
            if len(data) > MAX_MANIFEST_BYTES:
                raise ValueError('Dataset manifest exceeds 512 KiB')
            # Manifest is private in the staging directory until the single
            # directory rename publishes a complete, audited snapshot.
            _write(stage / 'manifest.json', data)
            load_manifest(stage / 'manifest.json', request=request, cancelled=cancelled)
            for directory, _, _ in os.walk(stage, topdown=False):
                if os.name != 'nt':
                    pathlib.Path(directory).chmod(0o700)
                _sync_directory(pathlib.Path(directory))
            def publish():
                _cancel(cancelled)
                if os.path.lexists(target):
                    raise FileExistsError('Existing dataset revision is preserved')
                os.rename(stage, target)
                _sync_directory(destination)
            if commit is None:
                publish()
            else:
                commit(publish)
            if stage.exists() or not (target / 'manifest.json').is_file():
                raise RuntimeError('Dataset publication was not committed')
            activity('rvc_dataset_ready')
            return target / 'manifest.json'
        finally:
            if stage.exists():
                shutil.rmtree(stage)
