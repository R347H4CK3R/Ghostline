# Source-only guarded runtime factory

This adapter starts nothing implicitly and does not install services, download dependencies, open listeners, change security settings or run inference during construction. It is not deployed or Windows ACL verified.

## API

`create_runtime(*, job_root, registry_root, engine_root, guard_root, python, platform=None, timeout=600)` returns a Runtime containing `.service` and `.guard`. All four paths must be explicit and nonoverlapping. Registry, engine and guard directories and interpreter must exist. The new private job root is created through ConversionService's existing permission checks. Real neural conversion still uses NeuralConverter and the existing run_stage process containment. The default Platform reuses the existing Windows gaming/RAM implementation; unsupported platforms fail closed.

`Runtime.start()` explicitly starts the cached sampler and then the serialized service worker. Until a completed fresh valid safety sample exists, the guard denies inference. `Runtime.close(probe_timeout=1)` immediately denies work, calls service.close(), then waits at most the selected probe timeout. The service retains its owner lock if active inference cannot stop within its own bounded shutdown. A blocked OS probe may outlive the join timeout: the adapter raises TimeoutError, keeps the thread reference and remains permanently stopped. Retry close after it exits. A still-running probe is not an abandoned active converter; never report a timeout as successful shutdown.

`CachedGuard(probe, *, stop=None, interval=1, max_age=2, monotonic=time.monotonic, wall=time.time)` is injectable for tests. `.start()` runs a single probe at a time in a background thread. The potentially blocking `.check_once()` is only for that sampler and explicit tests. The callable boolean and `.snapshot()` never perform filesystem, process or OS probes and never acquire the probe lock.

Snapshot fields are `allowed`, `reason`, `checkedAt`. Reasons are limited to ready, not-checked, stale, stopped, paused, paused-for-game, waiting-for-resources and guard-unavailable. No exception, path or process name is emitted. checkedAt is the wall time at the start of the last completed valid sample; timing freshness uses monotonic time. Failed and ongoing probes do not renew it. The conservative start timestamp prevents a slow successful probe from making old measurements appear fresh. Samples at least two seconds old deny work. Cached allowed status can remain true for at most two seconds after a condition changes; the service's100ms monitor then signals contained inference cancellation.

The factory reuses Guards unchanged:8GiB available RAM,20GiB free on both job and engine volumes, gaming check, pause/stop files in both job and guard roots, and explicit stop signal. Resource thresholds cannot be configured downward through this adapter. A stop file latches stop. Exceptions and unknown measurements deny work.

Windows privacy remains a separate deployment prerequisite: verify owner-only inherited ACLs for the job root, SQLite files and temporary descendants before enabling. Construction does not establish or verify those ACLs. Native process-containment and genuine model tests remain outstanding.
