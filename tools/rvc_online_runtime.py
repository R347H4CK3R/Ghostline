"""Explicit local runtime factory. No installation, networking, downloads or autostart.

Platform probes run in one background thread, never on inference's guard path.
A blocked probe cannot be forcibly killed; close reports timeout and keeps its
thread reference. Stop first denies work, and runtime shutdown closes the service
before waiting for that probe, so active inference is never abandoned.
"""
import math
import os
from pathlib import Path
import threading
import time

from tools.rvc_online import ConversionService, NeuralConverter, Registry, safe_root
from tools.rvc_worker import Guards, Platform, MIN_AVAILABLE_RAM, MIN_FREE_DISK

REASONS = frozenset({'ready', 'not-checked', 'stale', 'stopped', 'paused',
                     'paused-for-game', 'waiting-for-resources', 'guard-unavailable'})


class CachedGuard:
    def __init__(self, probe, *, stop=None, interval=1.0, max_age=2.0,
                 monotonic=time.monotonic, wall=time.time):
        if not callable(probe):
            raise ValueError('Explicit probe required')
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in (interval, max_age)) or not 0 < interval <= max_age <= 2:
            raise ValueError('Guard freshness must not exceed two seconds')
        self.probe, self.interval, self.max_age = probe, interval, max_age
        self.stop = stop if stop is not None else threading.Event()
        self.monotonic, self.wall = monotonic, wall
        self._lock = threading.Lock()
        self._probe_lock = threading.Lock()
        self._thread = None
        self._allowed, self._reason = False, 'not-checked'
        self._checked_at = self._checked_mono = None

    def snapshot(self):
        # Never take the probe lock here or call platform/file/process APIs.
        with self._lock:
            allowed, reason = self._allowed, self._reason
            checked_at, checked_mono = self._checked_at, self._checked_mono
        if self.stop.is_set():
            allowed, reason = False, 'stopped'
        elif checked_mono is not None:
            try:
                age = self.monotonic() - checked_mono
                if not math.isfinite(age) or age < 0 or age >= self.max_age:
                    allowed, reason = False, 'stale'
            except Exception:
                allowed, reason = False, 'guard-unavailable'
        return dict(allowed=allowed, reason=reason, checkedAt=checked_at)

    def __call__(self):
        return self.snapshot()['allowed'] is True

    def check_once(self):
        """Potentially blocking: only the background sampler or explicit tests call this."""
        if self.stop.is_set() or not self._probe_lock.acquire(blocking=False):
            return
        try:
            # Timestamp at start, not finish: a slow probe cannot refresh stale safety.
            started, wall = self.monotonic(), self.wall()
            try:
                answer = self.probe()
                if not isinstance(answer, tuple) or len(answer) != 2:
                    raise ValueError('Invalid guard result')
                allowed, reason = answer
                if type(allowed) is not bool or reason not in REASONS or (allowed and reason != 'ready') or (not allowed and reason == 'ready'):
                    raise ValueError('Invalid guard result')
            except Exception:
                allowed, reason = False, 'guard-unavailable'
            if (type(started) not in (int, float) or type(wall) not in (int, float) or
                    not math.isfinite(started) or not math.isfinite(wall)):
                allowed, reason = False, 'guard-unavailable'
            with self._lock:
                self._allowed, self._reason = allowed, reason
                if reason != 'guard-unavailable':
                    self._checked_at, self._checked_mono = wall, started
        finally:
            self._probe_lock.release()

    def start(self):
        with self._lock:
            if self.stop.is_set():
                raise RuntimeError('Guard is stopped')
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name='rvc-resource-guard', daemon=True)
                self._thread.start()

    def _run(self):
        try:
            while not self.stop.is_set():
                self.check_once()
                self.stop.wait(self.interval)
        except Exception:
            # Clock or unexpected sampler errors also permanently deny work.
            self.stop.set()

    def request_stop(self):
        self.stop.set()

    def close(self, timeout=1.0):
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 <= timeout <= 5:
            raise ValueError('Bounded shutdown timeout required')
        self.request_stop()
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
            if thread.is_alive():
                raise TimeoutError('Guard probe is still stopping')


class Runtime:
    def __init__(self, service, guard):
        self.service, self.guard = service, guard

    def start(self):
        self.guard.start()
        try:
            self.service.start()
        except BaseException:
            self.guard.request_stop()
            raise

    def close(self, probe_timeout=1.0):
        # On service close failure its owner lock and object stay retained. Do not
        # falsely claim successful closure or detach a still-running converter.
        self.guard.request_stop()
        self.service.close()
        self.guard.close(probe_timeout)


def create_runtime(*, job_root, registry_root, engine_root, guard_root, python,
                   platform=None, timeout=600):
    """Construct explicitly, start nothing. Existing Windows ACL prerequisite applies.

    Default Platform is the existing fail-closed Windows gaming/RAM boundary.
    Injectable platforms are for tests or an independently verified host adapter.
    Thresholds are imported unchanged: available RAM8GiB and disk20GiB on both
    job and engine volumes. Pause/stop files in job and guard roots are reused.
    """
    roots = [safe_root(p) for p in (job_root, registry_root, engine_root, guard_root)]
    for i, left in enumerate(roots):
        for right in roots[i + 1:]:
            if left == right or left in right.parents or right in left.parents:
                raise ValueError('Explicit nonoverlapping runtime paths required')
    job, registry_path, engine, guards_path = roots
    if any(not p.is_dir() for p in (registry_path, engine, guards_path)):
        raise ValueError('Existing registry, engine and guard paths required')
    executable = Path(python).resolve(strict=True)
    if not executable.is_file():
        raise ValueError('Existing interpreter required')
    registry = Registry(registry_path)
    converter = NeuralConverter(engine, executable, timeout=timeout)
    stop = threading.Event()
    boundary = Guards(job, guards_path, engine, Platform() if platform is None else platform, stop)
    def probe():
        blocked = boundary.cancelled()
        return (False, boundary.reason or 'guard-unavailable') if blocked else (True, 'ready')
    guard = CachedGuard(probe, stop=stop)
    service = ConversionService(job, registry, converter, guard=guard)
    return Runtime(service, guard)
