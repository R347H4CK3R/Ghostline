# VoiceMatrix

Native ARM64 iOS offline voice studio for iPhone, LiveContainer and Strata. Experimental releases include automated simulator evidence; physical iPhone verification is pending.

## Implemented
- Beginner Home with Make Speech and Change My Voice, plus Voices, Saved, Help and Settings.
- Shared Phonon 31m Core ML engine through pinned FluidAudio; direct local loading, no runtime model downloads or system speech fallback.
- 37 bundled English profiles (12 US, 13 UK, 12 original character performances), around 9.5 MB of profile data; complete model assets about 144 MB before packaging.
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

[Download VoiceMatrix 0.2.1 experimental](https://github.com/R347H4CK3R/Ghostline/releases/download/voicematrix-v0.2.1-experimental-24/VoiceMatrix-v0.2.1-experimental.ipa). Code commit `1879bb369de57c65e37943890df4d471e20651fd`; [successful build and tests](https://github.com/R347H4CK3R/Ghostline/actions/runs/42338999926). Seventeen Python checks and five native tests passed. All 37 profiles generated non-silent, decodable WAV audio on a hosted Apple simulator (94.676 seconds for the profile loop). The IPA was downloaded and independently inspected for ARM64, bundle identity, version, icon, complete asset hashes and matching per-profile synthesis evidence.

IPA: 128,442,096 bytes; SHA-256 `8317973747f4bfb10f162e67828521f3a7b67c96e6fb647f3e6874b68e905f1f`.

Automated synthesis checks: **37/37**. Human listening validation: **0**. Physical-device validation: **0**. Authorized recognizable likenesses: **0**. These tests establish working synthesis and valid audio, not near-indistinguishable quality or perceptual distinctness. The complete runtime and profiles are bundled; physical Airplane Mode and host installation tests remain pending. Genuine voice conversion is not yet available in this release. The previous 0.2.0 release is preserved.

[LiveContainer source](https://raw.githubusercontent.com/R347H4CK3R/Ghostline/main/source.json) · [Strata source](https://raw.githubusercontent.com/R347H4CK3R/Ghostline/main/strata-source.json). Feeds are published; installation remains untested on physical devices.

## Runtime compatibility

The hosted Xcode 16.4 / older iOS simulator timed out inside local Core ML model loading. The same pinned model and code passed synthesis on the macOS 26 runner. VoiceMatrix 0.2.1 therefore targets iOS 26 and later; physical iPhone testing is still pending.

## Additional automated intelligibility check

Independent development-only whisper.cpp tiny.en transcription matched the seven reference words for **36 of 37** retained simulator recordings, ignoring punctuation and case. `characters_Azgorath` was transcribed as “Hello. This is a boy’s test.” and needs a listening review. This one-sentence check is not a general intelligibility, naturalness, similarity or perceptual-distinctness score. [Per-profile results and exact model/source hashes](docs/qa/0.2.1-asr-intelligibility.json) are retained. No listening verification count was increased.

Reproduce with NumPy and SciPy installed, the retained QA WAV artifact from build 42338999926, an official whisper.cpp checkout/binary and the tiny.en model matching the report checksum:

```sh
python3 tools/asr_qa.py /path/to/qa-audio --output /path/to/results --whisper-cli /path/to/whisper-cli --model /path/to/ggml-tiny.en.bin --whisper-source /path/to/whisper.cpp
```
