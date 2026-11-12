"""Build-time-only, bounded staging of immutable Parakeet v3 CoreML assets.
No user audio, code execution, archive extraction, runtime downloads or cache purge.
"""
import contextlib
import hashlib
import json
import os
import pathlib
import re
import tempfile
import urllib.parse
import urllib.request
import zipfile

REVISION = '7dd20fe6b1797d35f5e3307e8b1732d9a178edfe'
REPOSITORY = 'FluidInference/parakeet-tdt-0.6b-v3-coreml'
BASE = f'https://huggingface.co/{REPOSITORY}/resolve/{REVISION}/'
LOCK = pathlib.Path(__file__).with_name('asr-resource-lock.json')
NOTICES = pathlib.Path(__file__).resolve().parents[1] / 'VoiceMatrix/Resources/ParakeetNotices'
CHUNK = 1_048_576


def entries(lock):
    files = lock.get('files', {})
    if not isinstance(files, dict) or not 1 <= len(files) <= 64:
        raise ValueError('Invalid ASR file count')
    total = 0
    for name, entry in files.items():
        if not isinstance(name, str) or '\\' in name or any(p in ('', '.', '..') for p in name.split('/')):
            raise ValueError('Unsafe ASR bundle path')
        size, digest = entry.get('size'), entry.get('sha256')
        if type(size) is not int or not 0 < size <= 650_000_000 or not isinstance(digest, str) or not re.fullmatch('[a-f0-9]{64}', digest):
            raise ValueError('Invalid ASR file bounds')
        total += size
        if total > 700_000_000: raise ValueError('ASR bundle exceeds byte limit')
    return files.items()


def safe_target(root, name):
    target = root.joinpath(*name.split('/'))
    for part in [target, *target.parents]:
        if part.is_symlink(): raise ValueError('Links are not ASR bundle files')
    return target


def digest_stream(stream, size, output=None):
    count = 0
    digest = hashlib.sha256()
    while True:
        chunk = stream.read(min(CHUNK, size - count + 1))
        if not chunk: break
        count += len(chunk)
        if count > size: raise ValueError('ASR asset exceeds pinned size')
        digest.update(chunk)
        if output is not None: output.write(chunk)
    if count != size: raise ValueError('ASR asset is truncated')
    return digest.hexdigest()


def stage(destination, lock, fetch):
    root = pathlib.Path(destination)
    for name, entry in entries(lock):
        target = safe_target(root, name)
        if target.exists():
            if not target.is_file() or target.stat().st_size != entry['size']: raise ValueError('Existing ASR asset differs; retained unchanged')
            with target.open('rb') as stream: digest = digest_stream(stream, entry['size'])
            if digest != entry['sha256']: raise ValueError('Existing ASR asset differs; retained unchanged')
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.asr-', suffix='.partial', delete=False) as output:
                temporary = pathlib.Path(output.name)
                with contextlib.closing(fetch(name)) as stream:
                    digest = digest_stream(stream, entry['size'], output)
                if digest != entry['sha256']: raise ValueError('Downloaded ASR asset hash mismatch')
                output.flush(); os.fsync(output.fileno())
            safe_target(root, name)
            os.link(temporary, target)  # Atomic exclusive publication; never replace a winner.
        finally:
            if temporary is not None: temporary.unlink(missing_ok=True)
    return root


def inspect_ipa(path, lock):
    prefix = 'Payload/VoiceMatrix.app/ParakeetASR/'
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)): raise ValueError('Duplicate archive entry')
        expected = {prefix + name for name, _ in entries(lock)} | {prefix + 'resource-lock.json'}
        actual = {name for name in names if name.startswith(prefix) and not name.endswith('/')}
        placeholder = prefix + '.gitkeep'
        if placeholder in actual:
            info = archive.getinfo(placeholder)
            if info.file_size != 0 or (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Invalid ASR placeholder')
            actual.remove(placeholder)
        if actual != expected: raise ValueError('Unexpected or missing ASR bundle file')
        for name, entry in entries(lock):
            info = archive.getinfo(prefix + name)
            if info.file_size != entry['size'] or (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Invalid packaged ASR asset')
            with archive.open(info) as stream:
                if digest_stream(stream, entry['size']) != entry['sha256']: raise ValueError('Packaged ASR hash differs')
        with archive.open(prefix + 'resource-lock.json') as stream:
            if stream.read(65_537) != LOCK.read_bytes(): raise ValueError('Packaged ASR lock differs')
        for filename in ('ATTRIBUTION.txt', 'CC-BY-4.0.txt', 'FluidAudio-APACHE-2.0.txt'):
            notice = (NOTICES / filename).read_bytes()
            name = 'Payload/VoiceMatrix.app/ParakeetNotices/' + filename
            if name not in names: raise ValueError('Missing ASR attribution or license notice')
            info = archive.getinfo(name)
            if info.file_size != len(notice) or (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Invalid ASR notice')
            with archive.open(info) as stream:
                if stream.read(len(notice) + 1) != notice: raise ValueError('ASR notice differs')
    return {'asrBundle': 'verified', 'files': len(lock['files']), 'modelRevision': REVISION}


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--destination', type=pathlib.Path, default=pathlib.Path('VoiceMatrix/Resources/ParakeetASR'))
    parser.add_argument('--inspect-ipa', type=pathlib.Path)
    args = parser.parse_args()
    raw = LOCK.read_bytes()
    if len(raw) > 65_536: raise ValueError('Oversized lock')
    lock = json.loads(raw)
    if lock.get('schemaVersion') != 1 or lock.get('repository') != REPOSITORY or lock.get('revision') != REVISION:
        raise ValueError('Wrong ASR lock identity')
    if args.inspect_ipa:
        print(json.dumps(inspect_ipa(args.inspect_ipa, lock))); return
    root = stage(args.destination, lock, lambda name: urllib.request.urlopen(BASE + urllib.parse.quote(name), timeout=90))
    target = safe_target(root, 'resource-lock.json')
    if target.exists():
        if target.read_bytes() != raw: raise ValueError('Existing lock differs; retained unchanged')
    else:
        with target.open('xb') as output: output.write(raw)
    print(json.dumps({'files': len(lock['files']), 'bytes': sum(x['size'] for x in lock['files'].values()), 'revision': REVISION}))

if __name__ == '__main__': main()
