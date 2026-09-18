"""Local Wi-Fi entry service; deliberately off until enabled on laptop."""
import hmac
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from kannada import suggest, RASHIS, NAKSHATRAS


def start(store, port=8765):
    tokens = {secrets.token_urlsafe(24): 'Reception', secrets.token_urlsafe(24): 'Cashier'}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Never write credentials or devotee details to access logs.

        def send(self, code, data, kind='application/json; charset=utf-8'):
            content = json.dumps(data, ensure_ascii=False).encode() if kind.startswith('application/json') else data.encode()
            self.send_response(code)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(content)

        def role(self):
            supplied = self.headers.get('Authorization', '').removeprefix('Bearer ')
            return next((role for token, role in tokens.items() if hmac.compare_digest(token, supplied)), None)

        def do_GET(self):
            if self.path == '/':
                return self.send(200, Path(__file__).with_name('mobile.html').read_text(encoding='utf-8'), 'text/html; charset=utf-8')
            role = self.role()
            if not role:
                return self.send(401, {'error':'Enter the access key displayed on the laptop.'})
            if self.path == '/api/catalog':
                return self.send(200, {**store.catalog(), 'role':role, 'rashis':RASHIS, 'nakshatras':NAKSHATRAS})
            if self.path == '/api/unpaid' and role == 'Cashier':
                rows = [{'id':b['id'],'devotee':b['devotee'],'total':b['total'],'currency':json.loads(b['snapshot'])['currency']}
                        for b in store.bookings() if b['status']=='UNPAID' and b['total']>0]
                return self.send(200, rows)
            self.send(404, {'error':'Not found or unavailable for your role.'})

        def do_POST(self):
            role = self.role()
            if not role:
                return self.send(401, {'error':'Invalid access key.'})
            try:
                size = int(self.headers.get('Content-Length','0'))
                if not 0 < size <= 65536:
                    raise ValueError('Invalid request size.')
                if not self.headers.get('Content-Type','').startswith('application/json'):
                    raise ValueError('JSON required.')
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError('Expected an object.')
                operator = str(data.get('operator','')).strip()
                if not operator or len(operator)>100:
                    raise ValueError('Enter the operator name (maximum 100 characters).')
                if self.path == '/api/transliterate':
                    return self.send(200, {'suggestion':suggest(str(data.get('text', ''))[:200])})
                if self.path == '/api/book':
                    return self.send(200, {'id':store.book(data, f'{role}: {operator}')})
                if self.path == '/api/pay' and role == 'Cashier':
                    store.pay(int(data['id']), f'Cashier: {operator}', data.get('method','Cash'))
                    return self.send(200, {'ok':True})
                self.send(403, {'error':'Operation not allowed.'})
            except (ValueError, KeyError, TypeError, OverflowError) as ex:
                self.send(400, {'error':str(ex)})
            except Exception:
                self.send(500, {'error':'Unable to save. Retry with the same request; do not create another booking.'})

    class Server(ThreadingHTTPServer):
        daemon_threads = True
        def get_request(self):
            conn, addr = super().get_request()
            conn.settimeout(15)
            return conn, addr

    server = Server(('0.0.0.0',port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, tokens
