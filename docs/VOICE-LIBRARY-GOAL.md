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

## Current status (November 5, 2026)

- **iOS compile/package milestone:** GitHub Actions [run 42124743868](https://github.com/R347H4CK3R/Ghostline/actions/runs/42124743868) succeeded at commit `9843f7e`. Unsigned IPA artifact contains `GHOSTLINE.app`, Piper dependencies, the eSpeak resource bundle and candidate metadata.
- **Candidate discovery:** 178 Piper models and 543 candidate speaker slots in the catalog; featured LibriTTS-R medium model config has 904 IDs (the source index incorrectly says 2,306); the UI offers an automated 500-ID trial. Both model and config asset checksums were corrected and pinned on the experimental branch.
- **Verified offline voices on the user's real iPhone:** **0 documented**. No iPhone-generated audio or independent airplane-mode test has been received. This does not mean no voices can work; it means none can responsibly be counted yet.
- **Next gate:** Install an experimental IPA on the iPhone through the authorized importer, download/checksum the optional Piper model, disable network connectivity, generate/play WAV samples and export an on-device test record. Assess waveforms and listening quality before counting distinct voices. Apple system voices and candidate metadata do not count toward the Piper goal.
- **Release stability:** Leave existing preview releases untouched while using a separate experimental build for evidence export and safer decoded PCM verification. Do not rebrand a 500-voice release solely on a green build.
