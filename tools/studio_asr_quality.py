"""Development-only independent ASR of actual native speech and conversion WAVs."""
import argparse,concurrent.futures,hashlib,json,pathlib,re,subprocess,wave
from fractions import Fraction
import numpy as np
from scipy.signal import resample_poly

def words(text):return re.findall(r'[a-z0-9]+',text.lower())
def edits(a,b):
 previous=list(range(len(b)+1))
 for i,x in enumerate(a,1):
  row=[i]
  for j,y in enumerate(b,1):row.append(min(row[-1]+1,previous[j]+1,previous[j-1]+(x!=y)))
  previous=row
 return previous[-1]
def main():
 p=argparse.ArgumentParser();p.add_argument('qa',type=pathlib.Path);p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--whisper-cli',type=pathlib.Path,required=True);p.add_argument('--model',type=pathlib.Path,required=True);p.add_argument('--verify-model',type=pathlib.Path);p.add_argument('--whisper-source',type=pathlib.Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
 proof=json.loads((a.qa/'voice-synthesis-results.json').read_text());default='Hello. This is a voice test.'
 checks=[dict(r,file=r['id']+'.wav',referenceText=default,check='baseline') for r in proof['profiles']]
 checks += [dict(r,check='varied-English') for r in proof.get('additionalEnglishChecks',[])]
 checks += [dict(r,check='voice-conversion') for r in proof.get('conversionChecks',[])]
 models=[a.model]+([a.verify_model] if a.verify_model else []);hashes={str(m):hashlib.sha256(m.read_bytes()).hexdigest() for m in models}
 def run(check):
  name=check['file']
  if pathlib.Path(name).name!=name:raise ValueError('Unsafe QA filename')
  src=a.qa/name
  if hashlib.sha256(src.read_bytes()).hexdigest()!=check['audioSHA256']:raise ValueError('QA audio checksum mismatch')
  with wave.open(str(src)) as f:
   if f.getsampwidth()!=2 or f.getnchannels()!=1 or f.getframerate() not in [22050,24000]:raise ValueError('Unexpected native WAV')
   rate=f.getframerate();audio=np.frombuffer(f.readframes(f.getnframes()),dtype='<i2').astype(np.float64)/32768
  key=check['id']+'-'+check['check']+'-'+check['audioSHA256'][:12];target=a.output/(key+'.wav')
  if not target.exists():
   ratio=Fraction(16000,rate);signal=resample_poly(audio,ratio.numerator,ratio.denominator)
   with wave.open(str(target),'wb') as f:
    f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes((np.clip(signal,-1,32767/32768)*32768).astype('<i2').tobytes())
  attempts=[]
  for model in models:
   prefix=a.output/(key+'-'+hashes[str(model)][:8]);textfile=prefix.with_suffix('.txt')
   if not textfile.is_file():
    result=subprocess.run([str(a.whisper_cli),'-m',str(model),'-f',str(target),'-l','en','-t','2','-nf','-otxt','-of',str(prefix)],capture_output=True,text=True,timeout=120)
    if result.returncode:raise RuntimeError(result.stderr[-2000:])
   transcript=textfile.read_text().strip();count=edits(words(check['referenceText']),words(transcript));wer=count/len(words(check['referenceText']))
   attempts.append(dict(modelSHA256=hashes[str(model)],transcript=transcript,wordErrors=count,wordErrorRate=wer))
   if wer<=.1:break
  best=min(attempts,key=lambda r:r['wordErrorRate']);rms=float(np.sqrt(np.mean(audio**2)));fullscale=float(np.mean(np.abs(audio)>=32767/32768))
  row=dict(id=check['id'],check=check['check'],referenceText=check['referenceText'],file=name,audioSHA256=check['audioSHA256'],referenceWords=len(words(check['referenceText'])),audioSeconds=len(audio)/rate,rms=rms,peak=float(np.max(np.abs(audio))),fullScaleSampleFraction=fullscale,attempts=attempts,**best)
  row['passed']=row['wordErrorRate']<=.1 and fullscale==0 and rms>.0001
  print(check['id'],check['check'],'PASS' if row['passed'] else 'REVIEW',repr(row['transcript']),flush=True);return row
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(run,checks))
 report=dict(method='Independent whisper.cpp English transcription without prompt or constrained vocabulary. Larger model rechecks only clips exceeding10% word error; all attempts retained.',scope='Automated functionality/intelligibility, not human naturalness, perceptual distinctness, character resemblance or device verification.',models=hashes,whisperCommit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=a.whisper_source,text=True).strip(),profiles=rows,profileCount=len(proof['profiles']),clipCount=len(rows),exactTranscriptCount=sum(r['wordErrors']==0 for r in rows),passedClips=sum(r['passed'] for r in rows),inferenceFingerprint=proof['inferenceFingerprint'])
 (a.output/'asr-intelligibility-results.json').write_text(json.dumps(report,indent=2)+'\n');print('PASSED CLIPS',report['passedClips'],'/',len(rows),flush=True)
if __name__=='__main__':main()
