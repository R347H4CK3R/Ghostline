import hashlib
import importlib.util
import json
from pathlib import Path
import plistlib
import struct
import subprocess
from unittest import mock
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]

class CharacterPackageTests(unittest.TestCase):
    def setUp(self):
        module_path = ROOT / 'tools/character_package.py'
        self.assertTrue(module_path.exists(), 'Dedicated no-stock F5 package gate is required')
        spec = importlib.util.spec_from_file_location('character_package', module_path)
        self.module = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.module)
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.files = {name: {'size': len(name.encode()), 'sha256': hashlib.sha256(name.encode()).hexdigest()}
                      for name in self.module.F5_FILES}
        self.entries = {
            'Info.plist': plistlib.dumps({'CFBundleIdentifier':'com.voicematrix.app',
                'CFBundleExecutable':'VoiceMatrix','CFBundleShortVersionString':'0.4.1',
                'CFBundleVersion':'1','MinimumOSVersion':'26.0'}),
            'VoiceMatrix': b'\xcf\xfa\xed\xfe'+struct.pack('<I',0x100000c)+b'\0'*24,
            'Assets.car': b'icon',
            'mlx-swift_Cmlx.bundle/default.metallib': b'MTLB'+b'\0'*1024,
            'Phonon/manifest.json': json.dumps({'voices':[],'files':[]}).encode(),
            'OpenVoice/model-manifest.json': json.dumps({'files':[]}).encode(),
        }
        self.entries['LaptopSettings.json']=json.dumps({'url':'https://laptop.example.ts.net:9443/','authentication':'tailscale-same-account'}).encode()
        self.base_files = {name: {'size':len(data),'sha256':hashlib.sha256(data).hexdigest()} for name,data in self.entries.items() if name.startswith(('Phonon/','OpenVoice/'))}
        self.entries.update({'F5TTS/'+name:name.encode() for name in self.files})
        self.entries['F5TTS/voicematrix-engine.json'] = json.dumps(self.module.engine_proof(self.files)).encode()
        for name in self.module.LICENSE_FILES:
            self.entries['F5TTS/Notices/'+name] = (ROOT/'tools/listening_licenses'/name).read_bytes()

        resolved=json.dumps({'pins':[{'identity':'speech-swift','state':{'revision':self.module.RUNTIME_REVISION}}]}).encode()
        license_bytes=b'fixture dependency license'
        self.entries['F5TTS/DependencyNotices/Package.resolved']=resolved
        self.entries['F5TTS/DependencyNotices/speech-swift/LICENSE']=license_bytes
        inventory={name.removeprefix('F5TTS/DependencyNotices/'):{'size':len(data),'sha256':hashlib.sha256(data).hexdigest()}
                   for name,data in self.entries.items() if name.startswith('F5TTS/DependencyNotices/')}
        self.dependency_proof={'schemaVersion':1,'files':inventory}
        self.entries['F5TTS/dependency-notices.json']=json.dumps(self.dependency_proof).encode()

    def archive(self):
        path=self.root/'test.ipa'
        with zipfile.ZipFile(path,'w') as z:
            for name,data in self.entries.items(): z.writestr('Payload/VoiceMatrix.app/'+name,data)
        return path

    def test_complete_no_stock_artifact_passes_with_explicit_unverified_device_status(self):
        result=self.module.inspect_ipa(self.archive(), self.files, self.base_files, self.dependency_proof)
        self.assertEqual(result['stockProfiles'],0)
        self.assertEqual(result['f5AssetBytes'],sum(f['size'] for f in self.files.values()))
        self.assertFalse(result['physicalIPhoneVerified'])
        self.assertFalse(result['characterLikenessVerified'])

    def test_explicit_build_identity_rejects_reused_package(self):
        with self.assertRaises(ValueError):
            self.module.inspect_ipa(self.archive(),self.files,self.base_files,self.dependency_proof,expected_build='2')
        info=plistlib.loads(self.entries['Info.plist']);info['CFBundleVersion']='2'
        self.entries['Info.plist']=plistlib.dumps(info)
        with self.assertRaises(ValueError):
            self.module.inspect_ipa(self.archive(),self.files,self.base_files,self.dependency_proof)
        result=self.module.inspect_ipa(self.archive(),self.files,self.base_files,self.dependency_proof,expected_build='2')
        self.assertEqual(result['build'],'2')

    def test_missing_or_tampered_f5_asset_fails(self):
        name='F5TTS/model.safetensors'
        for replacement in [None,b'tampered']:
            with self.subTest(replacement=replacement):
                original=self.entries.pop(name)
                if replacement is not None:self.entries[name]=replacement
                with self.assertRaises(ValueError):self.module.inspect_ipa(self.archive(),self.files,self.base_files,self.dependency_proof)
                self.entries[name]=original

    def test_self_signed_forged_proof_does_not_override_pinned_hash(self):
        self.entries['F5TTS/model.safetensors']=b'fake'
        proof=json.loads(self.entries['F5TTS/voicematrix-engine.json'])
        row=next(f for f in proof['files'] if f['path']=='model.safetensors')
        row.update(size=4,sha256=hashlib.sha256(b'fake').hexdigest())
        self.entries['F5TTS/voicematrix-engine.json']=json.dumps(proof).encode()
        with self.assertRaises(ValueError):self.module.inspect_ipa(self.archive(),self.files,self.base_files,self.dependency_proof)

    def test_stock_or_private_reference_payload_is_rejected(self):
        for name in ['Phonon/voices/stock.json','OpenVoice/Profiles/stock.json','F5TTS/reference.wav']:
            with self.subTest(name=name):
                self.entries[name]=b'not allowed'
                with self.assertRaises(ValueError):self.module.inspect_ipa(self.archive(),self.files,self.base_files,self.dependency_proof)
                del self.entries[name]
        self.entries['Phonon/manifest.json']=json.dumps({'voices':[{'id':'stock'}],'files':[]}).encode()
        with self.assertRaises(ValueError):self.module.inspect_ipa(self.archive(),self.files,self.base_files,self.dependency_proof)

    def test_bundled_private_pairing_token_is_rejected(self):
        self.entries['LaptopSettings.json']=json.dumps({'url':'https://laptop.example.ts.net:9443/','authentication':'tailscale-same-account','token':'not-a-real-secret-fixture'}).encode()
        with self.assertRaises(ValueError):self.module.inspect_ipa(self.archive(),self.files,self.base_files,self.dependency_proof)

    def test_missing_or_modified_license_is_rejected(self):
        name='F5TTS/Notices/'+self.module.LICENSE_FILES[0]
        self.entries[name]=b'wrong license'
        with self.assertRaises(ValueError):self.module.inspect_ipa(self.archive(),self.files,self.base_files,self.dependency_proof)

    def test_duplicate_and_traversal_archive_names_are_rejected(self):
        import warnings
        path=self.archive()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',UserWarning)
            with zipfile.ZipFile(path,'a') as z:z.writestr('Payload/VoiceMatrix.app/Assets.car',b'duplicate')
        with self.assertRaises(ValueError):self.module.inspect_ipa(path,self.files,self.base_files,self.dependency_proof)
        self.entries['../../escaped']=b'escape'
        with self.assertRaises(ValueError):self.module.inspect_ipa(self.archive(),self.files,self.base_files,self.dependency_proof)

    def test_missing_dependency_notice_or_resolved_proof_fails(self):
        for name in ['F5TTS/dependency-notices.json','F5TTS/DependencyNotices/speech-swift/LICENSE','F5TTS/DependencyNotices/Package.resolved']:
            original=self.entries.pop(name)
            with self.assertRaises(ValueError):self.module.inspect_ipa(self.archive(),self.files,self.base_files,self.dependency_proof)
            self.entries[name]=original

    def test_wrong_architecture_or_placeholder_fails(self):
        self.entries['VoiceMatrix']=b'not ARM64'
        with self.assertRaises(ValueError):self.module.inspect_ipa(self.archive(),self.files,self.base_files,self.dependency_proof)

    def test_rewritten_baseline_manifest_cannot_hide_missing_engine(self):
        self.entries['Phonon/manifest.json']=json.dumps({'voices':[],'files':[], 'forged':True}).encode()
        with self.assertRaises(ValueError):self.module.inspect_ipa(self.archive(),self.files,self.base_files,self.dependency_proof)

    def test_private_or_case_variant_resource_outside_f5_is_rejected(self):
        for name in ['PrivateReferences/reference.wav','OpenVoice/reference.wav','Phonon/Voices/stock.json']:
            with self.subTest(name=name):
                self.entries[name]=b'private'
                with self.assertRaises(ValueError):self.module.inspect_ipa(self.archive(),self.files,self.base_files,self.dependency_proof)
                del self.entries[name]

    def test_download_rejects_bad_hash_and_does_not_replace_existing_file(self):
        destination=self.root/'model'
        destination.write_bytes(b'existing')
        source=self.root/'source';source.write_bytes(b'invalid')
        with self.assertRaises(ValueError):
            self.module.download_verified(source.as_uri(),destination,{'size':7,'sha256':'0'*64})
        self.assertEqual(destination.read_bytes(),b'existing')

    def test_prepare_stages_exact_resources_and_refuses_existing_destination(self):
        baseline=self.archive()
        baseline_bytes=baseline.read_bytes()
        baseline_identity={'size':len(baseline_bytes),'sha256':hashlib.sha256(baseline_bytes).hexdigest()}
        assets=self.root/'assets';assets.mkdir()
        for name in self.files:(assets/name).write_bytes(name.encode())
        original_download=self.module.download_verified
        def local_download(url,destination,expected):
            if str(destination).endswith('no-stock-build9.ipa'):source=baseline
            else:source=assets/Path(destination).name
            return original_download(source.as_uri(),destination,expected)
        output=self.root/'staged'
        with mock.patch.object(self.module,'BASELINE',baseline_identity), mock.patch.object(self.module,'SOURCE_FILES',self.base_files), mock.patch.object(self.module,'F5_FILES',self.files), mock.patch.object(self.module,'download_verified',side_effect=local_download):
            self.module.prepare_resources(self.root/'cache',output)
            self.assertEqual((output/'F5TTS/model.safetensors').read_bytes(),b'model.safetensors')
            self.assertFalse((output/'Phonon/manifest.json').exists(), 'Unused Phonon engine must not enter the character build')
            self.assertEqual(json.loads((output/'F5TTS/voicematrix-engine.json').read_text()),self.module.engine_proof(self.files))
            for name in self.module.LICENSE_FILES:self.assertTrue((output/'F5TTS/Notices'/name).is_file())
            with self.assertRaises(ValueError):self.module.prepare_resources(self.root/'cache',output)

    def test_conversion_only_staging_does_not_fetch_or_install_f5_weights(self):
        baseline=self.archive();data=baseline.read_bytes()
        identity={'size':len(data),'sha256':hashlib.sha256(data).hexdigest()}
        original_download=self.module.download_verified
        def local_download(url,destination,expected):
            return original_download(baseline.as_uri(),destination,expected)
        output=self.root/'conversion-resources'
        with mock.patch.object(self.module,'BASELINE',identity), mock.patch.object(self.module,'SOURCE_FILES',self.base_files), mock.patch.object(self.module,'download_verified',side_effect=local_download):
            self.module.prepare_resources(self.root/'conversion-cache',output,include_f5=False)
        self.assertFalse((output/'F5TTS/model.safetensors').exists())
        self.assertFalse((output/'Phonon/manifest.json').exists())
        self.assertTrue((output/'OpenVoice/model-manifest.json').is_file())

    def test_dependency_collection_records_actual_revision_and_nested_notices(self):
        checkouts=self.root/'checkouts';source=checkouts/'example';source.mkdir(parents=True)
        (source/'LICENSE').write_text('Example source license')
        (source/'LICENSES').mkdir();(source/'LICENSES/MIT.txt').write_text('Nested dependency license')
        for command in [['git','init','-q'],['git','add','.'],['git','-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','Fixture']]:
            subprocess.run(command,cwd=source,check=True,capture_output=True)
        revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()
        resolved=self.root/'Package.resolved';resolved.write_text(json.dumps({'pins':[{'identity':'example','state':{'revision':revision}}]}))
        resources=self.root/'resources'
        result=self.module.collect_dependency_notices(checkouts,resolved,resources)
        self.assertEqual(result['dependencies'],1)
        self.assertEqual(result['noticeFiles'],2)
        inventory=json.loads((resources/'F5TTS/dependency-notices.json').read_text())['files']
        self.assertIn('example/LICENSES/MIT.txt',inventory)
        (source/'LICENSE').write_text('modified license')
        with self.assertRaises(ValueError):self.module.collect_dependency_notices(checkouts,resolved,self.root/'dirty-resources')
        resolved.write_text(json.dumps({'pins':[{'identity':'example','state':{'revision':'0'*40}}]}))
        with self.assertRaises(ValueError):self.module.collect_dependency_notices(checkouts,resolved,self.root/'wrong-resources')

    def test_rewritten_dependency_inventory_cannot_override_external_evidence(self):
        name='speech-swift/LICENSE'
        self.entries['F5TTS/DependencyNotices/'+name]=b'forged notice'
        proof=json.loads(self.entries['F5TTS/dependency-notices.json'])
        proof['files'][name]={'size':13,'sha256':hashlib.sha256(b'forged notice').hexdigest()}
        self.entries['F5TTS/dependency-notices.json']=json.dumps(proof).encode()
        with self.assertRaises(ValueError):self.module.inspect_ipa(self.archive(),self.files,self.base_files,self.dependency_proof)

    def test_missing_external_dependency_evidence_is_not_accepted(self):
        with self.assertRaises(ValueError):self.module.inspect_ipa(self.archive(),self.files,self.base_files)

    def test_symlink_and_case_collisions_fail(self):
        path=self.archive()
        with zipfile.ZipFile(path,'a') as archive:
            entry=zipfile.ZipInfo('Payload/VoiceMatrix.app/symlink')
            entry.create_system=3;entry.external_attr=0o120777 << 16
            archive.writestr(entry,'Info.plist')
        with self.assertRaises(ValueError):self.module.inspect_ipa(path,self.files,self.base_files,self.dependency_proof)
        self.entries['info.plist']=self.entries['Info.plist']
        with self.assertRaises(ValueError):self.module.inspect_ipa(self.archive(),self.files,self.base_files,self.dependency_proof)

    def test_download_accepts_exact_bytes(self):
        source=self.root/'source';source.write_bytes(b'exact')
        destination=self.root/'model'
        self.module.download_verified(source.as_uri(),destination,{'size':5,'sha256':hashlib.sha256(b'exact').hexdigest()})
        self.assertEqual(destination.read_bytes(),b'exact')


    def test_missing_compiled_speech_shader_is_rejected(self):
        self.entries.pop('mlx-swift_Cmlx.bundle/default.metallib',None)
        with self.assertRaises(ValueError): self.module.inspect_ipa(self.archive(),self.files,self.base_files,self.dependency_proof)

    def test_invalid_compiled_speech_shader_is_rejected(self):
        self.entries['mlx-swift_Cmlx.bundle/default.metallib']=b'not-a-metal-library'*100
        with self.assertRaises(ValueError): self.module.inspect_ipa(self.archive(),self.files,self.base_files,self.dependency_proof)

if __name__=='__main__':unittest.main()

