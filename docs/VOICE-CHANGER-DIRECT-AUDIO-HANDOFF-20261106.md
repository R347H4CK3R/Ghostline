# Experimental GHOSTLINE direct local source-audio handoff — 2026-11-06

This draft adds an optional **record/import → select private RVC pack → convert** path without manually saving the source recording to Files and importing it a second time. The original browser picker remains available and overrides the handoff. Recording must stop before conversion begins.

## Security and privacy

- The local Voice Changer writes or copies the recording to the iPhone app's temporary storage. The offline RVC server accepts only a regular file under that temporary directory, with an allowlisted `.wav`, `.mp3`, `.m4a` or `.caf` extension and maximum size 128 MiB.
- A SHA-256 of the complete local file is recorded in server memory and is checked again before streaming. Any file mismatch responds with HTTP 409 and **does not** hand untrusted bytes to the WebAssembly engine.
- Only a randomly generated, session-local `127.0.0.1` route is injected into the converter. No private audio bytes, original filename, private model contents or secret route are put in GitHub diagnostics. No remote inference service is used. The server revokes its audio/model endpoints when the converter closes.
- The native data route has `Cache-Control: no-store`, same-origin resource protection and disabled HEAD requests. The bundled web app has its existing network-limiting CSP.
- Very large source audio and incompatible audio codecs may still fail during browser decoding. ContentVec/RMVPE and compatible RVC v2 weights are still required locally. Optional FAISS `.index` retrieval is **not** integrated.

## Test status and limits

Source-level regression checks establish intended wiring, not microphone permission, WebKit playback, offline synthesis, codec support, memory compatibility, iOS compilation or authenticity. The GitHub Actions arm64 build must pass before an unsigned experimental IPA is considered package-testable. **0 voices currently have physical-device generation + completed audible playback + authorized identity evidence.** Keep prior releases unchanged and do not mark candidate packs verified.

## Physical iPhone / Strata acceptance checks

1. Import an authorized RVC v2 pack and local ContentVec/RMVPE files; in Voice Changer, record 5 seconds, stop, and open Convert.
2. Confirm the Source Audio picker can be left blank and conversion uses the private recording; repeat after importing a WAV to Voice Changer, then test a different file selected directly inside the converter to verify override.
3. Turn on airplane mode after provisioning the models; confirm local audio generation and native replay if inference completes. Export the private diagnostic report and actual WAV for human listening verification.
4. Check failure behavior for a missing/modified source file, unsupported extension, >128 MiB input, and returning to the previous screen. Confirm audio/model routes become unavailable after closing the converter.

A successful CI build or non-silent WAV hash alone does not establish a verified actor, character, singer, or other real-person voice identity.
