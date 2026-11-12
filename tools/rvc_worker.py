"""Opt-in private RVC worker, never a service installer or an iPhone runtime.

Run as ``python -m tools.rvc_worker --help``. All runtime and validation paths,
small epoch count, and once/poll mode are explicit. Existing laptop pause/stop
files must be named with --guard-root. No user-input/idle policy is inferred.
The default gaming guard supports the existing Windows laptop only; an unknown
platform or failed guard blocks work. Results remain in the private RVC root.
"""
import argparse
import ctypes
import json
import math
import os
import pathlib
import re
import shutil
import signal
import stat
import sys
import threading
import time

if __package__ in (None, ''):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

GIB = 1024**3
MIN_AVAILABLE_RAM = 8 * GIB
MIN_FREE_DISK = 20 * GIB


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'guard-root', 'engine-root', 'python', 'candidate-python',
                 'speaker-checkpoint', 'vad-checkpoint', 'whisper-cli', 'whisper-model',
                 'validation-wav', 'validation-transcript-file', 'validation-source-file'):
        result.add_argument('--' + name, type=pathlib.Path, required=True)
    result.add_argument('--epochs', type=int, required=True, choices=range(1, 21),
                        help='Explicit small diagnostic training budget, 1–20 epochs; not a quality claim')
    mode = result.add_mutually_exclusive_group(required=True)
    mode.add_argument('--once', action='store_true')
    mode.add_argument('--poll', action='store_true')
    result.add_argument('--poll-seconds', type=float, default=30)
    result.add_argument('--stage-timeout', type=float, default=3600,
                        help='Maximum seconds per neural stage, 1–3600 (default 3600)')
    return result


def validate(args):
    from tools.rvc_request import DATABASE, ensure_root
    from tools.rvc_export import read_bound
    if type(args.epochs) is not int or not 1 <= args.epochs <= 20:
        raise ValueError('Choose an explicit small epoch count')
    for value, low, high in ((args.poll_seconds, 5, 3600), (args.stage_timeout, 1, 3600)):
        if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError('Invalid worker timing')
    root = ensure_root(args.root)
    if not (root / DATABASE).is_file():
        raise ValueError('An existing explicit RVC request queue is required')
    engine = pathlib.Path(args.engine_root).absolute()
    guard = pathlib.Path(args.guard_root).absolute()
    for directory in (engine, guard):
        if directory.resolve() != directory or not directory.is_dir():
            raise ValueError('Configure existing unlinked runtime and guard directories')
    if engine == root or engine in root.parents or root in engine.parents:
        raise ValueError('The engine and private RVC data must not overlap')
    for name in ('python', 'candidate_python', 'speaker_checkpoint', 'vad_checkpoint',
                 'whisper_cli', 'whisper_model', 'validation_wav',
                 'validation_transcript_file', 'validation_source_file'):
        path = pathlib.Path(getattr(args, name))
        if not path.is_file():
            raise ValueError('A required local runtime or validation file is missing')
    text = read_bound(args.validation_transcript_file, 16384).decode('utf-8').strip()
    source = read_bound(args.validation_source_file, 16384).decode('utf-8').strip()
    if (not 1 <= len(text) <= 4000 or not re.search('[a-z0-9]', text.lower()) or
            not 1 <= len(source) <= 3000 or any(ord(char) < 32 for char in source)):
        raise ValueError('Configure original held-out speech transcript and provenance')
    return dict(root=root, guard_root=guard, engine_root=engine,
                validation_wav=pathlib.Path(args.validation_wav).absolute(),
                validation_text=text, validation_source=source,
                python=str(pathlib.Path(args.python).absolute()), epochs=args.epochs,
                stage_timeout=args.stage_timeout)


class Platform:
    """OS boundaries. A failed or unsupported guard is never a safe result."""
    def __init__(self):
        self._game_lock = threading.Lock()
        self._game_checked = 0.0
        self._game = True

    def gaming(self):
        if os.name != 'nt':
            raise RuntimeError('The existing Windows gaming guard is unavailable')
        from tools.laptop_supervisor import gaming
        with self._game_lock:
            if time.monotonic() - self._game_checked >= 1:
                # Mark unsafe before checking so exceptions cannot reuse a safe value.
                self._game = True
                self._game = gaming()
                self._game_checked = time.monotonic()
            return self._game

    def available_ram(self):
        if os.name != 'nt':
            raise RuntimeError('Available RAM guard is unsupported on this platform')
        class MemoryStatus(ctypes.Structure):
            _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong),
                        ('total', ctypes.c_ulonglong), ('available', ctypes.c_ulonglong),
                        ('total_page', ctypes.c_ulonglong), ('available_page', ctypes.c_ulonglong),
                        ('total_virtual', ctypes.c_ulonglong), ('available_virtual', ctypes.c_ulonglong),
                        ('extended', ctypes.c_ulonglong)]
        state = MemoryStatus()
        state.length = ctypes.sizeof(state)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(MemoryStatus)]
        kernel.GlobalMemoryStatusEx.restype = ctypes.c_int
        if not kernel.GlobalMemoryStatusEx(ctypes.byref(state)):
            raise ctypes.WinError(ctypes.get_last_error())
        return state.available

    def free_disk(self, path):
        return shutil.disk_usage(path).free

    def lower_priority(self):
        from tools.companion_runtime import lower_priority
        if os.name != 'nt' and not hasattr(os, 'nice'):
            raise RuntimeError('Below-normal scheduling is unavailable')
        lower_priority()


