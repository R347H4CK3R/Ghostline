# GHOSTLINE RVC loopback and offline-network verification (experimental)

This is a **candidate-engine test plan**, not proof of verified voice identity, permission, offline synthesis, or successful Strata playback.

## Implementation

- iOS host binds an ephemeral TCP port to IPv4 loopback (`127.0.0.1`) only.
- The request-header buffer accepts fragmented TCP headers through the terminating CRLF-CRLF, with a 16 KiB ceiling and explicit rejection of incomplete/oversized requests.
- The bundled document receives a restrictive Content-Security-Policy. Network requests, worker scripts and models are permitted only from the app's same-origin loopback host or local `blob:`/`data:` resources where needed. Remote HTTPS/HTTP origins are not permitted by the CSP. `unsafe-eval` is retained to allow WebKit WebAssembly execution and is **not** equivalent to runtime security proof.
- `.pth` files remain in private app storage and are served only through a fresh unpredictable same-origin route with SHA-256 verification. The `.index` retrieval pipeline is **not** implemented and must not be labeled functional.
- CI executes deterministic HTTP fragment/boundary tests and source-contract checks for the CSP attachment. CI does not test actual WebKit policy enforcement.

## Required physical iPhone 16 Plus / Strata evidence

1. Install the **unsigned experimental IPA** through the intended private installation method. Do not replace previously working releases. Confirm the five-tab interface and app version.
2. Use an original, permitted RVC v2 pack with a recorded source URL, license grant or written permission; import `.pth` and optionally `.index`. Record the weight SHA-256. Check imported-pack verification with the native private integrity audit.
3. Supply a compatible lawful ContentVec model, RMVPE model and a non-sensitive test recording. Confirm the local worker initializes, produces a WAV, native replay starts, and manual listening confirms audible speech (not simply a valid RIFF header).
4. Disable Wi-Fi and cellular (and verify both remain off). Repeat step 3. In a separate controlled session while online, instrument WKWebView and verify remote `fetch`, image, worker and navigation requests are denied; confirm local WASM, model and audio access remain available.
5. Capture installed iOS version, Strata version, app commit, model/WAV SHA-256, memory peak, failures and duration. Redact filenames, paths, rights notes or voice recordings before sharing. Confirm the actual identity and individual use rights separately if claiming a real-world voice.
6. Keep **verified voice count zero** until authorized identity, target-device offline audio generation, playback/listening and independent perceptual evidence all exist. Candidate slots are not verified voices.

## Current state

Source implementation and CI tests are useful diagnostics, **not physical device verification**. This branch does not claim functioning offline RVC conversion, proof of CSP enforcement, authentic voices, or an implemented `.index` retrieval stage.
