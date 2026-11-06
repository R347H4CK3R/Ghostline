# Experimental rights-traced derivative Piper packs (2026-11-06)

This branch builds on the draft RVC background-I/O experiment (PR #24). Existing releases are unchanged. Two more original, source-documented **UNVERIFIED** Piper model candidates are added; their model/config/MODEL_CARD byte lengths and SHA-256 hashes are pinned in the approved manifest at upstream revision `c10ece1aade47bb51c153c893d14e5bf8e5b7117`.

| Candidate | Source-declared corpus rights | Source-declared base checkpoint | Source model card |
|---|---|---|---|
| `en_US-john-medium` | LibriVox / public domain | `en_US-kristin-medium` (already bundled, scratch-trained on public-domain LibriVox) | https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/en/en_US/john/medium/MODEL_CARD |
| `nl_NL-alex-medium` | OHF-Voice dataset / CC0 (per upstream card) | `nl_BE-rdh-medium` (already bundled, scratch-trained on source-reported CC0 Dutch recordings) | https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/nl/nl_NL/alex/medium/MODEL_CARD |

The pack bundler checks a fixed, reviewable allowlist of source-card parent phrases and requires a source-cleared, scratch-trained included parent. It **fails closed** for any unreviewed derivative or mismatched model card. The same two parent mappings are checked by static regression tests, build gates and the iPhone runtime. Upstream repository declares MIT model-repository licensing; the native Piper engine has separate GPL-3.0 obligations.

This is provenance review, **not independent verification of speaker consent, voice identity, or on-device inference**. The model name John/Alex identifies upstream candidate labels, not proven human identities or permission for voice impersonation. No actor, singer, celebrity, character, film, TV or game identity replicas are bundled. Keep artifacts as experimental, not public releases.

Inventory: **13 bundled candidate model variants, 24 source-declared speaker slots, 0 device-verified voices, 0 verified human identities**. Model variants and slot counts are not unique verified individuals. Offline iPhone/Strata generation, completed playback, listening, and isolation evidence remain required before any verified count.
