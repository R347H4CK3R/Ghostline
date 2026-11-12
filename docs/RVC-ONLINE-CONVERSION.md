# Reconstructed opt-in online RVC service

This is newly reconstructed source, not the original byte-identical implementation. It has not been deployed, run against a real model, or verified on an iPhone. Neural tests use explicit test doubles. Existing F5 and live services are unchanged.

## Wiring

The host may supply `rvc_online=None` to `create_server`. At its existing GET/POST dispatch boundary, call `tools.rvc_online_http.dispatch(handler, rvc_online)` and return when true. The adapter owns only `/rvc/models`, `/rvc/conversions` and descendants. Existing `/rvc/capabilities`, `/rvc/status`, `/rvc/requests` remain untouched. Authentication uses `handler.authorized()` and sends401 itself if false. JSON uses `handler.respond(code, body)`.

No storage or worker is created by default. To opt in explicitly:

- `Registry(export_root)` resolves only verified separate RVC export manifests.
- `NeuralConverter(engine_root, python, timeout=600)` wraps the existing real rvc_validation child and contained run_stage implementation.
- `ConversionService(private_job_root, registry, converter=None, *, guard)` owns its SQLite database and lifetime process lock.
- `service.start()` starts one serialized worker; `service.close()` cancels and joins it before releasing ownership.

The required guard must be a fast, bounded, nonblocking callable returning exactlyTrue only when all existing resource/user-activity/pause constraints permit inference. Preserve the existing8GiB available-memory floor; do not substitute a weaker guard. Guard exceptions deny work. During conversion a100ms monitor checks guard and signals the contained runner to cancel on guard loss. Temporary roots and subprocess paths are canonical absolute paths.

`onlineConversionAvailable` means an adapter is configured and service is neither stopping nor faulted. It does not mean enough resources are currently free or inference has been independently demonstrated. Offline and TTS capabilities are alwaysfalse.

## HTTP contract

All endpoints require existing pairing auth; no alternate listener or auth is introduced.

- GET `/rvc/models`:200, schemaVersion1, format`rvc-online-conversion-v1`, onlineConversionAvailable, offlineAvailablefalse, textToSpeechAvailablefalse, models.
- POST `/rvc/conversions`:202 receipt. JSON fields exactly schemaVersion1/requestID/modelID/modelSHA256/indexSHA256/revision/inputSHA256/wavBase64.
- GET `/rvc/conversions/{requestID}`:200 receipt.
- GET `/rvc/conversions/{requestID}/result`:200 WAV only after success. Headers include Content-Length, X-Content-SHA256, Cache-Control:no-store and X-Content-Type-Options:nosniff. Otherwise409.
- POST `/rvc/conversions/{requestID}/cancel`:body`{}`,200 receipt.

Model IDs match `[a-z0-9_-]{1,100}`. Request IDs are canonical lowercase UUIDs. Hashes are lowercase SHA256. Revision is hash of exact export manifest bytes. Catalog models expose only id/name/categories/modelSHA256/indexSHA256/revision/identityVerifiedfalse/likenessVerifiedfalse.

Receipts echo schemaVersion/requestID/modelID/modelSHA256/indexSHA256/revision/inputSHA256 plus numeric createdAt/updatedAt and status. States:queued, waiting-for-resources, running, cancelling, cancelled, failed, succeeded. Success adds result{sha256,bytes,sampleRate:40000,seconds}. Waiting timestamps change on state transition only. Runtime errors never expose paths or diagnostics. Corrupt queue receipts fault the service closed and disable availability; operator investigation is needed.

Input is standard base64 of mono PCM16 WAV, .2–30seconds, max3MiB, sample rate16000/22050/24000/32000/40000/44100/48000. Bounded ancillary RIFF chunks and PCM fmt chunks of at least16bytes are supported. Exactly one fmt precedes one nonempty even-length data chunk. RIFF length and odd-chunk padding presence must match; padding need not be zero. Inconsistent sizes, non-PCM layouts, silence and full-scale clipping are rejected. Output requires40000Hz and duration within .25seconds of input. Both status hash and downloaded bytes must be validated by the client.

JSON bound4198400bytes; two body-read slots, one admission at a time,32 durable jobs,64 catalog models. Body reads use read1 with a10second absolute monotonic deadline and remaining socket timeout. Reject duplicate/nonfinite JSON, duplicate Content-Length, Transfer-Encoding, queries and wrong content type. Same requestID/content is idempotent; conflicts409. Missing404, capacity429, unavailable503, malformed400. Unconfigured service returns authenticated404.

## Durability and limits

Input/output remain in the private SQLite database. There is no automatic deletion of user audio. Explicit retention and recovery operations are a future integration requirement; capacity rejects rather than deleting. Interrupted running/cancelling jobs fail on restart, queued jobs remain. Cancellation or guard loss discards late output. Temporary model/input/output files are cleaned after each job; exported originals are preserved.

This service structurally validates real conversion output, but does not run independent transcription for arbitrary recordings and does not establish voice identity, character likeness, native/offline RVC, TTS or production readiness. Before enabling: review source, integrate transport tests, verify guard wiring and perform genuine end-to-end service inference. On Apple/Windows also verify containment and filesystem behavior natively.

Registry scans and immutable-artifact hashing use nonblocking single-flight admission per Registry instance. Concurrent calls return429 registry_busy instead of doing parallel multi-gigabyte reads. Each admitted catalog still hashes models to verify immutable identities; use one Registry instance and avoid excessive polling. Constructor failures close opened SQLite handles before releasing the root lock.


## Review hardening

Accepted jobs retry temporary registry contention instead of failing permanently, retaining immutable model identity and cancellation. SQLite failures in submission, scanning, transitions or result persistence fault the service closed. Availability becomes false, active cancellation is signaled and status exposes only sanitized503 errors. Recovery requires investigating the underlying storage problem and restarting; interrupted jobs are not silently replayed.

On POSIX, newly created job directories use0700 and marker/owner-lock/database files use0600, even under normal022 umask. Existing private paths must already belong to the current user, have no group/other access, be the expected file type and (for files) have a single link. Unsafe existing paths are rejected without chmod. Input/model snapshots are0600; generated child files are contained within a0700 temporary directory and the0700 job root. No preexisting permission change is performed.

Windows POSIX modes do not establish access control. Before enabling this service on Windows, verify that the selected job root inherits a private owner-only ACL and that SQLite/temporary descendants retain it. This implementation does not validate Windows ACLs, and no Windows privacy claim or deployment is made by these tests.

Export manifests additionally require validation/training proof hashes, wordErrorRate<=0.1, bounded nonempty source/permission provenance, and integer gateVersion1. Provenance stays private and is not emitted in catalog responses.

Shared Python/Swift WAV contract fixtures are in tests/fixtures/rvc_wav. The JSON manifest maps each filename to expected parser acceptance. All files contain synthetic constant-amplitude audio only.
