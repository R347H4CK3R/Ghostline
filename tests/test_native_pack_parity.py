"""Synthetic transport regressions for the production iPhone importer contract."""
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import wave
import zipfile
from tools.voice_pack import export_reference_pack, validate_pack
from tools.master_voices import publish


class NativePackParityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.audio = self.root / 'reference.wav'
        with wave.open(str(self.audio), 'wb') as out:
            out.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
            out.writeframes(struct.pack('<h', 4000) * 24000)
        self.original = self.audio.read_bytes()
        self.metadata = dict(id='neutral', name='Neutral', source='Synthetic fixture',
                             permission='Original synthetic fixture', referenceText='Neutral words.', categories=['Test'])

    def pack(self, data):
        pack = export_reference_pack(self.audio, self.metadata, self.root / 'voice.vmpack')
        with zipfile.ZipFile(pack) as archive:
            manifest = json.loads(archive.read('manifest.json'))
        manifest.update(referenceSHA256=hashlib.sha256(data).hexdigest(), referenceBytes=len(data))
        with zipfile.ZipFile(pack, 'w') as archive:
            archive.writestr('manifest.json', json.dumps(manifest))
            archive.writestr('reference.wav', data)
        return pack

    def assert_rejected(self, data):
        pack = self.pack(data)
        with self.assertRaises(ValueError):
            validate_pack(pack)
        with self.assertRaises(ValueError):
            publish([pack], self.root / 'Voices')
        self.assertFalse((self.root / 'Voices' / 'collection.json').exists())

    def test_trailing_bytes_outside_riff_are_rejected(self):
        self.assert_rejected(self.original + b'ignored trailing bytes')

    def test_wrong_byte_rate_is_rejected(self):
        bad = bytearray(self.original)
        struct.pack_into('<I', bad, 28, 1)
        self.assert_rejected(bytes(bad))

    def test_wrong_block_alignment_is_rejected(self):
        bad = bytearray(self.original)
        struct.pack_into('<H', bad, 32, 1)
        self.assert_rejected(bytes(bad))

    def test_duplicate_data_chunk_is_rejected(self):
        bad = bytearray(self.original + self.original[36:])
        struct.pack_into('<I', bad, 4, len(bad) - 8)
        self.assert_rejected(bytes(bad))

    def test_duplicate_format_chunk_is_rejected(self):
        bad = bytearray(self.original + self.original[12:36])
        struct.pack_into('<I', bad, 4, len(bad) - 8)
        self.assert_rejected(bytes(bad))

    def test_data_before_format_remains_rejected_by_desktop_decoder_contract(self):
        reordered = self.original[:12] + self.original[36:] + self.original[12:36]
        self.assert_rejected(reordered)

    def test_incomplete_trailing_chunk_is_rejected(self):
        bad = bytearray(self.original + b'JUNK')
        struct.pack_into('<I', bad, 4, len(bad) - 8)
        self.assert_rejected(bytes(bad))

    def test_well_formed_padded_metadata_chunk_is_preserved(self):
        bad = bytearray(self.original + b'JUNK' + struct.pack('<I', 1) + b'x\x00')
        struct.pack_into('<I', bad, 4, len(bad) - 8)
        self.assertEqual(validate_pack(self.pack(bytes(bad)))['seconds'], 1.0)
