# VoiceMatrix 0.4.8 Release Preparation Plan

> **For agentic workers:** Use the existing isolated candidate worktree. This preparation is authorized; publication is held for coordinated integration.

**Goal:** Package the approved private full video workflow in a fresh, same-source 0.4.8 candidate without changing the deployed companion or 0.4.7 release.

**Architecture:** Reuse the proven 0.4.7 package, speech and conversion gates. Bind all 0.4.8 package/native/UI/backend evidence to one new candidate SHA. Keep the publisher disabled until exact new run IDs, IPA hash and size have been verified and committed.

**Tech Stack:** XcodeGen, GitHub Actions, Python unittest, iOS 26 SwiftUI.

**Spec:** `docs/VIDEO-WORKFLOW-LOG.md` and the existing 0.4.7 publication safeguards.

## Constraints

- Work locally only until the parent confirms the integrated base.
- Preserve deployed e3d016c source, private data, bundle ID, minimum OS 26.0 and build 1.
- Do not reuse any 0.4.7 IPA, test run, checksum, release tag or feed entry.
- Publication must retain tag conflict checks, public release/evidence checks, redownload hash checks and feed compare-and-swap/monotonic preservation.

## Tasks

- [x] Add failing 0.4.8 tests for unbound publication, wrong-source/workflow gates, tag/release/feed conflict validation and versioned candidate filenames.
- [x] Set project version 0.4.8 and copy the read-only candidate workflow. Add project/candidate branch triggers to native/backend gates.
- [x] Copy the final 0.4.7 publisher protections into a separate 0.4.8 publisher with unset exact evidence bindings; stop before external calls when unbound.
- [x] Run full local regressions and review changed files. Keep release and feeds unpublished.
- [ ] After base coordination, run all fresh exact-source gates, bind the successful evidence, then coordinate publication separately.

The e3d016c UI run passed workflow navigation, playback, updater, speech controls and empty-library checks. Its second runner never launched because SpringBoard reported Busy / failed preflight checks. The fresh candidate reboots only its owned simulator between batches, preserving data, with bounded waits. It does not treat the failed run as a release pass.
