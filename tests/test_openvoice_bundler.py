import hashlib,json,os,runpy,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
SCRIPT=Path(__file__).parents[1]/'tools/bundle_openvoice.py'
class OpenVoiceBundlerTests(unittest.TestCase):
 def test_profile_copy_does_not_replace_model_source_directory(self):
  with tempfile.TemporaryDirectory() as folder:
   previous=Path.cwd();argv=sys.argv[:]
   try:
    os.chdir(folder);root=Path('build/openvoice-source');root.mkdir(parents=True);(root/'README.md').write_text('Publisher model notice')
    Path('models').mkdir();Path('LICENSES').mkdir();Path('LICENSES/OpenVoice-LICENSE').write_text('MIT model license')
    data=(root/'README.md').read_bytes()
    Path('models/openvoice-lock.json').write_text(json.dumps(dict(revision='pinned',repository='publisher',baseURL='https://unused.invalid',files=[dict(path='README.md',size=len(data),sha256=hashlib.sha256(data).hexdigest())])))
    profile=json.dumps(dict(id='approved',ttsEmbeddingSHA256='base',converterRevision='pinned')).encode();Path('models/profile.json').write_bytes(profile)
    Path('models/original-conversion-lock.json').write_text(json.dumps(dict(profiles=[dict(id='approved',path='models/profile.json',size=len(profile),sha256=hashlib.sha256(profile).hexdigest(),ttsEmbeddingSHA256='base')])))
    Path('models/reference-provenance.json').write_text('{}')
    def compile_model(command,check):
     output=Path(command[-1])/(Path(command[-2]).stem+'.mlmodelc');output.mkdir(parents=True);(output/'weight.bin').write_bytes(b'test compiled payload')
    sys.argv=[str(SCRIPT)]
    with patch('subprocess.run',side_effect=compile_model):runpy.run_path(str(SCRIPT),run_name='__main__')
    result=Path('VoiceMatrix/Resources/OpenVoice')
    self.assertEqual((result/'Model-Card.md').read_text(),'Publisher model notice')
    self.assertEqual((result/'Profiles/approved.json').read_bytes(),profile)
    self.assertTrue((result/'model-manifest.json').is_file())
   finally:os.chdir(previous);sys.argv=argv
