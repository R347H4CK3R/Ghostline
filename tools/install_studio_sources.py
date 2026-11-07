"""Create installation feeds for the exact inspected 0.3.0 release."""
import datetime,json,pathlib,sys
url=sys.argv[1];ipa=pathlib.Path(sys.argv[2]);lock=json.loads(pathlib.Path(sys.argv[3]).read_text())
if not url.startswith('https://github.com/R347H4CK3R/Ghostline/releases/download/'):raise ValueError('Unexpected release URL')
count=len(lock['voices'])
for filename,label in [('source.json','VoiceMatrix — LiveContainer'),('strata-source.json','VoiceMatrix — Strata')]:
 source={'name':label,'identifier':'com.voicematrix.'+filename.split('.')[0],'apps':[{'name':'VoiceMatrix Experimental','bundleIdentifier':'com.voicematrix.app','developerName':'VoiceMatrix','localizedDescription':f'Fully bundled offline speech and voice conversion. {count} conditioning profiles with automated English audio checks, searchable categories and vocal-depth filters. Conversion supports recordings up to 10 seconds. Physical per-profile listening and character resemblance remain unverified. Some reference-derived voices are noncommercial only.','iconURL':'https://raw.githubusercontent.com/R347H4CK3R/Ghostline/main/Assets.xcassets/AppIcon.appiconset/AppIcon.png','versions':[{'version':'0.3.0','buildVersion':'5','date':datetime.date.today().isoformat(),'downloadURL':url,'localizedDescription':f'{count} bundled profiles. Real offline neural conversion and speech; automated simulator audio checks, no near-indistinguishable claim.','minOSVersion':'26.0','size':ipa.stat().st_size}]}]}
 source['sourceURL']='https://raw.githubusercontent.com/R347H4CK3R/Ghostline/main/'+filename
 pathlib.Path(filename).write_text(json.dumps(source,indent=2)+'\n')
