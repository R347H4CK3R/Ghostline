"""Opt-in RVC conversion routes preserve the existing authenticated transport."""
import base64
import contextlib
import json
import pathlib
import tempfile
import threading
import time
import uuid
import unittest
import urllib.error
import urllib.request

from tools.queue_transport import create_server


class RVCOnlineTransportTests(unittest.TestCase):
    @contextlib.contextmanager
    def server(self, enabled=False):
        with tempfile.TemporaryDirectory() as directory:
            self.root = pathlib.Path(directory).resolve()
            from tools.rvc_online import ConversionService
            from tests.test_rvc_online import audio, fixture
            service = ConversionService(self.root / 'jobs', fixture(self.root),
                                        lambda folder, receipt, cancel: audio(), guard=lambda: True) if enabled else None
            server = create_server(self.root / 'f5' if enabled else self.root, 'a' * 40, rvc_online=service)
            if service is not None: service.start()
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.url = 'http://127.0.0.1:' + str(server.server_port)
            try:
                yield
            finally:
                server.shutdown(); server.server_close(); thread.join()
                if service is not None: service.close()

    def request(self, path, body=None, auth=True):
        headers = {'Authorization': 'Bearer ' + 'a' * 40} if auth else {}
        if body is not None:
            headers['Content-Type'] = 'application/json'
            body = json.dumps(body).encode()
        request = urllib.request.Request(self.url + path, data=body, headers=headers)
        try:
            response = urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def test_disabled_online_routes_require_pairing_and_create_no_state(self):
        with self.server():
            routes = [('/rvc/models', None), ('/rvc/conversions', {}),
                      ('/rvc/conversions/00000000-0000-4000-8000-000000000000', None)]
            for path, body in routes:
                self.assertEqual(self.request(path, body, auth=False)[0], 401)
                code, value = self.request(path, body)
                self.assertEqual(code, 404)
                self.assertEqual(value['error'], 'conversion_unavailable')
            self.assertEqual(list(self.root.iterdir()), [])

    def test_disabled_online_extension_preserves_existing_capabilities(self):
        with self.server():
            code, value = self.request('/rvc/capabilities')
            self.assertEqual(code, 200)
            self.assertFalse(value['rvcQueueConfigured'])
            self.assertFalse(value['nativeIPhoneRuntimeVerified'])
            self.assertEqual(list(self.root.iterdir()), [])

    def test_enabled_conversion_uses_real_http_preserves_f5_and_verifies_result(self):
        from tools.rvc_online import sha
        from tests.test_rvc_online import audio
        with self.server(enabled=True):
            code, catalog = self.request('/rvc/models')
            self.assertEqual(code, 200)
            self.assertTrue(catalog['onlineConversionAvailable'])
            self.assertFalse(catalog['offlineAvailable'])
            model = catalog['models'][0]
            data = audio()
            body = dict(schemaVersion=1, requestID=str(uuid.uuid4()), modelID=model['id'],
                        **{key: model[key] for key in ('revision', 'modelSHA256', 'indexSHA256')},
                        inputSHA256=sha(data), wavBase64=base64.b64encode(data).decode())
            code, receipt = self.request('/rvc/conversions', body)
            self.assertEqual(code, 202)
            self.assertEqual(receipt['requestID'], body['requestID'])
            path = '/rvc/conversions/' + body['requestID']
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                code, receipt = self.request(path)
                if receipt['status'] == 'succeeded': break
                time.sleep(.02)
            self.assertEqual(receipt['status'], 'succeeded')
            request = urllib.request.Request(self.url + path + '/result',
                                             headers={'Authorization': 'Bearer ' + 'a' * 40})
            with urllib.request.urlopen(request, timeout=5) as response:
                output = response.read()
                self.assertEqual(response.headers['X-Content-SHA256'], sha(output))
            self.assertEqual(sha(output), receipt['result']['sha256'])
            self.assertEqual(output, data)  # Deliberate neural double, not conversion quality proof.
            self.assertEqual(self.request('/rvc/conversions', body)[0], 202)
            self.assertEqual(self.request('/rvc/capabilities')[0], 200)
            self.assertEqual(list((self.root / 'f5').iterdir()), [])
