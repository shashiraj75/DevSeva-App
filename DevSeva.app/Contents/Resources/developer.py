# DevSeva — © 2026 Raviraj Shetty. All rights reserved.
"""Developer-only access (factory reset, customer Admin PIN reset).

The developer passphrase is stored as a salted PBKDF2 hash in `developer.key`,
kept INSIDE the application (next to app.py, or inside a standalone build) —
never in the customer's database — so restoring or resetting data cannot
remove it, and a copy that has a key cannot be re-keyed without the current
passphrase. Wrong passphrases are rate-limited per laptop.
"""
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
from pathlib import Path

ITERATIONS = 600_000
MAX_FAILURES = 5
LOCK_SECONDS = 15 * 60
MIN_LENGTH = 10


def key_path():
    here = Path(__file__).with_name('developer.key')
    frozen = Path(getattr(sys, '_MEIPASS', '')) / 'developer.key' if getattr(sys, '_MEIPASS', None) else None
    if frozen is not None and frozen.exists() and not here.exists():
        return frozen
    return here


def has_key(path=None):
    path = Path(path) if path else key_path()
    try:
        data = json.loads(path.read_text())
        return bool(data.get('salt') and data.get('hash'))
    except (OSError, ValueError):
        return False


def _digest(passphrase, salt, iterations=ITERATIONS):
    return hashlib.pbkdf2_hmac('sha256', passphrase.encode(), bytes.fromhex(salt), iterations).hex()


def _check_strength(passphrase):
    if len(passphrase) < MIN_LENGTH:
        raise ValueError(f'Use a developer passphrase of at least {MIN_LENGTH} characters.')
    if passphrase.isdigit() or len(set(passphrase)) < 5:
        raise ValueError('Choose a stronger passphrase (mix words, numbers or symbols).')


class Guard:
    """Tracks failed attempts in the laptop's data folder."""
    def __init__(self, data_folder, path=None):
        self.path = Path(path) if path else key_path()
        self.state_file = Path(data_folder) / 'developer-attempts.json'

    def _state(self):
        try:
            return json.loads(self.state_file.read_text())
        except (OSError, ValueError):
            return {'failures': 0, 'locked_until': 0}

    def _save(self, state):
        try:
            self.state_file.write_text(json.dumps(state))
        except OSError:
            pass

    def verify(self, passphrase):
        if not has_key(self.path):
            raise ValueError('This copy of DevSeva has no developer key yet.')
        state = self._state()
        now = time.time()
        if state.get('locked_until', 0) > now:
            minutes = int((state['locked_until'] - now) // 60) + 1
            raise ValueError(f'Too many wrong passphrases. Try again in {minutes} minute(s).')
        data = json.loads(self.path.read_text())
        ok = hmac.compare_digest(_digest(str(passphrase), data['salt'], data.get('iterations', ITERATIONS)), data['hash'])
        if ok:
            self._save({'failures': 0, 'locked_until': 0})
            return True
        failures = state.get('failures', 0) + 1
        locked = now + LOCK_SECONDS if failures >= MAX_FAILURES else 0
        self._save({'failures': 0 if locked else failures, 'locked_until': locked})
        raise ValueError('Developer passphrase is not correct.' + (' Developer tools are locked for 15 minutes.' if locked else ''))

    def set_key(self, new_passphrase, current=None):
        """Create the key (only when none exists) or change it (current passphrase required)."""
        if has_key(self.path):
            if current is None:
                raise ValueError('This copy already has a developer key. Enter the current passphrase to change it.')
            self.verify(current)
        _check_strength(str(new_passphrase))
        salt = secrets.token_hex(16)
        payload = {'version': 1, 'salt': salt, 'iterations': ITERATIONS, 'hash': _digest(str(new_passphrase), salt),
                   'created': time.strftime('%Y-%m-%d')}
        tmp = self.path.with_suffix('.tmp')
        try:
            tmp.write_text(json.dumps(payload))
            os.replace(tmp, self.path)
        except OSError as ex:
            raise ValueError(f'Could not save the developer key in {self.path.parent} ({ex.strerror}). '
                             'Move DevSeva.app to your Applications or Documents folder, open it from there and try again.')
        return self.path
