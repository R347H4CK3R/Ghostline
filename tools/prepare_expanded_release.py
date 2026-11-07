"""Keep only source-approved, independently English-checked candidate profiles.
Repackages an unsigned candidate without modifying its compiled executable.
"""
import argparse,hashlib,json,math,zipfile
from pathlib import Path
from assets import validate_qa_report
PREFIX='Payload/VoiceMatrix.app/Phonon/'
def prepare(candidate,output,approved,asr):
 with zipfile.ZipFile(candidate) as archive:
  if archive.testzip() is not None:raise ValueError('Corrupt candidate IPA')
  original=json.loads(archive.read(PREFIX+'manifest.json'))
  proof=json.loads(archive.read(PREFIX+'voice-synthesis-results.json'))
  validate_qa_report(proof,original)
  if approved['revision']!=original['revision']:raise ValueError('Wrong engine revision')
  old={v['id']:v for v in original['voices']};keep={v['id'] for v in approved['voices']}
  if not keep or not keep<=old.keys():raise ValueError('Approved profiles absent from candidate')
  evidence={p['id']:p for p in proof['profiles']}
  checks={(p['id'],p['check']):p for p in asr['profiles']}
  extra={p['id']:p for p in proof.get('additionalEnglishChecks',[])}
  for voice in approved['voices']:
   if voice['sha256']!=old[voice['id']]['sha256']:raise ValueError('Changed conditioning')
   if voice['category']!='International Voices':continue
   for kind,native in [('baseline',evidence[voice['id']]),('varied-English',extra.get(voice['id']))]:
    test=checks.get((voice['id'],kind))
    if not native or not test or native['audioSHA256']!=test['audioSHA256']:raise ValueError('Missing matching English audio evidence')
    if not all(math.isfinite(test[k]) for k in ['wordErrorRate','fullScaleSampleFraction','rms']) or not 0<=test['wordErrorRate']<=0.1 or test['fullScaleSampleFraction']!=0 or test['rms']<=0.0001:raise ValueError('New voice requires listening/quality review: '+voice['id'])
  # All retained model bytes must match the approved source lock.
  approved_paths={e['path'] for e in approved['files']}
  original_paths={e['path'] for e in original['files']}
  for entry in approved['files']:
   data=archive.read(PREFIX+entry['path'])
   if len(data)!=entry['size'] or hashlib.sha256(data).hexdigest()!=entry['sha256']:raise ValueError('Damaged retained model asset')
  proof['profiles']=[p for p in proof['profiles'] if p['id'] in keep]
  proof['additionalEnglishChecks']=[p for p in proof.get('additionalEnglishChecks',[]) if p['id'] in keep]
  validate_qa_report(proof,approved)
  replacements={PREFIX+'manifest.json':json.dumps(approved,indent=2).encode(),PREFIX+'voice-synthesis-results.json':json.dumps(proof,indent=2).encode()}
  with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as target:
   for info in archive.infolist():
    rel=info.filename.removeprefix(PREFIX)
    if info.filename.startswith(PREFIX) and rel in original_paths-approved_paths:continue
    target.writestr(info,replacements.get(info.filename,archive.read(info.filename)))
 print('Prepared approved profiles:',len(keep))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('candidate');p.add_argument('output');p.add_argument('--lock',default='models/phonon-lock.json');p.add_argument('--asr',required=True);a=p.parse_args()
 prepare(a.candidate,a.output,json.loads(Path(a.lock).read_text()),json.loads(Path(a.asr).read_text()))
