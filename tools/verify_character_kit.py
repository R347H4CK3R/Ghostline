"""Bind an IPA to pinned native speech/conversion diagnostics from the same source."""
import argparse,array,hashlib,json,math,pathlib,wave,zipfile
from tools.character_package import inspect_ipa,engine_proof,F5_FILES,BASE_FILES,PREFIX
from tools.character_evidence import digest,MODEL_HASHES

def checked_source(record,expected):
 assert record['sourceCommit']==expected,'Test and app source commits differ'
 unsigned={k:v for k,v in record.items() if k!='inferenceSourceFingerprint'}
 assert hashlib.sha256(json.dumps(unsigned,sort_keys=True,separators=(',',':')).encode()).hexdigest()==record['inferenceSourceFingerprint'],'Invalid source fingerprint'
 return record

def checked_wav(path,expected,rate):
 assert digest(path)==expected,'Generated WAV hash differs'
 with wave.open(str(path)) as f:
  assert (f.getnchannels(),f.getsampwidth(),f.getframerate())==(1,2,rate)
  pcm=array.array('h',f.readframes(f.getnframes()))
 assert pcm and math.sqrt(sum(x*x for x in pcm)/len(pcm))/32768>.0001 and not any(abs(x)>=32767 for x in pcm),'Silent or clipped WAV'

def verify(ipa_root,speech_root,conversion_root,expected):
 ipa_root,speech_root,conversion_root=map(pathlib.Path,(ipa_root,speech_root,conversion_root))
 proofs=[checked_source(json.loads((p/'source-proof.json').read_text()),expected) for p in (ipa_root,speech_root,conversion_root)]
 assert proofs[0]==proofs[1]==proofs[2],'Native tests and packaged app differ'
 ipa=ipa_root/'VoiceMatrix-0.4.0-character-test.ipa'
 dependency=json.loads((ipa_root/'dependency-notices.json').read_text())['proof']
 inspection=inspect_ipa(ipa,dependency_proof=dependency)
 with zipfile.ZipFile(ipa) as z:
  assert json.loads(z.read(PREFIX+'VoiceMatrix-Source-Proof.json'))==proofs[0]
  assert hashlib.sha256(z.read(PREFIX+'F5TTS/DependencyNotices/Package.resolved')).hexdigest()==proofs[0]['dependencyResolvedSHA256']
 speech=json.loads((speech_root/'speech-evidence.json').read_text())
 assert speech['networkDeniedBySandbox'] and not speech['physicalIPhoneVerified'] and not speech['likenessVerified']
 assert speech['engineProofSHA256']==hashlib.sha256((json.dumps(engine_proof(F5_FILES),indent=2)+'\n').encode()).hexdigest()
 assert len(speech['cases'])==13 and len({x['id'] for x in speech['cases']})==13
 selected=[x for x in speech['cases'] if x['configuration']=='steps32-seed0']
 assert len(selected)==4 and sum(bool(x.get('longMessage')) for x in selected)==1
 assert all(x['wordcheckPassed'] and x['wordErrorRate']<=.1 and x['fullScaleSamples']==0 and x['rms']>.0001 for x in selected)
 assert next(x for x in selected if x.get('longMessage'))['chunkCount']>1
 for row in speech['cases']:
  if row['status'].startswith('generated-'):
   assert pathlib.Path(row['file']).name==row['file']
   checked_wav(speech_root/'speech-evidence'/row['file'],row['generatedWAVSHA256'],24000)
 conversion=json.loads((conversion_root/'conversion-evidence/conversion-result.json').read_text())
 assert conversion['passed'] and not conversion['physicalDeviceVerified'] and not conversion['likenessVerified']
 assert speech['importedProfileID']==conversion['importedProfileID']=='diagnostic-neutral'
 assert speech['importedProfileCount']==conversion['importedProfileCount']==1
 assert speech['referenceAudioSHA256']==conversion['referenceAudioSHA256']
 assert conversion['sharedModelManifestSHA256']==BASE_FILES['OpenVoice/model-manifest.json']['sha256']
 assert abs(conversion['sourceSeconds']-conversion['outputSeconds'])<.04
 assert any(x['recognizerModelSHA256'] in MODEL_HASHES.values() and x['wordErrorRate']<=.1 for x in conversion['independentASR'])
 checked_wav(conversion_root/'conversion-evidence/reference-conditioned-conversion.wav',conversion['outputSHA256'],22050)
 return dict(sourceCommit=expected,inferenceSourceFingerprint=proofs[0]['inferenceSourceFingerprint'],dependencyResolvedSHA256=proofs[0]['dependencyResolvedSHA256'],ipaSHA256=digest(ipa),ipaBytes=ipa.stat().st_size,inspection=inspection,nativeDiagnosticSpeechPassed=True,nativeSimulatorConversionPassed=True,physicalIPhoneVerified=False,characterLikenessVerified=False,bundledCharacterProfiles=0,scope='Synthetic diagnostic checks only; imported characters still require individual device and likeness review.')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa_root');p.add_argument('speech_root');p.add_argument('conversion_root');p.add_argument('source_commit');p.add_argument('output');a=p.parse_args()
 pathlib.Path(a.output).write_text(json.dumps(verify(a.ipa_root,a.speech_root,a.conversion_root,a.source_commit),indent=2)+'\n')
