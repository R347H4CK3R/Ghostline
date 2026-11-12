"""Isolated private RVC queue orchestration. No server or native-app integration.

Run only with an explicitly initialized private root and operator-configured
local engine, speaker analyzer, held-out original WAV/transcript, and independent
word verifier. Production defaults invoke the real dataset/training/conversion
adapters and publisher. Dependency injection is for offline source tests.

Experiments and failed checks are retained. A crash can recover a completed
hash-checked stage, but never silently restart an incomplete neural experiment.
"""
import hashlib
import io
import json
import math
import pathlib
import re
import sys
import threading
import time
import uuid
import wave

from tools import rvc_export, rvc_training, rvc_validation
from tools.rvc_request import DATABASE, FORMAT, ensure_root, load
from tools.video_queue import VideoQueue, video_id


class ReviewRequired(ValueError):
    pass


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _path(root, relative):
    """Private persisted pointers must still remain bounded and unlinked."""
    if (not isinstance(relative, str) or not 1 <= len(relative) <= 400 or
            '\\' in relative or ':' in relative or
            pathlib.PurePosixPath(relative).is_absolute() or
            any(part in ('', '.', '..') for part in relative.split('/'))):
        raise ReviewRequired('Unsafe private artifact path')
    path = root.joinpath(*relative.split('/'))
    if path.resolve() != path or root not in path.parents:
        raise ReviewRequired('Private artifact location changed')
    return path


def _data(path, maximum=1024*1024, expected=None):
    if pathlib.Path(path).absolute().resolve() != pathlib.Path(path).absolute():
        raise ReviewRequired('Linked artifacts are unsupported')
    return rvc_export.read_bound(path, maximum, expected)


def _read(path):
    value = json.loads(_data(path))
    if not isinstance(value, dict):
        raise ReviewRequired('Invalid private artifact report')
    return value


def _pcm(data):
    with wave.open(io.BytesIO(data)) as stream:
        return _hash(stream.readframes(stream.getnframes()) + str(stream.getframerate()).encode())


def _configuration(engine, validation_wav, text, provenance, epochs, python, stage_timeout):
    if (not isinstance(text, str) or not 1 <= len(text.strip()) <= 4000 or
            not re.search('[a-z0-9]', text.lower()) or
            not isinstance(provenance, str) or not 1 <= len(provenance.strip()) <= 3000 or
            any(ord(character) < 32 for character in provenance)):
        raise ReviewRequired('Configure original held-out speech and its transcript/provenance')
    if type(epochs) is not int or not 1 <= epochs <= 1200:
        raise ValueError('Epochs must be 1–1200')
    if type(stage_timeout) not in (int, float) or not math.isfinite(stage_timeout) or not 0 < stage_timeout <= 86400:
        raise ValueError('Invalid neural stage timeout')
    data = _data(validation_wav, rvc_export.MAX_AUDIO_BYTES)
    rvc_export.audio_metrics(data)
    evidence = dict(engine=str(engine), inputSHA256=_hash(data), pcmSHA256=_pcm(data),
                    textSHA256=_hash(text.encode()), provenanceSHA256=_hash(provenance.encode()),
                    epochs=epochs, python=str(python), stageTimeout=stage_timeout)
    return evidence, _hash(_json(evidence).encode())


