"""Real HTTP/SQLite checks for the opt-in, isolated RVC transport."""
import contextlib
import json
import pathlib
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import uuid

from tools.queue_transport import create_server


def request_body():
    return dict(schemaVersion=1, format='rvc-v2-pth-index', requestID=str(uuid.uuid4()),
                videoURL='https://youtu.be/EAT0nWoEzJ8',
                sourceUse=dict(decision='approved-private-rvc-training', record='My authorized private audio 日本語'))


class RVCTransportTests(unittest.TestCase):
    @contextlib.contextmanager
    def server(self, configured=True, **kwargs):
        with tempfile.TemporaryDirectory() as directory:
            self.base = pathlib.Path(directory).resolve()
            self.f5 = self.base / 'f5'
            self.rvc = self.base / 'rvc'
            server = create_server(self.f5, 'a'*40, rvc_root=self.rvc if configured else None, **kwargs)
            self.url = 'http://127.0.0.1:' + str(server.server_port)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                yield
            finally:
                server.shutdown(); server.server_close(); thread.join()

    def request(self, path, body=None, *, auth=True, headers=None):
        headers = dict(headers or {})
        if auth:
            headers['Authorization'] = 'Bearer ' + 'a'*40
        if body is not None:
            headers.setdefault('Content-Type', 'application/json')
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode()
        request = urllib.request.Request(self.url + path, data=body, headers=headers)
        try:
            response = urllib.request.urlopen(request)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def test_disabled_routes_never_route_rvc_to_f5(self):
        with self.server(False):
            for path, body in [('/rvc/requests', request_body()), ('/rvc/status', None)]:
                self.assertEqual(self.request(path, body)[0], 404)
            code, result = self.request('/rvc/capabilities')
            self.assertEqual(code, 200)
            self.assertFalse(result['rvcQueueConfigured'])
            self.assertFalse(result['nativeIPhoneRuntimeVerified'])
            self.assertFalse((self.f5/'queue.db').exists())
            self.assertFalse(self.rvc.exists())

    def test_read_only_status_does_not_create_root_database_or_modify_rows(self):
        with self.server():
            code, result = self.request('/rvc/status')
            self.assertEqual((code, result['jobs']), (200, []))
            self.assertFalse(self.rvc.exists())
            self.request('/rvc/requests', request_body())
            db = self.rvc/'rvc-queue.db'
            before = db.read_bytes()
            code, result = self.request('/rvc/status')
            self.assertEqual(code, 200)
            self.assertEqual(result['jobs'], [dict(videoID='EAT0nWoEzJ8', status='waiting', progress=0.0, attempts=0)])
            self.assertEqual(db.read_bytes(), before)
            self.assertFalse((self.f5/'queue.db').exists())

    def test_authentication_including_explicit_tailscale_owner(self):
        with self.server(trusted_login='owner@example.test'):
            for path, body in [('/rvc/requests', request_body()), ('/rvc/status', None), ('/rvc/capabilities', None)]:
                self.assertEqual(self.request(path, body, auth=False)[0], 401)
                self.assertEqual(self.request(path, body, auth=False, headers={'Tailscale-User-Login':'stranger@example.test'})[0], 401)
                self.assertEqual(self.request(path, body, auth=False, headers={'Tailscale-User-Login':'owner@example.test'})[0], 200)

    def test_unicode_consent_scope_and_duplicates_preserve_f5(self):
        with self.server():
            self.assertEqual(self.request('/queue', {'videos':[{'url':'https://youtu.be/12345678901'}]})[0], 200)
            f5_before = (self.f5/'queue.db').read_bytes()
            body = request_body()
            code, result = self.request('/rvc/requests', body)
            self.assertEqual(code, 200)
            self.assertFalse(result['alreadyRequested'])
            self.assertFalse(result['nativeIPhoneRuntimeVerified'])
            self.assertTrue(self.request('/rvc/requests', body)[1]['alreadyRequested'])
            body['sourceUse']['record'] = 'Different permission'
            self.assertEqual(self.request('/rvc/requests', body)[0], 409)
            self.assertEqual((self.f5/'queue.db').read_bytes(), f5_before)
            with contextlib.closing(sqlite3.connect(self.rvc/'rvc-queue.db')) as db, db:
                saved = json.loads(db.execute('SELECT body FROM rvc_requests').fetchone()[0])
            self.assertIn('日本語', saved['sourceUse']['record'])
            self.assertEqual(self.request('/status')[1]['videos'][0]['id'], '12345678901')
            self.assertEqual(self.request('/voices')[0], 404)

    def test_invalid_scope_and_bounded_json_errors_are_redacted(self):
        with self.server():
            cases = [b'not json', b'\xff', b'[]', b'{}', b' '*16385]
            for key, value in [('format','f5-reference'), ('sourceUse',dict(decision='approved-reference-conditioning',record=str(self.base)))]:
                body = request_body(); body[key] = value; cases.append(body)
            for body in cases:
                code, result = self.request('/rvc/requests', body)
                self.assertEqual(code, 400)
                self.assertNotIn(str(self.base), json.dumps(result))
            self.assertFalse(self.rvc.exists())

    def test_status_is_bounded_allowlisted_and_never_returns_transcripts_or_paths(self):
        with self.server():
            self.request('/rvc/requests', request_body())
            with contextlib.closing(sqlite3.connect(self.rvc/'rvc-queue.db')) as db, db:
                db.execute("UPDATE job_control SET reason=?,token=?", ('PRIVATE TRANSCRIPT '+str(self.base), 'secret-token'))
                for index in range(105):
                    name = f'{index:011d}'
                    db.execute('INSERT INTO jobs VALUES (?,?,?,?,?)', (name, 'private-url', 'waiting', .5, index))
                    db.execute('INSERT INTO job_control VALUES (?,0,NULL,0,0,?)', (name, 'private-reason'))
                db.execute("UPDATE jobs SET status=? WHERE video_id='00000000000'", ('PRIVATE TRANSCRIPT',))
            code, result = self.request('/rvc/status')
            self.assertEqual(code, 200)
            self.assertEqual(len(result['jobs']), 100)
            self.assertTrue(result['truncated'])
            text = json.dumps(result)
            for secret in ['PRIVATE TRANSCRIPT', 'secret-token', 'private-url', 'private-reason', str(self.base)]:
                self.assertNotIn(secret, text)
            self.assertTrue(all(set(job)=={'videoID','status','progress','attempts'} for job in result['jobs']))
            self.assertEqual(self.request('/rvc/status?path=private')[0], 400)
            self.assertEqual(self.request('/rvc/voices')[0], 404)

    def test_corrupt_or_linked_status_database_fails_closed_without_replacement(self):
        with self.server():
            self.request('/rvc/requests',request_body())
            database=self.rvc/'rvc-queue.db'
            database.write_bytes(b'private corrupt database')
            self.assertEqual(self.request('/rvc/status')[0],503)
            self.assertEqual(database.read_bytes(),b'private corrupt database')
            database.unlink()
            outside=self.base/'keep.db';outside.write_bytes(b'outside private database')
            database.symlink_to(outside)
            self.assertEqual(self.request('/rvc/status')[0],503)
            self.assertEqual(outside.read_bytes(),b'outside private database')

    def test_all_root_overlaps_rejected_before_creating_or_changing_roots(self):
        for shape in ('same','inside','contains'):
            for existing in (False, True):
                with self.subTest(shape=shape, existing=existing), tempfile.TemporaryDirectory() as d:
                    base = pathlib.Path(d).resolve()
                    f5 = base/'f5'
                    rvc = f5 if shape=='same' else f5/'rvc' if shape=='inside' else base
                    if existing:
                        f5.mkdir(); (f5/'preserve').write_bytes(b'keep')
                    before = {str(p.relative_to(base)):p.read_bytes() for p in base.rglob('*') if p.is_file()}
                    with self.assertRaises(ValueError):
                        create_server(f5, 'a'*40, rvc_root=rvc)
                    self.assertEqual({str(p.relative_to(base)):p.read_bytes() for p in base.rglob('*') if p.is_file()}, before)
                    self.assertEqual(f5.exists(), existing)


if __name__ == '__main__':
    unittest.main()
