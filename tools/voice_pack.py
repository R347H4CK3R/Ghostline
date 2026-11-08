"""Portable F5 reference packs. These are conditioning assets, not RVC weights."""
import array,hashlib,json,os,pathlib,re,shutil,sys,tempfile,zipfile

MAX_AUDIO_BYTES=24_000*2*15+128_000

def _audio(data):
 # Match CharacterFolderStore.waveSeconds, not wave.open's permissive first-data
 # decoding: phone import rejects malformed RIFF sizes and duplicate chunks.
 def invalid():return ValueError('Reference must contain valid mono 24 kHz PCM16 WAV audio')
 def number(offset,size):return int.from_bytes(data[offset:offset+size],'little')
 if len(data)<44 or data[:4]!=b'RIFF' or data[8:12]!=b'WAVE' or number(4,4)!=len(data)-8:raise invalid()
 offset=12;pcm=None;format_ok=False
 while offset+8<=len(data):
  tag=data[offset:offset+4];size=number(offset+4,4);start=offset+8
  if size>len(data)-start:raise invalid()
  if tag==b'fmt ':
   if size<16 or format_ok or (number(start,2),number(start+2,2),number(start+4,4),number(start+8,4),number(start+12,2),number(start+14,2))!=(1,1,24000,48000,2,16):raise invalid()
   format_ok=True
  if tag==b'data':
   # Retain the desktop decoder's fmt-before-data requirement as well.
   if not format_ok or pcm is not None:raise invalid()
   pcm=data[start:start+size]
  offset=start+size+(size%2)
 if offset!=len(data) or not format_ok or pcm is None or len(pcm)%2 or not 24000<=len(pcm)<=720000:raise invalid()
 samples=array.array('h',pcm)
 if sys.byteorder!='little':samples.byteswap()
 if sum(x*x for x in samples)/len(samples)<16:raise ValueError('Silent reference')
 return len(pcm)/48000

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
 if 'referenceTranscriptStatus' in metadata:
  if metadata['referenceTranscriptStatus'] not in ('provided','provided-unverified','automatic-needs-review'):raise ValueError('Invalid reference transcript status')
  m['referenceTranscriptStatus']=metadata['referenceTranscriptStatus']
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

def export_collection_folder(packs,destination):
 """Publish a new importable collection; existing revision folders stay untouched."""
 destination=pathlib.Path(destination)
 destination.parent.mkdir(parents=True,exist_ok=True)
 stage=pathlib.Path(tempfile.mkdtemp(prefix='.voices-',dir=destination.parent))
 try:
  entries=[];identifiers=set();references=set()
  for pack in packs:
   m=validate_pack(pack);identifier=m['id']
   if identifier in identifiers:raise ValueError('Repeated voice ID: '+identifier)
   if m['referenceSHA256'] in references:raise ValueError('Repeated reference audio under another voice name')
   identifiers.add(identifier)
   references.add(m['referenceSHA256'])
   with zipfile.ZipFile(pack) as z:data=z.read('reference.wav')
   if hashlib.sha256(data).hexdigest()!=m['referenceSHA256'] or len(data)!=m['referenceBytes']:
    raise ValueError('Reference changed while exporting')
   _audio(data)
   folder=stage/identifier;folder.mkdir()
   (folder/'manifest.json').write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8')
   (folder/'reference.wav').write_bytes(data)
   entries.append(dict(id=identifier,folder=identifier))
  if not entries:raise ValueError('Choose at least one reusable reference pack')
  if len(entries)>1000:raise ValueError('At most 1,000 profiles per collection')
  (stage/'collection.json').write_text(json.dumps(dict(schemaVersion=1,voices=entries),indent=2)+'\n',encoding='utf-8')
  if destination.exists():raise FileExistsError('Export to a new revision folder; existing files are preserved')
  os.rename(stage,destination)
  return destination
 finally:
  if stage.exists():shutil.rmtree(stage)