def _training(engine, experiment, group, request, epochs):
    folder = _path(engine, 'logs/' + experiment)
    report_path = folder / 'voicematrix-training.json'
    report = _read(report_path)
    if (report.get('experiment') != experiment or report.get('epochs') != epochs or
            report.get('permission') != request['sourceUse']['record'] or
            report.get('status') != 'trained-needs-independent-conversion-check' or
            report.get('sourceRevision') != rvc_training.UPSTREAM or report.get('verified') is not False or
            report.get('completedStages') != ['preprocess', 'pitch', 'features', 'train', 'index'] or
            not isinstance(report.get('indices'), list) or len(report['indices']) != 1 or
            not isinstance(report.get('indexSHA256'), dict)):
        raise ReviewRequired('A retained neural experiment needs review')
    audit = report.get('dataset', {})
    if (not isinstance(audit, dict) or audit.get('status') != 'ready-for-training' or
            audit.get('minimumSeconds') != 60 or type(audit.get('uniqueSeconds')) not in (int, float) or
            not 60 <= audit['uniqueSeconds'] <= 300.1 or
            not isinstance(audit.get('files'), list) or not 1 <= len(audit['files']) <= 512):
        raise ReviewRequired('Training report is not bound to admitted original audio')
    expected = {pathlib.PurePosixPath(row['file']).name: row['sha256'] for row in group['trainingFiles']}
    if (len(audit['files']) != len(expected) or
            any(not isinstance(row, dict) or expected.get(row.get('file')) != row.get('sha256')
                for row in audit['files']) or len({row['file'] for row in audit['files']}) != len(expected)):
        raise ReviewRequired('Training dataset evidence changed')
    from tools.rvc_preprocess import audit_preprocessed
    effective = audit_preprocessed(folder, expected_sources=len(expected), validate_features=True)
    if (effective != report.get('effectiveDataset') or effective['status'] != 'ready-for-training' or
            type(effective.get('activeLowerBoundSeconds')) not in (int, float) or
            effective['activeLowerBoundSeconds'] < 60):
        raise ReviewRequired('Effective training data does not meet the sixty-second floor')
    model = _path(engine, 'assets/weights/' + experiment + '.pth')
    if report.get('model') != str(model):
        raise ReviewRequired('Unexpected training model path')
    index_value = report['indices'][0]
    if not isinstance(index_value, str) or len(index_value) > 1200:
        raise ReviewRequired('Unexpected training index path')
    index = pathlib.Path(index_value)
    if (index.parent != folder or not re.fullmatch(r'added_[A-Za-z0-9_.-]{1,220}\.index', index.name)
            or index.resolve() != index):
        raise ReviewRequired('Unexpected training index path')
    for path, limit, digest in ((model, rvc_export.MAX_MODEL_BYTES, report.get('modelSHA256')),
                               (index, rvc_export.MAX_INDEX_BYTES, report['indexSHA256'].get(str(index)))):
        if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
            raise ReviewRequired('Missing training artifact digests')
        _data(path, limit, digest)
    return report_path, report


def _proof(folder, training, validation, training_path):
    path = folder / 'conversion.json'
    proof = rvc_export._proof(path)
    training_bytes = _data(training_path)
    if json.loads(training_bytes) != training:
        raise ReviewRequired('Training report changed during conversion')
    gate = dict(gateVersion=1, status='passed', minimumActiveSeconds=60,
                activeLowerBoundSeconds=training['effectiveDataset']['activeLowerBoundSeconds'],
                effectiveDatasetSHA256=_hash(_json(training['effectiveDataset']).encode()))
    expected = dict(trainingReportSHA256=_hash(training_bytes), effectiveTrainingData=gate,
                    model=str(folder/'model.pth'), index=str(folder/'model.index'),
                    output=str(folder/'converted.wav'), inputSHA256=validation['inputSHA256'],
                    modelSHA256=training['modelSHA256'],
                    indexSHA256=training['indexSHA256'][training['indices'][0]],
                    identityVerified=False, likenessVerified=False, physicalDeviceVerified=False)
    if any(proof.get(key) != value for key, value in expected.items()):
        raise ReviewRequired('Conversion is not bound to this experiment and held-out clip')
    _data(folder/'input.wav', rvc_export.MAX_AUDIO_BYTES, validation['inputSHA256'])
    for name, limit, digest in [('model.pth', rvc_export.MAX_MODEL_BYTES, proof['modelSHA256']),
                              ('model.index', rvc_export.MAX_INDEX_BYTES, proof['indexSHA256']),
                              ('converted.wav', rvc_export.MAX_AUDIO_BYTES, proof['outputSHA256'])]:
        raw = _data(folder/name, limit, digest)
        if name == 'converted.wav':
            if rvc_export.audio_metrics(raw)['sampleRate'] != 40000:
                raise ReviewRequired('Conversion audio rate changed')
    return path, proof


