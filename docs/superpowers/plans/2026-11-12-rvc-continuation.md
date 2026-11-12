# RVC continuation and recovery plan

**Goal:** Complete the existing isolated online speech-to-speech path, then establish end-to-end offline feasibility without changing the F5 collection or overstating verification.

**Base:** 82081bf88fdd9d7a478d68f99e6df457f126e34b (published 0.4.9 candidate).

**Recovery:** Unpublished cloud backend/client files are absent following workspace rollback. Reconstructed files require fresh testing and review; historical hashes/passes do not validate them.

- [x] Restore exact public source into an isolated checkout; leave older dirty checkout intact.
- [x] Reconstruct independent durable backend/HTTP modules and focused tests in a separate directory.
- [x] Recover client DTO/connection/session and tests independently; reconcile wire contract.
- [x] Review security and integrity boundaries: pairing authorization, absolute request deadlines, input size/rate limits, immutable hash-bound model/input/result, cancellation/restart/idempotency, no unsafe path or error disclosure.
- [x] Integrate opt-in backend in queue transport, retaining all existing routes and behavior; test disabled/enabled and malformed clients.
- [ ] Compile native client and test successful/cancelled/disconnected/stale requests before exposing UI.
- [ ] Verify isolated real synthetic online conversion using existing local model/runtime without training or changing live voice assets.
- [ ] Review native app UI integration and CI on exact final source before new IPA release.
- [ ] Offline feasibility: assess complete HuBERT, pitch, retrieval, DSP and synthesizer graph, bounded memory/chunking and runtime licensing; fixed-shape synthesizer parity is not end-to-end support.

## Preservation and verification gates

Existing 60 F5 references remain untouched. No automatic live deployment or production training during recovery. Never replace voices from catalog observation. Keep synthetic evidence distinct from character identity/likeness and physical-device verification. A downloaded RVC model is not an offline-capable voice. Public changes exclude private audio, recordings, pairing data and credentials. Follow current publication approvals and denials.
