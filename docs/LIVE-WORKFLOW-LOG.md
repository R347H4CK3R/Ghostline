# Live workflow and catalog observations

The app's Video workflow screen and the authenticated laptop workflow page refresh
about every 30 seconds while visible and active. Refresh remains available manually.
A failed refresh retains the last snapshot and labels it unavailable. A snapshot
older than 75 seconds is stale, not proof that computation has stalled.

Receipts identify a **video link or candidate-processing request**, not an uploaded
movie. Queue receipts and stage history remain persisted in the existing queue
SQLite database. Current queue status, latest reported stage, stage time, last event,
and the worker lease are shown separately. A heartbeat indicates worker
responsiveness; neither heartbeat nor elapsed stage time measures compute progress.
No percentage is presented as whole-job completion.

The catalog section observes the existing validated F5 collection without modifying
it. A single background check runs at most once per 30 seconds, so catalog validation
cannot delay a queue snapshot. It shows safe voice names, current count, and first
observed, added, changed or missing entries. These are **observation times**, not exact
creation times. Initial existing voices are not labeled newly added. History is
limited to 160 events in companion memory and restarts with the companion. Changed
or missing remote voices never replace or remove saved phone voices.

Only bounded safe display names, opaque hashed IDs, timestamps, fixed stages and
counters appear in workflow responses. Raw errors, reference transcripts, audio,
paths and credentials are excluded. Existing voice files and queue entries are not
cleared. A first snapshot may show that catalog checking is still underway.

## Minimal companion deployment

Deploy these four files from the same tested source together, then restart the
existing companion with its current root, pairing and master arguments:

- `tools/queue_transport.py` (only the CatalogActivity integration is required)
- `tools/catalog_activity.py` (new)
- `tools/workflow_activity.py`
- `tools/workflow_log.html`

No database migration, collection re-import, voice rebuild, root relocation,
credential change or deletion is needed. Keep the current 60-voice master intact.
Do not replace the laptop's entire queue transport with an unrelated RVC branch.

The new app accepts the old schema-1 response without catalog/current-stage fields
and explains when a companion upgrade is needed. Older apps ignore the additive
fields from the upgraded companion. The native app's model and view changes require
an Apple SDK compile/typecheck and simulator validation before shipping an IPA;
Linux source tests alone do not establish iPhone behavior.
