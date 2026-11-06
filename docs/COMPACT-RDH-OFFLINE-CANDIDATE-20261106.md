# Compact Flemish Piper variant — experimental only (2026-11-06)

This change extends the private-test unsigned IPA inventory from **10 candidate packs / 21 speaker slots** to **11 candidate packs / 22 source-declared speaker slots**. Neither count is a cap. **Zero voices have been verified on a physical iPhone/Strata device.**

## New rights-documented candidate

- ID: `nl_BE-rdh-x_low`; 16 kHz, one source-declared speaker slot; **UNVERIFIED_CANDIDATE**.
- Pinned upstream source: [original MODEL_CARD](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/nl/nl_BE/rdh/x_low/MODEL_CARD) from `rhasspy/piper-voices` (repository MIT license).
- Original dataset: [Dutch VL TTS](https://github.com/r-dh/dutch-vl-tts), declared **CC0 1.0 Universal**, with **trained from scratch** stated in the upstream model card. Same corpus as the separately bundled RDH medium model; a quality/size variant, **not a newly authenticated identity**.
- `.onnx`: 20,628,813 bytes; SHA-256 `fe43651248219b4e816e47d9708f2812f2a09af99470ed822113f3e913430d52`.
- `.onnx.json`: 4,158 bytes; SHA-256 `15724b7ef0247d566d9c2bac252c1b0b6ec9ceb7ccbb2c0a0d1ed57bf03b4f5d`.
- `MODEL_CARD`: 242 bytes; SHA-256 `93803121905ddba966ad0ea89fdf26b7e34f1f700c0c3bbbd504fdeaede98009`.
- Rights-review decision: `SOURCE_DOCUMENTED_EXPERIMENTAL_ONLY`. Does not grant rights to impersonate an identifiable person's voice, film/TV/game character, celebrity, actor or singer. Piper GPL-3.0 runtime obligations remain separate.

## Technical correction

SHA-256 verification of each bundled ONNX file now runs in a detached utility task instead of synchronously on the SwiftUI main actor. It still rejects missing assets and size/checksum mismatches before constructing PiperPlayer; pack switching remains disabled while generating. This is source-level hardening and must not be described as target-device performance or audio validation.

## Test gate

Source-rights checks and static code regressions run before packaging. GitHub Actions will checksum the complete model/config/card bytes and assemble an **unsigned IPA artifact only**. Test on the physical iPhone/Strata offline and export the SHA-bound listening receipt; the model remains UNVERIFIED until synthesis and audible playback are independently confirmed. Existing releases, quarantine holds, and private voice models remain unchanged.
