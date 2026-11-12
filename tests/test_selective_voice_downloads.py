"""Catalog contract regression and native selective download checks."""
import json, pathlib, shutil, subprocess, sys, tempfile, unittest, wave
from tools.private_voices import PrivateVoices, TransferError
from tools.voice_pack import export_reference_pack, export_collection_folder
ROOT=pathlib.Path(__file__).resolve().parents[1]

class SelectiveCatalogTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name);packs=[]
  for index in range(2):
   audio=self.root/f'{index}.wav'
   with wave.open(str(audio),'wb') as out:
    out.setparams((1,2,24000,0,'NONE','not compressed'));out.writeframes(bytes([index,16])*24000)
   meta=dict(id=f'voice-{index}',name=f'Voice {index}',categories=['Original & Comedy'],source='Synthetic fixture',permission='Synthetic local test',referenceText='A test reference sentence.')
   packs.append(export_reference_pack(audio,meta,self.root/f'{index}.vmpack'))
  self.folder=export_collection_folder(packs,self.root/'Voices');self.source=PrivateVoices(self.folder)
 def tearDown(self):self.tmp.cleanup()
 def test_catalog_contains_validated_browse_metadata_without_audio_payloads(self):
  catalog=self.source.catalog()
  self.assertIn('voices',catalog,'Catalog must expose metadata for browsing without reference downloads')
  self.assertEqual([x['id'] for x in catalog['voices']],['voice-0','voice-1'])
  for voice in catalog['voices']:
   self.assertEqual(voice,json.loads((self.folder/voice['id']/'manifest.json').read_text()))
   self.assertNotIn('audio',voice)
  self.assertLess(len(json.dumps(catalog).encode()),1048576)
 def test_download_one_voice_does_not_require_other_voice_requests(self):
  catalog=self.source.catalog();self.assertIn('voices',catalog)
  paths=['voice-1/manifest.json','voice-1/reference.wav']
  for path in paths:
   self.assertEqual(self.source.file(catalog['revision'],path),(self.folder/path).read_bytes())
  # No mutable /download operation or accidental source removal.
  self.assertTrue((self.folder/'voice-0/reference.wav').is_file())
 def test_metadata_is_not_returned_when_its_reference_is_corrupt(self):
  (self.folder/'voice-0/reference.wav').write_bytes(b'broken')
  with self.assertRaises(TransferError):self.source.catalog()
 def test_browse_response_has_a_bounded_total_size(self):
  # Individually valid manifests may still exceed the phone's catalog cap.
  import unittest.mock
  with unittest.mock.patch('tools.private_voices.CATALOG_BYTE_LIMIT',64,create=True):
   with self.assertRaises(TransferError) as caught:self.source.catalog()
  self.assertEqual(caught.exception.status,413)
 def test_native_selective_download_contract(self):
  sources=[ROOT/'VoiceMatrix/CharacterFolderStore.swift',ROOT/'VoiceMatrix/VoiceSyncLog.swift',ROOT/'VoiceMatrix/VoiceFolderSync.swift',ROOT/'VoiceMatrix/RemoteVoiceCatalog.swift',ROOT/'tests/native/SelectiveVoiceDownloadChecks.swift']
  for path in sources:self.assertTrue(path.is_file(),f'Missing selective-download implementation: {path.name}')
  if sys.platform != 'darwin' or not shutil.which('swiftc'):self.skipTest('Apple Swift/CryptoKit unavailable; native checks require Apple CI')
  fixture=self.root/'catalog.json';fixture.write_text(json.dumps(self.source.catalog()))
  binary=self.root/'checks'
  subprocess.run(['swiftc','-parse-as-library',*map(str,sources),'-o',str(binary)],check=True,capture_output=True,text=True,timeout=120)
  result=subprocess.run([str(binary),str(fixture),str(self.folder)],check=True,capture_output=True,text=True,timeout=30)
  self.assertIn('Selective voice download checks passed',result.stdout)
