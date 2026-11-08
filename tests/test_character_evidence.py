import hashlib,json,tempfile,unittest,wave
from pathlib import Path
from tools.verify_character_kit import checked_source,checked_wav
class CharacterEvidenceTests(unittest.TestCase):
 def test_source_claim_cannot_change_without_fingerprint_change(self):
  record=dict(sourceCommit='a'*40,files={'VoiceMatrix/F5ReferenceEngine.swift':'b'*64},dependencyResolvedSHA256='c'*64)
  record['inferenceSourceFingerprint']=hashlib.sha256(json.dumps(record,sort_keys=True,separators=(',',':')).encode()).hexdigest()
  self.assertEqual(checked_source(record,'a'*40),record)
  with self.assertRaises(AssertionError):checked_source(record,'d'*40)
  record['files']['VoiceMatrix/F5ReferenceEngine.swift']='e'*64
  with self.assertRaises(AssertionError):checked_source(record,'a'*40)
 def test_saved_wav_must_be_hash_matching_audible_and_not_clipped(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'test.wav'
   for sample,valid in [(0,False),(32767,False),(1000,True)]:
    with wave.open(str(p),'wb') as f:f.setparams((1,2,24000,0,'NONE','not compressed'));f.writeframes(sample.to_bytes(2,'little',signed=True)*2400)
    h=hashlib.sha256(p.read_bytes()).hexdigest()
    if valid:checked_wav(p,h,24000)
    else:
     with self.assertRaises(AssertionError):checked_wav(p,h,24000)
   with self.assertRaises(AssertionError):checked_wav(p,'0'*64,24000)
 def test_recognizer_transcript_keeps_dotted_model_stem(self):
  from unittest import mock
  import tools.character_evidence as evidence
  from tools.character_package import BASE_FILES
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);audio=root/'reference-conditioned-conversion.wav'
   with wave.open(str(audio),'wb') as f:f.setparams((1,2,22050,0,'NONE','not compressed'));f.writeframes((1000).to_bytes(2,'little',signed=True)*11025)
   report=dict(outputSHA256=hashlib.sha256(audio.read_bytes()).hexdigest(),sharedModelManifestSHA256=BASE_FILES['OpenVoice/model-manifest.json']['sha256'],sourceSeconds=.5,outputSeconds=.5,expectedText='hello world')
   (root/'conversion-result.json').write_text(json.dumps(report));model=root/'tiny.en.bin';model.write_bytes(b'unit recognizer fixture')
   real_digest=evidence.digest
   def digest(path):return evidence.MODEL_HASHES['tiny.en.bin'] if Path(path)==model else real_digest(path)
   def command(args,**kwargs):
    if '-of' in args:Path(str(args[args.index('-of')+1])+'.txt').write_text('hello world')
   with mock.patch.object(evidence,'digest',side_effect=digest),mock.patch.object(evidence.subprocess,'run',side_effect=command):
    evidence.check_conversion(root,'unit-recognizer',[str(model)])
   self.assertEqual(json.loads((root/'conversion-result.json').read_text())['independentASR'][0]['recognizedText'],'hello world')
