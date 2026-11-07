"""Register only tested, nonduplicate conditioning profiles in the offline catalog."""
import argparse,base64,hashlib,json,pathlib,re,struct
from assets import conversion_tensor

def build(approved_path,artifacts,lock_path):
 approved=json.loads(pathlib.Path(approved_path).read_text());lock=json.loads(pathlib.Path(lock_path).read_text());converter=json.loads(pathlib.Path('models/openvoice-lock.json').read_text())
 # Re-running reconstructs the neural-conversion portion without duplicating it.
 prior=[v for v in lock['voices'] if v['engine']=='phonon31m'];prior_paths={v['path'] for v in lock['voices'] if v['engine']!='phonon31m'}
 lock['voices']=prior;lock['files']=[e for e in lock['files'] if e['path'] not in prior_paths];bases={v['id']:v for v in prior}
 files={}
 for p in pathlib.Path(artifacts).rglob('Profiles/*.json'):
  value=json.loads(p.read_text())
  if value['id'] in files:raise ValueError('Duplicate artifact profile ID')
  files[value['id']]=value
 root=pathlib.Path('models/profiles');root.mkdir(parents=True,exist_ok=True)
 audit=[];provenance=[]
 for index,record in enumerate(sorted(approved['profiles'],key=lambda r:r['provenance']['sourcePath']),1):
  if record['status']!='automated-checks-passed' or record['wordErrorRate']>0.1 or record['fullScaleSampleFraction']!=0 or record['targetCosineAfter']<=record['targetCosineBefore']+0.02:raise ValueError('Unapproved reference profile')
  source=record['provenance'];value=files[record['id']];base=bases[record['baseVoiceID']]
  if value['ttsEmbeddingSHA256']!=base['sha256'] or value['converterRevision']!=converter['revision'] or value['referenceAudioSHA256']!=source['referenceSHA256']:raise ValueError('Model/reference provenance mismatch')
  raw=struct.pack('<256e',*value['embedding'])
  if raw!=struct.pack('<256e',*record['targetEmbedding']):raise ValueError('Conditioning differs from tested inference input')
  compact={k:value[k] for k in ['id','ttsEmbeddingSHA256','converterRevision','referenceAudioSHA256']};compact['embeddingFP16Base64']=base64.b64encode(raw).decode()
  data=(json.dumps(compact,sort_keys=True,separators=(',',':'))+'\n').encode();path=root/(value['id']+'.json');path.write_bytes(data)
  digest=hashlib.sha256(data).hexdigest();prefix=source['sourcePath'].split('/')[0];stem=pathlib.PurePosixPath(source['sourcePath']).stem
  if prefix=='voice-donations':
   name=stem.replace('_',' ').strip()
   if len(name)<4 or len(name)>28 or re.fullmatch('[0-9a-fA-F]+',name):name='Community Voice '+str(index)
   else:name=name+' · Community'
   category='Community Voices'
  elif prefix=='vctk':name='Studio Voice '+stem.split('_')[0].removeprefix('p');category='Studio Voices'
  elif prefix=='ears':name='Studio Voice '+source['sourcePath'].split('/')[1].removeprefix('p');category='Studio Voices'
  else:name='Wayfarer Merchant';category='Fantasy & Characters'
  license=source['recordingLicense']
  profile=dict(id=value['id'],name=name,category=category,language='en',accent='English synthesis; reference accent unverified',path='voices/'+path.name,sha256=digest,size=len(data),engine='phonon31m-openvoicev2',baseVoiceID=base['id'],converterRevision=converter['revision'],source=f"https://huggingface.co/{source['sourceRepository']}/blob/{source['sourceRevision']}/{source['sourcePath']}",permissions=license+' reference recording; publisher-curated TTS prompt; required attribution and terms bundled. '+source['voiceUseBasis'],qualityStatus='native-conversion-and-English-ASR-checked; listening-pending',deviceVerified=False,embeddingFormat='OpenVoiceV2 256 x float16, little-endian base64 JSON',vocalCharacteristics=['Original reference conditioning; no official character identity claim'],referenceAudioSHA256=source['referenceSHA256'],sourceAudioSHA256=source['sourceSHA256'])
  if license=='CC-BY-NC-4.0':profile['usageRestriction']='Noncommercial use only'
  profile['tensorSha256']=conversion_tensor(data,profile,prior+[profile])
  lock['voices'].append(profile);lock['files'].append(dict(path=profile['path'],localPath=str(path),sha256=digest,size=len(data)))
  audit.append({k:record[k] for k in ['id','audioSHA256','audioSeconds','elapsedSeconds','wordErrors','referenceWords','wordErrorRate','fullScaleSampleFraction','rms','targetCosineBefore','targetCosineAfter','transcript']})
  provenance.append(dict(id=value['id'],conditioningSHA256=digest,conditioningTensorSHA256=profile['tensorSha256'],source=source))
 pathlib.Path(lock_path).write_text(json.dumps(lock,indent=2)+'\n')
 pathlib.Path('models/reference-provenance.json').write_text(json.dumps(dict(profiles=provenance,sourceCard='https://huggingface.co/kyutai/tts-voices/blob/323332d33f997de8394f24a193e1a76df720e01a/README.md'),indent=2)+'\n')
 qa=pathlib.Path('docs/qa');qa.mkdir(exist_ok=True,parents=True)
 (qa/'0.3.0-reference-checks.json').write_text(json.dumps(dict(nativeRun=42391645201,nativeCommit='f7a19bfecbbe0e808c22c79040184498619cac81',includedAdditionalProfiles=len(audit),includedCatalogProfiles=len(lock['voices']),physicalDeviceVerified=0,listeningVerified=0,characterSimilarity='not-measured',scope='Actual native conversion and independent English ASR; no human quality or likeness claim',excluded=approved['excluded'],profiles=audit),indent=2)+'\n')
 print('Registered real conditioned profiles:',len(audit),'Total catalog:',len(lock['voices']))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--approved',required=True);p.add_argument('--artifacts',required=True);p.add_argument('--lock',default='models/phonon-lock.json');a=p.parse_args();build(a.approved,a.artifacts,a.lock)
