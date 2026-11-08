"""Build-time assets and fail-closed inspection for the no-stock listening candidate.

No publication, runtime downloads, private references or likeness approval.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import shutil
import stat
import struct
import subprocess
import re
import tempfile
import urllib.request
import unicodedata
import zipfile

HERE = Path(__file__).resolve().parent
MODEL_REPOSITORY = 'aufklarer/F5TTS-v1-Base-MLX-fp16'
MODEL_REVISION = '685e88161a2841a5f102a6f8094613ba7131e350'
RUNTIME_REVISION = 'a57702e6f523fa36ac5532d2bdc5f35f701a052c'
F5_FILES = json.loads((HERE / 'f5-listening-lock.json').read_text())
SOURCE_FILES = json.loads((HERE / 'no-stock-resource-lock.json').read_text())
BASE_FILES = {name: identity for name, identity in SOURCE_FILES.items() if name.startswith('OpenVoice/')}
LICENSE_FILES = ('F5-CC-BY-NC-4.0.txt', 'speech-swift-APACHE-2.0.txt', 'ATTRIBUTION.txt', 'pypinyin-MIT.txt', 'jieba-MIT.txt', 'vocos-MIT.txt')
BASELINE = {'size': 188361114, 'sha256': '716d2f4152f8372fe07f2bd0faabed8464a219df1bdf0a7131b5caa7ab9268e9'}
BASELINE_URL = 'https://github.com/R347H4CK3R/Ghostline/releases/download/voicematrix-v0.3.1-no-stock-9/VoiceMatrix-0.3.1.ipa'
PREFIX = 'Payload/VoiceMatrix.app/'


def verify_stream(stream, expected):
    digest = hashlib.sha256()
    size = 0
    while chunk := stream.read(1024 * 1024):
        size += len(chunk)
        if size > expected['size']:
            raise ValueError('Asset exceeds pinned size')
        digest.update(chunk)
    if size != expected['size'] or digest.hexdigest() != expected['sha256']:
        raise ValueError('Asset size or SHA-256 differs from pinned identity')


def verify_file(path, expected):
    if path.is_symlink() or not path.is_file():
        raise ValueError('Expected a regular asset file')
    with path.open('rb') as stream:
        verify_stream(stream, expected)


def download_verified(url, destination, expected):
    """Do not replace an existing cached asset until new bytes fully verify."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise ValueError('Refusing symlink destination')
    if destination.exists():
        try:
            verify_file(destination, expected)
            return
        except ValueError:
            pass
    fd, temporary = tempfile.mkstemp(prefix='.download-', dir=destination.parent)
    try:
        with os.fdopen(fd, 'wb') as target, urllib.request.urlopen(url, timeout=60) as source:
            size = 0
            while chunk := source.read(1024 * 1024):
                size += len(chunk)
                if size > expected['size']:
                    raise ValueError('Download exceeds pinned size')
                target.write(chunk)
        verify_file(Path(temporary), expected)
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)


def engine_proof(files):
    return {'schemaVersion': 1, 'engine': 'F5TTS_v1_Base',
            'runtimeRevision': RUNTIME_REVISION, 'modelRepository': MODEL_REPOSITORY,
            'modelRevision': MODEL_REVISION,
            'files': [dict(path=name, **entry) for name, entry in sorted(files.items())]}


def checked_names(archive):
    names = [entry.filename for entry in archive.infolist()]
    normalized = [unicodedata.normalize('NFC', name).casefold().rstrip('/') for name in names]
    if len(names) != len(set(normalized)):
        raise ValueError('Duplicate archive paths')
    for entry in archive.infolist():
        path = PurePosixPath(entry.filename)
        if path.is_absolute() or '..' in path.parts or '\\' in entry.filename:
            raise ValueError('Unsafe archive path')
        if stat.S_ISLNK(entry.external_attr >> 16):
            raise ValueError('Symlink archive entry')
    return set(names)


def json_entry(archive, name):
    if archive.getinfo(name).file_size > 2_000_000:
        raise ValueError('Oversized metadata')
    return json.loads(archive.read(name))


def verify_entry(archive, name, expected):
    if archive.getinfo(name).file_size != expected['size']:
        raise ValueError('Archive asset size differs from pin: ' + name)
    with archive.open(name) as stream:
        verify_stream(stream, expected)


