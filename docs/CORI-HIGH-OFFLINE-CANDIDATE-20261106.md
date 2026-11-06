# Experimental Cori high-quality Piper candidate — 2026-11-06

This experimental change adds **en_GB-cori-high** to the privately distributed unsigned iPhone/Strata test artifact. The upstream source/model card describes a British English female voice trained **from scratch** for 500 epochs using about 24 hours of public-domain LibriVox audio. The Piper voice repository declares **MIT**. Source-declared rights allow an experimental *synthetic voice candidate*, but they do **not** authorize impersonation of a movie character, actor, singer, celebrity, or identifiable person.

This is the **high-quality variant of the already bundled Cori medium voice**, not a new person, novel identity, or distinct validated voice. It adds one model candidate and one *source-declared speaker slot*, with no arbitrary library cap. All candidates remain **UNVERIFIED** until successful target-iPhone/Strata airplane-mode waveform generation, completed playback, human listening, and separate identity/rights evidence.

## Immutable source and hashes

Repository: https://huggingface.co/rhasspy/piper-voices
Revision: `c10ece1aade47bb51c153c893d14e5bf8e5b7117`
Upstream model card: https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/en/en_GB/cori/high/MODEL_CARD
Training-data source: https://librivox.org
Model repository license: MIT (source-declared).
Training-data license: public domain (source-declared).
Model lineage: trained from scratch; not a derivative of a restricted Lessac/Ryan model.

| Pinned file | Exact bytes | SHA-256 |
| --- | ---: | --- |
| en_GB-cori-high.onnx | 114,219,352 | `470b4dd634c98f8a4850d7626ffc3dfc90774628eeef6605a6dd8f88f30a5903` |
| en_GB-cori-high.onnx.json | 4,963 | `9e7fb5b5671612c22f3c81cbe46c1ae87b031a4632bcb509e499dad6f1e2adec` |
| MODEL_CARD | 468 | `136e7bd168b6c35b4a5df01a0253297e5773b5775ceae0af5160f264aa58208f` |

Additional unpacked payload: **114,224,783 bytes** (approximately 109 MiB) plus application/archive overhead. The existing release remains unchanged. Experimental GitHub Actions artifacts only; no private celebrity/RVC checkpoint or token is bundled. Piper runtime GPL-3.0 distribution obligations still apply separately.

## Tests and limits

The manifest is reproducible and requires exact file byte counts and SHA-256 checks before use. Source rights, derivative lineage, private import, source recording handoff and synthetic speaker receipts are covered by non-device regression tests. A successful CI build is **not** iPhone audio evidence; current target-device verified voice count remains **0**. RVC FAISS retrieval and PocketTTS/Kokoro on-device synthesis are not established by this change.

Swedish NST remains quarantined because source-card/dataset provenance disagrees. All character/celebrity/actor/singer models without independently documented identity usage rights remain excluded.
