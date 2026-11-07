"""Acquire pinned, licensed development references; never part of app startup.
One recording per speaker is selected for donations/VCTK/EARS. Emotional variants
are not counted as additional speakers. Outputs are candidates, not working voices.
"""
import argparse,concurrent.futures,hashlib,json,subprocess,urllib.request,urllib.parse,wave
import numpy as np
from pathlib import Path
REVISION='323332d33f997de8394f24a193e1a76df720e01a'
REPOSITORY='kyutai/tts-voices'
LICENSES={'voice-donations':'CC0-1.0','vctk':'CC-BY-4.0','ears':'CC-BY-NC-4.0','alba-mackenna':'CC-BY-4.0'}
def median_pitch(path):
 with wave.open(str(path)) as f:
  rate=f.getframerate();samples=np.frombuffer(f.readframes(f.getnframes()),dtype='<i2').astype(np.float64)/32768
 length=int(rate*0.05);values=[];window=np.hanning(length);nfft=1 << (2*length-1).bit_length()
 for start in range(0,len(samples)-length,max(1,int(rate*0.1))):
  frame=samples[start:start+length];frame=(frame-frame.mean())*window
  if np.sqrt(np.mean(frame**2))<0.005:continue
  spectrum=np.fft.rfft(frame,nfft);ac=np.fft.irfft(spectrum*np.conj(spectrum),nfft)[:length]
  if ac[0]<=0:continue
  ac/=ac[0];low=int(rate/500);high=min(length-1,int(rate/60))
  peaks=np.where((ac[1:-1]>ac[:-2]) & (ac[1:-1]>=ac[2:]))[0]+1
  peaks=peaks[(peaks>=low)&(peaks<=high)]
  if len(peaks)==0:continue
  best=max(ac[peaks]);usable=peaks[ac[peaks]>=max(0.45,best*0.9)]
  if len(usable):values.append(rate/int(usable[0]))
 return float(np.median(values)) if len(values)>=5 else None

def acquire(destination,shard=0,shards=1):
 root=Path(destination);root.mkdir(parents=True,exist_ok=True)
 def listing(prefix):
  url=f'https://huggingface.co/api/models/{REPOSITORY}/tree/{REVISION}/{prefix}?recursive=true&limit=1000'
  with urllib.request.urlopen(url,timeout=120) as response:return json.load(response)
 selected=[]
 for prefix in LICENSES:
  for e in listing(prefix):
   name=e['path']
   if e['type']!='file' or not name.endswith('.wav') or name.endswith('_enhanced.wav'):continue
   if prefix=='ears' and not name.endswith('/freeform_speech_01.wav'):continue
   selected.append(e)
 selected=sorted(selected,key=lambda e:e["path"])
 selected=[e for i,e in enumerate(selected) if i % shards == shard]
 def download(e):
  name=e['path'];path=root/'original'/name;path.parent.mkdir(parents=True,exist_ok=True)
  wanted=e.get('lfs',{}).get('oid')
  if not path.is_file() or path.stat().st_size!=e['size'] or (wanted and hashlib.sha256(path.read_bytes()).hexdigest()!=wanted):
   url=f'https://huggingface.co/{REPOSITORY}/resolve/{REVISION}/'+urllib.parse.quote(name,safe='/')
   with urllib.request.urlopen(url,timeout=180) as response:path.write_bytes(response.read())
  digest=hashlib.sha256(path.read_bytes()).hexdigest()
  if path.stat().st_size!=e['size'] or (wanted and digest!=wanted):raise ValueError('Reference checksum mismatch: '+name)
  profile_id=name.split('/')[0]+'-'+hashlib.sha256(name.encode()).hexdigest()[:16]
  output=root/'normalized'/(profile_id+'.wav');output.parent.mkdir(exist_ok=True)
  # At most ten seconds of existing licensed speech, mono 22.05 kHz PCM.
  # Silence is trimmed only at the beginning; low quality clips are rejected later.
  subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(path),'-af','silenceremove=start_periods=1:start_duration=0.05:start_threshold=-45dB','-t','10','-ar','22050','-ac','1','-c:a','pcm_s16le',str(output)],check=True,timeout=60)
  prefix=name.split('/')[0]
  pitch=median_pitch(output)
  return dict(medianReferencePitchHz=pitch,ttsBaseVoiceID='en_us_Zoey' if pitch is not None and pitch>=170 else 'en_us_Micah',id=profile_id,sourceRepository=REPOSITORY,sourceRevision=REVISION,sourcePath=name,sourceSHA256=digest,sourceSize=e['size'],referenceFile='normalized/'+output.name,referenceSHA256=hashlib.sha256(output.read_bytes()).hexdigest(),recordingLicense=LICENSES[prefix],modelRedistributionLicense='No model created yet',voiceUseBasis='Volunteer voice donation for TTS' if prefix=='voice-donations' else 'Publisher-curated voice prompt for TTS; preserve original dataset terms and attribution',recognizableLikenessClaim=False,engine='OpenVoiceV2-candidate',status='reference-only; no inference, listening, distinctness or device verification')
 with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
  rows=[]
  for row in pool.map(download,selected):
   rows.append(row);print('Verified reference',row['id'],flush=True)
 report=dict(repository=REPOSITORY,revision=REVISION,sourceCard=f'https://huggingface.co/{REPOSITORY}/blob/{REVISION}/README.md',referenceCount=len(rows),shard=shard,shards=shards,workingVoiceCount=0,processing='Trim leading silence, take up to 10 seconds, resample to mono PCM16 22050 Hz using ffmpeg',profiles=rows)
 (root/'reference-manifest.json').write_text(json.dumps(report,indent=2)+'\n')
 print('REFERENCES',len(rows),'WORKING APP VOICES 0',flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('destination');p.add_argument('--shard',type=int,default=0);p.add_argument('--shards',type=int,default=1);a=p.parse_args();assert 0<=a.shard<a.shards;acquire(a.destination,a.shard,a.shards)
