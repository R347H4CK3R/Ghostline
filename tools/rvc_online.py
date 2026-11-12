"""Reconstructed source-only RVC service. Not a deployed or likeness-verified service."""
import array
import base64
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import struct
import tempfile
import threading
import time
import uuid
import wave

MAX_AUDIO = 3 * 1024 * 1024
MAX_MODEL = 512 * 1024 * 1024
RATES = (16000, 22050, 24000, 32000, 40000, 44100, 48000)
UPSTREAM = '81eed5e8f68b6bed1789f682fe78cdd324495afc'
HASH_FIELDS = ('modelSHA256', 'indexSHA256', 'revision', 'inputSHA256')
IDENTITY = ('schemaVersion', 'requestID', 'modelID', *HASH_FIELDS)
STATES = {'queued', 'waiting-for-resources', 'running', 'cancelling', 'cancelled', 'failed', 'succeeded'}


class ServiceError(Exception):
    def __init__(self, status=400, code='invalid_request'):
        self.status, self.code = status, code
        super().__init__(code)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def model_id(value):
    return isinstance(value, str) and re.fullmatch('[a-z0-9_-]{1,100}', value) is not None


def request_id(value):
    try:
        return isinstance(value, str) and str(uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def strict_json(data):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError('Duplicate JSON key')
            out[key] = value
        return out
    def constant(_):
        raise ValueError('Nonfinite JSON')
    return json.loads(data, object_pairs_hook=pairs, parse_constant=constant)


def safe_root(path):
    # Reject symlink components before normalizing; .. is normalized by resolve.
    raw = Path(path).absolute()
    if any(p.is_symlink() for p in (raw, *raw.parents)):
        raise ValueError('Linked root')
    root = raw.resolve()
    if any((p / 'collection.json').exists() for p in (root, *root.parents)):
        raise ValueError('Separate RVC root required')
    return root


def bounded_file(path, maximum, expected=None, destination=None):
    path = Path(path)
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Linked artifact')
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    fd = os.open(path, flags)
    result = bytearray() if destination is None else None
    hasher = hashlib.sha256()
    total = 0
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= maximum:
            raise ValueError('Invalid artifact size')
        with os.fdopen(fd, 'rb', closefd=False) as src:
            while True:
                chunk = src.read(min(1024 * 1024, maximum + 1 - total))
                if not chunk:
                    break
                total += len(chunk)
                if total > maximum:
                    raise ValueError('Artifact grew')
                hasher.update(chunk)
                if destination is None:
                    result.extend(chunk)
                else:
                    destination.write(chunk)
        if total != info.st_size or (expected is not None and hasher.hexdigest() != expected):
            raise ValueError('Artifact changed')
    finally:
        os.close(fd)
    return bytes(result) if result is not None else total


def wav_info(data, output=False):
    if not isinstance(data, bytes) or not 44 <= len(data) <= MAX_AUDIO:
        raise ValueError('Invalid WAV size')
    if data[:4] != b'RIFF' or data[8:12] != b'WAVE' or struct.unpack('<I', data[4:8])[0] != len(data) - 8:
        raise ValueError('Invalid RIFF')
    offset, seen = 12, set()
    while offset < len(data):
        if offset + 8 > len(data):
            raise ValueError('Invalid chunk')
        kind, size = data[offset:offset + 4], struct.unpack('<I', data[offset + 4:offset + 8])[0]
        if kind in (b'fmt ', b'data') and kind in seen:
            raise ValueError('Unsupported WAV chunk')
        if kind in (b'fmt ', b'data'):
            seen.add(kind)
        if offset + 8 + size > len(data):
            raise ValueError('Truncated chunk')
        if kind == b'fmt ':
            if size < 16:
                raise ValueError('Use PCM16')
            fmt, channels, rate, byte_rate, align, bits = struct.unpack('<HHIIHH', data[offset + 8:offset + 24])
            if (fmt, channels, align, bits) != (1, 1, 2, 16) or byte_rate != rate * 2:
                raise ValueError('Use mono PCM16')
        if kind == b'data' and (b'fmt ' not in seen or size % 2):
            raise ValueError('Invalid PCM data')
        offset += 8 + size + size % 2
    if offset != len(data) or seen != {b'fmt ', b'data'}:
        raise ValueError('Invalid chunks')
    with wave.open(io.BytesIO(data), 'rb') as audio:
        rate, count = audio.getframerate(), audio.getnframes()
        if rate not in RATES or (output and rate != 40000) or not .2 <= count / rate <= 30:
            raise ValueError('WAV bounds')
        pcm = audio.readframes(count)
        if len(pcm) != 2 * count:
            raise ValueError('Truncated audio')
        samples = array.array('h', pcm)
        if __import__('sys').byteorder != 'little':
            samples.byteswap()
        if any(abs(v) >= 32767 for v in samples) or sum(v*v for v in samples) / count <= (32768 * .0001) ** 2:
            raise ValueError('Silent or clipped audio')
    return dict(sampleRate=rate, seconds=count / rate)


def _registry_io(method):
    def admitted(self, *args, **kwargs):
        if not self.io_lock.acquire(blocking=False):
            raise ServiceError(429, 'registry_busy')
        try:
            return method(self, *args, **kwargs)
        finally:
            self.io_lock.release()
    return admitted


class Registry:
    def __init__(self, root):
        self.root = safe_root(root)
        self.io_lock = threading.RLock()
        if not self.root.is_dir():
            raise ValueError('Missing registry')

    @_registry_io
    def resolve(self, identifier, revision=None, modelSHA256=None, indexSHA256=None, destination=None):
        if not model_id(identifier):
            raise ServiceError()
        folder = self.root / identifier
        if not folder.is_dir() or folder.is_symlink():
            raise ServiceError(404, 'model_not_found')
        raw = bounded_file(folder / 'manifest.json', 65536)
        m = strict_json(raw)
        if not isinstance(m, dict):
            raise ValueError('Invalid manifest')
        expected = dict(schemaVersion=1, id=identifier, format='rvc-v2-pth-index',
                        status='conversion-checked-needs-review', modelVersion='v2', sampleRate=40000,
                        featureDimensions=768, sourceRevision=UPSTREAM, modelFile='model.pth', indexFile='model.index',
                        identityVerified=False, likenessVerified=False, nativeIPhoneRuntimeVerified=False)
        if any(type(m.get(k)) is not type(v) or m[k] != v for k, v in expected.items()):
            raise ValueError('Unsupported model')
        gate = m.get('effectiveTrainingData', {})
        if (not isinstance(gate, dict) or type(gate.get('gateVersion')) is not int or gate.get('gateVersion') != 1 or gate.get('status') != 'passed' or
                gate.get('minimumActiveSeconds') != 60 or type(gate.get('activeLowerBoundSeconds')) not in (int, float) or
                not 60 <= gate['activeLowerBoundSeconds'] <= 1800 or not digest(gate.get('effectiveDatasetSHA256'))):
            raise ValueError('Effective data gate')
        def label(value, limit):
            return isinstance(value, str) and 0 < len(value.strip()) <= limit and all(ord(c) >= 32 for c in value) and '/' not in value and '\\' not in value
        categories = m.get('categories')
        if (not label(m.get('name'), 200) or not isinstance(categories, list) or not 1 <= len(categories) <= 20 or
                any(not label(c, 100) for c in categories) or len(set(categories)) != len(categories) or
                type(m.get('indexVectors')) is not int or m['indexVectors'] < 1):
            raise ValueError('Invalid metadata')
        if (any(not digest(m.get(k)) for k in ('validationAudioSHA256', 'trainingReportSHA256')) or
                type(m.get('wordErrorRate')) not in (int, float) or not 0 <= m['wordErrorRate'] <= .1):
            raise ValueError('Invalid conversion proof')
        for field in ('source', 'permission'):
            text = m.get(field)
            if not isinstance(text, str) or not 1 <= len(text.strip()) <= 3000 or any(ord(c) < 32 for c in text):
                raise ValueError('Missing provenance')
        actual_revision = sha(raw)
        if revision is not None and revision != actual_revision:
            raise ServiceError(409, 'model_changed')
        for field, name, wanted in [('modelSHA256', 'model.pth', modelSHA256), ('indexSHA256', 'model.index', indexSHA256)]:
            size = m.get('modelBytes' if field == 'modelSHA256' else 'indexBytes')
            if not digest(m.get(field)) or type(size) is not int or not 0 < size <= MAX_MODEL:
                raise ValueError('Invalid artifact metadata')
            if wanted is not None and wanted != m[field]:
                raise ServiceError(409, 'model_changed')
            if destination is None:
                # Hash without accumulating model in RAM.
                with open(os.devnull, 'wb') as sink:
                    count = bounded_file(folder / name, MAX_MODEL, m[field], sink)
            else:
                _private_file(Path(destination) / name)
                with (Path(destination) / name).open('wb') as sink:
                    count = bounded_file(folder / name, MAX_MODEL, m[field], sink)
            if count != size:
                raise ValueError('Artifact size mismatch')
        return dict(id=identifier, name=m['name'], categories=categories, modelSHA256=m['modelSHA256'],
                    indexSHA256=m['indexSHA256'], revision=actual_revision, identityVerified=False, likenessVerified=False)

    @_registry_io
    def catalog(self):
        models = []
        with os.scandir(self.root) as entries:
            for i, entry in enumerate(entries):
                if i >= 256:
                    raise ValueError('Registry entry bound')
                if entry.name.startswith('.'):
                    continue
                if not model_id(entry.name) or not entry.is_dir(follow_symlinks=False):
                    raise ValueError('Unexpected registry entry')
                models.append(self.resolve(entry.name))
                if len(models) > 64:
                    raise ValueError('Model bound')
        return sorted(models, key=lambda m: m['id'])


def _private_check(path, directory=False):
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or (directory and not stat.S_ISDIR(info.st_mode)) or (not directory and not stat.S_ISREG(info.st_mode)):
        raise ValueError('Invalid private artifact')
    if os.name == 'posix' and (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077 or (not directory and info.st_nlink != 1)):
        raise ValueError('Existing artifact permissions are not private')


def _private_file(path):
    # Exclusive creation never changes permissions of preexisting user files.
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        _private_check(path)
    else:
        os.close(fd)
        _private_check(path)


def _private_directory(path):
    if not path.exists():
        if not path.parent.exists():
            _private_directory(path.parent)
        try:
            path.mkdir(mode=0o700)
        except FileExistsError:
            pass
    _private_check(path, directory=True)


def _db_safe(method):
    def guarded(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except sqlite3.Error:
            self._fault()
            raise ServiceError(503, 'storage_unavailable') from None
    return guarded


class ConversionService:
    def __init__(self, root, registry, converter=None, *, guard):
        from tools.master_voices import _publish_lock
        if not callable(guard):
            raise ValueError('Explicit resource guard required')
        self.root, self.registry, self.converter, self.guard = safe_root(root), registry, converter, guard
        if self.root == registry.root or self.root in registry.root.parents or registry.root in self.root.parents:
            raise ValueError('Separate job and registry roots required')
        _private_directory(self.root)
        marker = self.root / '.rvc-online.json'
        if marker.exists():
            _private_check(marker)
            if bounded_file(marker, 100) != b'{"schemaVersion":1}\n':
                raise ValueError('Invalid service root')
        elif any(self.root.iterdir()):
            raise ValueError('Use an empty private job root')
        else:
            _private_file(marker)
            marker.write_bytes(b'{"schemaVersion":1}\n')
        _private_file(self.root / '.owner.lock')
        self._owner = _publish_lock(self.root / '.owner.lock')
        self._owner.__enter__()
        try:
            for name in ('conversions.sqlite3', 'conversions.sqlite3-journal', 'conversions.sqlite3-wal', 'conversions.sqlite3-shm'):
                path = self.root / name
                if path.exists() or path.is_symlink():
                    _private_check(path)
            _private_file(self.root / 'conversions.sqlite3')
            self.db = sqlite3.connect(self.root / 'conversions.sqlite3', check_same_thread=False)
            self.db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, receipt TEXT NOT NULL, input BLOB NOT NULL, output BLOB)')
            self.lock = threading.RLock()
            self.admission = threading.Lock()
            self.upload_slot = threading.BoundedSemaphore(2)
            self.stop = threading.Event()
            self.wake = threading.Event()
            self.thread = None
            self.closed = False
            self.faulted = False
            self.cancel_events = {}
            for key, raw in self.db.execute('SELECT id,receipt FROM jobs').fetchall():
                state = strict_json(raw)
                if state.get('status') in ('running', 'cancelling'):
                    state.update(status='failed', updatedAt=time.time())
                    self._save(key, state)
        except BaseException:
            try:
                if hasattr(self, 'db'):
                    self.db.close()
            finally:
                self._owner.__exit__(None, None, None)
            raise

    def _fault(self):
        with self.lock:
            self.faulted = True
            for event in self.cancel_events.values():
                event.set()
            try:
                self.db.rollback()
            except Exception:
                pass

    @_db_safe
    def _save(self, key, receipt, output=None):
        self.db.execute('UPDATE jobs SET receipt=?,output=? WHERE id=?', (json.dumps(receipt, allow_nan=False), output, key))
        self.db.commit()

    def available(self):
        return self.converter is not None and not self.stop.is_set() and not self.faulted

    def _guard(self):
        try:
            return self.guard() is True
        except Exception:
            return False

    def catalog(self):
        return dict(schemaVersion=1, format='rvc-online-conversion-v1', onlineConversionAvailable=self.available(),
                    offlineAvailable=False, textToSpeechAvailable=False, models=self.registry.catalog())

    @_db_safe
    def submit(self, body):
        if not self.admission.acquire(blocking=False):
            raise ServiceError(429, 'admission_busy')
        try:
            if not isinstance(body, dict) or set(body) != {*IDENTITY, 'wavBase64'}:
                raise ServiceError()
            if (type(body['schemaVersion']) is not int or body['schemaVersion'] != 1 or not request_id(body['requestID']) or
                    not model_id(body['modelID']) or any(not digest(body[k]) for k in HASH_FIELDS) or
                    not isinstance(body['wavBase64'], str) or len(body['wavBase64']) > (MAX_AUDIO + 2) // 3 * 4):
                raise ServiceError()
            audio = base64.b64decode(body['wavBase64'], validate=True)
            wav_info(audio)
            if sha(audio) != body['inputSHA256']:
                raise ServiceError()
            key = body['requestID']
            with self.lock:
                if self.stop.is_set() or self.faulted:
                    raise ServiceError(503, 'service_unavailable')
                old = self.db.execute('SELECT receipt,input FROM jobs WHERE id=?', (key,)).fetchone()
                if old:
                    receipt = self._public(strict_json(old[0]))
                    if any(receipt[k] != body[k] for k in IDENTITY) or old[1] != audio:
                        raise ServiceError(409, 'request_conflict')
                    return receipt
                if not self.available():
                    raise ServiceError(503, 'conversion_unavailable')
                if self.db.execute('SELECT count(*) FROM jobs').fetchone()[0] >= 32:
                    raise ServiceError(429, 'job_capacity')
            self.registry.resolve(body['modelID'], body['revision'], body['modelSHA256'], body['indexSHA256'])
            now = time.time()
            receipt = dict((k, body[k]) for k in IDENTITY)
            receipt.update(status='queued', createdAt=now, updatedAt=now)
            with self.lock:
                if self.stop.is_set() or self.faulted:
                    raise ServiceError(503, 'service_unavailable')
                self.db.execute('INSERT INTO jobs VALUES (?,?,?,NULL)', (key, json.dumps(receipt), audio))
                self.db.commit()
            self.wake.set()
            return receipt
        finally:
            self.admission.release()

    def _public(self, value):
        if (not isinstance(value, dict) or type(value.get('schemaVersion')) is not int or value['schemaVersion'] != 1 or
                not request_id(value.get('requestID')) or not model_id(value.get('modelID')) or
                any(not digest(value.get(k)) for k in HASH_FIELDS) or value.get('status') not in STATES or
                any(type(value.get(k)) not in (int, float) or not math.isfinite(value[k]) for k in ('createdAt', 'updatedAt'))):
            raise ServiceError(503, 'invalid_receipt')
        result = {k: value[k] for k in (*IDENTITY, 'status', 'createdAt', 'updatedAt')}
        if value['status'] == 'succeeded':
            r = value.get('result')
            if (not isinstance(r, dict) or not digest(r.get('sha256')) or type(r.get('bytes')) is not int or
                    not 44 <= r['bytes'] <= MAX_AUDIO or type(r.get('sampleRate')) is not int or r['sampleRate'] != 40000 or
                    type(r.get('seconds')) not in (int, float) or not .2 <= r['seconds'] <= 30):
                raise ServiceError(503, 'invalid_receipt')
            result['result'] = {k: r[k] for k in ('sha256', 'bytes', 'sampleRate', 'seconds')}
        return result

    @_db_safe
    def status(self, key):
        if not request_id(key):
            raise ServiceError()
        with self.lock:
            if self.faulted:
                raise ServiceError(503, 'storage_unavailable')
            if self.closed:
                raise ServiceError(503, 'service_closed')
            row = self.db.execute('SELECT receipt FROM jobs WHERE id=?', (key,)).fetchone()
            if not row:
                raise ServiceError(404, 'job_not_found')
            value = self._public(strict_json(row[0]))
            if value['requestID'] != key:
                raise ServiceError(503, 'invalid_receipt')
            return value

    @_db_safe
    def result(self, key):
        with self.lock:
            status = self.status(key)
            if status['status'] != 'succeeded':
                raise ServiceError(409, 'result_not_ready')
            data = self.db.execute('SELECT output FROM jobs WHERE id=?', (key,)).fetchone()[0]
            info = wav_info(data, output=True)
            expected = status['result']
            if sha(data) != expected['sha256'] or len(data) != expected['bytes'] or info['seconds'] != expected['seconds']:
                raise ServiceError(503, 'invalid_result')
            return data

    @_db_safe
    def cancel(self, key):
        with self.lock:
            value = self.status(key)
            if value['status'] in ('queued', 'waiting-for-resources'):
                value.update(status='cancelled', updatedAt=time.time())
                self._save(key, value)
            elif value['status'] in ('running', 'cancelling'):
                value.update(status='cancelling', updatedAt=time.time())
                self._save(key, value)
                self.cancel_events[key].set()
            return value

    def start(self):
        with self.lock:
            if self.stop.is_set() or self.faulted:
                raise ServiceError(503, 'service_unavailable')
            if self.converter is None:
                raise ServiceError(503, 'conversion_unavailable')
            if self.thread is None:
                self.thread = threading.Thread(target=self._work, daemon=True)
                self.thread.start()

    def _work(self):
        try:
            self._work_loop()
        except Exception:
            # Any unexpected scan, transition or final-write failure is visible
            # as unavailable. Never leave a dead worker advertising readiness.
            with self.lock:
                self._fault()

    def _work_loop(self):
        while not self.stop.is_set():
            key = None
            with self.lock:
                if self.faulted:
                    return
                for candidate, raw in self.db.execute('SELECT id,receipt FROM jobs ORDER BY rowid').fetchall():
                    try:
                        value = self._public(strict_json(raw))
                        if value['requestID'] != candidate:
                            raise ValueError('Receipt identity mismatch')
                    except Exception:
                        self.faulted = True
                        return
                    if value['status'] in ('queued', 'waiting-for-resources'):
                        key = candidate
                        break
                if key is not None:
                    if not self._guard():
                        if value['status'] != 'waiting-for-resources':
                            value.update(status='waiting-for-resources', updatedAt=time.time())
                            self._save(key, value)
                        key = None
                    else:
                        event = threading.Event()
                        self.cancel_events[key] = event
                        value.update(status='running', updatedAt=time.time())
                        self._save(key, value)
            if key is None:
                self.wake.wait(.25)
                self.wake.clear()
                continue
            try:
                with tempfile.TemporaryDirectory(prefix='convert-', dir=str(self.root)) as temporary:
                    folder = Path(temporary).resolve(strict=True)
                    self.registry.resolve(value['modelID'], value['revision'], value['modelSHA256'], value['indexSHA256'], folder)
                    with self.lock:
                        audio = self.db.execute('SELECT input FROM jobs WHERE id=?', (key,)).fetchone()[0]
                    wav_info(audio)
                    if sha(audio) != value['inputSHA256']:
                        raise ValueError('Input changed')
                    _private_file(folder / 'input.wav')
                    (folder / 'input.wav').write_bytes(audio)
                    if event.is_set() or self.stop.is_set() or self.faulted or not self._guard():
                        raise InterruptedError()
                    monitor_stop = threading.Event()
                    def monitor():
                        while not monitor_stop.wait(.1):
                            if self.stop.is_set() or self.faulted or not self._guard():
                                event.set()
                                return
                    monitor_thread = threading.Thread(target=monitor, daemon=True)
                    monitor_thread.start()
                    try:
                        output = self.converter(folder, dict(value), event)
                    finally:
                        monitor_stop.set()
                        monitor_thread.join(timeout=2)
                        if monitor_thread.is_alive():
                            event.set()
                            raise TimeoutError('Guard monitor not stopped')
                    info = wav_info(output, output=True)
                    if abs(info['seconds'] - wav_info(audio)['seconds']) > .25:
                        raise ValueError('Duration changed')
                    with self.lock:
                        current = self.status(key)
                        if current['status'] == 'cancelling' or event.is_set():
                            current.update(status='cancelled')
                            output = None
                        elif self.stop.is_set() or self.faulted or not self._guard():
                            current.update(status='failed')
                            output = None
                        else:
                            current.update(status='succeeded', result=dict(sha256=sha(output), bytes=len(output), **info))
                        current['updatedAt'] = time.time()
                        self._save(key, current, output)
            except Exception as error:
                if isinstance(error, sqlite3.Error) or self.faulted:
                    raise
                with self.lock:
                    current = self.status(key)
                    retry = isinstance(error, ServiceError) and error.status == 429 and error.code == 'registry_busy'
                    current.update(status='cancelled' if event.is_set() else ('queued' if retry else 'failed'), updatedAt=time.time())
                    self._save(key, current)
                if retry:
                    self.stop.wait(.25)
            finally:
                with self.lock:
                    self.cancel_events.pop(key, None)

    def close(self):
        self.stop.set()
        self.wake.set()
        with self.lock:
            if self.closed:
                return
            for event in self.cancel_events.values():
                event.set()
        if not self.admission.acquire(timeout=30):
            raise TimeoutError('Admission still stopping')
        try:
            if self.thread is not None:
                self.thread.join(timeout=30)
                if self.thread.is_alive():
                    raise TimeoutError('Conversion still stopping')
            with self.lock:
                self.db.close()
                self.closed = True
                self._owner.__exit__(None, None, None)
        finally:
            self.admission.release()


class NeuralConverter:
    def __init__(self, engine_root, python, timeout=600):
        if type(timeout) not in (int, float) or not 0 < timeout <= 600:
            raise ValueError('Invalid timeout')
        self.root, self.python, self.timeout = Path(engine_root).resolve(), str(Path(python).resolve()), timeout

    def __call__(self, folder, receipt, cancel):
        from tools import rvc_validation
        from tools.rvc_training import run_stage
        folder = Path(folder).resolve(strict=True)
        rvc_validation.check_source(self.root)
        output, report = folder / 'converted.wav', folder / 'neural-result.json'
        env = dict(os.environ, HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', CUDA_VISIBLE_DEVICES='', OMP_NUM_THREADS='2', RVC_CUDA_GRAPH='0')
        command = [self.python, str(Path(rvc_validation.__file__).resolve()), '--child', str(self.root),
                   str(folder / 'model.pth'), str(folder / 'model.index'), str(folder / 'input.wav'), str(output), str(report)]
        with (folder / 'conversion.log').open('wb') as log:
            run_stage(command, cwd=self.root, env=env, log=log, timeout=self.timeout, cancel=cancel)
        if cancel.is_set():
            raise InterruptedError()
        proof = strict_json(bounded_file(report, 65536))
        if (not isinstance(proof, dict) or proof.get('modelVersion') != 'v2' or proof.get('sampleRate') != 40000 or
                proof.get('featureDimensions') != 768 or type(proof.get('indexVectors')) is not int or proof['indexVectors'] < 1 or
                any(proof.get(k) != receipt[k] for k in ('modelSHA256', 'indexSHA256', 'inputSHA256'))):
            raise ValueError('Invalid neural receipt')
        for name, field, maximum in [('model.pth', 'modelSHA256', MAX_MODEL), ('model.index', 'indexSHA256', MAX_MODEL), ('input.wav', 'inputSHA256', MAX_AUDIO)]:
            with open(os.devnull, 'wb') as sink:
                bounded_file(folder / name, maximum, receipt[field], sink)
        data = bounded_file(output, MAX_AUDIO)
        wav_info(data, output=True)
        return data
