"""Inject matched native evidence and the final approved catalog into an unsigned IPA.
The executable, icon and retained neural weights are preserved byte-for-byte.
"""
import argparse,hashlib,json,math,pathlib,zipfile
from assets import validate_qa_report
from inference_fingerprint import verify
APP='Payload/VoiceMatrix.app/';PH=APP+'Phonon/';CV=APP+'OpenVoice/'
def prepare(candidate,output,approved,qa,asr):
 with zipfile.ZipFile(candidate) as z:
  if z.testzip() is not None:raise ValueError('Corrupt candidate')
  original=json.loads(z.read(PH+'manifest.json'));validate_qa_report(qa,original)
  verify(lambda p:z.read(APP+p),original,json.loads(z.read(CV+'model-manifest.json')),qa,[n.removeprefix(APP) for n in z.namelist() if n.startswith(APP) and not n.endswith('/')])
  old={v['id']:v for v in original['voices']};keep={v['id'] for v in approved['voices']}
  if not keep or not keep<=old.keys():raise ValueError('Unbuilt profile in approved catalog')
  native={}
  for kind,rows in [('baseline',qa['profiles']),('varied-English',qa.get('additionalEnglishChecks',[])),('voice-conversion',qa.get('conversionChecks',[]))]:
   for row in rows:native[(row['id'],kind)]=row
  checks={(r['id'],r['check']):r for r in asr['profiles']}
  for voice in approved['voices']:
   if voice!=old[voice['id']]:raise ValueError('Changed conditioning after testing')
   if voice.get('baseVoiceID') and voice['baseVoiceID'] not in keep:raise ValueError('Missing source voice')
   modes=['baseline','voice-conversion']
   if voice['engine']=='phonon31m-openvoicev2' or voice['category']=='International Voices':modes.append('varied-English')
   for kind in modes:
    row=native.get((voice['id'],kind));test=checks.get((voice['id'],kind))
    if row is None or test is None or row['audioSHA256']!=test['audioSHA256']:raise ValueError('Missing matched audio evidence')
    if not all(math.isfinite(test[k]) for k in ['wordErrorRate','rms','fullScaleSampleFraction']) or not 0<=test['wordErrorRate']<=.1 or test['rms']<=.0001 or test['fullScaleSampleFraction']!=0:raise ValueError('Voice requires quality review: '+voice['id'])
  paths={e['path'] for e in approved['files']};oldpaths={e['path'] for e in original['files']}
  for entry in approved['files']:
   data=z.read(PH+entry['path'])
   if len(data)!=entry['size'] or hashlib.sha256(data).hexdigest()!=entry['sha256']:raise ValueError('Retained model asset mismatch')
  proof=dict(qa)
  for key in ['profiles','additionalEnglishChecks','conversionChecks']:proof[key]=[p for p in proof.get(key,[]) if p['id'] in keep]
  validate_qa_report(proof,approved)
  replacements={PH+'manifest.json':json.dumps(approved,indent=2).encode(),PH+'voice-synthesis-results.json':json.dumps(proof,indent=2).encode()}
  provenance=json.loads(z.read(CV+'reference-provenance.json'));provenance['profiles']=[p for p in provenance['profiles'] if p['id'] in keep]
  replacements[CV+'reference-provenance.json']=json.dumps(provenance,indent=2).encode()
  cv=json.loads(z.read(CV+'model-manifest.json'))
  original_profiles={v['id'] for v in original['voices'] if v['engine']=='phonon31m'}
  removed_cv={CV+'Profiles/'+vid+'.json' for vid in original_profiles-keep}
  cv['files']=[e for e in cv['files'] if CV+e['path'] not in removed_cv]
  for e in cv['files']:
   data=replacements.get(CV+e['path'])
   if data is not None:e['size']=len(data);e['sha256']=hashlib.sha256(data).hexdigest()
  replacements[CV+'model-manifest.json']=json.dumps(cv,indent=2).encode()
  with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as target:
   for info in z.infolist():
    if info.filename in removed_cv or (info.filename.startswith(PH) and info.filename.removeprefix(PH) in oldpaths-paths):continue
    target.writestr(info,replacements.get(info.filename,z.read(info.filename)))
   for name,data in replacements.items():
    if name not in z.namelist():target.writestr(name,data)
 print('Prepared approved offline TTS and conversion profiles:',len(keep))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('candidate');p.add_argument('output');p.add_argument('--lock',default='models/phonon-lock.json');p.add_argument('--qa',required=True);p.add_argument('--asr',required=True);a=p.parse_args();prepare(a.candidate,a.output,json.loads(pathlib.Path(a.lock).read_text()),json.loads(pathlib.Path(a.qa).read_text()),json.loads(pathlib.Path(a.asr).read_text()))
