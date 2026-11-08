"""Generate synthetic native-import fixtures through the actual publisher CLI."""
import json,pathlib,shutil,subprocess,sys,wave
from tools.voice_pack import export_reference_pack

root=pathlib.Path(sys.argv[1]);root.mkdir(parents=True,exist_ok=True)
def pack(identifier,amplitude):
 audio=root/(identifier+str(amplitude)+'.wav')
 with wave.open(str(audio),'wb') as w:
  w.setparams((1,2,24000,0,'NONE','not compressed'))
  w.writeframes(amplitude.to_bytes(2,'little',signed=True)*24000)
 return export_reference_pack(audio,dict(id=identifier,name=identifier,categories=['Animation','Fantasy'],source='Synthetic fixture',permission='Original synthetic fixture',referenceText='A test reference.'),root/(identifier+str(amplitude)+'.vmpack'))
def publish(p):
 r=subprocess.run([sys.executable,'-m','tools.voice_studio','publish-folder','--master',str(root/'Voices'),str(p)],check=True,capture_output=True,text=True)
 return json.loads(r.stdout)
assert publish(pack('original-test',4000))['added']==['original-test']
shutil.copytree(root/'Voices',root/'Initial')
assert publish(pack('second-test',6000))['added']==['second-test']
old=(root/'Voices/original-test/reference.wav').read_bytes()
assert publish(pack('original-test',8000))['needsReview']==['original-test']
assert old==(root/'Voices/original-test/reference.wav').read_bytes()
print('Actual publish-folder CLI created initial/expanded native collections; replacement remained separate.')
