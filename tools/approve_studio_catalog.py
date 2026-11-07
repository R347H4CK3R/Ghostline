"""Select only profiles passing every independently transcribed native output."""
import argparse,collections,hashlib,json,math,pathlib
from assets import validate_qa_report
from inference_fingerprint import validate_evidence
def approve(lock,qa,asr):
 validate_qa_report(qa,lock)
 if validate_evidence(qa)!=validate_evidence(asr):raise ValueError('ASR inference fingerprint mismatch')
 native={}
 for mode,key in [('baseline','profiles'),('varied-English','additionalEnglishChecks'),('voice-conversion','conversionChecks')]:
  for row in qa.get(key,[]):
   key=(row['id'],mode)
   if key in native:raise ValueError('Repeated native check')
   native[key]=row
 checked={}
 for row in asr['profiles']:
  key=(row['id'],row['check'])
  if key in checked or key not in native or row['audioSHA256']!=native[key]['audioSHA256']:raise ValueError('Unmatched or repeated independent audio check')
  good=all(math.isfinite(row[k]) for k in ['wordErrorRate','rms','fullScaleSampleFraction']) and 0<=row['wordErrorRate']<=.1 and row['rms']>.0001 and row['fullScaleSampleFraction']==0
  if row['passed']!=good:raise ValueError('Inconsistent quality result')
  checked[key]=row
 if set(checked)!=set(native):raise ValueError('Missing independent audio checks')
 accepted=[];rejected=[]
 for voice in lock['voices']:
  modes=['baseline','voice-conversion']
  if voice['engine']=='phonon31m-openvoicev2' or voice['category']=='International Voices':modes.append('varied-English')
  failed=[mode for mode in modes if not checked[(voice['id'],mode)]['passed']]
  (rejected if failed else accepted).append(dict(id=voice['id'],failedChecks=failed) if failed else voice)
 ids={v['id'] for v in accepted}
 for voice in list(accepted):
  if voice.get('baseVoiceID') and voice['baseVoiceID'] not in ids:
   accepted.remove(voice);rejected.append(dict(id=voice['id'],failedChecks=['source voice excluded']))
 retained={v['path'] for v in accepted};old={v['path'] for v in lock['voices']}
 result=dict(lock,voices=accepted,files=[f for f in lock['files'] if f['path'] not in old or f['path'] in retained])
 counts=collections.Counter(category for v in accepted for category in dict.fromkeys([v['category']]+v.get('categories',[])))
 summary=dict(candidateProfiles=len(lock['voices']),approvedProfiles=len(accepted),rejectedProfiles=rejected,categories=dict(sorted(counts.items())),distinctConditioningHashes=len({v['sha256'] for v in accepted}),physicalDeviceVerified=0,controlledListeningVerified=0,authorizedRecognizableLikenesses=0,nativeClipCount=len(native),independentPassedClips=sum(r['passed'] for r in checked.values()),inferenceFingerprint=qa['inferenceFingerprint'],scope='Automated speech/conditioning/intelligibility; perceptual distinctness and character resemblance not established.')
 return result,summary
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--lock',default='models/phonon-lock.json');p.add_argument('--qa',required=True);p.add_argument('--asr',required=True);p.add_argument('--output',required=True);a=p.parse_args()
 lock,summary=approve(*[json.loads(pathlib.Path(p).read_text()) for p in [a.lock,a.qa,a.asr]])
 root=pathlib.Path(a.output);root.mkdir(parents=True,exist_ok=True)
 (root/'phonon-lock.json').write_text(json.dumps(lock,indent=2)+'\n')
 (root/'catalog-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 print(json.dumps(summary,indent=2),flush=True)
 if len(lock['voices'])<500:raise ValueError('Fewer than 500 profiles pass all required independent checks')
