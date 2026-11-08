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
