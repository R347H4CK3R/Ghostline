"""Isolated RVC consent and SQLite scope tests; never touches the F5 queue."""
import copy
import importlib
import json
import pathlib
import tempfile
import unittest

from tools.video_queue import VideoQueue


class RVCRequestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.tmp.name).resolve()
        self.root = self.base / 'private-rvc'
        self.body = dict(schemaVersion=1, format='rvc-v2-pth-index',
                         requestID='b3e5fa2b-2b08-44ba-946a-299860f2e765',
                         videoURL='https://youtu.be/EAT0nWoEzJ8',
                         sourceUse=dict(decision='approved-private-rvc-training',
                                        record='I may train private models from this recording.'))

    def tearDown(self):
        self.tmp.cleanup()

    def module(self):
        return importlib.import_module('tools.rvc_request')

    def test_explicit_rvc_consent_is_canonical_and_atomic(self):
        module = self.module()
        result = module.submit(self.root, self.body)
        self.assertTrue(result['accepted'])
        self.assertEqual(result['format'], 'rvc-v2-pth-index')
        self.assertFalse(result['identityVerified'])
        self.assertFalse((self.root / 'queue.db').exists())
        queue = VideoQueue(str(self.root / 'rvc-queue.db'))
        try:
            request = module.load(queue.db, 'EAT0nWoEzJ8')
            self.assertEqual(request['videoURL'], 'https://www.youtube.com/watch?v=EAT0nWoEzJ8')
            self.assertEqual(request['sourceUse'], self.body['sourceUse'])
            self.assertEqual(queue.export()['videos'][0]['status'], 'waiting')
        finally:
            queue.close()

    def test_multilingual_provenance_round_trips_without_scope_truncation(self):
        module = self.module()
        for number, record in enumerate(['é' * 2000, '声' * 3000, '🎙' * 3000]):
            with self.subTest(record=record[:1]):
                root = self.base / ('unicode-' + str(number))
                body = dict(self.body, sourceUse=dict(decision='approved-private-rvc-training', record=record))
                self.assertTrue(module.submit(root, body)['accepted'])
                queue = VideoQueue(str(root / 'rvc-queue.db'))
                try:
                    restored = module.load(queue.db, 'EAT0nWoEzJ8')
                    self.assertEqual(restored['sourceUse']['record'], record)
                    raw = queue.db.execute('SELECT body FROM rvc_requests').fetchone()[0]
                    self.assertLessEqual(len(raw.encode('utf-8')), 16384)
                finally:
                    queue.close()
                self.assertTrue(module.submit(root, body)['alreadyRequested'])

    def test_invalid_unicode_never_creates_a_private_root(self):
        body = dict(self.body, sourceUse=dict(decision='approved-private-rvc-training', record='\ud800'))
        with self.assertRaises(ValueError):
            self.module().submit(self.root, body)
        self.assertFalse(self.root.exists())

    def test_old_f5_consent_and_external_paths_never_create_root(self):
        for change in [dict(sourceUse=dict(decision='approved-private-candidates', record='Yes')),
                       dict(format='f5-reference'), dict(model='/tmp/model.pth'),
                       dict(schemaVersion=True), dict(requestID='../escape'),
                       dict(videoURL='https://evil.test/EAT0nWoEzJ8'),
                       dict(sourceUse=dict(decision='approved-private-rvc-training', record='\n'))]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.module().submit(self.root, dict(self.body, **change))
            self.assertFalse(self.root.exists())

    def test_retry_alias_is_reserved_without_resetting_work(self):
        module = self.module()
        module.submit(self.root, self.body)
        queue = VideoQueue(str(self.root / 'rvc-queue.db'))
        job = queue.claim()
        queue.review_with(job['id'], job['token'], lambda: None)
        alias = dict(self.body, requestID='a3e5fa2b-2b08-44ba-946a-299860f2e765')
        result = module.submit(self.root, alias)
        self.assertTrue(result['alreadyRequested'])
        self.assertEqual(result['requestID'], self.body['requestID'])
        self.assertEqual(queue.export()['videos'][0]['status'], 'needs-review')
        with self.assertRaises(FileExistsError):
            module.submit(self.root, dict(alias, videoURL='https://youtu.be/ZNFskLKrhx4'))
        self.assertEqual(len(queue.export()['videos']), 1)
        queue.close()

    def test_changed_scope_is_rejected_and_original_survives(self):
        module = self.module()
        module.submit(self.root, self.body)
        changed = copy.deepcopy(self.body)
        changed['sourceUse']['record'] = 'Different consent scope'
        with self.assertRaises(FileExistsError):
            module.submit(self.root, changed)
        queue = VideoQueue(str(self.root / 'rvc-queue.db'))
        try:
            self.assertEqual(module.load(queue.db, 'EAT0nWoEzJ8')['sourceUse'], self.body['sourceUse'])
        finally:
            queue.close()

    def test_f5_root_or_descendant_and_unknown_saved_data_are_untouched(self):
        for marker in ('queue.db', 'collection.json', 'saved-voice.wav'):
            root = self.base / marker.replace('.', '-')
            root.mkdir()
            (root / marker).write_bytes(b'preserve exactly')
            with self.subTest(marker=marker), self.assertRaises(ValueError):
                self.module().submit(root, self.body)
            self.assertEqual(sorted(path.name for path in root.iterdir()), [marker])
            self.assertEqual((root / marker).read_bytes(), b'preserve exactly')
        f5 = self.base / 'f5'
        f5.mkdir()
        (f5 / 'collection.json').write_text('{}')
        with self.assertRaises(ValueError):
            self.module().submit(f5 / 'rvc', self.body)
        self.assertFalse((f5 / 'rvc').exists())

    def test_unscoped_queue_job_cannot_be_upgraded_to_training(self):
        module = self.module()
        module.ensure_root(self.root, create=True)
        queue = VideoQueue(str(self.root / 'rvc-queue.db'))
        queue.add([self.body['videoURL']])
        queue.close()
        with self.assertRaises(FileExistsError):
            module.submit(self.root, self.body)

    def test_linked_destination_is_rejected_without_writing_target(self):
        target = self.base / 'target'
        target.mkdir()
        self.root.symlink_to(target, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.module().submit(self.root, self.body)
        self.assertEqual(list(target.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
