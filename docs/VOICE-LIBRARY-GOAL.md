# GHOSTLINE — Offline Voice Library Goal

## Product target

**Goal: 300–500+ genuinely functional, free, offline voices on iPhone, importable through Strata.** This is a target, not a statement of current availability. A *functional voice* is a distinctive voice/model configuration that produces audible, intelligible speech on the target iPhone after initial model setup with network disabled. Do not equate catalog entries, duplicated preset names or merely downloadable weights with functional voices.

## Requirements
- Zero required subscription fees, tokens, external API calls, or ongoing network use for speech generation.
- User need not record or supply a voice sample; ready-made redistributable voices must be prioritized.
- Model assets and per-voice licenses/attributions must be verified; respect noncommercial restrictions and voice-owner permissions.
- Device storage/memory use must be disclosed; support optional model/voice pack downloads and deletions, not a forced enormous IPA.
- Include searchable metadata: language, accent, model, license, installed state, download size, verified status.
- No false claims that a synthetic preset is an authentic actor, singer or fictional-character voice clone. Original 235-entry catalog remains reference-only until verified authorized identity models exist.
- Protect user privacy: offline inference with no generated speech or sample uploads.
- Voice count computed from a tested manifest, not from a marketing number. Count only voice+model pairs verified to generate distinct speech on iPhone.
- Verify unsigned IPA packaging, Strata import and first-run setup on device. Demonstrate airplane-mode speech after model preparation.

## Milestones
1. **Stable baseline:** successful iOS release build, app launch, local Apple device voices, local recording.
2. **Neural minimum:** integrate Kokoro and PocketTTS, compile with supported toolchain, verify on-device playback for available voice presets (estimated 72+ before de-duplication and license filtering).
3. **Voice packs:** integrate Piper (or another compatible ONNX/CoreML mobile engine) with model-card/license-aware manifests, downloads, local cache and per-pack smoke tests.
4. **300 verified voices:** automated manifest checks plus on-device sample tests, model provenance and app-side availability states.
5. **500+ stretch goal:** optional multilingual voice packs, memory/latency testing, storage management, regression testing, Strata compatibility.

## Definition of done
A release is only labeled **300 voices** or **500 voices** once that many specific voices have generated and played valid offline WAV samples on the target iPhone. Model discovery, repository file counts, Swift compilation or a catalog name do not satisfy this bar.

## Current status (November 2026)
Neural Kokoro/PocketTTS integration source has been committed; previous build attempts failed due to toolchain/dependency resolution and subsequent attempts require verification. Functional count on a real device has not been confirmed. The last independently verified IPA was the offline Apple-device-voice preview, not the final neural library.
