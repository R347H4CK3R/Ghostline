"""Create the experimental no-stock LiveContainer feed from actual IPA metadata."""
import hashlib
import json
from pathlib import Path
import plistlib
import zipfile
import sys

TAG = 'voicematrix-v0.3.2-no-stock-f5-10'
BASE = 'https://github.com/R347H4CK3R/Ghostline/releases/download/' + TAG
IPA_NAME = 'VoiceMatrix-0.3.2-listening-candidate.ipa'
SOURCE_NAME = 'livecontainer-listening.json'
DESCRIPTION = ('Experimental offline F5 character speech with your imported reference recordings, and listening review. '
               'No bundled stock voices or private recordings. Noncommercial use only: F5 model CC-BY-NC 4.0. '
               'Unsigned iOS 26+ candidate. Physical iPhone synthesis, performance and character likeness are not yet verified.')

def generate(ipa):
    ipa = Path(ipa)
    with zipfile.ZipFile(ipa) as archive:
        info = plistlib.loads(archive.read('Payload/VoiceMatrix.app/Info.plist'))
    expected = {'CFBundleIdentifier':'com.voicematrix.app','CFBundleShortVersionString':'0.3.2','CFBundleVersion':'10','MinimumOSVersion':'26.0'}
    if any(info.get(key) != value for key,value in expected.items()):
        raise ValueError('Unexpected IPA identity or minimum OS')
    with ipa.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    version = dict(version='0.3.2',buildVersion='10',date='2026-11-08',downloadURL=BASE+'/'+IPA_NAME,
                   localizedDescription=DESCRIPTION,minOSVersion='26.0',size=ipa.stat().st_size,sha256=digest)
    return dict(name='VoiceMatrix — No-stock F5 Listening',identifier='com.voicematrix.listening-source',
                sourceURL=BASE+'/'+SOURCE_NAME,apps=[dict(name='VoiceMatrix — Character Listening',
                bundleIdentifier='com.voicematrix.app',developerName='VoiceMatrix',localizedDescription=DESCRIPTION,
                iconURL='https://raw.githubusercontent.com/R347H4CK3R/Ghostline/16d0654dd43c0adc6f4f07c2d3af196a45e5bc85/Assets.xcassets/AppIcon.appiconset/AppIcon.png',versions=[version])])

if __name__ == '__main__':
    Path(sys.argv[2]).write_text(json.dumps(generate(sys.argv[1]),indent=2)+'\n')
