# GHOSTLINE experimental CC0 expansion — November 6, 2026

This experimental branch adds **three locally bundled Piper candidate packs** to the prior seven-pack IPA. The resulting bundle contains **10 model-pack candidates and 21 source-declared speaker slots**, with **0 iPhone/Strata device-verified audio voices** and **0 authenticated named identities**. All entries remain `UNVERIFIED_CANDIDATE`. The full library and import paths have **no preset numerical cap**; counts here describe one test IPA, not a limit.

## Rights and source evidence

The weight repository [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices) declares MIT; each original `MODEL_CARD` and model/config files are bundled and SHA-256 pinned to revision `c10ece1aade47bb51c153c893d14e5bf8e5b7117`. **Individual CC0 recordings and Piper's GPL-3.0 runtime obligations are separate.** A CC0 training dataset permits data use, but does **not establish consent to market or impersonate a named person's identity**.

| Added model ID | Size of ONNX weights | Declared slots | Card / source |
| --- | ---: | ---: | --- |
| `no_NO-nvcc-medium` | 76,770,227 bytes | 10 | [Pinned source card](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/no/no_NO/nvcc/medium/MODEL_CARD); [National Library of Norway NVCC corpus, CC0](https://www.nb.no/sprakbanken/en/resource-catalogue/oai-nb-no-sbr-75/) |
| `nl_BE-nathalie-x_low` | 20,628,813 bytes | 1 | [Pinned source card](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/nl/nl_BE/nathalie/x_low/MODEL_CARD); [original dataset, CC0 1.0](https://github.com/rhasspy/dataset-voice-nathalie) |
| `sv_SE-nst-medium` | 63,104,526 bytes | 1 | [Pinned source card](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/sv/sv_SE/nst/medium/MODEL_CARD); [Swedish NST source catalogue](https://www.nb.no/sprakbanken/en/) |

The Norwegian NVCC source confirms CC0 and records speech from 11 human contributors; its Piper ONNX config exposes **10 speaker identifiers**, not independently authenticated persons. The Dutch dataset is CC0 and is described as a recording of a female speaker; its dataset name must **not** be construed as authorization for a named-person identity replica. The Swedish model card states CC0, trained from scratch by KBLab; however, the precise original `sbr-17` URL in the card currently does not resolve, so Swedish corpus-level attribution needs independent reconciliation before any public distribution. These three models are available **only for controlled candidate testing** and are not identity-verified.

## Integrity, UI and device testing

For every new and previous model, `Ghostline/Resources/approved-piper-bundle.json` contains **exact model ID, language, provenance, license, full source paths, sizes and SHA-256 of ONNX/config/card**. The build downloads from immutable revision paths, independently hashes each asset, verifies config speaker counts and card contents, and bundles original attribution plus a copy of the manifest into the IPA. Model weights are not added to Git. Do not place private RVC `.pth/.index` identity files into Actions or public releases.

In app: choose an included Piper model and **each distinct selected speaker ID**, generate offline (all networking disabled), listen to the entire native playback, export SHA-bound WAV/receipt and observe memory/error logs. Changing speaker ID invalidates prior WAV/listening evidence. On-device inference, phonemizer coverage, 10-speaker selector usability, offline playback and audible voice quality remain **untested**. Do not mark any candidate verified based on the packaged ONNX, a GitHub Actions success, or desktop output. Keep branch and IPA experimental until a target iPhone/Strata test proves generation and listening.