class Guards:
    def __init__(self, root, guard_root, engine_root, platform, stop):
        self.roots = (root, guard_root)
        self.engine = engine_root
        self.platform = platform
        self.stop = stop
        self.reason = None

    @staticmethod
    def flag(path):
        # Unlike exists(), unexpected permission/stat failures must block work.
        try:
            path.lstat()
            return True
        except FileNotFoundError:
            return False

    def cancelled(self):
        if self.stop.is_set():
            self.reason = 'stopped'
            return True
        try:
            for root in self.roots:
                if root.resolve() != root or not stat.S_ISDIR(root.stat().st_mode):
                    raise ValueError('Guard directory unavailable')
                if self.flag(root / 'stop'):
                    self.stop.set()
                    self.reason = 'stopped'
                    return True
                if self.flag(root / 'pause'):
                    self.reason = 'paused'
                    return True
            game = self.platform.gaming()
            if type(game) is not bool:
                raise ValueError('Unknown gaming state')
            if game:
                self.reason = 'paused-for-game'
                return True
            values = [(self.platform.available_ram(), MIN_AVAILABLE_RAM)]
            values += [(self.platform.free_disk(path), MIN_FREE_DISK)
                       for path in (self.roots[0], self.engine)]
            if any(type(value) is not int or value < 0 for value, _ in values):
                raise ValueError('Unknown resource state')
            if any(value < floor for value, floor in values):
                self.reason = 'waiting-for-resources'
                return True
            self.reason = None
            return False
        except Exception:
            self.reason = 'guard-unavailable'
            return True


def load_runtime(args, cancelled):
    """Pinned local speaker model and independent Whisper verifier, no downloads."""
    from tools.speaker_candidates import _verified_bytes, MODEL_SHA256, VAD_SHA256
    from tools.candidate_engine import analyzer
    from tools.queue_processor import recognizer
    if cancelled():
        raise InterruptedError('Worker guarded before runtime setup')
    _verified_bytes(args.speaker_checkpoint, MODEL_SHA256, 90_000_000)
    _verified_bytes(args.vad_checkpoint, VAD_SHA256, 10_000_000)
    if cancelled():
        raise InterruptedError('Worker guarded during runtime setup')
    return dict(analyze=analyzer(args.candidate_python, args.speaker_checkpoint, args.vad_checkpoint),
                verify_words=recognizer(args.whisper_cli, args.whisper_model, cancelled))


def run(args, *, platform=None, runtime_factory=None, once_runner=None, stop=None, emit=print):
    """Run with injectable external boundaries, never a CLI safety bypass."""
    from tools.companion_runtime import worker_lock, WorkerBusy, cpu_environment
    from tools.rvc_request import DATABASE
    stop = threading.Event() if stop is None else stop
    platform = Platform() if platform is None else platform
    runtime_factory = load_runtime if runtime_factory is None else runtime_factory
    try:
        options = validate(args)
        root, guard_root = options.pop('root'), options.pop('guard_root')
        guards = Guards(root, guard_root, options['engine_root'], platform, stop)
        with worker_lock(root / DATABASE):
            cpu_environment(2)
            platform.lower_priority()
            runtime = None
            while not stop.is_set():
                if guards.cancelled():
                    emit(json.dumps(dict(status=guards.reason, nativeIPhoneRuntimeVerified=False)))
                    if args.once or stop.is_set():
                        return 0 if stop.is_set() else 4
                else:
                    if runtime is None:
                        runtime = runtime_factory(args, guards.cancelled)
                    if once_runner is None:
                        from tools.rvc_queue_processor import run_once
                        once_runner = run_once
                    result = once_runner(root, **options, **runtime, cancel=stop, paused=guards.cancelled)
                    if result:
                        status = result.get('status')
                        safe = dict(status=status if status in {'paused','needs-review','failed'} else 'checked-needs-review',
                                    nativeIPhoneRuntimeVerified=False)
                        if re.fullmatch('[A-Za-z0-9_-]{11}', str(result.get('videoID', ''))):
                            safe['videoID'] = result['videoID']
                        emit(json.dumps(safe))
                    if args.once:
                        return 0
                # Stop files and signals interrupt polling without another model call.
                deadline = time.monotonic() + args.poll_seconds
                while not stop.wait(min(.25, max(0, deadline-time.monotonic()))):
                    guards.cancelled()
                    if time.monotonic() >= deadline:
                        break
        return 0
    except WorkerBusy:
        emit(json.dumps(dict(status='worker-busy')))
        return 3
    except InterruptedError:
        emit(json.dumps(dict(status='paused', nativeIPhoneRuntimeVerified=False)))
        return 4
    except Exception:
        # Never print local paths, model errors, transcripts or source-use records.
        emit(json.dumps(dict(status='worker-blocked', nativeIPhoneRuntimeVerified=False)))
        return 2


def main(argv=None):
    args = parser().parse_args(argv)
    stop = threading.Event()
    previous = {}
    def cancel(_signal, _frame):
        stop.set()
    try:
        for number in (signal.SIGINT, signal.SIGTERM):
            previous[number] = signal.signal(number, cancel)
        return run(args, stop=stop)
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


if __name__ == '__main__':
    raise SystemExit(main())
