import io
import json
from email.message import Message
import unittest
from unittest.mock import patch
from tools.rvc_online_http import dispatch,read_json
from tools.rvc_online import ServiceError


class Connection:
    def __init__(self):self.timeout=None
    def gettimeout(self):return self.timeout
    def settimeout(self,value):self.timeout=value


class Handler:
    def __init__(self,path='/rvc/models',method='GET',body=b'{}',authorized=True):
        self.path=path;self.command=method;self.responses=[];self.ok=authorized
        self.headers=Message();self.headers['Content-Length']=str(len(body));self.headers['Content-Type']='application/json'
        self.connection=Connection();self.rfile=io.BufferedReader(io.BytesIO(body));self.wfile=io.BytesIO()
    def authorized(self):return self.ok
    def respond(self,code,value):self.responses.append((code,value))


class HTTPTests(unittest.TestCase):
    def test_unrelated_route_untouched(self):
        h=Handler('/voices');self.assertFalse(dispatch(h,None));self.assertEqual(h.responses,[])
    def test_missing_service_authenticated_404(self):
        h=Handler();self.assertTrue(dispatch(h,None));self.assertEqual(h.responses[0][0],404)
    def test_unauthorized_401(self):
        h=Handler(authorized=False);dispatch(h,None);self.assertEqual(h.responses[0][0],401)
    def test_duplicate_json_rejected(self):
        h=Handler(body=b'{"a":1,"a":2}')
        with self.assertRaises(ValueError):read_json(h)
    def test_nonfinite_rejected(self):
        with self.assertRaises(ValueError):read_json(Handler(body=b'{"a":NaN}'))
    def test_duplicate_length_rejected(self):
        h=Handler();h.headers['Content-Length']='2'
        with self.assertRaises(ServiceError):read_json(h)
    def test_transfer_encoding_rejected(self):
        h=Handler();h.headers['Transfer-Encoding']='chunked'
        with self.assertRaises(ServiceError):read_json(h)
    def test_absolute_deadline_trickle(self):
        h=Handler(body=b'{"valid":true}')
        class Trickle:
            def read1(self,n):return b' '
        h.rfile=Trickle()
        with patch('tools.rvc_online_http.time.monotonic',side_effect=[0,0,3,3,6,6,9,9,12]):
            with self.assertRaises(TimeoutError):read_json(h)
        self.assertIsNone(h.connection.gettimeout())
    def test_socket_remaining_timeout(self):
        h=Handler()
        with patch('tools.rvc_online_http.time.monotonic',side_effect=[5,7,8]):self.assertEqual(read_json(h),{})
        self.assertIsNone(h.connection.gettimeout())
    def test_upload_slots(self):
        import threading
        class Service:upload_slot=threading.BoundedSemaphore(2)
        service=Service();service.upload_slot.acquire();service.upload_slot.acquire()
        h=Handler('/rvc/conversions','POST');dispatch(h,service)
        self.assertEqual(h.responses[0][0],429)
    def test_exception_no_path_leak(self):
        class Service:
            def catalog(self):raise RuntimeError('/private/secret')
        h=Handler();dispatch(h,Service());self.assertEqual(h.responses,[(503,{'error':'conversion_unavailable'})])
    def test_existing_rvc_routes_untouched(self):
        for path in ['/rvc/capabilities','/rvc/status','/rvc/requests','/rvc/request/abc']:
            h=Handler(path);self.assertFalse(dispatch(h,None));self.assertEqual(h.responses,[])
