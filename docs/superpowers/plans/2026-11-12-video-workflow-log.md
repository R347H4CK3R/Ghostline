# Video workflow log implementation plan

**Goal:** Show the entire actual private YouTube request workflow, including waiting and missing evidence.

**Architecture:** Add bounded structured events to the existing local SQLite queue, alongside existing durable jobs and attempts. Instrument actual transitions and worker calls. Serve authenticated read-only snapshots and a live page; the phone polls only while its log is visible and records local submission attempts separately.

**Constraints:** Preserve the 0.4.7 candidate. Do not change processing gates, retry policy, voice replacement or queue preservation. No names, audio, transcripts, paths, credentials or raw exception text in the new timeline. Needs-review is not completed; a laptop file response is not phone installation. Older companions and missing history must remain explicit.

## Tasks
- [x] Add tests for bounded transactional history, ownership fencing, repeat polling, privacy and legacy snapshots; implement structured events.
- [x] Test and instrument actual preparation, inspection, generation, checking, publication and review transitions, preserving existing semantics.
- [x] Add authenticated workflow endpoint and safe live page with stalled/offline states, review links and separate sync evidence.
- [x] Add phone models/client/view plus local submission history, decoding and native checks.
- [ ] Run full Python suite, native CI gates, privacy review and independent code review before integration. No live deployment in this task without coordinating with the parent.

## Review focus
- Old databases and old workers have missing history, never invented stages.
- Stale/expired worker lease is not live progress; stages are discrete, percentages existing coarse worker values.
- Huge queues/events remain bounded; polling does not mutate the queue or cause duplicate history.
- Failures retain links/voices and do not expose subprocess text or private metadata.
- Publication and listening records do not prove final completion, likeness, native/device checks or per-video phone receipt.

Local verification: 245 Python tests passed with one Swift-unavailable skip. Independent review findings were fixed and rechecked. Native/iPhone/browser CI remains pending. Local Chromium was blocked by OS socket permissions; no browser success is claimed.
