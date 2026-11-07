"""Update the public README using only the actually published release evidence."""
import json,pathlib
summary=json.load(open('catalog-summary.json'));verification=json.load(open('release-verification.json'));asr=json.load(open('asr-intelligibility-results.json'));lock=json.load(open('phonon-lock.json'));native=json.load(open('voice-synthesis-results.json'))
count=len(lock['voices']);assert count==summary['approvedProfiles'] and count>=500
nc=sum(bool(v.get('usageRestriction')) for v in lock['voices'])
url=json.load(open('source.json'))['apps'][0]['versions'][0]['downloadURL']
rows='\n'.join('| '+name+' | '+str(n)+' |' for name,n in summary['categories'].items())
readme=f"""# VoiceMatrix

Native ARM64 offline English voice studio for iPhone, LiveContainer and Strata. Current experimental version: **0.3.0 build 5**, iOS 26 or later.

[Download the inspected unsigned IPA]({url}) · [LiveContainer source](https://raw.githubusercontent.com/R347H4CK3R/Ghostline/main/source.json) · [Strata source](https://raw.githubusercontent.com/R347H4CK3R/Ghostline/main/strata-source.json)

## Included functionality

- **{count} neural conditioning profiles**, with {summary['distinctConditioningHashes']} distinct conditioning hashes. Different source speakers and numerical duplicate checks support this library; perceptual distinctness remains unverified by human listeners.
- Shared local Phonon 31m speech, plus one shared OpenVoice V2 converter. {sum(v['engine']=='phonon31m' for v in lock['voices'])} direct Phonon profiles and {sum(v['engine']=='phonon31m-openvoicev2' for v in lock['voices'])} reference-derived profiles rendered through the converter.
- Make Speech: choose, type, Speak, Listen, Save and Share WAV. Longer text uses bounded generation chunks. Selected-voice previews use actual inference.
- Change My Voice: record or import audio up to 10 seconds, choose, Convert, Listen, Save and Share. This is offline neural speech-to-speech conversion, not a real-time microphone effect.
- Search, categories, favorites, recently used voices, selected indicators and private saved recordings with rename/delete/share.
- Beginner screens, clear cancellation/errors, microphone/session ownership and exportable diagnostics without automatic text/audio uploads.
- Complete runtime, weights, target profiles and notices bundled. No runtime downloads, server, login, paid API or default system-voice substitution.

## Categories

Categories overlap; each profile counts once. Vocal-depth groups use measurements from reference QA clips and are broad browsing aids. Character categories describe original styles, without official character or performer claims.

| Category | Included profiles |
|---|---:|
{rows}

## Evidence and limits

The final source and packaging regressions passed in GitHub Actions. All 538 candidate profiles underwent native simulator speech and conversion checks, plus varied English where required. Independent recognition examined {asr['clipCount']} actual native WAVs, without a reference prompt or constrained vocabulary; {asr['passedClips']} clips passed the <=10% word-error, non-silence and no-full-scale gate. Only profiles passing every required clip were retained. Larger-model retries and all attempts are recorded.

The exact inference fingerprint binds model files, target profiles, routing, source and dependency identity. The ARM64 app and simulator tests share the same compiled asset archive. Final packaging preserves the executable and approved model/profile bytes, checks metadata/icon/ARM64, and downloads the published IPA for repeated SHA/archive/asset inspection. IPA: {verification['bytes']:,} bytes; SHA-256: `{verification['sha256']}`.

[Approved released manifest](models/released-voices.json) · [Category/approval summary](docs/qa/0.3.0-catalog-summary.json) · [Native evidence](docs/qa/0.3.0-native-results.json) · [Independent ASR evidence](docs/qa/0.3.0-asr-intelligibility.json) · [Published archive check](docs/qa/0.3.0-release-verification.json). Raw native QA WAVs are archived separately with the release for future listening, rather than bloating the installed app.

Automated checks establish generation, decoding and short-clip intelligibility. **Physical per-profile verification: 0 recorded. Controlled listening verification: 0. Authorized recognizable likeness models: 0.** No near-indistinguishable, official-character, naturalness or listener-similarity claim is made. Memory samples come from the hosted simulator, not physical iPhone peak memory. Airplane Mode, host-container microphone behavior, latency, battery and listening remain device-test work.

{nc} profiles are marked noncommercial-only in the picker. Source recordings, model code, model weights and likeness permissions are tracked separately in bundled provenance and notices. Donated, licensed and original recordings are used; no scraped celebrity recordings or hosted proprietary models are bundled.

## Build and reproduce

macOS, Xcode supporting iOS 26+, Swift 6 and XcodeGen:

```sh
python3 -m unittest discover -s tests -v
python3 tools/assets.py
python3 tools/bundle_openvoice.py
xcodegen generate
xcodebuild -project VoiceMatrix.xcodeproj -scheme VoiceMatrix -sdk iphoneos -destination 'generic/platform=iOS' -derivedDataPath build CODE_SIGNING_ALLOWED=NO build
```

The development lock in models/phonon-lock.json contains all 538 candidates for reproducible whole-catalog testing; models/released-voices.json identifies the smaller approved set when candidates were excluded. Release packaging filters only from the exact tested candidate using tools/prepare_studio_ipa.py, matched native/ASR evidence and the approved manifest. Build-time downloads are development only. Runtime uses local model loading.

[Release notes](docs/RELEASE-NOTES-0.3.0.md) · [Current release]({verification['release']}). The previous working [101-profile 0.2.2 IPA](https://github.com/R347H4CK3R/Ghostline/releases/download/voicematrix-v0.2.2-expanded-1/VoiceMatrix-v0.2.2-experimental.ipa) is preserved.
"""
pathlib.Path('README.md').write_text(readme)