def _metadata(group, request, manifest):
    return dict(id=group['id'], name='Speaker ' + str(group['group']).zfill(2) + ' (unreviewed)',
                categories=['Unreviewed private RVC speakers'],
                source='Private original source ' + request['videoURL'] + '; SHA-256 ' +
                       manifest['source']['sourceSHA256'] + '; automatic grouping, identity unverified',
                permission=request['sourceUse']['record'])


def _existing(target, metadata, proof):
    """Recover a rename-before-journal crash only for the same checked export."""
    if target.resolve() != target or not target.is_dir():
        raise ReviewRequired('Existing RVC export location changed')
    if set(path.name for path in target.iterdir()) != {'model.pth', 'model.index', 'manifest.json'}:
        raise ReviewRequired('Existing RVC export contents conflict')
    manifest = _read(target/'manifest.json')
    expected = dict(metadata, schemaVersion=1, format=FORMAT,
                    status='conversion-checked-needs-review', modelVersion='v2', sampleRate=40000,
                    featureDimensions=768, indexVectors=proof['indexVectors'],
                    sourceRevision=rvc_training.UPSTREAM, modelFile='model.pth', indexFile='model.index',
                    modelSHA256=proof['modelSHA256'], indexSHA256=proof['indexSHA256'],
                    validationAudioSHA256=proof['outputSHA256'], wordErrorRate=proof['wordcheck']['wordErrorRate'],
                    identityVerified=False, likenessVerified=False, nativeIPhoneRuntimeVerified=False,
                    trainingReportSHA256=proof['trainingReportSHA256'], effectiveTrainingData=proof['effectiveTrainingData'])
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ReviewRequired('Existing RVC export conflicts with checked artifacts')
    for name, limit, digest, field in [('model.pth', rvc_export.MAX_MODEL_BYTES, proof['modelSHA256'], 'modelBytes'),
                                      ('model.index', rvc_export.MAX_INDEX_BYTES, proof['indexSHA256'], 'indexBytes')]:
        if len(_data(target/name, limit, digest)) != manifest.get(field):
            raise ReviewRequired('Existing RVC export bytes changed')


