# DevSeva — © 2026 Raviraj Shetty. All rights reserved.
"""DevSeva security helpers: staff PIN hashing, role permissions and the
self-signed certificate used for the encrypted local phone connection.

Standard library only. Certificates are made with the operating system's
openssl command (present on every macOS); without it the phone service falls
back to unencrypted HTTP and says so.
"""
import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import shutil
import socket
import ssl
import subprocess
import tempfile
import re
from pathlib import Path

ROLES = ('Admin', 'Supervisor', 'Cashier', 'Reception')
PIN_ITERATIONS = 200_000
MAX_FAILURES = 5
LOCK_MINUTES = 5

# What each role may do.
PERMISSIONS = {
    'book': ROLES,
    'devotees': ROLES,
    'print': ROLES,
    'pay': ROLES,  # event-day reception counters also collect cash (cash handover report per person)
    'reports': ('Admin', 'Supervisor', 'Cashier'),
    'override_price': ('Admin', 'Supervisor'),
    'void': ('Admin', 'Supervisor'),
    'refund': ('Admin', 'Supervisor'),
    'correct': ('Admin', 'Supervisor'),
    'link': ('Admin', 'Supervisor'),
    'mobile': ('Admin', 'Supervisor'),
    'backup': ('Admin', 'Supervisor'),
    'import': ('Admin', 'Supervisor'),
    'masters': ('Admin',),
    'staff': ('Admin',),
    'restore': ('Admin',),
}

ACTION_NAMES = {
    'pay': 'receive payments', 'reports': 'view reports', 'override_price': 'change fixed seva prices',
    'void': 'cancel bookings', 'refund': 'refund payments', 'correct': 'correct bookings',
    'link': 'link bookings to devotees', 'mobile': 'start mobile access', 'backup': 'back up the database',
    'masters': 'change events and sevas', 'import': 'import bookings', 'staff': 'manage staff', 'restore': 'restore a backup',
}


def can(role, action):
    return role in PERMISSIONS.get(action, ())


def require(role, action):
    if not can(role, action):
        raise PermissionError(f'A {role} login cannot {ACTION_NAMES.get(action, action)}. Ask a supervisor or administrator.')


def check_pin(pin):
    pin = str(pin or '').strip()
    if not pin.isdigit() or not 4 <= len(pin) <= 12:
        raise ValueError('PIN must be 4 to 12 digits.')
    if len(set(pin)) == 1 or pin in '0123456789012' or pin in '9876543210987':
        raise ValueError('Choose a less obvious PIN (not 1111 or 1234).')
    return pin


def hash_pin(pin, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', str(pin).encode(), bytes.fromhex(salt), PIN_ITERATIONS).hex()
    return salt, digest


def pin_matches(pin, salt, digest):
    return hmac.compare_digest(hash_pin(pin, salt)[1], digest)


# ------------------------------------------------------------ certificates
def local_addresses():
    found = set()
    # Prefer the interface carrying the Mac's default route. Hostname lookup
    # can return stale VPN/virtual addresses that a phone on Wi-Fi cannot
    # reach, which presents as a browser timeout rather than a login error.
    try:
        route = subprocess.run(['/usr/sbin/route', '-n', 'get', 'default'],
                               capture_output=True, text=True, timeout=3, check=False)
        interface = next((line.split(':', 1)[1].strip() for line in route.stdout.splitlines()
                          if line.strip().startswith('interface:')), '')
        if interface:
            net = subprocess.run(['/sbin/ifconfig', interface], capture_output=True, text=True,
                                 timeout=3, check=False).stdout
            found.update(re.findall(r'\binet\s+(\d+\.\d+\.\d+\.\d+)\b', net))
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        found.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    # Discover the address used for the local network without sending traffic.
    for probe in ('10.255.255.255', '192.168.255.255', '172.31.255.255'):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect((probe, 1))
                found.add(s.getsockname()[0])
        except OSError:
            pass
    return sorted(ip for ip in found if not ip.startswith('127.') and not ip.startswith('169.254.'))


def find_openssl():
    for candidate in ('/usr/bin/openssl', shutil.which('openssl')):
        if candidate and os.access(candidate, os.X_OK):
            return candidate
    return None


def fingerprint(cert_path):
    der = ssl.PEM_cert_to_DER_cert(Path(cert_path).read_text())
    digest = hashlib.sha256(der).hexdigest().upper()
    return ' '.join(digest[i:i + 2] for i in range(0, len(digest), 2))


def ensure_certificate(folder, addresses=None):
    """Create (or reuse) a self-signed certificate valid for this laptop's addresses.

    Returns (cert_path, key_path). Raises RuntimeError if openssl is unavailable.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    os.chmod(folder, 0o700)
    cert, key, meta = folder / 'devseva-local.crt', folder / 'devseva-local.key', folder / 'devseva-local.json'
    names = sorted(set(addresses if addresses is not None else local_addresses()) | {'127.0.0.1'})
    host = socket.gethostname().split('.')[0][:50] or 'devseva'
    try:
        existing = json.loads(meta.read_text())
        if cert.exists() and key.exists() and set(names) <= set(existing['addresses']):
            ssl.create_default_context(ssl.Purpose.CLIENT_AUTH).load_cert_chain(cert, key)
            return cert, key
    except (OSError, ValueError, KeyError, ssl.SSLError):
        pass
    openssl = find_openssl()
    if not openssl:
        raise RuntimeError('The openssl tool was not found, so the encrypted connection is unavailable.')
    ips = [ip for ip in names if _is_ip(ip)]
    alt_lines = [f'IP.{i} = {ip}' for i, ip in enumerate(ips, 1)] + ['DNS.1 = localhost', f'DNS.2 = {host}.local']
    config = '\n'.join([
        '[req]', 'distinguished_name = dn', 'x509_extensions = ext', 'prompt = no',
        '[dn]', f'CN = DevSeva {host}', 'O = DevSeva offline desk',
        '[ext]', 'basicConstraints = critical,CA:FALSE', 'keyUsage = critical,digitalSignature,keyEncipherment',
        'extendedKeyUsage = serverAuth', 'subjectAltName = @alt',
        '[alt]', *alt_lines, ''])
    with tempfile.TemporaryDirectory() as tmp:
        conf = Path(tmp) / 'devseva.cnf'
        conf.write_text(config)
        new_cert, new_key = Path(tmp) / 'c.pem', Path(tmp) / 'k.pem'
        result = subprocess.run([openssl, 'req', '-x509', '-newkey', 'rsa:2048', '-sha256', '-nodes', '-days', '825',
                                 '-keyout', str(new_key), '-out', str(new_cert), '-config', str(conf)],
                                capture_output=True, text=True, timeout=60)
        if result.returncode != 0 or not new_cert.exists():
            raise RuntimeError('Could not create the encryption certificate: ' + (result.stderr or result.stdout)[-300:])
        ssl.create_default_context(ssl.Purpose.CLIENT_AUTH).load_cert_chain(new_cert, new_key)
        shutil.copyfile(new_key, key)
        os.chmod(key, 0o600)
        shutil.copyfile(new_cert, cert)
    meta.write_text(json.dumps({'addresses': names}))
    return cert, key


def _is_ip(value):
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False
