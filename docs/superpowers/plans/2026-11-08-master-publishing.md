# Incremental Master Folder Publishing

Goal: enable the companion to add real native-format voice folders while preserving existing active voices and quarantining replacements.

Architecture: extend `tools/master_voices.py` with an exclusive canonical-path publisher and index-last commit; expose `publish-folder` in `voice_studio`. Retain existing one-shot folder export. This implements the user's authorized expandable master-folder architecture without assuming new likeness approvals.

Task 1:
- [x] Write publisher behavior tests; observe missing-publisher failures.
- [x] Implement validation, append-only active profile installation, idempotence, duplicate rejection and separate replacement candidates.
- [x] Reproduce/fix linked candidate-parent escape.
- [x] Independent review found relative aliases bypassed the lock and changed candidate location. Two regression tests failed before canonicalization and passed afterward.
- [x] Add a parent-alias regression for normal OS temporary paths and retain candidate-symlink rejection.
- [x] Flush new files/index; add POSIX directory barriers. Document Windows sudden-power-loss limit rather than claiming universal durability.
- [x] Full local source suite:83tests passed.

Task 2:
- [x] Exercise actual `publish-folder` CLI with synthetic initial/addition/replacement fixtures.
- [x] Add Windows/Linux checks and actual production Swift importer integration.
- [ ] Verify hosted checks and integrate without changing app release or private voices.

Review focus: lost active voice on retry, same reference renamed, crash orphan overwrite, canonical-lock bypass, symlink escape and false verification claims. Candidate acceptance/promotion, automated video processor and queue-completion ledger remain separate work.
