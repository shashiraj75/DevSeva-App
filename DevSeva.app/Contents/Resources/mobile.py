# DevSeva — © 2026 Raviraj Shetty. All rights reserved.
"""DevSeva local Wi-Fi entry service; deliberately off until enabled on the laptop.

Phones need the laptop's network access code AND a staff name + PIN. Each
login gets a short-lived session token. Phone access is always HTTPS; it never
falls back to unencrypted HTTP.
"""
import hmac
import json
import secrets
import ssl
import sys
import threading
import time
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from kannada import suggest, RASHIS, NAKSHATRAS, ALIASES
import icons
import core
import security

SESSION_HOURS = 12
ICON_ROUTES = {'/apple-touch-icon.png': (180, False), '/icon-192.png': (192, False),
               '/icon-512.png': (512, False), '/icon-512-maskable.png': (512, True)}
MAX_BAD_CODES = 20


def page_path():
    """mobile.html sits next to this file, or in the bundle folder of a standalone build."""
    here = Path(__file__).with_name('mobile.html')
    if here.exists():
        return here
    return Path(getattr(sys, '_MEIPASS', here.parent)) / 'mobile.html'


def masked(phone):
    digits = ''.join(c for c in str(phone) if c.isdigit())
    return ('•••• ' + digits[-4:]) if len(digits) >= 4 else ''


