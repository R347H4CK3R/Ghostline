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
- Core ML synthesis, Airplane Mode, installation, microphone and UI require Apple/device execution. Linux source checks do not verify those.
- Engine choice is provisional pending comparative iPhone load-time, peak-memory and audio-quality measurements.
- No near-indistinguishable quality claim. 500+ remains the expansion target; no renamed DSP copies are counted.

## Build
macOS with Xcode supporting iOS 18+, Swift 6 and XcodeGen:

```
python3 tools/assets.py
xcodegen generate
xcodebuild -project VoiceMatrix.xcodeproj -scheme VoiceMatrix -sdk iphoneos -destination 'generic/platform=iOS' -derivedDataPath build CODE_SIGNING_ALLOWED=NO build
```

Build-time downloads are development only. Complete assets are copied inside the IPA; initialization calls FluidAudio's local `load(from:)`, never its download-enabled `initialize()`.

No release URL or installation-source entry is published until an actual IPA has passed archive inspection. Previous releases are preserved.
