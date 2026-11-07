"""Text-to-speech routing for validated reference packs; desktop runtime only."""
import array,hashlib,math,os,pathlib,sys,tempfile,wave,zipfile
from tools.voice_pack import validate_pack

def speak(pack,text,destination,model):
 if not isinstance(text,str) or not text.strip() or len(text)>5000:raise ValueError('Enter 1–5000 characters')
 metadata=validate_pack(pack)
 if model is None:raise ValueError('Compatible F5 engine must be loaded before speaking')
 destination=pathlib.Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory(prefix='voicematrix-speak-') as directory:
  reference=pathlib.Path(directory)/'reference.wav'
  with zipfile.ZipFile(pack) as z:
   data=z.read('reference.wav')
  if hashlib.sha256(data).hexdigest()!=metadata['referenceSHA256']:raise ValueError('Pack changed during loading')
  reference.write_bytes(data)
  audio,sample_rate,_=model.infer(ref_file=str(reference),ref_text=metadata['referenceText'],gen_text=text,nfe_step=32,seed=347)
  values=[float(x) for x in audio]
  if sample_rate!=24000 or not 1200<=len(values)<=24000*600 or any(not math.isfinite(x) for x in values):raise ValueError('Invalid generated audio')
  if sum(x*x for x in values)/len(values)<1e-8:raise ValueError('Engine returned silent audio')
  gain=min(1,.98/max(abs(x) for x in values))
  pcm=array.array('h',(round(x*gain*32767) for x in values))
  if sys.byteorder!='little':pcm.byteswap()
  fd,temporary=tempfile.mkstemp(dir=destination.parent,suffix='.wav');os.close(fd)
  try:
   with wave.open(temporary,'wb') as w:
    w.setparams((1,2,sample_rate,0,'NONE','not compressed'));w.writeframes(pcm.tobytes())
   os.replace(temporary,destination)
  finally:pathlib.Path(temporary).unlink(missing_ok=True)
 return dict(profileID=metadata['id'],engine=metadata['engine'],file=str(destination),seconds=len(values)/sample_rate,audioSHA256=hashlib.sha256(destination.read_bytes()).hexdigest())
