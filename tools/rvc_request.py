"""Explicit private RVC requests in an isolated queue, never F5 consent upgrades.

The caller must choose a new, private root. Only an explicitly configured RVC HTTP route may submit jobs; no live service
uses this module implicitly. Requests contain provenance, not executable paths.
"""
import json
import os
import pathlib
import time
import uuid

from tools.rvc_export import read_bound
from tools.video_queue import VideoQueue, video_id
from tools.workflow_activity import append

FORMAT = 'rvc-v2-pth-index'
MARKER = {'schemaVersion': 1, 'format': FORMAT, 'purpose': 'private-rvc-training'}
DATABASE = 'rvc-queue.db'
MAX_REQUEST_BYTES = 16 * 1024


def _serialize(body):
    text = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    if len(text.encode('utf-8')) > MAX_REQUEST_BYTES:
        raise ValueError('RVC request exceeds its UTF-8 byte bound')
    return text


def validate(body):
    if (not isinstance(body, dict) or
            set(body) != {'schemaVersion', 'format', 'requestID', 'videoURL', 'sourceUse'} or
            type(body['schemaVersion']) is not int or body['schemaVersion'] != 1 or
            body['format'] != FORMAT):
        raise ValueError('An explicit private RVC request is required')
    identifier = body['requestID']
    if not isinstance(identifier, str) or len(identifier) != 36:
        raise ValueError('Invalid request identifier')
    try:
        if str(uuid.UUID(identifier)) != identifier:
            raise ValueError('Invalid request identifier')
    except (ValueError, AttributeError) as error:
        raise ValueError('Invalid request identifier') from error
    url = body['videoURL']
    if not isinstance(url, str) or not 1 <= len(url) <= 2048:
        raise ValueError('Invalid source URL')
    source = video_id(url)
    use = body['sourceUse']
    if (not isinstance(use, dict) or set(use) != {'decision', 'record'} or
            use['decision'] != 'approved-private-rvc-training' or
            not isinstance(use['record'], str) or
            not 1 <= len(use['record'].strip()) <= 3000 or
            any(ord(character) < 32 for character in use['record'])):
        raise ValueError('Explicit permission for private RVC training is required')
    normalized = dict(body, videoURL='https://www.youtube.com/watch?v=' + source,
                      sourceUse=dict(use, record=use['record'].strip()))
    _serialize(normalized)
    return normalized


def ensure_root(root, *, create=False):
    """Refuse unknown/F5 data or linked paths before opening any writable DB."""
    root = pathlib.Path(root).absolute()
    if root.resolve() != root or any(path.is_symlink() for path in (root, *root.parents)):
        raise ValueError('Linked RVC roots are unsupported')
    for ancestor in (root, *root.parents):
        if any((ancestor / name).exists() for name in ('collection.json', 'queue.db')):
            raise ValueError('Choose a separate RVC root; existing F5 data is preserved')
    marker = root / '.rvc-root.json'
    if not marker.exists():
        if not create or (root.exists() and any(root.iterdir())):
            raise ValueError('Choose a new empty private RVC root')
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            with marker.open('x', encoding='utf-8') as stream:
                json.dump(MARKER, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            pass
    if json.loads(read_bound(marker, 1024)) != MARKER:
        raise ValueError('RVC root marker is invalid')
    database = root / DATABASE
    if database.is_symlink() or database.resolve() != database:
        raise ValueError('Linked RVC databases are unsupported')
    return root


def load(db, identifier):
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='candidate_requests'").fetchone():
        raise ValueError('An F5 database cannot be used for RVC training')
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='rvc_requests'").fetchone():
        return None
    row = db.execute('SELECT body FROM rvc_requests WHERE video_id=?', (identifier,)).fetchone()
    if row is None:
        return None
    if not isinstance(row[0], str) or len(row[0].encode('utf-8')) > MAX_REQUEST_BYTES:
        raise ValueError('Saved RVC request exceeds its bound')
    body = validate(json.loads(row[0]))
    if video_id(body['videoURL']) != identifier:
        raise ValueError('Saved request does not match the queued source')
    return body


def submit(root, body):
    body = validate(body)
    identifier = video_id(body['videoURL'])
    root = ensure_root(root, create=True)
    queue = VideoQueue(str(root / DATABASE))
    try:
        queue.db.execute('BEGIN IMMEDIATE')
        queue.db.execute('CREATE TABLE IF NOT EXISTS rvc_requests '
                         '(video_id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, '
                         'body TEXT NOT NULL, created REAL NOT NULL)')
        queue.db.execute('CREATE TABLE IF NOT EXISTS rvc_request_ids '
                         '(request_id TEXT PRIMARY KEY, video_id TEXT NOT NULL)')
        repeated = queue.db.execute('SELECT video_id FROM rvc_request_ids WHERE request_id=?',
                                    (body['requestID'],)).fetchone()
        if repeated and repeated[0] != identifier:
            raise FileExistsError('Request identifier already belongs to another source')
        previous = load(queue.db, identifier)
        if previous is not None:
            if any(previous[key] != body[key] for key in ('videoURL', 'sourceUse', 'format')):
                raise FileExistsError('Existing RVC source-use scope was preserved')
        else:
            if queue.db.execute('SELECT 1 FROM jobs WHERE video_id=?', (identifier,)).fetchone():
                raise FileExistsError('Unscoped or existing work cannot become an RVC request')
            now = time.time()
            queue.db.execute('INSERT INTO jobs VALUES (?,?,?,?,?)',
                             (identifier, body['videoURL'], 'waiting', 0, now))
            queue.db.execute("INSERT INTO job_control VALUES (?,0,NULL,0,0,'')", (identifier,))
            append(queue.db, identifier, 'received', now=now)
            queue.db.execute('INSERT INTO rvc_requests VALUES (?,?,?,?)',
                             (identifier, body['requestID'], _serialize(body), now))
        queue.db.execute('INSERT OR IGNORE INTO rvc_request_ids VALUES (?,?)',
                         (body['requestID'], identifier))
        queue.db.commit()
        return dict(schemaVersion=1, accepted=True, videoID=identifier,
                    requestID=(previous or body)['requestID'], alreadyRequested=previous is not None,
                    format=FORMAT, identityVerified=False, likenessVerified=False,
                    nativeIPhoneRuntimeVerified=False)
    except BaseException:
        queue.db.rollback()
        raise
    finally:
        queue.close()
