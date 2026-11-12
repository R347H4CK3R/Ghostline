# VoiceMatrix 1.0.0 implementation and acceptance plan

**Goal:** Deliver the complete autonomous video-to-voice workflow, not a renamed preview build.

**Architecture:** Preserve the current authenticated companion and native library. Add retained acquisition, durable output/sync manifests and verified destination receipts around existing reference-conditioned synthesis and optional real RVC training. Keep desktop and iPhone responsibilities explicit; an unsupported mobile runtime remains laptop-only.

**Tech stack:** Windows/Python/SQLite/FFmpeg, paired Tailscale HTTPS, Swift/iOS, GitHub Actions.

**Spec:** Owner's November 12 autonomous video-to-voice requirements. This is an engineering acceptance map, not a statement that these stages already work.

## Global constraints

- Reserve 1.0.0 for the complete acceptance scope. Intermediate candidates must not overwrite published 0.4.9 or claim 1.0.0 acceptance.
- Preserve existing voices, identifiers, local selections, pairing and queue history. No automatic replacement of a valid voice or only model copy.
- Retain sources and generated work until outputs are committed, hash verified, sync-visible and destination-verified. A server-sent response is not delivery proof.
- Do not promise indistinguishable voices. Unknown speakers stay unknown; same actor is not proof of same character. Never substitute stock speech under a character label.
- Distinguish reference-conditioned previews, genuinely trained RVC and genuinely verified on-device runtime support.
- Keep credentials, recordings, models and private logs out of public source/build artifacts.

## Review focus

1. App/laptop crashes after download but before import or acknowledgment: resume without deleting the only valid copy.
2. A second writer changes a catalog, model or prepared job: conflict is explicit; immutable evidence cannot be silently reused.
3. Musical/overlapping source or short effective data: review/preview-only result, not fabricated character identity or trained-model success.
4. Offline phone, duplicate taps, stale connection or disk exhaustion: durable bounded retries, honest stage and actionable reason.
5. Low-memory/gaming laptop and unsupported iPhone model: refuse/defer safely, expose why, never claim an unrun inference.

## Task 1: Retained acquisition boundary

Files: `tools/video_reference.py`, its production callers, retention tests and acquisition docs.

- [ ] Persist source, extraction scratch and partial attempts under an explicit private root.
- [ ] Lock writers across processes; hash-bind reusable sources and reject corruption without deletion.
- [ ] Enforce per-source/aggregate/free-space bounds by refusing new work rather than evicting valid data.
- [ ] Disable historical one-off cleanup paths that bypass the retention contract.
- [ ] Test successful acquisition, restart reuse, consumer error, cancellation, corruption and quota exhaustion using real synthetic media.
- [ ] Pass full Linux/Windows source gates before replacing the paused live worker.

No cleanup eligibility is exposed until Task 3 establishes destination verification.

## Task 2: Desktop output layout and identity

Files: new `tools/studio_outputs.py`, tests, companion configuration and output-publishing integration.

- [ ] Create configured `Desktop/VoiceMatrix Sync` layout: Characters/{stable-id}/{Models,References,Previews,Metadata,Training}, Incoming, Processing, Completed, Failed, Manifests and Logs.
- [ ] Add immutable, versioned, hash-bound output manifests and atomic commit. Sanitized display names cannot determine identity or escape the root.
- [ ] Preserve existing flat F5 master as a compatible projection. Never relocate/delete the original master as a migration shortcut.
- [ ] Test duplicate names/IDs, existing destination conflicts, interrupted commit, path/link attacks and insufficient disk.

## Task 3: Durable incremental sync and verified receipt

Files: new `tools/sync_delivery.py`, `tools/private_voices.py`, `tools/queue_transport.py`, native sync/connection/library files and focused native/HTTP tests.

- [ ] Persist authenticated transfer sessions bound to exact manifest revision, selected outputs and paired destination. Do not equate an arbitrary device label with authentication.
- [ ] Serve bounded hash-bound chunks with resumable offsets; maintain per-output version/conflict state.
- [ ] Persist client progress and verify complete bytes before atomic import/registration. A repeated transfer should fetch only missing valid chunks.
- [ ] Acknowledge exact imported output hashes only after committed local files are revalidated. Persist server receipt idempotently across restart.
- [ ] Retain safely if acknowledgment is lost. Cleanup requires all required outputs acknowledged plus configured retention and preserved model copies.
- [ ] Test disconnect/reconnect, duplicate/reordered chunks, changed revision, wrong destination, hash mismatch, canceled import, storage full and crash between import/ack.
- [ ] Keep unrelated preexisting voices selective; automatic sync applies to outputs requested by the active generation job.

## Task 4: Video Voice Studio orchestration

Files: `VideoWorkflow` model/view, new orchestration/status adapter and queue/native tests.

- [ ] Provide URL/clipboard/Generate Voices, pairing/connection, actual stages, candidates/previews, individual/bulk sync and durable history.
- [ ] Connect cancel/pause/resume/retry to persisted queue actions, including recovery after companion/app restart.
- [ ] Refresh at most 30 seconds while visible without overlapping requests; show stage, last activity and stale/waiting/error distinctly.
- [ ] Configure persistent companion startup and authenticated HTTPS without embedding credentials in the IPA.
- [ ] Test repeated taps, navigation away/back, cancellation races, offline start, waiting for resources and actual laptop receipt visibility.

## Task 5: Honest clean-source analysis and generation

Files: analysis/preparation, reference selection, F5 and RVC queue integrations and evidence tests.

- [ ] Improve bounded clean-speech selection, preserving all candidate outcomes and explicit music/overlap/uncertainty evidence.
- [ ] Add reliable transcription/embedding and supported visual-name evidence without inventing names or merging distinct characters solely by actor.
- [ ] Reproduce the prior authorized reference-conditioned workflow on retained input; measure intelligibility separately from likeness.
- [ ] Train real RVC only with sufficient effective clean data and report preview-only otherwise. Never relabel F5 metadata as a trained model.
- [ ] Verify isolated real online conversion with an existing valid synthetic model before enabling the companion path.
- [ ] Keep resource reserve/CPU/gaming controls, unload idle models and record exact reason when work is deferred.

## Task 6: Mobile compatibility and release

- [ ] Verify native UI and interrupted flows for the exact candidate, then real iPhone upload → laptop receipt → source retention → analysis → preview/model → sync → import → playback.
- [ ] Complete mobile HuBERT/pitch/retrieval/DSP/synthesizer and measured memory/latency if full offline RVC is in release scope. Synthesizer-only ONNX parity is not sufficient.
- [ ] Clearly label model/runtime compatibility and laptop-only capabilities; test airplane-mode behavior for supported offline voices.
- [ ] Run source, native, speech, conversion, packaging and security gates on a frozen commit; preserve license/source provenance.
- [ ] Bump to 1.0.0 only after acceptance evidence; build a fresh IPA, inspect exact contents, publish authorized release and verify final bytes/feed links.

## Current evidence boundary

The earlier public candidate passed Linux source and native compile checks. Windows exposed test-fixture portability/timing errors, corrected in a test-only follow-up; full Windows rerun remains required. Retention is being implemented and has not yet been deployed. Existing voice library remains unchanged. Full new sync, physical-iPhone flow and full offline RVC acceptance are outstanding.