def run_once(root, *, engine_root, validation_wav, validation_text, validation_source,
             verify_words, analyze, python=sys.executable, epochs=200,
             stage_timeout=6*60*60, cancel=None, paused=lambda: False,
             prepare_job=None, train_job=None, conversion_job=None,
             lease_seconds=120, heartbeat_interval=5):
    """Process one RVC-only job and return a redacted technical status, never likeness.

    `validation_source` records the operator's provenance for a separately held-out
    original clip. WAV/PCM hashes are checked against every retained training segment.
    `verify_words` must independently transcribe real converted audio; the existing
    queue_processor.recognizer factory supplies the pinned local implementation.
    """
    from tools.rvc_dataset_prepare import prepare, load_manifest
    if (cancel is not None and cancel.is_set()) or paused():
        return None
    if (type(lease_seconds) not in (int, float) or not 1 <= lease_seconds <= 3600 or
            type(heartbeat_interval) not in (int, float) or not .01 <= heartbeat_interval < lease_seconds/3):
        raise ValueError('Invalid worker heartbeat configuration')
    root = ensure_root(root)
    engine = pathlib.Path(engine_root).absolute()
    if engine.resolve() != engine or not engine.is_dir() or engine == root or engine in root.parents or root in engine.parents:
        raise ValueError('Configure a separate unlinked local RVC engine')
    prepare_job = prepare if prepare_job is None else prepare_job
    train_job = rvc_training.train if train_job is None else train_job
    conversion_job = rvc_validation.verify_conversion if conversion_job is None else conversion_job
    queue = VideoQueue(str(root/DATABASE))
    stop, lost, stage_cancel = threading.Event(), threading.Event(), threading.Event()
    job = None
    thread = None
    states = {}
    current = None
    percent = [0.0]
    missing_hook = object()
    previous_hook = missing_hook
    recognizer_hook = False

    def interrupted():
        return (cancel is not None and cancel.is_set()) or paused()

    def check(renew=True):
        if lost.is_set():
            stage_cancel.set()
            raise ValueError('Worker ownership was lost')
        if interrupted():
            stage_cancel.set()
            raise InterruptedError('Private RVC work paused')
        try:
            if renew:
                queue.progress(job['id'], percent[0], token=job['token'], lease_seconds=lease_seconds)
            else:
                queue._owner(job['id'], job['token'], time.time())
        except ValueError as error:
            lost.set()
            stage_cancel.set()
            raise ValueError('Worker ownership was lost') from error

    def heartbeat():
        pulse = None
        due = time.monotonic() + heartbeat_interval
        try:
            pulse = VideoQueue(str(root/DATABASE))
            while not stop.wait(min(.1, heartbeat_interval)):
                if interrupted():
                    stage_cancel.set()
                    return
                if time.monotonic() >= due:
                    pulse.progress(job['id'], percent[0], token=job['token'], lease_seconds=lease_seconds)
                    due = time.monotonic() + heartbeat_interval
        except Exception:
            lost.set()
            stage_cancel.set()
        finally:
            if pulse is not None:
                pulse.close()

    def owned(operation):
        return queue.owned_call(job['id'], job['token'], operation)

    def save(group_id):
        state = states[group_id]
        owned(lambda: queue.db.execute('INSERT INTO rvc_groups VALUES (?,?,?) '
              'ON CONFLICT(video_id,group_id) DO UPDATE SET state=excluded.state',
              (job['id'], group_id, _json(state))))

    def result(status, reason):
        statuses = {'exported': 'exported-needs-review', 'checked': 'checked-needs-review',
                    'trained': 'trained-needs-review', 'insufficient-data': 'insufficient-data'}
        return dict(schemaVersion=1, format=FORMAT, videoID=job['id'], attempt=job['attempt'],
                    status=status, reasonCode=reason,
                    groups=[dict(id=identifier, status=statuses.get(state['status'], 'needs-review'))
                            for identifier, state in states.items()],
                    identityVerified=False, likenessVerified=False, nativeIPhoneRuntimeVerified=False)

    def finish(reason):
        check()
        answer = result('needs-review', reason)
        queue.review_with(job['id'], job['token'], lambda: queue.db.execute(
            'INSERT INTO rvc_results VALUES (?,?) ON CONFLICT(video_id) DO UPDATE SET body=excluded.body',
            (job['id'], _json(answer))))
        return answer

    try:
        job = queue.claim(lease_seconds=lease_seconds)
        if job is None:
            return None
        with queue.db:
            queue.db.execute('CREATE TABLE IF NOT EXISTS rvc_jobs '
                             '(video_id TEXT PRIMARY KEY, manifest TEXT NOT NULL, digest TEXT NOT NULL, configuration TEXT NOT NULL)')
            queue.db.execute('CREATE TABLE IF NOT EXISTS rvc_groups '
                             '(video_id TEXT NOT NULL, group_id TEXT NOT NULL, state TEXT NOT NULL, PRIMARY KEY(video_id,group_id))')
            queue.db.execute('CREATE TABLE IF NOT EXISTS rvc_results (video_id TEXT PRIMARY KEY, body TEXT NOT NULL)')
        if hasattr(verify_words, 'transcribe'):
            previous_hook = getattr(verify_words, 'job_cancelled', missing_hook)
            verify_words.job_cancelled = stage_cancel.is_set
            recognizer_hook = True
        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        check()
        request = load(queue.db, job['id'])
        if request is None or request['videoURL'] != job['url'] or video_id(job['url']) != job['id']:
            raise ReviewRequired('Explicit matching RVC source-use request is required')
        if not callable(verify_words):
            raise ReviewRequired('An independent word verifier must be configured')
        validation, configuration = _configuration(engine, validation_wav, validation_text,
                                                    validation_source, epochs, python, stage_timeout)
        previous = queue.db.execute('SELECT manifest,digest,configuration FROM rvc_jobs WHERE video_id=?',
                                    (job['id'],)).fetchone()
        if previous:
            if previous[2] != configuration:
                raise ReviewRequired('The held-out validation or training configuration changed')
            manifest_path = _path(root, previous[0])
            _data(manifest_path, expected=previous[1])
        else:
            check()
            manifest_path = pathlib.Path(prepare_job(request, _path(root, 'datasets'), analyze=analyze,
                                         cancelled=stage_cancel.is_set, activity=lambda *args: check(),
                                         commit=lambda operation: (check(), owned(operation))[1])).absolute()
            relative = manifest_path.relative_to(root).as_posix()
            if not re.fullmatch(r'datasets/[A-Za-z0-9_-]{11}/[0-9a-f]{64}/manifest\.json', relative):
                raise ReviewRequired('Unexpected dataset manifest path')
            _path(root, relative)
            raw = _data(manifest_path)
            load_manifest(manifest_path, request=request, cancelled=stage_cancel.is_set)
            owned(lambda: queue.db.execute('INSERT INTO rvc_jobs VALUES (?,?,?,?)',
                                           (job['id'], relative, _hash(raw), configuration)))
        check()
        manifest = load_manifest(manifest_path, request=request, cancelled=stage_cancel.is_set)
        groups = manifest['groups']
        if not isinstance(groups, list) or len(groups) > 32:
            raise ReviewRequired('Invalid dataset group count')
        # Check the original validation clip against source-media and segment PCM,
        # not only container hashes. A changed WAV header cannot defeat this gate.
        if validation['inputSHA256'] == manifest['source']['sourceSHA256']:
            raise ReviewRequired('Validation must be held out from the training source')
        all_hashes = set()
        ids = set()
        for group in groups:
            if group['id'] in ids or not re.fullmatch(r'rvc-[a-z0-9_-]{11}-[0-9a-f]{12}-group-[0-9]{2}', group['id']):
                raise ReviewRequired('Invalid or repeated anonymous group identifier')
            ids.add(group['id'])
            for sample in group['trainingFiles']:
                if sample['pcmSHA256'] in all_hashes:
                    raise ReviewRequired('Repeated training source audio')
                all_hashes.add(sample['pcmSHA256'])
                if validation['inputSHA256'] == sample['sha256'] or validation['pcmSHA256'] == sample['pcmSHA256']:
                    raise ReviewRequired('Validation speech was used for training')
            row = queue.db.execute('SELECT state FROM rvc_groups WHERE video_id=? AND group_id=?',
                                   (job['id'], group['id'])).fetchone()
            if row:
                if len(row[0]) > 4096:
                    raise ReviewRequired('Private group journal exceeds its bound')
                state = json.loads(row[0])
                if (not isinstance(state, dict) or set(state) != {'status', 'experiment', 'datasetRevision', 'configuration'} or
                        state['datasetRevision'] != manifest['revision'] or state['configuration'] != configuration or
                        not isinstance(state['experiment'], str) or not re.fullmatch('rvc_[0-9a-f]{32}', state['experiment']) or
                        state['status'] not in {'pending', 'training', 'trained', 'checking', 'checked', 'exported', 'insufficient-data', 'needs-review'}):
                    raise ReviewRequired('Private group journal is invalid or changed')
                states[group['id']] = state
            else:
                states[group['id']] = dict(status='insufficient-data' if group['status'] != 'ready-for-training' else 'pending',
                                          experiment='rvc_' + uuid.uuid4().hex,
                                          datasetRevision=manifest['revision'], configuration=configuration)
                save(group['id'])
        for number, group in enumerate(groups):
            current = group['id']
            state = states[current]
            percent[0] = .1 + .8 * number/max(1, len(groups))
            check()
            if state['status'] == 'insufficient-data':
                continue
            if state['status'] == 'needs-review':
                return finish('retained-attempt-needs-review')
            experiment = state['experiment']
            check_folder = _path(root, 'checks/' + experiment)
            training_path = _path(engine, 'logs/' + experiment + '/voicematrix-training.json')
            if state['status'] == 'pending':
                dataset = _path(manifest_path.parent, group['trainingDirectory'])
                expected_files = {pathlib.PurePosixPath(row['file']).name for row in group['trainingFiles']}
                if (set(path.name for path in dataset.iterdir()) != expected_files or
                        any(path.resolve() != path for path in dataset.iterdir()) or
                        rvc_training.audit_dataset(dataset) != group['audit']):
                    raise ReviewRequired('Original training audio changed before training')
                check()
                state['status'] = 'training'
                save(current)
                check()
                train_job(engine, dataset, experiment, request['sourceUse']['record'], python=python,
                          epochs=epochs, cancel=stage_cancel, stage_timeout=stage_timeout)
            # Recovery reads only the expected durable report for this experiment.
            # Missing/failed reports require review, never a second blind train.
            check()
            training_path, training = _training(engine, experiment, group, request, epochs)
            if state['status'] == 'training':
                state['status'] = 'trained'
                save(current)
            check()
            if state['status'] == 'trained':
                if check_folder.exists():
                    # A complete durable conversion may have outlived its DB write.
                    _proof(check_folder, training, validation, training_path)
                else:
                    state['status'] = 'checking'
                    save(current)
                    check()
                    conversion_job(engine, training_path, validation_wav, check_folder,
                                   expected_text=validation_text, verify_words=verify_words,
                                   python=python, cancel=stage_cancel, timeout=min(stage_timeout, 600))
            proof_path, proof = _proof(check_folder, training, validation, training_path)
            if state['status'] != 'exported':
                state['status'] = 'checked'
                save(current)
            check()
            metadata = _metadata(group, request, manifest)
            voices = _path(root, 'voices')
            target = _path(voices, current)

            def fenced_cancelled():
                if interrupted() or lost.is_set() or stage_cancel.is_set():
                    return True
                try:
                    queue._owner(job['id'], job['token'], time.time())
                    return False
                except ValueError:
                    lost.set()
                    stage_cancel.set()
                    return True

            def publish():
                if fenced_cancelled():
                    raise InterruptedError('Private RVC publication paused')
                if target.exists() or target.is_symlink():
                    _existing(target, metadata, proof)
                elif state['status'] == 'exported':
                    raise ReviewRequired('Previously exported artifacts are missing')
                else:
                    rvc_export.export_folder(proof_path, metadata, voices, cancelled=fenced_cancelled)
            owned(publish)
            state['status'] = 'exported'
            save(current)
        return finish('technical-checks-only' if any(state['status'] == 'exported' for state in states.values()) else 'insufficient-data')
    except Exception as error:
        if job is None:
            raise
        # A stale worker cannot mark someone else's job failed or paused.
        try:
            queue._owner(job['id'], job['token'], time.time())
        except ValueError as ownership:
            lost.set()
            stage_cancel.set()
            raise ValueError('Worker ownership was lost; no status was changed') from ownership
        if lost.is_set():
            raise ValueError('Worker ownership was lost; no status was changed') from error
        if isinstance(error, InterruptedError) or interrupted():
            queue.pause(job['id'], job['token'])
            return result('paused', 'cancelled-retained')
        if current is not None:
            states[current]['status'] = 'needs-review'
            save(current)
        # No raw model paths, transcript, audio, or exception text enters results.
        return finish('retained-attempt-needs-review' if current is not None else 'configuration-or-dataset-needs-review')
    finally:
        stop.set()
        if thread is not None:
            thread.join()
        if recognizer_hook:
            if previous_hook is missing_hook:
                del verify_words.job_cancelled
            else:
                verify_words.job_cancelled = previous_hook
        queue.close()
