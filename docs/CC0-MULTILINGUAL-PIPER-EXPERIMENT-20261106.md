# GHOSTLINE: CC0 multilingual Piper experiment (November 6, 2026)

## Status and scope

This private experimental build extends the five previous, SHA-256-pinned synthetic Piper candidates to **seven packaged model candidates** spanning English, Spanish, Dutch (Belgium), and Ukrainian. They expose **nine source-declared speaker slots**, NOT nine verified voices. The library has no preset pack/speaker-count ceiling; these are build-budget milestones, not limits.

**Target-device offline voices verified: 0.** CI, source attribution, checksum verification, and available speaker IDs are not evidence that offline audio runs or sounds correct on iPhone/Strata. All seven packs are explicitly **UNVERIFIED_CANDIDATE**, and no authentic actor, celebrity, TV, film, animation, singer or game identity is claimed. Nothing is intended for a public GitHub Release.

## Two new candidates and their source rights

**Flemish Dutch RDH (`nl_BE-rdh-medium`)**: source model card [rhasspy/piper-voices (pinned)](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/nl/nl_BE/rdh/medium/MODEL_CARD). Dataset [r-dh/dutch-vl-tts](https://github.com/r-dh/dutch-vl-tts) declared **CC0 1.0 Universal**; model card states trained from scratch. Model is **63,104,526 bytes**, SHA-256 `fb1a9d89ff53dbd510c5d10bd1365c36a5f76249c3ca603076646fd778003db1`. Source-pinned config declares Piper 0.2.0 and one speaker slot. Target iPhone compatibility remains untested.

**Ukrainian TTS (`uk_UA-ukrainian_tts-medium`)**: source model card [rhasspy/piper-voices (pinned)](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/uk/uk_UA/ukrainian_tts/medium/MODEL_CARD). Dataset [OHF-Voice/voice-datasets](https://github.com/OHF-Voice/voice-datasets) declared **CC0**; trained from scratch. Model is **76,735,663 bytes**, SHA-256 `7920419ac5f6fd8b6450520f24b52ed5a319cb53dd018fbcd71c9e079cbac84f`. Source config has **text phonemes** and three speaker slots (names Lada, Mykyta, Tetiana in the config, *not authenticated real identities*). This may require additional device compatibility work; it is UNVERIFIED.

All six new assets (two ONNX weights, JSON configs, and original MODEL_CARD texts) were independently downloaded from exact pinned upstream revision `c10ece1aade47bb51c153c893d14e5bf8e5b7117` and checked for size/SHA-256 on November 6. Their **full per-file sizes and hashes**, source paths, dataset links and rights statements are in `Ghostline/Resources/approved-piper-bundle.json`, delivered inside the IPA as `PiperIncluded/manifest.json`. The original cards and attribution notice are included too. The overarching voice repository identifies MIT terms; individual dataset/source rights and the Piper runtime's GPL-3.0 obligations remain separately applicable. CC0/MIT source records do **not** constitute permission to impersonate a living or famous person.

## Changes to safety and usability

The bundler accepts a dynamically sized, tightly path-validated model list, supports source-declared multi-speaker IDs, and rejects mismatching source license text, missing original model cards, altered files, or unexpected speaker counts. It intentionally does not ingest unspecified online voices or user-provided identities. The iOS UI offers a selector for multi-speaker slots and clears the previous WAV, playback flags and user-listening receipt when switching. Every exported test receipt now binds the selected speaker ID; no automatic verification is granted.

## Device validation still required

On an actual iPhone/Strata, install the private unsigned test IPA, disable Wi-Fi and cellular, synthesize new Dutch and Ukrainian sentences on every available slot, listen to completed native playback, and export the WAV plus SHA-bound diagnostic receipt. Monitor load failure, text phoneme support, memory, and identity provenance. Until that happens, all packs and slots remain unverified, and previously working builds/releases should remain unchanged.
