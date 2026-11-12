# Private laptop voice synchronization

Current development source uses metadata-only refresh and explicit per-voice downloads. See [Selective voice downloads](SELECTIVE-VOICE-DOWNLOADS.md) for the current UI, protocol extension, migration and limits. The complete-revision transfer and published checks below document the earlier bulk-sync implementation, which remains available for older clients.

The companion can serve its configured native Voices collection through the existing authenticated, tailnet-only HTTPS connection. The app downloads a complete revision into temporary storage, checks every byte, then uses the production CharacterFolderStore importer to commit private offline copies.

## Using it

With the laptop companion and Tailscale available on both devices under the same owner, a build containing this feature checks the collection when the character screen opens or returns to the foreground. “Sync voices from laptop” retries explicitly; “Stop sync” cancels the transfer. No pairing JSON is needed for the configured same-account connection. Manual Voices folder selection remains available.

Saved voices remain usable when the laptop or network is unavailable. Network transfer does not occupy the audio-processing lease. If speech or recording conversion starts during transfer, import waits for a later sync rather than interrupting audio. A revision is remembered only after the complete native import succeeds.

This source feature is not present in the existing published 0.4.0 build 1. A new packaged app must pass its native engine and packaging gates before publication. Physical iPhone synchronization and individual character inference/likeness are unverified.

## Private transfer protocol

The endpoint must receive an explicit master folder. Without one, these routes return 404. Existing authorization is checked before either catalog or file access; anonymous loopback requests remain 401. No public/Funnel route is added, and the existing same-account Tailscale or private bearer authorization is reused.

GET /voices returns schemaVersion 1, revision and a list of relative paths with byte sizes and SHA256 hashes. Only collection.json and each safe-ID folder's manifest.json/reference.wav pair are allowed. The revision hashes sorted ASCII lines of path:sha256:bytes followed by a newline. GET /voices/<revision>/<path> returns only that snapshot's allowlisted bytes. Changed snapshots are rejected. Responses are not cacheable.

Both ends enforce collection/file count and size bounds. The server validates the exact captured manifest/audio pairs using the strict reusable-pack validator, including PCM format, duration, non-silence and unclipped reference requirements. It pins the configured root identity and validates actual opened paths; POSIX directory-descriptor traversal rejects symlinks, while Windows checks final paths on opened handles. A source changing during snapshot or transfer causes an error.

The native client verifies paths, exact pair inventory, revision, each size/hash and the final native collection. HTTPS credentials/query/fragment and redirects are rejected. Downloads have per-request/resource timeouts and one monotonic 120-second overall deadline that cancels the session. Temporary transfer files are removed on success, error or cancellation.

The existing reference-preservation guard remains in force: an existing ID with changed audio or conditioning text rejects the whole incoming collection. Old active voices remain intact. This is not reviewed candidate promotion, and an unapproved replacement cannot be activated through sync. Missing remote entries never delete local voices.

## Evidence and limits

At source d6799389e993c131167df06434e9c069f582bb42, all 190 Python tests passed locally, on the actual Windows laptop, and on hosted Windows/Linux/macOS with zero skips. Actual production Swift checks stage a transferred fixture and import it, exercise unchanged revisions, reject unsafe/corrupt transfers and enforce cancellation deadlines. The iPhone SDK typecheck passed.

The installed companion endpoint downloaded its actual private collection through same-account HTTPS: 121 files, 25,103,331 bytes, 60 profiles and 60 distinct reference hashes, in 5.12 seconds. Every transferred file's size/hash and the strict native-format collection were verified in temporary private storage, then deleted. Anonymous local access returned 401. The master folder was not modified; no neural synthesis or character review was performed. See [public-safe measurements](qa/private-voice-sync-checks.json).

The speech worker and queue monitor were not restarted. Full automatic source labeling, human feedback/promotion and final completion-ledger cleanup remain separate unfinished work.


## Live sync activity

Open **Voices → Manage your collection → Live sync log** to see the current app session's latest sync, with the newest event first. Sending a request is labeled as waiting until a laptop response or request-correlated activity proves receipt. Laptop events show collection checking, catalog preparation and file responses. Phone events show byte transfer, hash validation, deferred import, unchanged revision, and completed private storage. Stop and errors keep previously saved voices. The elapsed timer is not a claim of progress.

The companion exposes authenticated `/sync-log` (browser) and `/voice-sync/<random-UUID>` (phone) through the existing private connection. Older clients also appear in the browser when their catalog request arrives. The log keeps up to 32 recent syncs for 15 minutes in memory, 160 events each; the phone keeps the latest 200 events until the next sync or app restart. Names, paths, recordings, transcripts, credentials and source revisions are not stored in log events. Opaque file identities used to deduplicate counts are capped at the 2001-file protocol bound. No log upload or automatic export is added.

The phone sends `X-VoiceMatrix-Sync-ID` on transfer requests; receipt is recorded before catalog validation holds the collection lock. Status polling runs independently once per second during transfer and cannot change whether a transfer succeeds. A legacy companion still works, but only its HTTP responses confirm receipt. A laptop file-sent event is not proof of phone import or voice processing/training completion. Stopping after the private store has committed cannot replace a successful completion with a misleading pending-stop state.

This feature is being checked for the 0.4.7 candidate. It is not yet a verified published phone update or a physical-device sync claim.