def check_baseline_inventory(archive, names, expected):
    actual = {name.removeprefix(PREFIX) for name in names
              if name.startswith(PREFIX) and name.removeprefix(PREFIX).split('/')[0].casefold() in ('phonon','openvoice') and not name.endswith('/')}
    if actual != set(expected):
        raise ValueError('Baseline engine resource inventory differs from verified no-stock build')
    for name, identity in expected.items():
        verify_entry(archive, PREFIX+name, identity)


def check_no_stock(archive, names):
    manifest = json_entry(archive, PREFIX + 'Phonon/manifest.json') if PREFIX + 'Phonon/manifest.json' in names else {'voices':[], 'files':[]}
    converter = json_entry(archive, PREFIX + 'OpenVoice/model-manifest.json')
    if manifest.get('voices') != []:
        raise ValueError('Stock voices remain in manifest')
    for name in names:
        if name.startswith((PREFIX+'Phonon/voices/', PREFIX+'OpenVoice/Profiles/')) and not name.endswith('/'):
            raise ValueError('Stock profile payload remains: ' + name)
    for folder, document in [('Phonon/', manifest), ('OpenVoice/', converter)]:
        for entry in document['files']:
            path = PurePosixPath(entry['path'])
            if path.is_absolute() or '..' in path.parts or '\\' in entry['path']:
                raise ValueError('Unsafe manifest path')
            verify_entry(archive, PREFIX + folder + entry['path'], entry)


def prepare_resources(cache, destination, include_f5=True):
    """Stage verified build inputs in a new directory; never touch app user data."""
    cache, destination = Path(cache), Path(destination)
    if destination.exists():
        raise ValueError('Use a new staging resource directory')
    cache.mkdir(parents=True, exist_ok=True)
    baseline = cache / 'no-stock-build9.ipa'
    download_verified(BASELINE_URL, baseline, BASELINE)
    if include_f5:
        for name, expected in F5_FILES.items():
            url = f'https://huggingface.co/{MODEL_REPOSITORY}/resolve/{MODEL_REVISION}/{name}'
            download_verified(url, cache / 'f5' / name, expected)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.listening-stage-', dir=destination.parent) as temporary:
        stage = Path(temporary)
        with zipfile.ZipFile(baseline) as archive:
            names = checked_names(archive)
            check_baseline_inventory(archive, names, SOURCE_FILES)
            check_no_stock(archive, names)
            for name in sorted(names):
                relative = name.removeprefix(PREFIX)
                if not name.startswith(PREFIX) or not relative.startswith('OpenVoice/') or name.endswith('/'):
                    continue
                target = stage / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(name) as source, target.open('wb') as output:
                    shutil.copyfileobj(source, output)
        (stage / 'Phonon').mkdir()
        model = stage / 'F5TTS'
        model.mkdir()
        if include_f5:
            for name in F5_FILES:
                shutil.copyfile(cache / 'f5' / name, model / name)
            (model / 'voicematrix-engine.json').write_text(json.dumps(engine_proof(F5_FILES), indent=2)+'\n')
        notices = model / 'Notices'
        notices.mkdir()
        for name in LICENSE_FILES:
            shutil.copyfile(HERE / 'listening_licenses' / name, notices / name)
        os.replace(stage, destination)
    return {'stockProfiles': 0, 'f5AssetBytes': sum(x['size'] for x in F5_FILES.values()) if include_f5 else 0,
            'modelRevision': MODEL_REVISION, 'license': 'CC-BY-NC-4.0', 'nativeExecutionVerified': False}



