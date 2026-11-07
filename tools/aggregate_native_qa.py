"""Combine disjoint native QA shards only when every catalog profile is covered."""
import argparse,hashlib,json,pathlib,shutil,unicodedata
from assets import validate_qa_report
from inference_fingerprint import validate_evidence

def combine(artifacts,lock,output):
 output=pathlib.Path(output);output.mkdir(parents=True,exist_ok=True);records=[];english=[];converted=[];ids=set();peaks=[];reports=list(pathlib.Path(artifacts).rglob('voice-synthesis-results.json'))
 fingerprints=set()
 for path in reports:
  report=json.loads(path.read_text());fingerprints.add(validate_evidence(report));subset=dict(lock,voices=[v for v in lock['voices'] if v['id'] in {p['id'] for p in report['profiles']}]);validate_qa_report(report,subset)
  files={unicodedata.normalize('NFC',p.name):p for p in path.parent.glob('*.wav')}
  for profile in report['profiles']:
   if profile['id'] in ids:raise ValueError('Overlapping or repeated native QA profile')
   ids.add(profile['id'])
  for profile in report['profiles']+report.get('additionalEnglishChecks',[])+report.get('conversionChecks',[]):
   name=profile.get('file',profile['id']+'.wav')
   if pathlib.Path(name).name!=name:raise ValueError('Unsafe QA output filename')
   source=files[unicodedata.normalize('NFC',name)]
   if hashlib.sha256(source.read_bytes()).hexdigest()!=profile['audioSHA256']:raise ValueError('Native QA WAV checksum mismatch')
   shutil.copyfile(source,output/name)
  records+=report['profiles'];english+=report.get('additionalEnglishChecks',[]);converted+=report.get('conversionChecks',[])
  if report.get('sampledPeakPhysicalFootprintBytes'):peaks.append(report['sampledPeakPhysicalFootprintBytes'])
 if len(fingerprints)!=1:raise ValueError('Native shards have mismatched inference fingerprints')
 result=dict(inferenceFingerprint=next(iter(fingerprints)),schemaVersion=1,kind='text-to-speech',platform='iOS Simulator CPU',engine='phonon31m+OpenVoiceV2',modelRevision=lock['revision'],physicalDeviceVerified=0,listeningVerified=0,profiles=records,additionalEnglishChecks=english,conversionChecks=converted,sampledPeakPhysicalFootprintBytes=max(peaks) if peaks else None,memoryMeasurement='Maximum observed across 50ms simulator process samples, not physical iPhone memory')
 validate_qa_report(result,lock)
 expected={v['id'] for v in lock['voices'] if v['category']=='International Voices' or v['engine']=='phonon31m-openvoicev2'}
 if len(english)!=len(expected) or {p['id'] for p in english}!=expected:raise ValueError('Missing varied-English checks')
 (output/'voice-synthesis-results.json').write_text(json.dumps(result,indent=2)+'\n');print('Verified speech and conversion for unique profiles:',len(records))
 return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('artifacts');p.add_argument('--output',required=True);p.add_argument('--lock',default='models/phonon-lock.json');a=p.parse_args();combine(a.artifacts,json.loads(pathlib.Path(a.lock).read_text()),a.output)
