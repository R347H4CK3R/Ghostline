"""Development-only independent transcription of actual native conversion WAVs."""
import argparse,concurrent.futures,hashlib,json,math,pathlib,re,subprocess,wave
import numpy as np
from scipy.signal import resample_poly

def words(text):return re.findall(r'[a-z0-9]+',text.lower())
def distance(a,b):
 previous=list(range(len(b)+1))
 for i,x in enumerate(a,1):
  row=[i]
  for j,y in enumerate(b,1):row.append(min(row[-1]+1,previous[j]+1,previous[j-1]+(x!=y)))
  previous=row
 return previous[-1]
def main():
 p=argparse.ArgumentParser();p.add_argument('artifacts',type=pathlib.Path);p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--whisper-cli',type=pathlib.Path,required=True);p.add_argument('--model',type=pathlib.Path,required=True);p.add_argument('--whisper-source',type=pathlib.Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
 modelhash=hashlib.sha256(a.model.read_bytes()).hexdigest();tasks=[]
 for report_path in sorted(a.artifacts.rglob('bank-results.json')):
  report=json.loads(report_path.read_text());references=json.loads(report_path.with_name('reference-manifest.json').read_text());provenance={r['id']:r for r in references['profiles']}
  for record in report['profiles']:
   if record['status']!='native-audio-checked-awaiting-ASR':continue
   tasks.append((report_path.parent,record,provenance[record['id']]))
 def check(task):
  root,record,source=task;voice=record['id'];path=root/(voice+'.wav');data=path.read_bytes()
  if hashlib.sha256(data).hexdigest()!=record['audioSHA256']:raise ValueError('Native WAV checksum mismatch')
  with wave.open(str(path)) as f:
   if f.getsampwidth()!=2 or f.getnchannels()!=1 or f.getframerate()!=22050:raise ValueError('Invalid converted WAV format')
   audio=np.frombuffer(f.readframes(f.getnframes()),dtype='<i2').astype(np.float64)/32768
  key=voice+'-'+record['audioSHA256'][:12]+'-'+modelhash[:8];prefix=a.output/key;target=prefix.with_suffix('.wav')
  if not prefix.with_suffix('.txt').is_file():
   signal=resample_poly(audio,320,441)
   with wave.open(str(target),'wb') as f:
    f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes((np.clip(signal,-1,32767/32768)*32768).astype('<i2').tobytes())
   result=subprocess.run([str(a.whisper_cli),'-m',str(a.model),'-f',str(target),'-l','en','-t','2','-nf','-otxt','-of',str(prefix)],capture_output=True,text=True,timeout=60)
   if result.returncode:raise RuntimeError(result.stderr[-2000:])
  transcript=prefix.with_suffix('.txt').read_text().strip();expected=record['referenceText'];errors=distance(words(expected),words(transcript));wer=errors/len(words(expected));rms=float(np.sqrt(np.mean(audio**2)));clipped=float(np.mean(np.abs(audio)>=32767/32768))
  output=dict(record);output.update(provenance=source,transcript=transcript,wordErrors=errors,referenceWords=len(words(expected)),wordErrorRate=wer,rms=rms,fullScaleSampleFraction=clipped,peak=float(np.max(np.abs(audio))),status='automated-checks-passed' if wer<=0.1 and clipped==0 and rms>0.0001 else 'rejected-ASR-or-waveform')
  print(voice,output['status'],repr(transcript),flush=True);return output
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(check,tasks))
 report=dict(schemaVersion=1,method='Actual native OpenVoice conversion, finite/non-silent WAV and duration check, positive target-speaker movement, followed by independent whisper.cpp tiny.en transcription; no prompt or constrained vocabulary',scope='Automated functionality/intelligibility and numerical speaker conditioning only; not human listening, perceptual distinctness, character resemblance or physical-device verification',asrModelSHA256=modelhash,whisperCommit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=a.whisper_source,text=True).strip(),profiles=results,nativeRenderedProfiles=len(results),automatedPassed=sum(r['status']=='automated-checks-passed' for r in results))
 (a.output/'reference-bank-validation.json').write_text(json.dumps(report,indent=2)+'\n');print('AUTOMATED PASS',report['automatedPassed'],'/',len(results),flush=True)
if __name__=='__main__':main()
