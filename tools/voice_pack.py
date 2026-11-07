"""Portable F5 reference packs. These are conditioning assets, not RVC weights."""
import array,hashlib,io,json,os,pathlib,re,sys,tempfile,wave,zipfile

MAX_AUDIO_BYTES=24_000*2*15+128_000

def _audio(data):
 try:
  with wave.open(io.BytesIO(data)) as w:
   if w.getnchannels()!=1 or w.getsampwidth()!=2 or w.getframerate()!=24000 or w.getcomptype()!='NONE':
    raise ValueError('Reference must be mono 24 kHz PCM16 WAV')
   frames=w.getnframes()
   if not 12000<=frames<=360000:raise ValueError('Reference must be 0.5–15 seconds')
   pcm=w.readframes(frames)
   if len(pcm)!=frames*2:raise ValueError('Truncated reference')
 except (wave.Error,EOFError) as e:raise ValueError('Invalid WAV') from e
 samples=array.array('h',pcm)
 if sys.byteorder!='little':samples.byteswap()
 if sum(x*x for x in samples)/len(samples)<16:raise ValueError('Silent reference')
 return frames/24000

def _metadata(m):
 for key in ('id','name','source','permission','referenceText'):
  if not isinstance(m.get(key),str) or not m[key].strip():raise ValueError('Missing '+key)
 if not re.fullmatch(r'[a-z0-9_-]{1,100}',m['id']):raise ValueError('Unsafe profile ID')
 cats=m.get('categories')
 if not isinstance(cats,list) or not cats or any(not isinstance(c,str) or not c.strip() for c in cats):raise ValueError('Missing categories')

def export_reference_pack(audio,metadata,destination):
 _metadata(metadata)
 source=pathlib.Path(audio)
 if source.stat().st_size>MAX_AUDIO_BYTES:raise ValueError('Reference too large')
 data=source.read_bytes();seconds=_audio(data)
 m={key:metadata[key] for key in ('id','name','source','permission','referenceText')}
 m.update(schemaVersion=1,kind='f5-reference',engine='F5TTS_v1_Base',trainedModel=False,
  categories=list(dict.fromkeys(metadata['categories'])),referenceFile='reference.wav',
  referenceSHA256=hashlib.sha256(data).hexdigest(),referenceBytes=len(data),seconds=seconds,
  runtimeRequirement='Compatible F5-TTS runtime and shared model weights required; native iOS support unverified')
 destination=pathlib.Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
 fd,tmp=tempfile.mkstemp(dir=destination.parent,suffix='.tmp');os.close(fd)
 try:
  with zipfile.ZipFile(tmp,'w',compression=zipfile.ZIP_DEFLATED) as z:
   z.writestr('manifest.json',json.dumps(m,indent=2));z.writestr('reference.wav',data)
  validate_pack(tmp);os.replace(tmp,destination)
 finally:
  pathlib.Path(tmp).unlink(missing_ok=True)
 return destination

def validate_pack(path):
 try:
  with zipfile.ZipFile(path) as z:
   entries=z.infolist()
   if len(entries)!=2 or {x.filename for x in entries}!={'manifest.json','reference.wav'}:raise ValueError('Unexpected or duplicated archive entry')
   if any(x.flag_bits&1 for x in entries):raise ValueError('Encrypted pack unsupported')
   if z.getinfo('manifest.json').file_size>65536 or z.getinfo('reference.wav').file_size>MAX_AUDIO_BYTES:raise ValueError('Oversized pack')
   m=json.loads(z.read('manifest.json'));data=z.read('reference.wav')
 except (zipfile.BadZipFile,KeyError,json.JSONDecodeError,UnicodeError) as e:raise ValueError('Invalid voice pack') from e
 if not isinstance(m,dict):raise ValueError('Invalid manifest')
 _metadata(m)
 if m.get('schemaVersion')!=1 or m.get('kind')!='f5-reference' or m.get('engine')!='F5TTS_v1_Base' or m.get('trainedModel') is not False or m.get('referenceFile')!='reference.wav':raise ValueError('Unsupported pack format')
 if m.get('referenceBytes')!=len(data) or m.get('referenceSHA256')!=hashlib.sha256(data).hexdigest():raise ValueError('Reference checksum mismatch')
 if m.get('seconds')!=_audio(data):raise ValueError('Reference duration mismatch')
 return m
