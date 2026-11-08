# Durable laptop job ownership

The queue source now supports crash recovery and an initial attempt plus three retries. This is worker infrastructure, not an installed automatic voice-generation pipeline. The published 0.4.0 IPA and feeds remain unchanged.

`VideoQueue.claim(lease_seconds=120)` atomically returns one job with `id`, `url`, `attempt`, `token` and `leaseUntil`, or `None`. Another connection cannot claim that active job. A worker must renew ownership more often than its deadline with `progress(id, fraction, token=token)`. Leases must be between 1 and 3600 seconds; long neural calls require a separate heartbeat loop. Do not run heartbeat and job mutations concurrently on the same SQLite connection.

`fail(id, token, reason, retry_delay=30)` durably saves the attempt reason. The first three failures schedule retries after the delay; the fourth is terminal. Worker crashes consume attempts too: the next claim detects expired ownership, saves a lease-expired reason and recovers eligible jobs. An expired or replaced owner cannot update progress, report a failure or resurrect itself. Attempts and reasons survive restarts. Exported status includes attempts, next-attempt time, last failure reason and attempt history, without exposing worker tokens.

`progress(id, 1, 'needs-review', token=token)` releases ownership for human review; it does not mean a usable voice was published. Generic progress updates cannot mark a job completed. A future processor must validate all expected native-compatible voice exports and required audio checks, append its durable completion ledger, and only then remove pending links/names. This patch does not implement that completion transaction, video acquisition, generation, model training, discovery, or folder synchronization.

Existing databases retain video IDs, duplicate protection and the transport's names table. Legacy `processing` rows without ownership metadata return to waiting once; newly leased work is not reset when another HTTP/status connection opens. Callers using the earlier tokenless `progress` interface must adopt the returned worker token. There is currently no installed generator using that obsolete interface.

Tests exercise real SQLite files, independent connections, simultaneous workers, restart/backoff, old database migration, stale owners, bounded retries, review state and invalid numerical values. The Windows/Linux workflow also runs the authenticated HTTP transport tests. No heavy inference or gaming-laptop deployment is performed by these checks.
