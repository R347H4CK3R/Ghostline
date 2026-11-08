# Queue Recovery Implementation Plan

Goal: recover stopped workers safely, allow three retries, and preserve terminal reasons without pretending a preview is a completed export.

Architecture: extend the existing SQLite queue with separate ownership/attempt tables; retain existing jobs and names. Transactional leases fence stale writers. Keep the current app release and laptop deployment intact.

Spec: the user's authorized continuous laptop queue, duplication protection, initial attempt plus three retries, and honest terminal failure reasons.

Task 1 — `tools/video_queue.py`, `tests/test_queue_recovery.py`:
- [x] Write failing tests for lease expiry, stale ownership, four failures/crashes, heartbeat renewal, restart/backoff, migration and numerical validation.
- [x] Observe missing-interface failures before implementation.
- [x] Implement transactional claims/heartbeats/failures with durable attempt history; reject progress-only completion.
- [x] Add real concurrent-connection and expired-before-reclaim tests.
- [x] Run full source suite: 72 tests passed locally.

Task 2 — `.github/workflows/queue-recovery.yml`, `docs/QUEUE-RECOVERY.md`:
- [x] Add lightweight Linux/Windows queue and HTTP integration checks.
- [x] Document token migration, heartbeat requirements and remaining processor/export gates.
- [x] Independent review found stale time captured before a blocking SQLite lock. Two real lock-wait regression tests failed before the fix and passed afterward; all72 source tests passed.
- [x] Hosted run42459103748 passed both Windows and Linux queue/HTTP checks before integration. No app release was replaced.

Review focus: stale writers after a reclaim; repeated crashes exhausting the budget; existing names surviving schema migration; invalid times/progress; no leaked tokens or false completion. Automated generation remains disconnected. No private voice assets are read or published by this change.
