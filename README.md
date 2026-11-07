# VoiceMatrix

Native ARM64 iOS offline voice studio for iPhone, LiveContainer and Strata. Experimental releases include automated simulator evidence; physical iPhone verification is pending.

## Implemented
- Beginner Home with Make Speech and Change My Voice, plus Voices, Saved, Help and Settings.
- Shared Phonon 31m Core ML engine through pinned FluidAudio; direct local loading, no runtime model downloads or system speech fallback.
- 101 bundled profiles (12 US, 13 UK, 12 original character performances, 64 additional source-locale profiles tested on English speech), around 25.9 MB of profile data; complete model assets about 160 MB before packaging.
- WAV generation with finite/sample-energy/decode checks, cancellation, selected-profile previews, search, favorites and recently used filtering.
- Private recording/import, playback, save/share/rename/delete. Neural speech-to-speech conversion is **not implemented**.
- Hash-locked assets, pinned dependency and model revision, archive inspection and experimental build workflow.

## Honest verification status
- Asset integrity tests: run `python3 -m unittest discover -s tests -v`.
- Bundle: `python3 tools/assets.py`; inspect: `python3 tools/assets.py --verify`.
- Different embedding checksums do not establish perceptual distinctness or quality.
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

## Current expanded release

Version 0.2.2 includes **101** actual bundled conditioning profiles, with 101 successful native synthesis checks. The 65 new candidates each generated two English sentences; 64 met the independent ASR/no-clipping gate and one was excluded. Native synthesis evidence comes from [run 42389360824](https://github.com/R347H4CK3R/Ghostline/actions/runs/42389360824), whose five tests passed; subsequent packaging failed on Unicode filename normalization. [Run 42390971417](https://github.com/R347H4CK3R/Ghostline/actions/runs/42390971417) repaired packaging and retained all 167 original test WAVs without changing the compiled app source.

[Approval record](models/expansion-approval.json) · [Full candidate ASR results](docs/qa/0.2.2-asr-intelligibility.json) · [Numerical conditioning duplicate screen](models/conditioning-duplicate-screen.json). These are automated checks, not listening, perceptual distinctness or likeness-quality scores. The unsigned candidate was downloaded and inspected independently; the approved catalog excludes Rebeca. The release workflow filters and checks the approved archive before publication.

[LiveContainer source](https://raw.githubusercontent.com/R347H4CK3R/Ghostline/main/source.json) · [Strata source](https://raw.githubusercontent.com/R347H4CK3R/Ghostline/main/strata-source.json). The previous [0.2.1 IPA](https://github.com/R347H4CK3R/Ghostline/releases/download/voicematrix-v0.2.1-experimental-24/VoiceMatrix-v0.2.1-experimental.ipa) is preserved. Physical per-profile verification and controlled human listening remain pending.

## Runtime compatibility

The hosted Xcode 16.4 / older iOS simulator timed out inside local Core ML model loading. The same pinned model and code passed synthesis on the macOS 26 runner. VoiceMatrix 0.2.1 therefore targets iOS 26 and later; physical iPhone testing is still pending.

## Additional automated intelligibility check

Independent development-only whisper.cpp tiny.en transcription matched the six reference words for **36 of 37** retained simulator recordings, ignoring punctuation and case. `characters_Azgorath` was transcribed as “Hello. This is a boy’s test.” and needs a listening review. This one-sentence check is not a general intelligibility, naturalness, similarity or perceptual-distinctness score. [Per-profile results and exact model/source hashes](docs/qa/0.2.1-asr-intelligibility.json) are retained. No listening verification count was increased.

Reproduce with NumPy and SciPy installed, the retained QA WAV artifact from build 42338999926, an official whisper.cpp checkout/binary and the tiny.en model matching the report checksum:

```sh
python3 tools/asr_qa.py /path/to/qa-audio --output /path/to/results --whisper-cli /path/to/whisper-cli --model /path/to/ggml-tiny.en.bin --whisper-source /path/to/whisper.cpp
```
