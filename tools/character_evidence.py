"""Build-time evidence for actual shared-runtime speech and conversion diagnostics."""
import argparse,array,hashlib,json,math,os,pathlib,re,subprocess,wave
MODEL_HASHES={'tiny.en.bin':'921e4cf8686fdd993dcd081a5da5b6c365bfde1162e72b08d75ac75289920b1f','base.en.bin':'a03779c86df3323075f5e796cb2ce5029f00ec8869eee3fdfb897afe36c6d002'}
def digest(path):
 with pathlib.Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def source_proof(resolved):
 paths=[pathlib.Path('probes/native-conversion/RuntimeHost.swift')]+list(pathlib.Path('VoiceMatrix').glob('*.swift'))+list(pathlib.Path('Assets.xcassets').rglob('*'))+[pathlib.Path('project.yml'),pathlib.Path('VoiceMatrix/LaptopSettings.json'),pathlib.Path('tools/f5-listening-lock.json'),pathlib.Path('tools/no-stock-resource-lock.json')]
 files={p.as_posix():digest(p) for p in sorted(set(paths)) if p.is_file()}
 record=dict(sourceCommit=os.environ['GITHUB_SHA'],files=files,dependencyResolvedSHA256=digest(resolved))
 record['inferenceSourceFingerprint']=hashlib.sha256(json.dumps(record,sort_keys=True,separators=(',',':')).encode()).hexdigest();return record

def words(text):return re.findall('[a-z0-9]+',text.lower())
def edits(a,b):
 prior=list(range(len(b)+1))
 for i,x in enumerate(a,1):
  row=[i]
  for j,y in enumerate(b,1):row.append(min(row[-1]+1,prior[j]+1,prior[j-1]+(x!=y)))
  prior=row
 return prior[-1]
def check_conversion(root,cli,models):
 from tools.character_package import BASE_FILES
 root=pathlib.Path(root);report=json.loads((root/'conversion-result.json').read_text());audio=root/'reference-conditioned-conversion.wav'
 assert digest(audio)==report['outputSHA256']
 assert report['sharedModelManifestSHA256']==BASE_FILES['OpenVoice/model-manifest.json']['sha256']
 with wave.open(str(audio)) as f:
  assert (f.getnchannels(),f.getsampwidth(),f.getframerate())==(1,2,22050)
  pcm=array.array('h',f.readframes(f.getnframes()))
 rms=math.sqrt(sum(x*x for x in pcm)/len(pcm))/32768;fullscale=sum(abs(x)>=32767 for x in pcm);attempts=[]
 decoded=root/'conversion16k.wav';subprocess.run(['ffmpeg','-v','error','-y','-i',str(audio),'-ac','1','-ar','16000',str(decoded)],check=True,capture_output=True)
 for model in map(pathlib.Path,models):
  assert digest(model)==MODEL_HASHES[model.name]
  prefix=root/('independent-'+model.stem);subprocess.run([str(cli),'-m',str(model),'-f',str(decoded),'-l','en','-t','2','-nf','-otxt','-of',str(prefix)],check=True,capture_output=True,timeout=120)
  text=pathlib.Path(str(prefix)+'.txt').read_text().strip();wer=edits(words(report['expectedText']),words(text))/len(words(report['expectedText']));attempts.append(dict(recognizerModelSHA256=digest(model),recognizedText=text,wordErrorRate=wer))
  if wer<=.1:break
 passed=min(x['wordErrorRate'] for x in attempts)<=.1 and rms>.0001 and fullscale==0 and abs(report['sourceSeconds']-report['outputSeconds'])<.04
 report.update(independentASR=attempts,rms=rms,fullScaleSamples=fullscale,passed=passed,physicalDeviceVerified=False,likenessVerified=False)
 (root/'conversion-result.json').write_text(json.dumps(report,indent=2)+'\n')
 assert passed,'Actual CoreML conversion failed word/audio/timing checks'
 print(json.dumps(dict(passed=True,wordErrorRate=min(x['wordErrorRate'] for x in attempts),physicalDeviceVerified=False)))
if __name__=='__main__':
 p=argparse.ArgumentParser();s=p.add_subparsers(dest='command',required=True);a=s.add_parser('source');a.add_argument('resolved');a.add_argument('output');a=s.add_parser('conversion');a.add_argument('root');a.add_argument('cli');a.add_argument('models',nargs='+');a=p.parse_args()
 if a.command=='source':pathlib.Path(a.output).write_text(json.dumps(source_proof(a.resolved),indent=2)+'\n')
 else:check_conversion(a.root,a.cli,a.models)
