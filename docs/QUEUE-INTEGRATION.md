# Shared laptop queue

The existing iPhone Video List exports a UTF-8 file containing one name, a tab,
and one HTTPS YouTube URL per line. Copy that exported list to the laptop
monitor's `video-queue.txt`. Plain URL-only lines also work.

The supervisor now imports the complete file transactionally into `queue.db`,
the same SQLite queue used by `tools.queue_transport`. Character names survive
imports and API submissions. Repeated imports neither create duplicate jobs nor
restart completed ones. Unchanged files do not overwrite newer API name edits.
Malformed imports leave the queue and source file intact. The dashboard reports
waiting and completed counts from the database, rather than counting file lines.

The supervisor must be deployed with `video_queue.py` beside it when launched
as a standalone script. Existing databases migrate automatically without
removing jobs. Existing `video-queue.txt` files are preserved.

Manual pause wins over gaming detection. If the game check fails, monitoring
reports that heavy processing is paused. Monitoring itself never downloads or
processes video, changes network settings, or exposes the queue on the LAN.

## Verification

Run `python -m unittest discover -s tests -v` from the repository root.
The queue integration CI runs the three queue-related suites on both Windows
and Linux. Tests cover HTTP authorization, durable names/deduplication, atomic
malformed-file rejection, database counts, completed-job preservation, and pause
behavior. Real local HTTP requests are used for the transport tests.

## Remaining integration work

This is a durable list handoff, not automatic iPhone-to-laptop transport or
voice creation. The HTTP server remains loopback-only until an authenticated,
encrypted device connection is implemented. No pairing credentials are created
or installed by this update. The reviewed-reference processing pipeline, native
character voice inference/import, and physical-device/listening checks remain
unfinished. No additional usable voices or character replicas are claimed.
