"""Write feeds only for the inspected IPA URL supplied by the release job."""
import datetime, json, sys
from pathlib import Path
url=sys.argv[1]
count=len(json.loads(Path('models/phonon-lock.json').read_text())['voices'])
size=Path('VoiceMatrix-v0.2.2-experimental.ipa').stat().st_size
if not url.startswith('https://github.com/R347H4CK3R/Ghostline/releases/download/'): raise ValueError('Unexpected release URL')
for filename,label in [('source.json','VoiceMatrix — LiveContainer'),('strata-source.json','VoiceMatrix — Strata')]:
 source={'name':label,'identifier':'com.voicematrix.'+filename.split('.')[0],'apps':[{'name':'VoiceMatrix Experimental','bundleIdentifier':'com.voicematrix.app','developerName':'VoiceMatrix','localizedDescription':f'Offline Phonon speech studio. {count} bundled profiles with automated English speech checks; physical per-profile verification and neural conversion pending.','iconURL': 'https://raw.githubusercontent.com/R347H4CK3R/Ghostline/main/Assets.xcassets/AppIcon.appiconset/AppIcon.png','versions':[{'version':'0.2.2','buildVersion':'4','date':datetime.date.today().isoformat(),'downloadURL':url,'localizedDescription':'Experimental: integrity-checked IPA; physical-device audio tests pending.','minOSVersion':'26.0','size':size}]}]}
 source['sourceURL']='https://raw.githubusercontent.com/R347H4CK3R/Ghostline/main/'+filename
 open(filename,'w').write(json.dumps(source,indent=2)+'\n')
