# Nonblocking RVC private candidate import experiment — 2026-11-06

**Scope:** experimental draft only; no release or production merge. Built on the source-cleared 11-Piper-candidate branch. This does not enable full RVC inference or FAISS retrieval.

## Change

Previously, copying and SHA-256 hashing up to 1 GB of security-scoped `.pth` or `.index` data, and re-auditing that data, ran synchronously on the SwiftUI MainActor. That could freeze the five-tab interface and trigger iOS watchdog termination before any audio test. Now `importWeights`, `attachIndex`, and `audit` are asynchronous and perform heavy file IO on detached tasks; they publish status and mutate the catalog only on the MainActor. Index inspection still reads only a bounded FAISS header. Security-scoped access is opened and closed on the IO worker; failed imports clean staged files; a failed index replacement restores the previous index. UI actions dispatch async tasks while controls remain disabled during a transaction.

## Verification protocol

- Regression guard: `python scripts/test_rvc_background_io.py`.
- Existing RVC pack bridge and header fixture tests must continue passing.
- Swift 6 compilation and unsigned IPA packaging must pass macOS GitHub Actions.
- On iPhone/Strata: import an authorized, reasonably sized `.pth`, optionally attach a `.index`, switch tabs during an import, export an integrity audit, and confirm a failed index import preserves the previous index.
- A successful CI build or hash-match is **not** on-device import timing, RVC synthesis, sound-quality, offline isolation, authorized identity match, or listening evidence.

**Candidate status: UNVERIFIED. Device-verified RVC voices: 0.** Source and identity permissions must still be checked individually; no public release of private voice packs. No arbitrary library count cap is introduced (the existing per-file 1 GB safety limit remains).
