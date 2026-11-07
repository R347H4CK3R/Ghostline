# VoiceMatrix

Native ARM64 iOS offline voice studio for iPhone, LiveContainer and Strata. This branch is an experimental implementation, not a verified release.

## Implemented
- Beginner Home with Make Speech and Change My Voice, plus Voices, Saved, Help and Settings.
- Shared Phonon 31m Core ML engine through pinned FluidAudio; direct local loading, no runtime model downloads or system speech fallback.
- 37 bundled English profile candidates (12 US, 13 UK, 12 original character performances), around 9.5 MB of profile data; complete model assets about 144 MB before packaging.
- WAV generation with finite/sample-energy/decode checks, cancellation, selected-profile previews, search, favorites and recently used filtering.
- Private recording/import, playback, save/share/rename/delete. Neural speech-to-speech conversion is **not implemented**.
- Hash-locked assets, pinned dependency and model revision, archive inspection and experimental build workflow.

## Honest verification status
- Asset integrity tests: run `python3 -m unittest discover -s tests -v`.
- Bundle: `python3 tools/assets.py`; inspect: `python3 tools/assets.py --verify`.
- 37 different embedding checksums do not establish perceptual distinctness or quality.
- Physical-device-verified voices: 0. Authorized recognizable likenesses: 0.
- Core ML speech generation, WAV decoding and file tests passed on a hosted Apple simulator. Airplane Mode, installation, microphone and UI still need physical-device execution.
- Engine choice is provisional pending comparative iPhone load-time, peak-memory and audio-quality measurements.
- No near-indistinguishable quality claim. 500+ remains the expansion target; no renamed DSP copies are counted.

## Build
macOS with Xcode supporting iOS 26+, Swift 6 and XcodeGen:

```
python3 tools/assets.py
xcodegen generate
xcodebuild -project VoiceMatrix.xcodeproj -scheme VoiceMatrix -sdk iphoneos -destination 'generic/platform=iOS' -derivedDataPath build CODE_SIGNING_ALLOWED=NO build
```

Build-time downloads are development only. Complete assets are copied inside the IPA; initialization calls FluidAudio's local `load(from:)`, never its download-enabled `initialize()`.

No release URL or installation-source entry is published until an actual IPA has passed archive inspection. Previous releases are preserved.

## Verified experimental release

[Download VoiceMatrix 0.2.0 experimental](https://github.com/R347H4CK3R/Ghostline/releases/tag/voicematrix-v0.2.0-experimental-20). Ten Python checks and five native tests passed. The CPU simulator smoke test generated 2.24 seconds of non-silent, decodable WAV audio for en_us_Zoey in 3.223 seconds including loading. This is one automated profile check, not verification of all 37 voices or iPhone performance.

[LiveContainer source](https://raw.githubusercontent.com/R347H4CK3R/Ghostline/main/source.json) · [Strata source](https://raw.githubusercontent.com/R347H4CK3R/Ghostline/main/strata-source.json). Feeds are published; installation remains untested on physical devices.

## Runtime compatibility

The hosted Xcode 16.4 / older iOS simulator timed out inside local Core ML model loading. The same pinned model and code passed synthesis on the macOS 26 runner. VoiceMatrix 0.2.1 therefore targets iOS 26 and later; physical iPhone testing is still pending.
