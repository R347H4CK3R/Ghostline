# Automatic private voice candidates Implementation Plan

> For agentic workers: implement task by task with tests first and final independent review.

**Goal:** Start useful private laptop processing from an explicit phone request and download selected compatible voices for offline use.
**Architecture:** Authenticated request records, bounded candidate-preparation stage, existing owned queue and F5 verification, additive remote catalog metadata and per-voice download.
**Tech Stack:** Python SQLite, FFmpeg, CPU speaker embeddings, F5, whisper.cpp, Swift/SwiftUI.
**Spec:** docs/superpowers/specs/2026-11-12-automatic-candidates-design.md

## Global Constraints
Preserve all existing private voices and audio. Never fabricate identity, rights, training, likeness or device verification. No billing or security expansion. Only delete temporary downloaded media. All external source access must be ordinary public access without bypass. Existing approval/review records are not overwritten.

## Review Focus
- Duplicate request or changed source-use affirmation must not silently overwrite approved work.
- Paused, failed or ownership-lost workers must not publish.
- One invalid or mixed-speaker candidate must be clearly rejected, never mislabeled a known character.
- Cached catalog and missing local files must not report offline availability.
- Temporary movie cleanup must not remove references, existing voices or unrelated files.

### Task 1: Transactional automatic requests
- [ ] Add failing tests for validation, duplicate idempotence, conflicts and no mutation on invalid batch.
- [ ] Implement tools/video_request.py and authenticated route; preserve legacy queue semantics.
- [ ] Add fixed stage events and native request/receipt UI with explicit source-use affirmation.
- [ ] Run transport/queue/native checks and full Python suite.

### Task 2: Real bounded candidate preparation
- [ ] Choose and verify CPU embedding engine without account grants or cost.
- [ ] Add failing tests for deterministic source-specific IDs, bounded media, uncertain labels, transcripts and cleanup.
- [ ] Implement source-bound candidate preparation and owned queue integration using real embedding/transcription, not fake identities.
- [ ] Verify actual laptop engine/fixture and preserve pause/lease checks.

### Task 3: Selective offline downloads
- [ ] Separate worker adds metadata-only catalog, exact selected asset transfer and native availability UI.
- [ ] Verify old client compatibility, integrity, persisted selection and old voices.

### Task 4: Integration and release
- [ ] Independent full diff review, final suites and native compile/UI.
- [ ] Stage private laptop runtime with backup and idle fence only after tests.
- [ ] Verify real stages, temporary cleanup and unchanged existing files.
- [ ] Publish only verified app artifact and feeds under existing authorization; disclose unrun physical/RVC checks.
