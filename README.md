# VoiceMatrix

## Character-replica objective — source development

The current IPA contains 12 original character performances and 525 other speakers, with **0 verified recognizable character replicas**. Its 537-profile count is a functional speech-library milestone, not completion of the 500-character-replica objective. Character resemblance, naturalness and perceptual distinctness still need reference-based listening tests.

Source development now separates **Character styles**, **Replicas**, and **Other speakers** in the voice picker, defaults browsing to character styles, and searches target/franchise names and overlapping genres when identity metadata exists. Replica entries require named targets, reference checksums and authorization-record paths; those records require human source/rights review and do not establish resemblance. No existing ordinary voice is renamed as a replica. These UI changes are source-only until a future compiled release; the 0.3.0 IPA and installation feeds remain unchanged.

Native ARM64 offline English voice studio for iPhone, LiveContainer and Strata. Current experimental version: **0.3.0 build 5**, iOS 26 or later.

[Download the inspected unsigned IPA](https://github.com/R347H4CK3R/Ghostline/releases/download/voicematrix-v0.3.0-studio-1/VoiceMatrix-v0.3.0-experimental.ipa) · [LiveContainer source](https://raw.githubusercontent.com/R347H4CK3R/Ghostline/main/source.json) · [Strata source](https://raw.githubusercontent.com/R347H4CK3R/Ghostline/main/strata-source.json)

## Rick and Morty development experiment

A two-identity **CPU RVC experiment** now produces labeled Rick Sanchez and Morty Smith AI-imitation WAVs. Eight parameter/sentence trials generated non-silent, unclipped audio, preserved source duration within 150 ms, and independently transcribed with zero word errors on the two short test sentences. This tests intelligibility, not likeness. Multiple trials do not count as extra voices.

[Measured experiment](docs/qa/rick-morty-rvc-prototype.json) · [Independent transcription](docs/qa/rick-morty-rvc-asr.json) · [Run and labeled audio artifacts](https://github.com/R347H4CK3R/Ghostline/actions/runs/42406774670). `tools/prototype_rick_morty.py` is development-only and uses real neural target checkpoints, not renamed system voices. Candidate weights are downloaded only for the experiment and are not committed or distributed with the app. Torch loading remains restricted to weights-only; retrieval indices are not executed or loaded. The source, encoder, target archives and test inputs are pinned or hash-checked.

**Not integrated into iOS.** This experiment does not enable the profiles in VoiceMatrix, establish recognizable-likeness authorization, or verify perceptual resemblance/naturalness. Native inference conversion, device performance and reference-based listening remain incomplete. The public 0.3.0 IPA and feeds are unchanged; no IPA was built for this experiment.

## Included functionality

- **537 neural conditioning profiles**, with 537 distinct conditioning hashes. Different source speakers and numerical duplicate checks support this library; perceptual distinctness remains unverified by human listeners.
- Shared local Phonon 31m speech, plus one shared OpenVoice V2 converter. 100 direct Phonon profiles and 437 reference-derived profiles rendered through the converter.
- Make Speech: choose, type, Speak, Listen, Save and Share WAV. Longer text uses bounded generation chunks. Selected-voice previews use actual inference.
- Change My Voice: record or import audio up to 10 seconds, choose, Convert, Listen, Save and Share. This is offline neural speech-to-speech conversion, not a real-time microphone effect.
- Search, categories, favorites, recently used voices, selected indicators and private saved recordings with rename/delete/share.
- Beginner screens, clear cancellation/errors, microphone/session ownership and exportable diagnostics without automatic text/audio uploads.
- Complete runtime, weights, target profiles and notices bundled. No runtime downloads, server, login, paid API or default system-voice substitution.

## Categories

Categories overlap; each profile counts once. Vocal-depth groups use measurements from reference QA clips and are broad browsing aids. Character categories describe original styles, without official character or performer claims.

| Category | Included profiles |
|---|---:|
| Animation & Cartoon Styles | 4 |
| Cinematic & Narration | 3 |
| Community Voices | 226 |
| Everyday & Conversation | 525 |
| Everyday Voices | 25 |
| Fantasy & Characters | 12 |
| Gaming Characters | 5 |
| Higher Voices | 37 |
| Horror & Monsters | 6 |
| International Voices | 64 |
| Lower Voices | 339 |
| Midrange Voices | 160 |
| Original Voices | 537 |
| Studio Voices | 210 |

## Evidence and limits

The final source and packaging regressions passed in GitHub Actions. All 538 candidate profiles underwent native simulator speech and conversion checks, plus varied English where required. Independent recognition examined 1577 actual native WAVs, without a reference prompt or constrained vocabulary; 1576 clips passed the <=10% word-error, non-silence and no-full-scale gate. Only profiles passing every required clip were retained. Larger-model retries and all attempts are recorded.

The exact inference fingerprint binds model files, target profiles, routing, source and dependency identity. The ARM64 app and simulator tests share the same compiled asset archive. Final packaging preserves the executable and approved model/profile bytes, checks metadata/icon/ARM64, and downloads the published IPA for repeated SHA/archive/asset inspection. IPA: 205,958,246 bytes; SHA-256: `9d6a48ef402d76162ef04f3f653f151d0413605e97575397cad86027fe5ad951`.

[Approved released manifest](models/released-voices.json) · [Category/approval summary](docs/qa/0.3.0-catalog-summary.json) · [Native evidence](docs/qa/0.3.0-native-results.json) · [Independent ASR evidence](docs/qa/0.3.0-asr-intelligibility.json) · [Published archive check](docs/qa/0.3.0-release-verification.json). Raw native QA WAVs are archived separately with the release for future listening, rather than bloating the installed app.

Automated checks establish generation, decoding and short-clip intelligibility. **Physical per-profile verification: 0 recorded. Controlled listening verification: 0. Authorized recognizable likeness models: 0.** No near-indistinguishable, official-character, naturalness or listener-similarity claim is made. Memory samples come from the hosted simulator, not physical iPhone peak memory. Airplane Mode, host-container microphone behavior, latency, battery and listening remain device-test work.

104 profiles are marked noncommercial-only in the picker. Source recordings, model code, model weights and likeness permissions are tracked separately in bundled provenance and notices. Donated, licensed and original recordings are used; no scraped celebrity recordings or hosted proprietary models are bundled.

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

[Release notes](docs/RELEASE-NOTES-0.3.0.md) · [Current release](https://github.com/R347H4CK3R/Ghostline/releases/tag/voicematrix-v0.3.0-studio-1). The previous working [101-profile 0.2.2 IPA](https://github.com/R347H4CK3R/Ghostline/releases/download/voicematrix-v0.2.2-expanded-1/VoiceMatrix-v0.2.2-experimental.ipa) is preserved.