def collect_dependency_notices(checkouts, resolved, resources):
    """Capture notices from the actual resolved source trees, before native build."""
    checkouts, resolved = Path(checkouts), Path(resolved)
    target = Path(resources) / 'F5TTS' / 'DependencyNotices'
    if target.exists():
        raise ValueError('Use a clean dependency-notice destination')
    pins = json.loads(resolved.read_text())['pins']
    if not pins:
        raise ValueError('Missing resolved dependencies')
    directories = {p.name.casefold():p for p in checkouts.iterdir() if p.is_dir() and not p.is_symlink()}
    target.mkdir(parents=True)
    shutil.copyfile(resolved, target/'Package.resolved')
    for pin in pins:
        identity = pin['identity']
        if not re.fullmatch(r'[a-zA-Z0-9_.-]+', identity):
            raise ValueError('Unsafe dependency identity')
        source = directories.get(identity.casefold())
        if source is None:
            raise ValueError('Missing dependency checkout: '+identity)
        actual = subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
        if actual != pin['state']['revision']:
            raise ValueError('Resolved dependency checkout differs: '+identity)
        if subprocess.check_output(['git','-C',str(source),'status','--porcelain','--untracked-files=all','--ignore-submodules=none'],text=True).strip():
            raise ValueError('Dependency checkout is not clean: '+identity)
        count = 0
        tracked = subprocess.check_output(['git','-C',str(source),'ls-files','--recurse-submodules','-z']).decode().split('\0')
        for name in sorted(filter(None,tracked)):
            relative = Path(name)
            path = source / relative
            is_notice = re.match(r'^(LICENSE|LICENCE|NOTICE|COPYING|COPYRIGHT|THIRD[-_]PARTY[-_]NOTICES)([._-].*)?$',path.name,re.I)
            in_notice_folder = any(part.casefold() in ('licenses','licences','notices') for part in relative.parts[:-1])
            if '.git' in relative.parts or not (is_notice or in_notice_folder) or path.is_dir():
                continue
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 4_000_000:
                raise ValueError('Unsupported dependency notice: '+str(relative))
            destination = target / identity / relative
            destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(path,destination)
            count += 1
        if count == 0:
            raise ValueError('Dependency has no captured license or notice: '+identity)
    inventory = {}
    for path in sorted(target.rglob('*')):
        if path.is_file():
            with path.open('rb') as stream:
                digest=hashlib.file_digest(stream,'sha256').hexdigest()
            inventory[path.relative_to(target).as_posix()]={'size':path.stat().st_size,'sha256':digest}
    proof={'schemaVersion':1,'files':inventory}
    (target.parent/'dependency-notices.json').write_text(json.dumps(proof,indent=2)+'\n')
    return {'dependencies':len(pins),'noticeFiles':len(inventory)-1,'proof':proof}


def check_dependency_notices(archive, expected):
    proof=json_entry(archive,PREFIX+'F5TTS/dependency-notices.json')
    if expected is None or proof != expected:
        raise ValueError('Dependency notice inventory differs from external build evidence')
    if proof.get('schemaVersion') != 1 or not isinstance(proof.get('files'),dict) or len(proof['files']) < 2:
        raise ValueError('Missing dependency license inventory')
    for name, expected in proof['files'].items():
        path=PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or '\\' in name:
            raise ValueError('Unsafe dependency notice path')
        verify_entry(archive,PREFIX+'F5TTS/DependencyNotices/'+name,expected)
    resolved=json_entry(archive,PREFIX+'F5TTS/DependencyNotices/Package.resolved')
    pins=resolved.get('pins',[])
    runtime=next((pin for pin in pins if pin.get('identity')=='speech-swift'),None)
    if runtime is None or runtime.get('state',{}).get('revision') != RUNTIME_REVISION:
        raise ValueError('Wrong resolved speech runtime')
    for pin in pins:
        if not any(name.startswith(pin['identity']+'/') for name in proof['files']):
            raise ValueError('Dependency lacks captured license notices')
    return {'DependencyNotices/'+name for name in proof['files']} | {'dependency-notices.json'}

