# GHOSTLINE experimental v0.9.5 — conversion-attempt evidence

A WebKit RVC generation attempt is **not** an authenticated identity or an on-device inference success merely because the app compiled or received a JavaScript callback.

## Why this change exists

Previously, starting a new conversion left the previous native WAV, playback-completion flag, and user listening acknowledgment visible until the *next WAV passed validation*. If the new generation failed, returned invalid bytes, or delivered late asynchronous FileReader results, stale evidence could be confused with the latest attempt.

The browser now clears its old preview and download link, issues a random conversion ID, and sends `conversion_started` before attempting inference. The Swift controller invalidates the previous player, WAV link, SHA evidence, completed playback state, and listening acknowledgment on every valid new attempt. Only WAV messages carrying the active ID are eligible for validation and storage. Duplicate or late exports are rejected. Leaving the screen cancels the active attempt ID.

## Reproducible regression checks

`python scripts/test_rvc_playback_evidence.py` checks the JavaScript/native bridge's attempt-ID contract, browser-link clearing, and native evidence invalidation. `python scripts/test_private_rvc_pack_bridge.py` checks the imported-weight integrity bridge. Full CI builds the arm64 iOS app, bundled offline runtime and IPA.

These source-contract checks do **not** replace physical iPhone/Strata testing. A valid target-device test should import an authorized model, generate WAV with cellular/Wi-Fi disabled, independently inspect the exported audio and SHA-256, replay it completely in the native player, and examine the private diagnostic JSON for the corresponding conversion attempt ID. A second generation that fails must not inherit the first generation's playback or listening flags.

## Still not verified

- No physical target-device inference, audio listening, or airplane-mode testing has been performed by this CI change.
- No voice is authenticated as a specific actor, singer, celebrity, or character.
- RVC `.index` retrieval is not implemented.
- No private voice pack, raw recording, or identity model is included in the IPA.
