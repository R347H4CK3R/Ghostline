"""Reconstructed regression tests. All neural output here is an explicit test double."""
import base64
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import uuid
import wave
from tools.rvc_online import *


def audio(rate=40000, seconds=.3, value=1000):
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as out:
        out.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
        out.writeframes(struct.pack('<h', value) * int(rate * seconds))
    return stream.getvalue()


def fixture(root):
    folder = root / 'voices' / 'test'
    folder.mkdir(parents=True)
    (folder / 'model.pth').write_bytes(b'model')
    (folder / 'model.index').write_bytes(b'index')
    m = dict(schemaVersion=1, id='test', name='Test', categories=['Test'], format='rvc-v2-pth-index',
             status='conversion-checked-needs-review', modelVersion='v2', sampleRate=40000, featureDimensions=768,
             validationAudioSHA256='b'*64, trainingReportSHA256='c'*64, wordErrorRate=0.0,
             source='Synthetic test fixture', permission='Synthetic fixture permitted',
             sourceRevision=UPSTREAM, modelFile='model.pth', indexFile='model.index', indexVectors=1,
             modelSHA256=sha(b'model'), indexSHA256=sha(b'index'), modelBytes=5, indexBytes=5,
             identityVerified=False, likenessVerified=False, nativeIPhoneRuntimeVerified=False,
             effectiveTrainingData=dict(gateVersion=1, status='passed', minimumActiveSeconds=60,
                                        activeLowerBoundSeconds=70, effectiveDatasetSHA256='a'*64))
    (folder / 'manifest.json').write_text(json.dumps(m))
    return Registry(root / 'voices')


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.registry = fixture(self.root)
        self.service = ConversionService(self.root / 'jobs', self.registry, lambda f, r, c: audio(), guard=lambda: True)
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.service.close)

    def body(self):
        model = self.registry.catalog()[0]
        data = audio()
        return dict(schemaVersion=1, requestID=str(uuid.uuid4()), modelID=model['id'],
                    **{k:model[k] for k in ('modelSHA256','indexSHA256','revision')}, inputSHA256=sha(data),
                    wavBase64=base64.b64encode(data).decode())

    def wait(self, key, status):
        deadline = time.monotonic()+3
        while time.monotonic()<deadline:
            value=self.service.status(key)
            if value['status']==status:return value
            time.sleep(.01)
        self.fail(value)

    def test_registry_sanitizes(self):
        value=self.registry.catalog()[0]
        self.assertNotIn('source',value)
        self.assertFalse(value['identityVerified'])
        self.assertNotIn(str(self.root),json.dumps(value))

    def test_changed_hash_rejected(self):
        (self.root/'voices/test/model.pth').write_bytes(b'other')
        with self.assertRaises(ValueError):self.registry.catalog()

    def test_registry_path_rejected(self):
        with self.assertRaises(ServiceError):self.registry.resolve('../test')

    def test_symlink_rejected(self):
        link=self.root/'link';link.symlink_to(self.root/'voices',target_is_directory=True)
        with self.assertRaises(ValueError):Registry(link)

    def test_metadata_gate_and_duplicates(self):
        path=self.root/'voices/test/manifest.json';m=json.loads(path.read_text())
        m['categories']=['Test','Test'];path.write_text(json.dumps(m))
        with self.assertRaises(ValueError):self.registry.catalog()
        m['categories']=['Test'];m['effectiveTrainingData']['activeLowerBoundSeconds']=59;path.write_text(json.dumps(m))
        with self.assertRaises(ValueError):self.registry.catalog()

    def test_job_success(self):
        b=self.body();self.service.submit(b);self.service.start()
        result=self.wait(b['requestID'],'succeeded')
        data=self.service.result(b['requestID'])
        self.assertEqual(result['result']['sha256'],sha(data))
        self.assertEqual(result['inputSHA256'],b['inputSHA256'])

    def test_idempotence_conflict(self):
        b=self.body();first=self.service.submit(b)
        self.assertEqual(first,self.service.submit(b))
        b['revision']='f'*64
        with self.assertRaises(ServiceError) as cm:self.service.submit(b)
        self.assertEqual(cm.exception.status,409)

    def test_missing_converter(self):
        self.service.converter=None
        self.assertFalse(self.service.catalog()['onlineConversionAvailable'])
        with self.assertRaises(ServiceError):self.service.submit(self.body())

    def test_queued_cancel(self):
        b=self.body();self.service.submit(b)
        self.assertEqual(self.service.cancel(b['requestID'])['status'],'cancelled')
        with self.assertRaises(ServiceError):self.service.result(b['requestID'])

    def test_late_output_after_cancel_discarded(self):
        entered=threading.Event();release=threading.Event()
        def convert(f,r,c):
            entered.set();release.wait(2);return audio()
        self.service.converter=convert
        b=self.body();self.service.submit(b);self.service.start();self.assertTrue(entered.wait(2))
        self.assertEqual(self.service.cancel(b['requestID'])['status'],'cancelling')
        release.set();self.wait(b['requestID'],'cancelled')
        with self.assertRaises(ServiceError):self.service.result(b['requestID'])

    def test_guard_waits(self):
        self.service.guard=lambda:False
        b=self.body();self.service.submit(b);self.service.start();self.wait(b['requestID'],'waiting-for-resources')
        self.service.guard=lambda:True;self.wait(b['requestID'],'succeeded')

    def test_serialized(self):
        current=0;maximum=0
        def convert(f,r,c):
            nonlocal current,maximum
            current+=1;maximum=max(maximum,current);time.sleep(.03);current-=1;return audio()
        self.service.converter=convert
        a,b=self.body(),self.body();self.service.submit(a);self.service.submit(b);self.service.start()
        self.wait(b['requestID'],'succeeded');self.assertEqual(maximum,1)

    def test_changed_model_fails_before_converter(self):
        b=self.body();self.service.submit(b)
        (self.root/'voices/test/model.pth').write_bytes(b'other')
        self.service.start();self.wait(b['requestID'],'failed')

    def test_no_path_leak_on_error(self):
        def bad(*_):raise RuntimeError(str(self.root))
        self.service.converter=bad;b=self.body();self.service.submit(b);self.service.start()
        self.assertNotIn(str(self.root),json.dumps(self.wait(b['requestID'],'failed')))

    def test_stored_extra_path_removed(self):
        b=self.body();r=self.service.submit(b);r['path']=str(self.root)
        with self.service.lock:self.service._save(b['requestID'],r)
        self.assertNotIn('path',self.service.status(b['requestID']))

    def test_restart_interrupted_not_replayed(self):
        b=self.body();r=self.service.submit(b);r['status']='running'
        with self.service.lock:self.service._save(b['requestID'],r)
        self.service.close()
        self.service=ConversionService(self.root/'jobs',self.registry,lambda *a:audio(),guard=lambda:True)
        self.addCleanup(self.service.close)
        self.assertEqual(self.service.status(b['requestID'])['status'],'failed')

    def test_owner_lock(self):
        with self.assertRaises(Exception):ConversionService(self.root/'jobs',self.registry,guard=lambda:True)

    def test_close_prevents_submit(self):
        b=self.body();self.service.close()
        with self.assertRaises(ServiceError):self.service.submit(b)

    def test_busy_admission(self):
        b=self.body();self.service.admission.acquire()
        try:
            with self.assertRaises(ServiceError) as cm:self.service.submit(b)
            self.assertEqual(cm.exception.status,429)
        finally:self.service.admission.release()

    def test_temp_paths_canonical(self):
        seen=[]
        def convert(f,r,c):seen.append(f);return audio()
        self.service.converter=convert;b=self.body();self.service.submit(b);self.service.start();self.wait(b['requestID'],'succeeded')
        self.assertEqual(seen[0],seen[0].resolve());self.assertFalse(seen[0].exists())

    def test_wav_bounds(self):
        for data in (audio(value=0),audio(value=32767),audio(rate=8000),audio(seconds=.1),audio()+b'x'):
            with self.assertRaises(ValueError):wav_info(data)
        for rate in RATES:self.assertEqual(wav_info(audio(rate=rate))['sampleRate'],rate)

    def test_neural_adapter_receipt_and_canonical_command(self):
        from tools import rvc_validation, rvc_training
        folder=self.root/'neural';folder.mkdir()
        b=self.body()
        (folder/'model.pth').write_bytes(b'model');(folder/'model.index').write_bytes(b'index');(folder/'input.wav').write_bytes(audio())
        def runner(command,**kwargs):
            self.assertTrue(all(Path(p).is_absolute() for p in command[3:]))
            Path(command[-2]).write_bytes(audio())
            Path(command[-1]).write_text(json.dumps(dict(modelVersion='v2',sampleRate=40000,featureDimensions=768,indexVectors=1,**{k:b[k] for k in ('modelSHA256','indexSHA256','inputSHA256')})))
        with patch.object(rvc_validation,'check_source'),patch.object(rvc_training,'run_stage',runner):
            result=NeuralConverter(self.root,__import__('sys').executable)(folder,b,threading.Event())
        self.assertEqual(result,audio())

    def test_waiting_timestamp_stable(self):
        self.service.guard=lambda:False
        b=self.body();self.service.submit(b);self.service.start()
        first=self.wait(b['requestID'],'waiting-for-resources')
        time.sleep(.6)
        self.assertEqual(first['updatedAt'],self.service.status(b['requestID'])['updatedAt'])

    def test_guard_loss_cancels_running(self):
        allowed=threading.Event();allowed.set();entered=threading.Event();observed=threading.Event()
        def convert(f,r,c):
            entered.set()
            if c.wait(2):observed.set()
            return audio()
        self.service.guard=allowed.is_set;self.service.converter=convert
        b=self.body();self.service.submit(b);self.service.start();self.assertTrue(entered.wait(1));allowed.clear()
        self.assertTrue(observed.wait(1));self.wait(b['requestID'],'cancelled')
        with self.assertRaises(ServiceError):self.service.result(b['requestID'])

    def test_corrupt_receipt_fails_closed(self):
        b=self.body();self.service.submit(b)
        with self.service.lock:
            self.service.db.execute('UPDATE jobs SET receipt=? WHERE id=?', ('{"path":"/secret"}',b['requestID']));self.service.db.commit()
        self.service.start();self.service.thread.join(1)
        self.assertTrue(self.service.faulted);self.assertFalse(self.service.available())
        with self.assertRaises(ServiceError):self.service.status(b['requestID'])

    def test_capacity_retains_existing_jobs(self):
        for _ in range(32):self.service.submit(self.body())
        with self.assertRaises(ServiceError) as cm:self.service.submit(self.body())
        self.assertEqual(cm.exception.status,429)
        self.assertEqual(self.service.db.execute('SELECT count(*) FROM jobs').fetchone()[0],32)

    def test_receipt_result_tampering_rejected(self):
        b=self.body();self.service.submit(b);self.service.start();self.wait(b['requestID'],'succeeded')
        with self.service.lock:
            self.service.db.execute('UPDATE jobs SET output=? WHERE id=?',(audio(value=2000),b['requestID']));self.service.db.commit()
        with self.assertRaises(ServiceError):self.service.result(b['requestID'])

    def test_close_during_admission_rejects_insert(self):
        b=self.body();entered=threading.Event();release=threading.Event();errors=[]
        original=self.registry.resolve
        def resolve(*a,**kw):entered.set();release.wait(2);return original(*a,**kw)
        self.registry.resolve=resolve
        def submit():
            try:self.service.submit(b)
            except Exception as e:errors.append(e)
        t=threading.Thread(target=submit);t.start();self.assertTrue(entered.wait(1))
        closer=threading.Thread(target=self.service.close);closer.start()
        self.assertTrue(self.service.stop.wait(1));release.set();t.join(2);closer.join(2)
        self.assertTrue(self.service.closed);self.assertEqual(len(errors),1);self.assertIsInstance(errors[0],ServiceError)

    def test_changed_output_rate_fails(self):
        self.service.converter=lambda *a:audio(rate=16000)
        b=self.body();self.service.submit(b);self.service.start();self.wait(b['requestID'],'failed')

    def test_body_schema_and_hash_fail_closed(self):
        b=self.body();b['path']='/private/path'
        with self.assertRaises(ServiceError):self.service.submit(b)
        del b['path'];b['inputSHA256']='f'*64
        with self.assertRaises(ServiceError):self.service.submit(b)
        b=self.body();b['requestID']=b['requestID'].upper()
        with self.assertRaises(ServiceError):self.service.submit(b)

    def test_initialization_error_closes_database(self):
        b=self.body();self.service.submit(b)
        self.service.db.execute('UPDATE jobs SET receipt=?', ('not json',));self.service.db.commit();self.service.close()
        real=sqlite3.connect(self.root/'jobs/conversions.sqlite3',check_same_thread=False)
        from unittest.mock import MagicMock
        wrapped=MagicMock(wraps=real)
        with patch('tools.rvc_online.sqlite3.connect',return_value=wrapped):
            with self.assertRaises(ValueError):ConversionService(self.root/'jobs',self.registry,guard=lambda:True)
        wrapped.close.assert_called_once()
        with self.assertRaises(sqlite3.ProgrammingError):real.execute('SELECT 1')

    def test_registry_single_flight_io(self):
        entered=threading.Event();release=threading.Event()
        def hold():
            with self.registry.io_lock:entered.set();release.wait(2)
        t=threading.Thread(target=hold);t.start();self.assertTrue(entered.wait(1))
        try:
            for operation in (self.registry.catalog,lambda:self.registry.resolve('test')):
                with self.assertRaises(ServiceError) as cm:operation()
                self.assertEqual(cm.exception.status,429)
        finally:release.set();t.join(1)

    def test_registry_busy_retries_accepted_job(self):
        b=self.body();self.service.submit(b)
        entered=threading.Event();release=threading.Event()
        def hold():
            with self.registry.io_lock:entered.set();release.wait(3)
        t=threading.Thread(target=hold);t.start();self.assertTrue(entered.wait(1));self.service.start()
        time.sleep(.35)
        self.assertIn(self.service.status(b['requestID'])['status'],('queued','running'))
        release.set();t.join(1)
        r=self.wait(b['requestID'],'succeeded');self.assertEqual(r['revision'],b['revision'])

    def test_registry_busy_cancel_preserved(self):
        b=self.body();self.service.submit(b)
        entered=threading.Event();release=threading.Event()
        def hold():
            with self.registry.io_lock:entered.set();release.wait(3)
        t=threading.Thread(target=hold);t.start();self.assertTrue(entered.wait(1));self.service.start();time.sleep(.1)
        self.service.cancel(b['requestID']);release.set();t.join(1);self.wait(b['requestID'],'cancelled')

    def test_database_transition_failure_faults_worker(self):
        b=self.body();self.service.submit(b)
        with patch.object(self.service,'_save',side_effect=sqlite3.OperationalError('/private/db failed')):
            self.service.start();self.service.thread.join(1)
        self.assertTrue(self.service.faulted);self.assertFalse(self.service.available())
        with self.assertRaises(ServiceError) as cm:self.service.status(b['requestID'])
        self.assertNotIn('/private',str(cm.exception))
        with self.assertRaises(ServiceError):self.service.submit(self.body())

    def test_database_finish_failure_faults_worker(self):
        original=self.service._save
        def save(key,receipt,output=None):
            if receipt['status']=='succeeded':raise sqlite3.OperationalError('disk full')
            return original(key,receipt,output)
        b=self.body();self.service.submit(b)
        with patch.object(self.service,'_save',save):
            self.service.start();self.service.thread.join(1)
        self.assertTrue(self.service.faulted);self.assertFalse(self.service.available())

    def test_database_scan_failure_faults_worker(self):
        from unittest.mock import MagicMock
        original=self.service.db;wrapped=MagicMock(wraps=original)
        wrapped.execute.side_effect=sqlite3.OperationalError('disk error')
        self.service.db=wrapped;self.service.start();self.service.thread.join(1)
        self.assertTrue(self.service.faulted);self.assertFalse(self.service.available())

    @unittest.skipUnless(os.name=='posix','POSIX mode test')
    def test_new_private_modes_under_normal_umask(self):
        old=os.umask(0o022)
        try:other=ConversionService(self.root/'private-new',self.registry,guard=lambda:True)
        finally:os.umask(old)
        try:
            self.assertEqual(stat.S_IMODE(other.root.stat().st_mode),0o700)
            for name in ['.rvc-online.json','.owner.lock','conversions.sqlite3']:
                self.assertEqual(stat.S_IMODE((other.root/name).stat().st_mode),0o600)
        finally:other.close()

    @unittest.skipUnless(os.name=='posix','POSIX mode test')
    def test_unsafe_existing_root_rejected_unchanged(self):
        path=self.root/'unsafe';path.mkdir(mode=0o755)
        before=stat.S_IMODE(path.stat().st_mode)
        with self.assertRaises(ValueError):ConversionService(path,self.registry,guard=lambda:True)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode),before)

    @unittest.skipUnless(os.name=='posix','POSIX mode test')
    def test_unsafe_existing_database_rejected_unchanged(self):
        self.service.close();path=self.root/'jobs/conversions.sqlite3';path.chmod(0o644)
        with self.assertRaises(ValueError):ConversionService(self.root/'jobs',self.registry,guard=lambda:True)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o644)

    def test_manifest_requires_proof_and_provenance(self):
        path=self.root/'voices/test/manifest.json';original=json.loads(path.read_text())
        for key,value in [('validationAudioSHA256',None),('trainingReportSHA256','bad'),('wordErrorRate',.2),('wordErrorRate',True),('source',''),('permission',None)]:
            m=dict(original);m[key]=value;path.write_text(json.dumps(m))
            with self.assertRaises(ValueError,msg=key):self.registry.catalog()
        m=dict(original);m['effectiveTrainingData']=dict(m['effectiveTrainingData'],gateVersion=True);path.write_text(json.dumps(m))
        with self.assertRaises(ValueError):self.registry.catalog()

    def test_wav_ancillary_chunks_and_odd_pcm(self):
        good=bytearray(audio());good.extend(b'JUNK'+struct.pack('<I',4)+b'1234');good[4:8]=struct.pack('<I',len(good)-8)
        self.assertEqual(wav_info(bytes(good))['seconds'],.3)
        bad=bytearray(audio());bad[40:44]=struct.pack('<I',len(bad)-44+1);bad.extend(b'\x01\x00');bad[4:8]=struct.pack('<I',len(bad)-8)
        with self.assertRaises(ValueError):wav_info(bytes(bad))

    def test_shared_wav_fixtures(self):
        root=Path(__file__).parent/'fixtures/rvc_wav'
        for name,valid in json.loads((root/'manifest.json').read_text()).items():
            with self.subTest(name=name):
                if valid:self.assertEqual(wav_info((root/name).read_bytes())['sampleRate'],40000)
                else:
                    with self.assertRaises((ValueError,wave.Error)):wav_info((root/name).read_bytes())

    def test_submit_database_failure_faults_service(self):
        from unittest.mock import MagicMock
        b=self.body();real=self.service.db;wrapped=MagicMock(wraps=real)
        wrapped.execute.side_effect=sqlite3.OperationalError('/private/path')
        self.service.db=wrapped
        with self.assertRaises(ServiceError) as cm:self.service.submit(b)
        self.assertEqual(cm.exception.code,'storage_unavailable');self.assertTrue(self.service.faulted)
        self.assertFalse(self.service.available())

    def test_public_read_fault_blocks_start_and_preserves_queued_job(self):
        from unittest.mock import MagicMock
        b=self.body();self.service.submit(b);real=self.service.db
        wrapped=MagicMock(wraps=real);wrapped.execute.side_effect=sqlite3.OperationalError('transient')
        self.service.db=wrapped
        with self.assertRaises(ServiceError):self.service.status(b['requestID'])
        self.service.db=real
        called=threading.Event();self.service.converter=lambda *a:called.set()
        with self.assertRaises(ServiceError):self.service.start()
        self.assertFalse(called.is_set())
        persisted=json.loads(real.execute('SELECT receipt FROM jobs').fetchone()[0])
        self.assertEqual(persisted['status'],'queued')
        self.service.close()
        self.service=ConversionService(self.root/'jobs',self.registry,lambda *a:audio(),guard=lambda:True)
        self.addCleanup(self.service.close);self.service.start();self.wait(b['requestID'],'succeeded')

    def test_public_read_fault_stops_existing_idle_worker(self):
        from unittest.mock import MagicMock
        self.service.guard=lambda:False
        b=self.body();self.service.submit(b);self.service.start();self.wait(b['requestID'],'waiting-for-resources')
        real=self.service.db
        with self.service.lock:
            wrapped=MagicMock(wraps=real);wrapped.execute.side_effect=sqlite3.OperationalError('transient')
            self.service.db=wrapped
            with self.assertRaises(ServiceError):self.service.status(b['requestID'])
            self.service.db=real
            called=threading.Event();self.service.converter=lambda *a:called.set();self.service.guard=lambda:True
        self.service.wake.set();self.service.thread.join(1)
        self.assertFalse(self.service.thread.is_alive());self.assertFalse(called.is_set())
        persisted=json.loads(real.execute('SELECT receipt FROM jobs').fetchone()[0])
        self.assertEqual(persisted['status'],'waiting-for-resources')

    def test_unconfigured_restart_preserves_accepted_queue(self):
        b=self.body();self.service.submit(b);self.service.close()
        unconfigured=ConversionService(self.root/'jobs',self.registry,guard=lambda:True)
        try:
            with self.assertRaises(ServiceError) as cm:unconfigured.start()
            self.assertEqual((cm.exception.status,cm.exception.code),(503,'conversion_unavailable'))
            self.assertIsNone(unconfigured.thread)
            self.assertEqual(unconfigured.status(b['requestID'])['status'],'queued')
        finally:unconfigured.close()
        self.service=ConversionService(self.root/'jobs',self.registry,lambda *a:audio(),guard=lambda:True)
        self.addCleanup(self.service.close);self.service.start();self.wait(b['requestID'],'succeeded')
