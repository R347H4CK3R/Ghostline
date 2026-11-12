# Private live video workflow log

Open **Video List → Live video workflow** on the phone, or the authenticated laptop **/workflow-log** page. Individual video links open a longer retained history. The existing **/sync-log** links back to the workflow page, and the private supervisor dashboard links to it too.

## What it proves

- The phone's sending log distinguishes a local send attempt, a verified accepted queue response, and a failed/unconfirmed response. The saved link list is preserved.
- Laptop receipts come from committed SQLite queue writes. Duplicate submissions retain the existing job and record a duplicate receipt; supervisor mirror polls are not new submissions.
- New workers record actual inspection, download, media check, extraction, transcription, preparation, reference validation, model acquisition, synthesis, audio/word checking and publication calls. Source review, inspection request/stop and listening decisions have separate receipts.
- Waiting, review, pause, retry and failure are distinct from running work. A current lease only means a recent worker lease/heartbeat, not GPU activity or successful inference. Progress is the existing coarse worker stage estimate, never an overall completion percentage.
- A successful technical run still ends at **needs-review**. New profiles may have entered the private master while likeness and native/device checks remain pending. No log event invents final completion.
- Voice sync remains separate evidence: laptop catalog/file responses are on **/sync-log**, and phone validation and atomic saving are in **Voices → Live sync log**. There is no per-video-to-phone receipt correlation, and the workflow view does not start a sync.

## Privacy and limits

All routes use the existing pairing bearer or explicitly configured same-account Tailscale authentication. Responses are `no-store`; browser scripts/styles use the server nonce and a restrictive CSP. The new timeline contains video IDs, timestamps, fixed allowlisted stage messages and integer counters only. It does not copy names, audio, transcripts, paths, tokens, raw exceptions or subprocess output. Existing private diagnostics retain their existing behavior.

Events are in the existing private `queue.db`, bounded to 160 per video. The overview returns the newest 200 jobs and the latest 20 events per job; a selected video returns up to 160. History is labeled partial when the receipt is absent. Polling is read-only and does not create/migrate an absent database. There is no Clear button and no log operation deletes queued links, imported profiles or audio. The companion does not publish this database.

Both clients poll every two seconds while visible/foreground, with no overlap. Hidden views pause polling. Failed refreshes retain but label the last displayed snapshot as stale. Older companions without the endpoint yield an unavailable message, preserving local offline voices.

## Safe rollout

The endpoint, supervisor and worker may run **different pinned source releases**. Updating only the endpoint cannot create missing stage events from an older worker. Do not copy files into a running pinned release or interrupt active inference/preparation.

1. Run source regressions, the workflow model executable, iPhone SDK typecheck, browser checks and the next release's existing app/audio gates at an exact source commit.
2. Inspect the current process command lines and queue state. Back up the queue with SQLite's backup API, preserving voices, specifications, recipes, work and existing release directories.
3. Stage a new immutable source release. Switch the worker only at a verified idle boundary under the existing single-worker lock. Do not run two workers, erase a lease, or overwrite old pinned wrappers blindly.
4. Switch endpoint/supervisor references separately and confirm authentication, receipts, current waiting/active status and actual new-worker events. Keep rollback references. If only the endpoint was updated, explicitly disclose that old-worker stage history is unavailable.
5. Confirm ordinary voice sync and existing queue-preservation tests still pass. Never use the user's private videos or voices as public CI fixtures.

## Verification

- `python3 -m unittest discover -s tests -v`
- `xcrun swiftc -parse-as-library VoiceMatrix/VideoWorkflow.swift tests/native/VideoWorkflowChecks.swift -o /tmp/workflow-checks && /tmp/workflow-checks`
- `.github/workflows/native-queue.yml` runs iPhone SDK typechecking and native workflow model checks.
- `VM_BROWSER_EXECUTABLE=/usr/bin/chromium node tests/workflow_browser.cjs` (or Playwright's installed Chromium) exercises real authenticated HTTP receipts, waiting versus processing, duplicate requests, private text exclusion, per-video navigation, mobile layout and stale connection messaging using synthetic fixtures only.
