"""Write feeds only for the inspected IPA URL supplied by the release job."""
import datetime, json, sys
from pathlib import Path
url=sys.argv[1]
size=Path('VoiceMatrix-v0.2.0-experimental.ipa').stat().st_size
if not url.startswith('https://github.com/R347H4CK3R/Ghostline/releases/download/'): raise ValueError('Unexpected release URL')
for filename,label in [('source.json','VoiceMatrix — LiveContainer'),('strata-source.json','VoiceMatrix — Strata')]:
 source={'name':label,'identifier':'com.voicematrix.'+filename.split('.')[0],'apps':[{'name':'VoiceMatrix Experimental','bundleIdentifier':'com.voicematrix.app','developerName':'VoiceMatrix','localizedDescription':'Offline Phonon speech studio. 37 experimental English profiles; no device verification or neural voice conversion yet.','iconURL': 'https://raw.githubusercontent.com/R347H4CK3R/Ghostline/feature/voicematrix-phonon-offline-20261106/Assets.xcassets/AppIcon.appiconset/AppIcon.png','versions':[{'version':'0.2.0','buildVersion':'2','date':datetime.date.today().isoformat(),'downloadURL':url,'localizedDescription':'Experimental: integrity-checked IPA; physical-device audio tests pending.','minOSVersion':'18.0','size':size}]}]}
 open(filename,'w').write(json.dumps(source,indent=2)+'\n')
