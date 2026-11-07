import argparse,pathlib,json,hashlib,subprocess,re,wave
import numpy as np
from scipy.signal import resample_poly
parser=argparse.ArgumentParser(description="Development-only speech-recognition check of retained simulator QA WAVs. Requires NumPy, SciPy and whisper.cpp; no app runtime dependency.")
parser.add_argument("qa",type=pathlib.Path)
parser.add_argument("--output",type=pathlib.Path,required=True)
parser.add_argument("--whisper-cli",type=pathlib.Path,required=True)
parser.add_argument("--model",type=pathlib.Path,required=True)
parser.add_argument("--whisper-source",type=pathlib.Path,required=True)
args=parser.parse_args()
root=args.qa;out=args.output;out.mkdir(parents=True,exist_ok=True)
proof=json.loads((root/'voice-synthesis-results.json').read_text());expected='Hello. This is a voice test.'
def words(t):return re.findall(r"[a-z0-9]+",t.lower())
def distance(a,b):
 d=list(range(len(b)+1))
 for i,x in enumerate(a,1):
  n=[i]
  for j,y in enumerate(b,1):n.append(min(n[-1]+1,d[j]+1,d[j-1]+(x!=y)))
  d=n
 return d[-1]
results=[]
for p in proof['profiles']:
 src=root/(p['id']+'.wav');raw=src.read_bytes();assert hashlib.sha256(raw).hexdigest()==p['audioSHA256']
 with wave.open(str(src)) as f:
  assert f.getsampwidth()==2 and f.getnchannels()==1
  rate=f.getframerate();audio=np.frombuffer(f.readframes(f.getnframes()),dtype='<i2').astype(np.float64)/32768
 converted=resample_poly(audio,2,3);assert rate==24000
 dst=out/(p['id']+'.wav')
 with wave.open(str(dst),'wb') as f:
  f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes((np.clip(converted,-1,32767/32768)*32768).astype('<i2').tobytes())
 prefix=out/p['id'];r=subprocess.run([str(args.whisper_cli),'-m',str(args.model),'-t','4','-l','en','-nf','-otxt','-of',str(prefix),str(dst)],capture_output=True,text=True,timeout=60)
 if r.returncode:raise RuntimeError(r.stderr[-2000:])
 transcript=prefix.with_suffix('.txt').read_text().strip();err=distance(words(expected),words(transcript))
 result={'id':p['id'],'audioSHA256':p['audioSHA256'],'transcript':transcript,'wordErrors':err,'referenceWords':len(words(expected)),'wordErrorRate':err/len(words(expected)),'audioSeconds':len(audio)/rate,'rms':float(np.sqrt(np.mean(audio**2))),'peak':float(np.max(np.abs(audio))),'fullScaleSampleFraction':float(np.mean(np.abs(audio)>=32767/32768))}
 results.append(result);print(p['id'],repr(transcript),'errors',err,flush=True)
report={'method':'whisper.cpp tiny.en, English, no initial prompt or constrained vocabulary','scope':'One short fixed sentence per profile; ASR errors do not alone prove unintelligibility. No human listening, likeness, perceptual distinctness, or physical-device verification.','referenceText':expected,'modelSHA256':hashlib.sha256((args.model).read_bytes()).hexdigest(),'whisperCommit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=args.whisper_source,text=True).strip(),'profiles':results,'exactTranscriptCount':sum(x['wordErrors']==0 for x in results),'profileCount':len(results)}
(out/'asr-intelligibility-results.json').write_text(json.dumps(report,indent=2)+'\n');print('EXACT',report['exactTranscriptCount'],'/',len(results),flush=True)
