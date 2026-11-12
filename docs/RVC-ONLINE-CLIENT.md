# RVC online client source

This is **unreleased, locally integrated client source**, not a verified iPhone feature or an offline RVC runtime. App.swift now owns an RVCOnlineStudio and adds a separate Laptop RVC destination. Existing F5 paths, voice catalogs, downloaded voices and recordings are not replaced. Do not release this integration with the independently verified log-only build without compiling and testing the combined source.

## Contract and integration

- `RVCOnlineConnection.paired()` captures the existing HTTPS laptop origin and optional keychain pairing token. Missing tokens use the existing same-owner Tailscale authentication, not anonymous access to a new service.
- `catalog()` retrieves `/rvc/models`. Catalogs claiming offline RVC, RVC text-to-speech, verified identity or verified likeness are rejected. An empty unavailable catalog is valid. Catalogs are bounded to 64 distinct models and 1 MiB.
- `RVCOnlineConnection.request(model:wav:)` validates mono PCM16 RIFF/WAV, 0.2–30 seconds and at most 3 MiB, rejects silent or full-scale-clipped input, hashes its exact bytes, assigns a lowercase UUID and pins the selected model/index/revision. Accepted input rates are 16000, 22050, 24000, 32000, 40000, 44100 and 48000 Hz. The JSON upload is bounded to 4 MiB + 4096 bytes, with base64 slashes left unescaped so valid maximum-size WAV files fit. It does not resample or synthesize speech.
- `RVCOnlineSession.submit` uploads only after checking the current catalog still contains those exact weights. `refresh` checks the same immutable job and retrieves output on success. Call `refresh` periodically only while a job is active; it is a single bounded request, not an unbounded background poller.
- `cancel` invalidates local work first, then requests server cancellation. A network failure becomes `cancellationUnconfirmed`, never a false cancelled result. `disconnect` cancels local work and retains the job identity for a later status check; it does not claim the laptop stopped. If a submission remains uncertain, explicit `retrySubmission` reuses the exact request ID and bytes. It is blocked after cancellation is requested.
- Generation checks suppress responses from superseded uploads, polls and downloads. A successful laptop job discovered after the owner requested cancellation is `completedBeforeCancellation`, with no audio published.
- Conversion receipts must echo the request ID, model ID, model/index/revision/input SHA-256. Results must have matching bytes, receipt digest, HTTP digest header, mono PCM16 WAV, duration and 40 kHz rate.
- All HTTP responses are streamed under explicit byte bounds. Redirects, cookies, ambient credentials and cache reuse are disabled. Error pages and unexpected content types are rejected before parsing. Requests have bounded timeouts and cancellation invalidates their URLSession.

The connection sends raw input speech only to the already paired laptop. Call it only for an owner-requested online conversion and label the feature **Online RVC conversion**. Do not route text synthesis into this API or relabel F5 references as RVC models. Publication remains a separate approval and verification step.

## Checks and limits

`python3 -m unittest tests.test_rvc_online_native -v` runs the real Swift catalog/WAV/receipt/session checks when `swiftc` exists, or explicitly skips without a compiler. `VoiceMatrixTests/RVCOnlineConnectionTests.swift` adds native CryptoKit integrity and safe-origin checks to the existing Xcode unit-test target. No compiler pass, iOS execution, real-laptop inference or physical-device check is claimed by these source files.

Before release, compile the production iOS target and run both native suites on an Apple executor, then test actual HTTPS authentication, interrupted upload/poll/download, cancellation during processing, reconnect and a real validated RVC model. The source alone is not evidence of working voice conversion or character likeness.

## Integrated screen and remaining verification

The screen requires an explicit Send tap before uploading a selected bounded WAV. App-owned state retains the same request and paired origin across Back/foreground transitions. Automatic checks are nonoverlapping and no more frequent than every 30 seconds while the screen is active. Server activity and the local last-successful check are separate values. Successful audio is checksum-verified again before a temporary playback file is created. Stop tracking requires an explicit warning and does not cancel the laptop job.

An observation ownership token prevents a superseded navigation task from clearing visibility or suspending a replacement screen. Deterministic token checks are included in the native contract runner; a Python source-wiring regression checks that the controller uses the fence. The source check is not runtime or UI verification.

Tracking is only retained for the current app process. App termination does not cancel the laptop job; durable iPhone request recovery is not implemented. No online real-model inference, offline RVC, simulator UI or physical-device behavior has been verified by this local integration. The native compiler is unavailable in this environment; native regressions must execute on an authorized Apple build executor before release.

User-facing failures are mapped to the fixed RVC error vocabulary. Unknown transport/file errors use a generic connection message, not raw descriptions that might contain private paths or URLs.
