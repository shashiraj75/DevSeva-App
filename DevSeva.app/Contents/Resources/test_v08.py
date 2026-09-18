# DevSeva — © 2026 Raviraj Shetty. All rights reserved.
"""Version 0.8: organisation settings, factory reset, developer key, copyright."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock
import core
import developer
from core import Store, receipt, COPYRIGHT


def filled(folder):
    db = Store(Path(folder) / 'v08.db')
    db.add_staff('Admin One', 'Admin', '4821')
    eid = db.event(dict(name='Sri Satyanarayana Pooja', kannada='ಶ್ರೀ ಸತ್ಯನಾರಾಯಣ ಪೂಜೆ', day='2026-10-25', place='Hall', currency='AED'))
    sid = db.seva(dict(event_id=eid, name='Pooja Booking', price='50', kind='Seva'))
    bid = db.book(dict(request_key='r1', event_id=eid, devotee='Shobha Shetty', phone='0507595420',
                       items=[dict(seva_id=sid, quantity=1)]), 'Admin: Admin One')
    return db, bid


class Settings(unittest.TestCase):
    def test_round_trip_and_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, bid = filled(tmp)
            self.assertEqual(db.settings(), {})
            db.save_settings({'org_name': 'Sri Krishna Mandir, Dubai', 'org_name_kn': 'ಶ್ರೀ ಕೃಷ್ಣ ಮಂದಿರ', 'junk': 'x'}, 'Admin: Admin One')
            self.assertEqual(db.settings(), {'org_name': 'Sri Krishna Mandir, Dubai', 'org_name_kn': 'ಶ್ರೀ ಕೃಷ್ಣ ಮಂದಿರ'})
            page = receipt(db.detail(bid))
            self.assertIn('Sri Krishna Mandir, Dubai', page)
            self.assertIn(COPYRIGHT, page)
            with db.connect() as conn:
                actions = [r[0] for r in conn.execute('SELECT action FROM audit')]
            self.assertIn('settings saved', actions)

    def test_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, _ = filled(tmp)
            db.save_settings({'org_name': '  ' + 'x' * 500}, 'Admin')
            self.assertEqual(db.settings()['org_name'], 'x' * 120)

    def test_copyright_constant(self):
        self.assertIn('Raviraj Shetty', core.COPYRIGHT)
        self.assertTrue(core.COPYRIGHT.startswith('©'))
        self.assertEqual(core.VERSION, '0.8')


class FactoryReset(unittest.TestCase):
    def test_erases_everything(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, _ = filled(tmp)
            db.save_settings({'org_name': 'Old Temple'}, 'Admin')
            backup = Path(tmp) / 'final.sqlite3'
            db.backup(backup)
            cleared = db.factory_reset('Developer')
            self.assertGreater(cleared, 5)
            fresh = Store(db.path)
            stats = fresh.stats()
            self.assertEqual({k: v for k, v in stats.items() if k != 'audit'},
                             {'events': 0, 'sevas': 0, 'bookings': 0, 'families': 0, 'members': 0, 'staff': 0})
            self.assertEqual(stats['audit'], 1)  # only the reset itself
            self.assertFalse(fresh.has_staff())
            self.assertEqual(fresh.settings(), {})
            # the final backup still holds the old data
            self.assertEqual(Store(backup).stats()['bookings'], 1)
            # the app works normally after the reset
            fresh.add_staff('New Admin', 'Admin', '1357')
            self.assertEqual(fresh.login('New Admin', '1357')['role'], 'Admin')


class DeveloperKey(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.key = self.folder / 'developer.key'
        self.guard = developer.Guard(self.folder, self.key)

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_and_verify(self):
        self.assertFalse(developer.has_key(self.key))
        with self.assertRaises(ValueError):
            self.guard.verify('anything at all')
        self.guard.set_key('Correct horse 42')
        self.assertTrue(developer.has_key(self.key))
        data = json.loads(self.key.read_text())
        self.assertNotIn('Correct horse 42', self.key.read_text())
        self.assertEqual(len(data['salt']), 32)
        self.assertTrue(self.guard.verify('Correct horse 42'))

    def test_strength(self):
        for weak in ('short', '1234567890123', 'aaaaaaaaaaaa'):
            with self.assertRaises(ValueError):
                self.guard.set_key(weak)
        self.assertFalse(self.key.exists())

    def test_cannot_rekey_without_current(self):
        self.guard.set_key('Correct horse 42')
        with self.assertRaises(ValueError):
            self.guard.set_key('Someone else 99')
        with self.assertRaises(ValueError):
            self.guard.set_key('Someone else 99', current='wrong passphrase')
        self.assertTrue(self.guard.verify('Correct horse 42'))
        self.guard.set_key('Brand new phrase 7', current='Correct horse 42')
        self.assertTrue(self.guard.verify('Brand new phrase 7'))
        with self.assertRaises(ValueError):
            self.guard.verify('Correct horse 42')

    def test_lockout(self):
        self.guard.set_key('Correct horse 42')
        for _ in range(developer.MAX_FAILURES - 1):
            with self.assertRaisesRegex(ValueError, 'not correct'):
                self.guard.verify('nope nope nope')
        with self.assertRaisesRegex(ValueError, 'locked'):
            self.guard.verify('nope nope nope')
        with self.assertRaisesRegex(ValueError, 'Too many'):
            self.guard.verify('Correct horse 42')  # even the right one waits
        later = time.time() + developer.LOCK_SECONDS + 1
        with mock.patch('developer.time.time', return_value=later):
            self.assertTrue(self.guard.verify('Correct horse 42'))

    def test_key_survives_data_reset(self):
        self.guard.set_key('Correct horse 42')
        db, _ = filled(self.folder)
        db.factory_reset()
        self.assertTrue(developer.has_key(self.key))


class Countdown(unittest.TestCase):
    def test_labels(self):
        try:
            import app
        except ImportError:
            self.skipTest('Tk not available')
        once = {'recurrence': 'Once', 'day': '2026-10-25', 'end_day': None}
        c = app.App.countdown
        self.assertEqual(c(once, '2026-09-16'), 'in 39 days')
        self.assertEqual(c(once, '2026-10-24'), 'Tomorrow')
        self.assertEqual(c(once, '2026-10-25'), 'TODAY')
        self.assertEqual(c(once, '2026-10-26'), 'Finished')
        self.assertEqual(c(once, '2026-10-30'), 'Finished 5 days ago')
        multi = {'recurrence': 'Once', 'day': '2026-10-25', 'end_day': '2026-10-27'}
        self.assertEqual(c(multi, '2026-10-26'), 'ON NOW · day 2 of 3')
        daily = {'recurrence': 'Daily', 'day': '2026-01-01', 'end_day': None}
        self.assertEqual(c(daily, '2026-09-16'), 'Daily — running')


if __name__ == '__main__':
    unittest.main()
