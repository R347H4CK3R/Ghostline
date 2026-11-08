"""Independent diagnostic word checks; no character likeness score is inferred."""
import array,hashlib,json,pathlib,re,subprocess,sys,wave,math

def words(s):return re.findall(r'[a-z0-9]+',s.lower())
def distance(a,b):
 prior=list(range(len(b)+1))
 for i,x in enumerate(a,1):
  row=[i]
  for j,y in enumerate(b,1):row.append(min(row[-1]+1,prior[j]+1,prior[j-1]+(x!=y)))
  prior=row
 return prior[-1]

def main():
 root,report_path,cli,model=map(pathlib.Path,sys.argv[1:5])
 assert hashlib.sha256(model.read_bytes()).hexdigest()=='921e4cf8686fdd993dcd081a5da5b6c365bfde1162e72b08d75ac75289920b1f'
 report=json.loads(report_path.read_text());configs={}
 for row in report['cases']:
  row['wordcheckPassed']=False
  if row['status'].startswith('generated-'):
   assert pathlib.Path(row['file']).name==row['file']
   audio=root/row['file'];assert hashlib.sha256(audio.read_bytes()).hexdigest()==row['generatedWAVSHA256']
   with wave.open(str(audio)) as f:
    assert (f.getnchannels(),f.getsampwidth(),f.getframerate())==(1,2,24000)
    pcm=array.array('h',f.readframes(f.getnframes()))
   if sys.byteorder!='little':pcm.byteswap()
   rms=math.sqrt(sum(x*x for x in pcm)/max(len(pcm),1))/32768
   fullscale=sum(abs(x)>=32767 for x in pcm)
   target=root/(row['id']+'-16k.wav');prefix=root/(row['id']+'-asr')
   subprocess.run(['ffmpeg','-v','error','-y','-i',str(audio),'-ac','1','-ar','16000',str(target)],check=True,capture_output=True)
   subprocess.run([str(cli),'-m',str(model),'-f',str(target),'-l','en','-t','2','-nf','-otxt','-of',str(prefix)],check=True,capture_output=True,timeout=120)
   recognized=prefix.with_suffix('.txt').read_text().strip();wer=distance(words(row['expectedText']),words(recognized))/len(words(row['expectedText']))
   row.update(recognizedText=recognized,wordErrorRate=wer,rms=rms,fullScaleSamples=fullscale,wordcheckPassed=wer<=.1 and rms>.0001 and fullscale==0)
  if not row.get('longMessage'):configs.setdefault(row['configuration'],[]).append(row['wordcheckPassed'])
 report['passingConfigurations']=[name for name,checks in configs.items() if len(checks)==3 and all(checks)]
 report['independentASR']='whisper.cpp 727d3e7666485e12450746b523bfb4e7f057cc5e tiny.en with pinned SHA-256; no prompt or forced vocabulary'
 report['scope']='Three diagnostic texts per configuration; does not verify character likeness or physical iPhone execution.'
 report_path.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({'passingConfigurations':report['passingConfigurations'],'checkedClips':len(report['cases'])}))
 long_cases=[row for row in report['cases'] if row.get('longMessage')]
 if len(report['cases'])!=13 or 'steps32-seed0' not in report['passingConfigurations'] or len(long_cases)!=1 or not long_cases[0]['wordcheckPassed'] or long_cases[0]['chunkCount']<=1:raise SystemExit('Production settings or actual multi-chunk speech failed the unmodified word/audio gates')
if __name__=='__main__':main()
