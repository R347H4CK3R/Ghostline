# GHOSTLINE: experimental Piper provenance gate and Greek CC0 candidate — 2026-11-06

## Scope

This draft advances the **experimental unsigned IPA only**. It does not alter production releases or introduce private RVC models, recordings, credentials, identity replicas or publicity-rights claims. The goal remains an **unbounded library**; pack counts describe this artifact, not a cap.

The bundle contains **10 candidate packs, 21 source-declared speaker slots, zero device-verified voices and zero identity-verified voices**. It substitutes one newly sourced Greek candidate for a Swedish model that requires provenance reconciliation.

## Added candidate: Greek

| Property | Source-verified value |
| --- | --- |
| Model ID | el_GR-rapunzelina-medium |
| Engine | Piper ONNX, Greek locale el_GR, source-declared single speaker |
| Original model card | [Pinned MODEL_CARD](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/el/el_GR/rapunzelina/medium/MODEL_CARD) |
| Model repository | [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices), pinned revision c10ece1aade47bb51c153c893d14e5bf8e5b7117, declared MIT |
| Original dataset | [Greek Single Speaker Speech Dataset](https://www.kaggle.com/datasets/bryanpark/greek-single-speaker-speech-dataset), Kyubyong Park |
| Dataset licence | **CC0: Public Domain** per original Kaggle dataset API and pinned Piper card |
| Training lineage | Original model card says **Trained from scratch** |
| Model ONNX | 62,950,044 bytes, SHA-256 3ca9fb3092215ee92edfc019b43feb0115ff4dfe638eb34474833ab1de840952 |
| Config JSON | 4,973 bytes, SHA-256 3a6182ec7c7550e14ef15e5d9badbb18f973a434086ac9658a1b10991fd192f8 |
| MODEL_CARD | 276 bytes, SHA-256 dc69f15382dabed061fa8d31b65c14e5c4b57ba2fe6906012c756478da156b50 |
| Runtime verification | **UNVERIFIED_CANDIDATE**. No target iPhone/Strata synthesis, listening or compatibility evidence. |

File sizes and SHA-256 were calculated over pinned Hugging Face downloads. The model config declares num_speakers = 1 and phoneme_type = espeak. Actual iPhone Greek phonemization and playback have **not** been proved. The upstream name does **not** establish a real person's identity, actor/celebrity endorsement, character voice or singer rights.

## Quarantined: Swedish NST

sv_SE-nst-medium is **excluded from the next IPA's bundle**. Its pinned upstream MODEL_CARD cites sbr-17 (NST Swedish Dictation), whereas the [KBLab author report (May 24, 2023)](https://kb-labb.github.io/posts/2023-05-24-swedish-text-to-speech/) attributes training to sbr-18 (a separate single-speaker speech-synthesis corpus). The original catalogue sbr-18 URL currently returns 404. Third-party catalogue summaries report CC0, but the authoritative corpus record was not retrievable for independent reconciliation. **Do not claim independently cleared Swedish corpus provenance.**

Original exact model/card/config IDs, licence claims, sizes and hashes are retained in Ghostline/Resources/quarantined-piper-candidates.json as a **metadata-only** ledger. It contains no model files. Older experiments remain unchanged.

## Reproducible safeguards

- Every bundled model carries rights_review.decision = SOURCE_DOCUMENTED_EXPERIMENTAL_ONLY, source evidence URLs, review date, and explicit false identity authorization/device-generation flags.
- The fail-closed scripts/test_embedded_piper_rights_review.py runs before downloading any ONNX in Actions; the bundle builder also rejects overlap with the quarantine ledger.
- All source assets are pinned by immutable source revision, byte count and SHA-256. The manifest, original model cards and attribution ship within the IPA. A passing SHA or CI build does **not** prove a legitimate identity, fidelity, phonemization or offline iPhone playback.
- Piper runtime has separate GPL source-distribution obligations. Restrict to experimental private installation; do not publish private voice packs or promote models to production without legal and device evidence.

For each slot: install the new unsigned IPA; disconnect network; synthesize and replay on the target iPhone/Strata host; export SHA-bound WAV and local diagnostic receipts; independently listen and document permission before claiming any verification.
