# GHOSTLINE v0.10.0 — source-cleared Piper test bundles

## Scope and truthful count

The first experimental unsigned IPA with this manifest contains four **UNVERIFIED** synthetic voice models. It does **not** contain verified celebrity, actor, singer, film/TV, animation, or game voice identities. Four is an initial build budget, **not a library cap**: the embedded manifest and UI iterate dynamically. Neither checksum validation, CI, nor a speaker ID qualifies as iPhone/Strata-confirmed voice generation.

## Exact original sources, rights, and training chain

All four packs are from the publisher's `rhasspy/piper-voices` repository, pinned to revision `c10ece1aade47bb51c153c893d14e5bf8e5b7117`. The hosting repository publishes MIT terms, but **each MODEL_CARD controls dataset and model lineage**. The bundle includes each original MODEL_CARD, model ONNX, and model configuration, with exact byte size and SHA-256 pinned in `Ghostline/Resources/approved-piper-bundle.json`. Downloading or bundling is aborted if any byte differs.

| ID | Training data / original card | Lineage | Asset size (ONNX) |
| --- | --- | --- | ---: |
| `en_US-ljspeech-medium` | [Piper LJSpeech model card](https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/ljspeech/medium/MODEL_CARD), LJ Speech public-domain corpus | Trained from scratch | 63,531,379 bytes |
| `en_US-kristin-medium` | [Piper Kristin model card](https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/kristin/medium/MODEL_CARD), LibriVox public-domain recordings | Trained from scratch | 63,531,379 bytes |
| `en_US-norman-medium` | [Piper Norman model card](https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/norman/medium/MODEL_CARD), LibriVox public-domain recordings | Trained from scratch | 63,531,379 bytes |
| `en_GB-cori-medium` | [Piper Cori model card](https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_GB/cori/medium/MODEL_CARD), LibriVox public-domain recordings | Trained from scratch | 63,531,379 bytes |

The project also includes Piper runtime components, which have **GPL-3.0 obligations independent of the model-weight and corpus rights**. A private experimental IPA is not blanket authorization to redistribute binaries, use a speaker's real identity commercially, or make branded entertainment replicas. Treat those uses separately.

## Packaging and provenance audit

The opt-in build step downloads approximately **254.1 MB** of source-pinned ONNX models and small configs/cards into `build/embedded-piper`, validates SHA-256 and exact byte sizes, and copies the contents into the unsigned app's `PiperIncluded` resource directory. The same audit runs against the final app bundle before the IPA is assembled. No online inference API is called to generate speech; the bundled files are intended for offline use by the on-device Piper engine. CI source integrity is not proof that device inference succeeds.

No model weights are committed to Git, uploaded as individual public voice packs, or added to a public GitHub Release. Previously built IPAs and existing production branches are untouched.

## Device test steps

In Ghostline, open **Included Piper Test Voices** from Home or from Piper Test Lab. Pick any candidate, enable Airplane Mode (also disable Wi-Fi), enter a novel sentence, and tap **Generate and play local WAV**. Use the share/export option for its SHA-256 evidence JSON. Listen carefully for audible, intelligible playback and export the WAV. Check all four models separately, watch peak memory and thermal behavior, and confirm that no network requests occur. Human listening, full playback completion, true offline isolation, and any real-world identity claim remain separately unverified until explicitly supported by target-device evidence.

Test receipts intentionally contain `airplane_mode_confirmed: false`, `human_listening_confirmed: false`, and `authorized_identity_match_confirmed: false`. A successful CI build or WAV checksum must never flip these flags automatically.

## Intentionally excluded

`en_US-libritts_r-medium` has 904 speaker IDs and a CC BY 4.0 LibriTTS-R dataset, but its model card says it was **fine-tuned from Lessac medium**, whose Blizzard 2013 dataset carries narrower rights. Thus, the 904-ID candidate is not included in this four-pack **rights-cleared** bundle. The pre-existing separate Piper Test Lab can still inspect candidate metadata; this test IPA does not quietly represent 904 identities as authorized voices. Rights and technical compatibility must be checked independently.

No celebrity/character replication model is included without specific documented identity and voice-usage authorization.
