"""Create a synthetic WAV corpus shared by Python and production Swift checks."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import wave
import zipfile
from tools.voice_pack import export_reference_pack, validate_pack

def prepare(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    audio = root / 'neutral.wav'
    with wave.open(str(audio), 'wb') as writer:
        writer.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        writer.writeframes(struct.pack('<h', 4000) * 24000)
    original = audio.read_bytes()
    metadata = dict(id='neutral', name='Neutral', source='Synthetic fixture', permission='Original synthetic fixture', referenceText='Neutral words.', categories=['Test'])
    pack = export_reference_pack(audio, metadata, root / 'neutral.vmpack')
    with zipfile.ZipFile(pack) as archive:
        manifest = json.loads(archive.read('manifest.json'))
    def riff_append(extra):
        data = bytearray(original + extra)
        struct.pack_into('<I', data, 4, len(data) - 8)
        return bytes(data)
    rate = bytearray(original); struct.pack_into('<I', rate, 28, 1)
    alignment = bytearray(original); struct.pack_into('<H', alignment, 32, 1)
    corpus = {
        'valid': (original, True),
        'padded-metadata': (riff_append(b'JUNK' + struct.pack('<I', 1) + b'x\0'), True),
        'trailing-bytes': (original + b'unindexed bytes', False),
        'wrong-byte-rate': (bytes(rate), False),
        'wrong-alignment': (bytes(alignment), False),
        'duplicate-data': (riff_append(original[36:]), False),
        'duplicate-format': (riff_append(original[12:36]), False),
        'incomplete-chunk': (riff_append(b'JUNK'), False),
        'missing-padding': (riff_append(b'JUNK' + struct.pack('<I', 1) + b'x'), False),
    }
    expected = {}
    for name, (data, valid) in corpus.items():
        folder = root / name / 'neutral'
        folder.mkdir(parents=True, exist_ok=True)
        record = dict(manifest, referenceBytes=len(data), referenceSHA256=hashlib.sha256(data).hexdigest())
        (folder / 'reference.wav').write_bytes(data)
        (folder / 'manifest.json').write_text(json.dumps(record), encoding='utf-8')
        (folder.parent / 'collection.json').write_text(json.dumps(dict(schemaVersion=1, voices=[dict(id='neutral', folder='neutral')])), encoding='utf-8')
        candidate = root / (name + '.vmpack')
        with zipfile.ZipFile(candidate, 'w') as archive:
            archive.writestr('manifest.json', json.dumps(record))
            archive.writestr('reference.wav', data)
        try:
            validate_pack(candidate)
            accepted = True
        except ValueError:
            accepted = False
        assert accepted == valid, name
        expected[name] = valid
    (root / 'expected.json').write_text(json.dumps(expected), encoding='utf-8')
    print('Python corpus: 2 valid accepted, 7 malformed rejected')

if __name__ == '__main__':
    prepare(sys.argv[1])