def start(store, port=8765, cert=None, key=None):
    """Start encrypted phone access and return ``(server, info)``.

    Keeping the requirement here, rather than only in the desktop screen,
    prevents a future caller from exposing booking and staff-PIN traffic over
    plain HTTP by mistake.
    """
    if not cert or not key:
        raise RuntimeError('Phone access requires an HTTPS certificate and private key.')
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(cert), str(key))
    code = '-'.join(secrets.token_hex(2).upper() for _ in range(3))  # e.g. 4F2A-91BC-07DE
    sessions = {}
    lock = threading.Lock()
    bad_codes = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Never write credentials or devotee details to access logs.

        def send(self, code_, data, kind='application/json; charset=utf-8', cache='no-store'):
            if isinstance(data, bytes):
                content = data
            elif kind.startswith('application/json') or kind.startswith('application/manifest'):
                content = json.dumps(data, ensure_ascii=False).encode()
            else:
                content = data.encode()
            self.send_response(code_)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', cache)
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(content)

        def session(self):
            supplied = self.headers.get('Authorization', '').removeprefix('Bearer ')
            now = time.time()
            with lock:
                for token in [t for t, s in sessions.items() if s['expires'] < now]:
                    del sessions[token]
                for token, user in sessions.items():
                    if hmac.compare_digest(token, supplied):
                        return user
            return None

        def do_GET(self):
            # Keep the app page reachable when a QR scanner converts the
            # fragment into a query parameter (some Android camera apps do
            # this when handing the link to the browser).
            route = urlsplit(self.path).path
            if route in ('/', '/index.html'):
                return self.send(200, page_path().read_text(encoding='utf-8'), 'text/html; charset=utf-8')
            if route == '/manifest.webmanifest':
                return self.send(200, icons.manifest(), 'application/manifest+json', 'max-age=3600')
            if route in ICON_ROUTES:
                return self.send(200, icons.png(*ICON_ROUTES[route]), 'image/png', 'max-age=86400')
            user = self.session()
            if not user:
                return self.send(401, {'error': 'Please log in again.'})
            if self.path == '/api/catalog':
                return self.send(200, {**store.catalog(active_only=True), 'role': user['role'], 'name': user['name'],
                                       'can_pay': security.can(user['role'], 'pay'),
                                       'rashis': RASHIS, 'nakshatras': NAKSHATRAS, 'aliases': ALIASES,
                                       'today': date.today().isoformat(), 'org': store.settings(),
                                       'version': core.VERSION, 'copyright': core.COPYRIGHT})
            if self.path == '/api/unpaid' and security.can(user['role'], 'pay'):
                rows = [{'id': b['id'], 'devotee': b['devotee'], 'total': b['total'], 'date': b['service_date'],
                         'currency': json.loads(b['snapshot'])['currency']}
                        for b in store.bookings() if b['status'] == 'UNPAID' and b['total'] > 0]
                return self.send(200, rows)
            self.send(404, {'error': 'Not found or not allowed for your role.'})

        def read_json(self):
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 65536:
                raise ValueError('Invalid request size.')
            if not self.headers.get('Content-Type', '').startswith('application/json'):
                raise ValueError('JSON required.')
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError('Expected an object.')
            return data

        def login(self, data):
            ip = self.client_address[0]
            with lock:
                if bad_codes.get(ip, 0) >= MAX_BAD_CODES:
                    return self.send(429, {'error': 'Too many wrong access codes from this phone. Restart mobile access on the laptop.'})
            supplied = str(data.get('code', '')).strip().upper().replace(' ', '')
            if not hmac.compare_digest(supplied.replace('-', ''), code.replace('-', '')):
                with lock:
                    bad_codes[ip] = bad_codes.get(ip, 0) + 1
                return self.send(401, {'error': 'The access code does not match the one shown on the laptop.'})
            user = store.login(data.get('name'), data.get('pin'))  # ValueError -> 400
            token = secrets.token_urlsafe(32)
            with lock:
                sessions[token] = {**user, 'expires': time.time() + SESSION_HOURS * 3600}
            return self.send(200, {'token': token, 'name': user['name'], 'role': user['role']})

        def do_POST(self):
            try:
                data = self.read_json()
                if self.path == '/api/login':
                    return self.login(data)
                user = self.session()
                if not user:
                    return self.send(401, {'error': 'Please log in again.'})
                actor = f"{user['role']}: {user['name']} (phone)"
                if self.path == '/api/logout':
                    with lock:
                        for token in [t for t, s in sessions.items() if s is user]:
                            del sessions[token]
                    return self.send(200, {'ok': True})
                if self.path == '/api/transliterate':
                    return self.send(200, {'suggestion': suggest(str(data.get('text', ''))[:200])})
                if self.path == '/api/devotees':
                    query = str(data.get('q', '')).strip()[:100]
                    if len(query) < 2:
                        return self.send(200, [])
                    return self.send(200, [{
                        'id': f['id'], 'head': f['head'], 'phone': masked(f['phone']), 'gotra': f['gotra'],
                        'members': [{k: m[k] for k in ('id', 'name', 'kannada', 'relation', 'rashi', 'nakshatra', 'gotra')}
                                    for m in f['members'] if m['active']]} for f in store.families(query, 15)])
                if self.path == '/api/availability':
                    left = store.availability(int(data['event_id']), str(data.get('service_date', '')))
                    return self.send(200, {str(k): v for k, v in left.items()})
                if self.path == '/api/book':
                    data.pop('operator', None)
                    return self.send(200, {'id': store.book(data, actor, security.can(user['role'], 'override_price'))})
                if self.path == '/api/find':
                    query = str(data.get('q', '')).strip()[:100]
                    if data.get('unpaid'):
                        rows, _ = store.bookings_page('', 100, 0, data.get('event_id') or None, ('UNPAID',))
                        rows = [b for b in rows if b['total'] > 0]
                    elif len(query) < 2:
                        return self.send(200, [])
                    else:
                        rows, _ = store.bookings_page(query, 25, 0, data.get('event_id') or None)
                    out = []
                    for b in rows:
                        e = json.loads(b['snapshot'])
                        detail = store.detail(b['id'])
                        names = {}
                        for item in detail['items']:
                            names[item['name']] = names.get(item['name'], 0) + 1
                        out.append({'id': b['id'], 'ref': b['external_ref'], 'devotee': b['devotee'], 'phone': masked(b['phone']),
                                    'total': b['total'], 'refunded': b['refunded'], 'currency': e['currency'], 'event': e['name'],
                                    'date': b['service_date'], 'status': b['status'], 'method': b['payment_method'] or '',
                                    'printed': not b['print_pending'], 'sevas': ', '.join(f'{n}× {k}' for k, n in names.items())})
                    return self.send(200, out)
                if self.path == '/api/print':
                    store.request_print(int(data['id']), actor)
                    return self.send(200, {'ok': True})
                if self.path == '/api/pay':
                    security.require(user['role'], 'pay')
                    store.pay(int(data['id']), actor, data.get('method', 'Cash'))
                    return self.send(200, {'ok': True})
                self.send(404, {'error': 'Not found.'})
            except PermissionError as ex:
                self.send(403, {'error': str(ex)})
            except (ValueError, KeyError, TypeError, OverflowError) as ex:
                self.send(400, {'error': str(ex)})
            except Exception:
                self.send(500, {'error': 'Unable to save. Retry with the same request; do not create another booking.'})

    class Server(ThreadingHTTPServer):
        daemon_threads = True
        allow_reuse_address = True

        def get_request(self):
            conn, addr = super().get_request()
            conn.settimeout(15)
            return conn, addr

        def finish_request(self, request, client_address):
            # TLS handshake happens in the worker thread so a slow phone cannot block others.
            if not context:
                return super().finish_request(request, client_address)
            try:
                secure = context.wrap_socket(request, server_side=True)
            except (ssl.SSLError, OSError):
                return  # e.g. a phone that has not yet accepted the certificate
            try:
                super().finish_request(secure, client_address)
            finally:
                try:
                    secure.close()
                except OSError:
                    pass

    server = Server(('0.0.0.0', port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    # Draw the home-screen icons in the background so the first phone gets them quickly.
    threading.Thread(target=lambda: [icons.png(*args) for args in ICON_ROUTES.values()], daemon=True).start()
    return server, {'code': code, 'encrypted': True, 'scheme': 'https',
                    'port': server.server_port}
