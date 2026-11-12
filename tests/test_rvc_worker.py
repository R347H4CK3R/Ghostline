"""Safe entrypoint tests. Neural/runtime and OS boundaries are injected only here."""
import contextlib
import importlib.util
import io
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from tools.rvc_request import submit
from tests.test_rvc_request_transport import request_body


class Platform:
    def __init__(self):
        self.game = False
        self.ram = 16 * 1024**3
        self.disk = 40 * 1024**3
        self.priority = False
        self.fail = None

    def gaming(self):
        if self.fail == 'gaming':
            raise OSError('private machine details')
        return self.game

    def available_ram(self):
        if self.fail == 'ram':
            raise OSError('private machine details')
        return self.ram

    def free_disk(self, path):
        if self.fail == 'disk':
            raise OSError('private machine details')
        return self.disk

    def lower_priority(self):
        if self.fail == 'priority':
            raise OSError('private machine details')
        self.priority = True


class WorkerTests(unittest.TestCase):
    def worker(self):
        self.assertIsNotNone(importlib.util.find_spec('tools.rvc_worker'), 'The safe RVC worker entrypoint is missing')
        from tools import rvc_worker
        return rvc_worker

    def arguments(self, root, once=True):
        worker = self.worker()
        root = pathlib.Path(root).resolve()
        (root/'engine').mkdir()
        (root/'guard').mkdir()
        submit(root/'rvc', request_body())
        flags = ['--root',str(root/'rvc'),'--guard-root',str(root/'guard'),
                 '--engine-root',str(root/'engine'),'--epochs','2','--poll-seconds','5']
        for name in ['python','candidate-python','speaker-checkpoint','vad-checkpoint','whisper-cli','whisper-model','validation-wav','validation-transcript-file','validation-source-file']:
            path = root/name
            path.write_text('Held-out original speech' if name.endswith('file') else 'fixture', encoding='utf8')
            flags += ['--'+name,str(path)]
        flags += ['--once'] if once else ['--poll']
        return worker.parser().parse_args(flags)

    def test_module_and_direct_help_need_no_neural_imports(self):
        self.worker()
        for command in [[sys.executable,'-m','tools.rvc_worker','--help'], [sys.executable,'tools/rvc_worker.py','--help']]:
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('--epochs', result.stdout)
            self.assertIn('--guard-root', result.stdout)
        code = "import sys; import tools.rvc_worker; assert not any(x in sys.modules for x in ('torch','numpy','speechbrain','tools.local_f5'))"
        self.assertEqual(subprocess.run([sys.executable,'-c',code],capture_output=True).returncode,0)

    def test_missing_paths_mode_or_small_explicit_epoch_count_are_rejected(self):
        worker = self.worker()
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stderr(io.StringIO()):
            args = self.arguments(d)
            for epochs in (0,21,200):
                args.epochs = epochs
                with self.assertRaises(ValueError):
                    worker.validate(args)
            with self.assertRaises(SystemExit):
                worker.parser().parse_args(['--once'])

    def test_once_routes_all_configuration_cancel_and_thread_limits_without_f5(self):
        worker = self.worker()
        with tempfile.TemporaryDirectory() as d:
            args = self.arguments(d); platform = Platform(); stop = threading.Event(); calls=[]
            def runtime(config, cancelled):
                self.assertTrue(platform.priority)
                self.assertEqual([os.environ.get(key) for key in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS')], ['2','2','2'])
                return dict(analyze=lambda *a,**kw:None, verify_words=lambda *a:None)
            def once(root, **kwargs):
                calls.append(root)
                self.assertEqual(root, pathlib.Path(d).resolve()/'rvc')
                self.assertEqual(kwargs['engine_root'], pathlib.Path(d).resolve()/'engine')
                self.assertEqual(kwargs['epochs'], 2)
                self.assertEqual(kwargs['validation_text'], 'Held-out original speech')
                self.assertEqual(kwargs['validation_source'], 'Held-out original speech')
                self.assertIs(kwargs['cancel'], stop)
                self.assertFalse(kwargs['paused']())
                stop.set()
                self.assertTrue(kwargs['paused']())
                return {'status':'paused','videoID':'EAT0nWoEzJ8','private':'never print this'}
            output=[]
            with patch.dict(os.environ):
                self.assertEqual(worker.run(args, platform=platform, runtime_factory=runtime, once_runner=once, stop=stop, emit=output.append), 0)
            self.assertEqual(len(calls),1)
            self.assertNotIn('never print this', str(output))
            self.assertFalse((pathlib.Path(d).resolve()/'guard'/'queue.db').exists())

    def test_game_pause_stop_resource_and_uncheckable_guards_never_load_runtime(self):
        worker = self.worker()
        cases=['game','pause','stop','ram','disk','gaming-error','ram-error','disk-error','priority-error','missing-guard']
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as d:
                args=self.arguments(d); platform=Platform()
                if case=='game':platform.game=True
                if case in ('pause','stop'):(pathlib.Path(d).resolve()/'guard'/case).touch()
                if case=='ram':platform.ram=1024**3
                if case=='disk':platform.disk=1024**3
                if case.endswith('-error'):platform.fail=case[:-6]
                if case=='missing-guard':(pathlib.Path(d).resolve()/'guard').rmdir()
                def forbidden(*a, **kw):self.fail('Blocked guard allowed a runtime/claim')
                output=[]
                self.assertIn(worker.run(args, platform=platform, runtime_factory=forbidden, once_runner=forbidden, emit=output.append), (0,2,4))
                self.assertNotIn('private machine details', str(output))
                with __import__('sqlite3').connect(pathlib.Path(d).resolve()/'rvc'/'rvc-queue.db') as db:
                    self.assertEqual(db.execute('SELECT status FROM jobs').fetchone()[0],'waiting')

    def test_live_pause_game_resource_loss_and_signal_cancel_reach_runtime_callback(self):
        worker=self.worker()
        for change in ('pause','stop','game','ram','disk','guard-error','signal'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as d:
                args=self.arguments(d); platform=Platform(); stop=threading.Event(); callback=[]
                def runtime(config, cancelled):
                    callback.append(cancelled)
                    return dict(analyze=lambda *a,**kw:None,verify_words=lambda *a:None)
                def once(root, **kwargs):
                    self.assertFalse(kwargs['paused']())
                    if change in ('pause','stop'):(pathlib.Path(d).resolve()/'guard'/change).touch()
                    if change=='game':platform.game=True
                    if change=='ram':platform.ram=0
                    if change=='disk':platform.disk=0
                    if change=='guard-error':platform.fail='gaming'
                    if change=='signal':stop.set()
                    self.assertTrue(callback[0]())
                    self.assertTrue(kwargs['paused']())
                    return dict(status='paused')
                self.assertEqual(worker.run(args,platform=platform,runtime_factory=runtime,once_runner=once,stop=stop,emit=lambda _:None),0)

    def test_poll_stop_interrupts_wait_and_releases_actual_worker_lock(self):
        worker=self.worker()
        from tools.companion_runtime import worker_lock,WorkerBusy
        with tempfile.TemporaryDirectory() as d:
            args=self.arguments(d,False); stop=threading.Event(); count=[]
            def once(root,**kwargs):
                count.append(1)
                with self.assertRaises(WorkerBusy):
                    with worker_lock(pathlib.Path(d).resolve()/'rvc'/'rvc-queue.db'):pass
                stop.set()
            self.assertEqual(worker.run(args,platform=Platform(),runtime_factory=lambda *a:dict(analyze=None,verify_words=None),once_runner=once,stop=stop,emit=lambda _:None),0)
            self.assertEqual(count,[1])
            with worker_lock(pathlib.Path(d).resolve()/'rvc'/'rvc-queue.db'):pass

    def test_main_routes_to_real_processor_entrypoint_and_restores_signal_handlers(self):
        import signal
        worker=self.worker()
        with tempfile.TemporaryDirectory() as d:
            args=self.arguments(d); flags=[]; calls=[]
            for key,value in vars(args).items():
                if isinstance(value,bool):
                    if value:flags += ['--'+key.replace('_','-')]
                else:flags += ['--'+key.replace('_','-'),str(value)]
            original=signal.getsignal(signal.SIGTERM)
            def process(root,**kwargs):
                calls.append(root)
                self.assertFalse(kwargs['cancel'].is_set())
                signal.getsignal(signal.SIGTERM)(signal.SIGTERM,None)
                self.assertTrue(kwargs['cancel'].is_set())
                self.assertTrue(kwargs['paused']())
                return dict(status='paused')
            with patch.object(worker,'Platform',return_value=Platform()), patch.object(worker,'load_runtime',return_value=dict(analyze=None,verify_words=None)), patch('tools.rvc_queue_processor.run_once',process), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(worker.main(flags),0)
            self.assertEqual(calls,[pathlib.Path(d).resolve()/'rvc'])
            self.assertIs(signal.getsignal(signal.SIGTERM),original)

    def test_unsupported_default_platform_does_not_claim_gaming_is_clear(self):
        worker=self.worker()
        if os.name!='nt':
            with self.assertRaises(RuntimeError):worker.Platform().gaming()
            with self.assertRaises(RuntimeError):worker.Platform().available_ram()

    def test_default_runtime_uses_pinned_analyzer_and_independent_recognizer_callbacks(self):
        worker=self.worker()
        with tempfile.TemporaryDirectory() as d:
            args=self.arguments(d); cancelled=threading.Event(); captures={}
            def analyzer(python, speaker, vad):
                captures['analyzer']=(python,speaker,vad)
                return 'analyzer'
            def recognizer(cli, model, callback):
                captures['asr']=(cli,model,callback)
                return 'verifier'
            with patch('tools.speaker_candidates._verified_bytes') as pinned, patch('tools.candidate_engine.analyzer', analyzer), patch('tools.queue_processor.recognizer',recognizer):
                runtime=worker.load_runtime(args,cancelled.is_set)
            self.assertEqual(runtime,dict(analyze='analyzer',verify_words='verifier'))
            self.assertEqual(len(pinned.call_args_list),2)
            self.assertEqual(captures['analyzer'],(args.candidate_python,args.speaker_checkpoint,args.vad_checkpoint))
            self.assertEqual(captures['asr'][:2],(args.whisper_cli,args.whisper_model))
            self.assertFalse(captures['asr'][2]());cancelled.set();self.assertTrue(captures['asr'][2]())


if __name__=='__main__':unittest.main()
