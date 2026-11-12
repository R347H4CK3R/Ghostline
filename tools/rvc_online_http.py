"""Opt-in authenticated HTTP adapter; reconstruction, no server/start side effects."""
import contextlib
import time
from tools.rvc_online import MAX_AUDIO, ServiceError, request_id, sha, strict_json

MAX_BODY = ((MAX_AUDIO + 2) // 3) * 4 + 4096
READ_DEADLINE = 10.0


def read_json(handler):
    lengths = handler.headers.get_all('Content-Length', [])
    types = handler.headers.get_all('Content-Type', [])
    if (handler.headers.get_all('Transfer-Encoding', []) or len(lengths) != 1 or
            not lengths[0].isascii() or not lengths[0].isdigit() or len(lengths[0]) > 10 or
            types != ['application/json']):
        raise ServiceError()
    length = int(lengths[0])
    if not 0 < length <= MAX_BODY:
        raise ServiceError()
    # read1 makes at most one underlying read. A per-read timeout alone would
    # allow an attacker to keep a thread alive forever by trickling bytes.
    end = time.monotonic() + READ_DEADLINE
    old_timeout = handler.connection.gettimeout()
    data = bytearray()
    try:
        while len(data) < length:
            remaining = end - time.monotonic()
            if remaining <= 0:
                raise TimeoutError()
            handler.connection.settimeout(remaining)
            chunk = handler.rfile.read1(min(65536, length - len(data)))
            if not chunk or time.monotonic() >= end:
                raise TimeoutError()
            data.extend(chunk)
        return strict_json(bytes(data))
    finally:
        handler.connection.settimeout(old_timeout)


def dispatch(handler, service):
    path = handler.path
    route = path.split('?', 1)[0].split('#', 1)[0]
    if route not in ('/rvc/models', '/rvc/conversions') and not route.startswith('/rvc/conversions/'):
        return False
    if not handler.authorized():
        handler.respond(401, dict(error="pairing_required"))
        return True
    try:
        if '?' in path or '#' in path:
            raise ServiceError()
        if service is None:
            raise ServiceError(404, 'conversion_unavailable')
        method = handler.command
        if path == '/rvc/models' and method == 'GET':
            handler.respond(200, service.catalog())
            return True
        if method == 'POST':
            if not service.upload_slot.acquire(blocking=False):
                raise ServiceError(429, 'upload_busy')
            try:
                body = read_json(handler)
            finally:
                service.upload_slot.release()
            if path == '/rvc/conversions':
                handler.respond(202, service.submit(body))
                return True
        parts = path.split('/')
        if len(parts) not in (4, 5) or parts[1:3] != ['rvc', 'conversions'] or not request_id(parts[3]):
            raise ServiceError(404, 'route_not_found')
        key = parts[3]
        if len(parts) == 4 and method == 'GET':
            handler.respond(200, service.status(key))
        elif len(parts) == 5 and parts[4] == 'cancel' and method == 'POST':
            if body != {}:
                raise ServiceError()
            handler.respond(200, service.cancel(key))
        elif len(parts) == 5 and parts[4] == 'result' and method == 'GET':
            data = service.result(key)
            handler.send_response(200)
            for name, value in [('Content-Type', 'audio/wav'), ('Content-Length', str(len(data))),
                                ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff'),
                                ('X-Content-SHA256', sha(data))]:
                handler.send_header(name, value)
            handler.end_headers()
            handler.wfile.write(data)
        else:
            raise ServiceError(404, 'route_not_found')
    except ServiceError as error:
        handler.close_connection = True
        handler.respond(error.status, dict(error=error.code))
    except (ValueError, TypeError, TimeoutError, EOFError, OSError):
        handler.close_connection = True
        handler.respond(400, dict(error='invalid_request'))
    except Exception:
        handler.close_connection = True
        handler.respond(503, dict(error='conversion_unavailable'))
    return True