def inspect_ipa(path, files=None, base_files=None, dependency_proof=None):
    """Default pins are trusted repository data, never the archive's own proof."""
    files = F5_FILES if files is None else files
    base_files = BASE_FILES if base_files is None else base_files
    try:
        with zipfile.ZipFile(path) as archive:
            names = checked_names(archive)
            if archive.testzip() is not None:
                raise ValueError('Corrupt archive')
            if archive.getinfo(PREFIX+'Info.plist').file_size > 1_000_000:
                raise ValueError('Oversized Info.plist')
            info = plistlib.loads(archive.read(PREFIX+'Info.plist'))
            if (info.get('CFBundleIdentifier'), info.get('CFBundleShortVersionString'), info.get('CFBundleVersion')) != ('com.voicematrix.app','0.4.2','1'):
                raise ValueError('Unexpected listening-candidate app identity')
            if tuple(map(int, info['MinimumOSVersion'].split('.'))) < (26,0):
                raise ValueError('Unexpected deployment target')
            executable = info['CFBundleExecutable']
            if PurePosixPath(executable).name != executable:
                raise ValueError('Unsafe executable path')
            with archive.open(PREFIX+executable) as stream:
                header = stream.read(32)
            if len(header) != 32 or header[:4] != b'\xcf\xfa\xed\xfe' or struct.unpack_from('<I',header,4)[0] != 0x100000c:
                raise ValueError('Not an ARM64 Mach-O executable')
            if PREFIX+'Assets.car' not in names:
                raise ValueError('Missing app icons')
            shader = PREFIX+'mlx-swift_Cmlx.bundle/default.metallib'
            if shader not in names or archive.getinfo(shader).file_size < 1024:
                raise ValueError('Missing compiled speech shader library')
            with archive.open(shader) as stream:
                if stream.read(4) != b'MTLB':raise ValueError('Invalid compiled speech shader library')
            settings = json_entry(archive, PREFIX + 'LaptopSettings.json')
            from urllib.parse import urlsplit
            if set(settings) != {'url','authentication'} or settings.get('authentication') != 'tailscale-same-account':
                raise ValueError('Only nonsecret same-account connection settings may be bundled')
            address = urlsplit(settings['url'])
            if address.scheme != 'https' or address.username or address.password or address.query or address.fragment or not (address.hostname or '').endswith('.ts.net'):
                raise ValueError('Unexpected or credential-bearing laptop address')
            check_baseline_inventory(archive, names, base_files)
            check_no_stock(archive, names)
            for name in names:
                if not name.endswith('/') and (PurePosixPath(name).suffix.casefold() in ('.wav','.aiff','.aif','.mp3','.m4a','.flac','.ogg','.vmpack','.pth') or PurePosixPath(name).name.casefold() in ('collection.json','voicematrix-pairing.json')):
                    raise ValueError('Private/reference audio or character pack is forbidden in candidate')
            proof = json_entry(archive, PREFIX+'F5TTS/voicematrix-engine.json')
            if proof != engine_proof(files):
                raise ValueError('F5 proof differs from pinned bundle identity')
            dependency_files = check_dependency_notices(archive, dependency_proof)
            allowed = dependency_files | set(files) | {'voicematrix-engine.json'} | {'Notices/'+name for name in LICENSE_FILES}
            for name in names:
                if name.startswith(PREFIX+'F5TTS/') and not name.endswith('/') and name.removeprefix(PREFIX+'F5TTS/') not in allowed:
                    raise ValueError('Unapproved F5 payload; placeholders and private references are forbidden')
            for name, expected in files.items():
                verify_entry(archive, PREFIX+'F5TTS/'+name, expected)
            for name in LICENSE_FILES:
                expected = (HERE/'listening_licenses'/name).read_bytes()
                verify_entry(archive, PREFIX+'F5TTS/Notices/'+name,
                             {'size':len(expected),'sha256':hashlib.sha256(expected).hexdigest()})
        return {'archive':'passed','compiledSpeechShaders':True,'version':'0.4.2','build':'1','bundleIdentifier':'com.voicematrix.app','runtimeRevision':RUNTIME_REVISION,'stockProfiles':0,'f5AssetBytes':sum(x['size'] for x in files.values()),
                'modelRevision':MODEL_REVISION,'physicalIPhoneVerified':False,'characterLikenessVerified':False}
    except (KeyError, zipfile.BadZipFile, json.JSONDecodeError, plistlib.InvalidFileException) as error:
        raise ValueError('Incomplete or invalid listening archive') from error


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    stage=sub.add_parser('prepare');stage.add_argument('--cache',required=True);stage.add_argument('--resources',required=True);stage.add_argument('--skip-f5',action='store_true')
    inspect=sub.add_parser('inspect');inspect.add_argument('ipa');inspect.add_argument('--dependency-proof',required=True)
    notices=sub.add_parser('notices');notices.add_argument('--checkouts',required=True);notices.add_argument('--resolved',required=True);notices.add_argument('--resources',required=True)
    args=parser.parse_args()
    if args.command=='prepare':result=prepare_resources(args.cache,args.resources,include_f5=not args.skip_f5)
    elif args.command=='notices':result=collect_dependency_notices(args.checkouts,args.resolved,args.resources)
    else:result=inspect_ipa(args.ipa,dependency_proof=json.loads(Path(args.dependency_proof).read_text())['proof'])
    print(json.dumps(result,indent=2))
