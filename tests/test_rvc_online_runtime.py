import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
import sys

from tools.rvc_online_runtime import CachedGuard, Runtime, create_runtime, MIN_AVAILABLE_RAM, MIN_FREE_DISK


class Clock:
    def __init__(self):self.value=100.0
    def __call__(self):return self.value


class GuardTests(unittest.TestCase):
    def setUp(self):self.clock=Clock()
    def guard(self,probe):return CachedGuard(probe,monotonic=self.clock,wall=self.clock)
    def test_initial_then_ready_then_stale(self):
        g=self.guard(lambda:(True,'ready'))
        self.assertFalse(g());self.assertEqual(g.snapshot(),dict(allowed=False,reason='not-checked',checkedAt=None))
        g.check_once();self.assertTrue(g());self.assertEqual(g.snapshot()['checkedAt'],100)
        self.clock.value+=2;self.assertFalse(g());self.assertEqual(g.snapshot()['reason'],'stale')
    def test_stop_overrides_ready_immediately(self):
        g=self.guard(lambda:(True,'ready'));g.check_once();g.request_stop()
        self.assertFalse(g());self.assertEqual(g.snapshot()['reason'],'stopped')
        with self.assertRaises(RuntimeError):g.start()
    def test_errors_and_untrusted_reasons(self):
        for probe in [lambda:(_ for _ in ()).throw(ValueError('/private/path')),lambda:(True,'paused'),lambda:(False,'/private/path'),lambda:(1,'ready')]:
            g=self.guard(probe);g.check_once();self.assertEqual(g.snapshot()['reason'],'guard-unavailable');self.assertFalse(g())
    def test_slow_probe_does_not_block_snapshot_or_shutdown(self):
        entered=threading.Event();release=threading.Event()
        def probe():entered.set();release.wait(2);return True,'ready'
        g=self.guard(probe);g.start();self.assertTrue(entered.wait(1))
        start=time.monotonic()
        for _ in range(100):self.assertFalse(g())
        self.assertLess(time.monotonic()-start,.1)
        with self.assertRaises(TimeoutError):g.close(timeout=.01)
        self.assertTrue(g._thread.is_alive());self.assertFalse(g())
        release.set();g.close(timeout=1);self.assertFalse(g._thread.is_alive())
    def test_slow_success_is_stale_at_completion(self):
        def slow():self.clock.value+=3;return True,'ready'
        g=self.guard(slow);g.check_once();self.assertFalse(g());self.assertEqual(g.snapshot()['reason'],'stale')
    def test_probe_single_flight(self):
        g=self.guard(Mock(return_value=(True,'ready')))
        g._probe_lock.acquire()
        try:g.check_once();g.probe.assert_not_called()
        finally:g._probe_lock.release()
    def test_shutdown_stops_service_before_joining_probe(self):
        order=[];service=Mock();guard=Mock()
        guard.request_stop.side_effect=lambda:order.append('deny')
        service.close.side_effect=lambda:order.append('service')
        guard.close.side_effect=lambda _:order.append('probe')
        Runtime(service,guard).close();self.assertEqual(order,['deny','service','probe'])
    def test_failed_service_shutdown_retains_objects(self):
        service=Mock();guard=Mock();service.close.side_effect=TimeoutError('active')
        runtime=Runtime(service,guard)
        with self.assertRaises(TimeoutError):runtime.close()
        guard.request_stop.assert_called_once();guard.close.assert_not_called();self.assertIs(runtime.service,service)

    def test_failed_probe_does_not_renew_checked_time(self):
        g=self.guard(lambda:(True,'ready'));g.check_once();self.clock.value+=1
        g.probe=lambda:(False,'guard-unavailable');g.check_once()
        self.assertFalse(g());self.assertEqual(g.snapshot()['checkedAt'],100)
        fresh=self.guard(lambda:(False,'guard-unavailable'));fresh.check_once()
        self.assertIsNone(fresh.snapshot()['checkedAt'])


class Platform:
    def __init__(self):self.ram=MIN_AVAILABLE_RAM;self.disk=MIN_FREE_DISK;self.game=False
    def gaming(self):return self.game
    def available_ram(self):return self.ram
    def free_disk(self,path):return self.disk


class FactoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
        for name in ['registry','engine','guard']:(self.root/name).mkdir()
        self.platform=Platform()
        self.args=dict(job_root=self.root/'jobs',registry_root=self.root/'registry',engine_root=self.root/'engine',guard_root=self.root/'guard',python=sys.executable,platform=self.platform)
        self.runtime=create_runtime(**self.args);self.addCleanup(self.runtime.close)
    def test_factory_does_not_start(self):
        self.assertIsNone(self.runtime.service.thread);self.assertIsNone(self.runtime.guard._thread)
        self.assertFalse(self.runtime.guard());self.assertEqual(MIN_AVAILABLE_RAM,8*1024**3);self.assertEqual(MIN_FREE_DISK,20*1024**3)
    def test_exact_resource_floors(self):
        guard=self.runtime.guard;guard.check_once();self.assertTrue(guard())
        self.platform.ram-=1;guard.check_once();self.assertFalse(guard());self.assertEqual(guard.snapshot()['reason'],'waiting-for-resources')
        self.platform.ram+=1;self.platform.disk-=1;guard.check_once();self.assertFalse(guard())
    def test_game_pause_and_stop(self):
        guard=self.runtime.guard;self.platform.game=True;guard.check_once();self.assertEqual(guard.snapshot()['reason'],'paused-for-game')
        self.platform.game=False;(self.root/'guard/pause').write_text('');guard.check_once();self.assertEqual(guard.snapshot()['reason'],'paused')
        (self.root/'guard/stop').write_text('');guard.check_once();self.assertEqual(guard.snapshot()['reason'],'stopped')
    def test_job_pause_also_respected(self):
        (self.root/'jobs/pause').write_text('');self.runtime.guard.check_once();self.assertEqual(self.runtime.guard.snapshot()['reason'],'paused')
    def test_platform_error_denies_without_paths(self):
        self.platform.gaming=Mock(side_effect=RuntimeError('/private/game'))
        self.runtime.guard.check_once();self.assertEqual(self.runtime.guard.snapshot()['reason'],'guard-unavailable')
        self.assertNotIn('/private',json.dumps(self.runtime.guard.snapshot()))
    def test_overlapping_paths_rejected(self):
        args=dict(self.args,job_root=self.root/'engine/jobs')
        with self.assertRaises(ValueError):create_runtime(**args)
    def test_missing_runtime_rejected_before_storage(self):
        args=dict(self.args,job_root=self.root/'other-jobs',engine_root=self.root/'missing')
        with self.assertRaises(ValueError):create_runtime(**args)
        self.assertFalse((self.root/'other-jobs').exists())
