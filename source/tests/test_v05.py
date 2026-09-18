"""Version 0.5: devotee register, daily poojas, per-person slips, schedule, reports."""
import concurrent.futures
import csv
import datetime as dt
import json
import shutil
import sqlite3
import ssl
import tempfile
import unittest
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from core import Store, receipt, report_text, schedule_html, parse_weekdays, local_date
from mobile import start
import security


def next_weekday(weekday, after=None):
    day = after or dt.date.today()
    while day.weekday() != weekday:
        day += dt.timedelta(days=1)
    return day.isoformat()


class V05Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Store(Path(self.temp.name) / 'v05.db')
        self.start = dt.date.today().isoformat()
        self.daily = self.db.event(dict(name='Temple daily poojas', kannada='', day=self.start, place='Temple',
                                        currency='INR', recurrence='Daily', weekdays='Mon, Tue, Fri'))
        self.abhisheka = self.db.seva(dict(event_id=self.daily, name='Rudrabhisheka', kannada='ರುದ್ರಾಭಿಷೇಕ',
                                           price='250', kind='Seva', daily_limit='3'))
        self.fam = self.db.family(dict(head='Raviraj Shetty', phone='+971 50 123 4567', gotra='Kashyapa'))
        self.me = self.db.member(dict(family_id=self.fam, name='Raviraj Shetty', kannada='ರವಿರಾಜ್ ಶೆಟ್ಟಿ',
                                      relation='Self', rashi='Mesha / ಮೇಷ', nakshatra='Ashwini / ಅಶ್ವಿನಿ'))
        self.son = self.db.member(dict(family_id=self.fam, name='Rishabh Shetty', kannada='ರಿಷಭ್ ಶೆಟ್ಟಿ',
                                       relation='Son', rashi='Simha / ಸಿಂಹ', nakshatra='Magha / ಮಘಾ'))
        self.monday = next_weekday(0)

    def tearDown(self):
        self.temp.cleanup()

    def booking(self, key, day=None, qty=1, members=(None,), **extra):
        data = dict(request_key=key, event_id=self.daily, service_date=day or self.monday, devotee='Raviraj Shetty',
                    family_id=self.fam, gotra='Kashyapa',
                    items=[dict(seva_id=self.abhisheka, quantity=qty, member_id=m) for m in members])
        data.update(extra)
        return data

    def test_weekday_parsing(self):
        self.assertEqual(parse_weekdays('All'), '0123456')
        self.assertEqual(parse_weekdays('fri, Monday'), '04')
        with self.assertRaises(ValueError):
            parse_weekdays('Funday')

    def test_daily_pooja_date_rules(self):
        bid = self.db.book(self.booking('ok'), 'Admin')
        self.assertEqual(self.db.detail(bid)['service_date'], self.monday)
        with self.assertRaises(ValueError):  # Wednesday is not an allowed day
            self.db.book(self.booking('wed', next_weekday(2)), 'Admin')
        with self.assertRaises(ValueError):  # before the start date
            self.db.book(self.booking('old', next_weekday(0, dt.date.today() - dt.timedelta(days=14))), 'Admin')
        with self.assertRaises(ValueError):
            self.db.book(self.booking('bad', 'not-a-date'), 'Admin')
        self.db.event(dict(name='Temple daily poojas', kannada='', day=self.start, place='Temple', currency='INR',
                           recurrence='Daily', weekdays='All', end_day=self.start), self.daily)
        with self.assertRaises(ValueError):  # after the end date
            self.db.book(self.booking('late', next_weekday(0, dt.date.today() + dt.timedelta(days=1))), 'Admin')

    def test_once_event_uses_event_date(self):
        eid = self.db.event(dict(name='Festival', day='2026-10-25', place='Hall', currency='AED'))
        sid = self.db.seva(dict(event_id=eid, name='Pooja', price='50', kind='Seva'))
        bid = self.db.book(dict(request_key='f', event_id=eid, service_date='2030-01-01', devotee='X',
                                items=[dict(seva_id=sid, quantity=1)]), 'Admin')
        self.assertEqual(self.db.detail(bid)['service_date'], '2026-10-25')

    def test_postponed_festival_moves_bookings(self):
        eid = self.db.event(dict(name='Festival', day='2026-10-25', place='Hall', currency='AED'))
        sid = self.db.seva(dict(event_id=eid, name='Pooja', price='50', kind='Seva'))
        keep = self.db.book(dict(request_key='a', event_id=eid, devotee='A', items=[dict(seva_id=sid, quantity=1)]), 'Admin')
        gone = self.db.book(dict(request_key='b', event_id=eid, devotee='B', items=[dict(seva_id=sid, quantity=1)]), 'Admin')
        self.db.void(gone, 'Cancelled')
        self.db.event(dict(name='Festival', day='2026-11-01', place='Hall', currency='AED'), eid)
        self.assertEqual(self.db.detail(keep)['service_date'], '2026-11-01')
        self.assertEqual(self.db.detail(keep)['event']['day'], '2026-10-25')  # snapshot untouched
        self.assertEqual(self.db.detail(gone)['service_date'], '2026-10-25')
        self.assertEqual(len(self.db.schedule('2026-11-01')), 1)
        self.assertIn('2026-11-01', receipt(self.db.detail(keep)))

    def test_daily_limit_is_enforced_under_concurrency(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            def attempt(n):
                try:
                    return self.db.book(self.booking(f'k{n}'), 'Reception')
                except ValueError:
                    return None
            results = list(pool.map(attempt, range(10)))
        self.assertEqual(len([r for r in results if r]), 3)
        self.assertEqual(self.db.availability(self.daily, self.monday)[self.abhisheka], 0)
        # Cancelling frees a slot; another day is unaffected.
        self.db.void(next(r for r in results if r), 'Changed plan')
        self.assertEqual(self.db.availability(self.daily, self.monday)[self.abhisheka], 1)
        self.assertEqual(self.db.availability(self.daily, next_weekday(1))[self.abhisheka], 3)
        with self.assertRaises(ValueError):
            self.db.book(self.booking('two', qty=2), 'Reception')

    def test_per_person_slips(self):
        bid = self.db.book(self.booking('fam', members=(self.me, self.son)), 'Reception')
        b = self.db.detail(bid)
        self.assertEqual([i['person'] for i in b['items']], ['Raviraj Shetty', 'Rishabh Shetty'])
        self.assertEqual(b['items'][1]['nakshatra'], 'Magha / ಮಘಾ')
        html = receipt(b)
        self.assertEqual(html.count('<section>'), 3)
        self.assertIn('ರಿಷಭ್ ಶೆಟ್ಟಿ', html)
        self.assertIn('for Rishabh Shetty', html)
        self.assertIn('Kashyapa', html)
        self.assertIn(self.monday, html)
        # Later register edits do not change the printed snapshot.
        self.db.member(dict(family_id=self.fam, name='Rishabh S', relation='Son'), self.son)
        self.assertEqual(self.db.detail(bid)['items'][1]['person'], 'Rishabh Shetty')

    def test_member_must_belong_to_family(self):
        other = self.db.family(dict(head='Someone Else'))
        stranger = self.db.member(dict(family_id=other, name='Stranger'))
        with self.assertRaises(ValueError):
            self.db.book(self.booking('x', members=(stranger,)), 'Reception')
        data = self.booking('y', members=(self.me,))
        data['family_id'] = None
        with self.assertRaises(ValueError):
            self.db.book(data, 'Reception')

    def test_save_new_devotee_once_on_retry(self):
        data = dict(request_key='walkin', event_id=self.daily, service_date=self.monday, devotee='Walk In',
                    devotee_kn='ವಾಕ್', phone='0501112222', gotra='Bharadwaja', rashi='Tula / ತುಲಾ',
                    save_devotee=True, items=[dict(seva_id=self.abhisheka, quantity=1)])
        first = self.db.book(data, 'Reception')
        self.assertEqual(self.db.book(data, 'Reception'), first)
        found = self.db.families('1112222')
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['members'][0]['rashi'], 'Tula / ತುಲಾ')
        self.assertEqual(self.db.detail(first)['family_id'], found[0]['id'])
        self.assertEqual(self.db.family_detail(found[0]['id'])['bookings'][0]['id'], first)

    def test_search(self):
        self.assertEqual([f['id'] for f in self.db.families('rishabh')], [self.fam])
        self.assertEqual([f['id'] for f in self.db.families('kashyapa')], [self.fam])
        self.assertEqual([f['id'] for f in self.db.families('4567')], [self.fam])
        self.assertEqual(self.db.families('nobody'), [])

    def test_archive_hides_and_blocks(self):
        self.db.set_active('events', self.daily, False)
        self.assertEqual(self.db.catalog(active_only=True)['events'], [])
        with self.assertRaises(ValueError):
            self.db.book(self.booking('arch'), 'Admin')
        self.db.set_active('events', self.daily, True)
        self.db.set_active('sevas', self.abhisheka, False)
        self.assertEqual(self.db.catalog(active_only=True)['sevas'], [])
        with self.assertRaises(ValueError):
            self.db.book(self.booking('arch2'), 'Admin')

    def test_schedule_and_reports(self):
        paid = self.db.book(self.booking('p', members=(self.me, self.son)), 'Admin')
        self.db.pay(paid, 'Cashier', 'UPI')
        unpaid = self.db.book(self.booking('u'), 'Admin')
        voided = self.db.book(self.booking('v', next_weekday(1)), 'Admin')
        self.db.void(voided, 'Duplicate')
        rows = self.db.schedule(self.monday)
        self.assertEqual(len(rows), 3)
        self.assertEqual(self.db.schedule(next_weekday(1)), [])
        page = schedule_html(self.monday, rows)
        self.assertIn('Rudrabhisheka', page)
        self.assertIn('Kashyapa', page)
        today = local_date(dt.datetime.now(dt.timezone.utc).isoformat())
        rep = self.db.report(today, today)
        self.assertEqual(rep['collected']['INR'], 50000)
        self.assertEqual(rep['by_method'][('INR', 'UPI')], 50000)
        self.assertEqual(rep['by_seva'][('INR', 'Rudrabhisheka')], [2, 50000])
        self.assertEqual(rep['outstanding']['INR'], 25000)
        self.assertEqual((rep['bookings'], rep['void']), (2, 1))
        self.assertIn('UPI', report_text(rep))
        tomorrow = (dt.date.fromisoformat(today) + dt.timedelta(days=1)).isoformat()
        self.assertEqual(dict(self.db.report(tomorrow, tomorrow)['collected']), {})
        with self.assertRaises(ValueError):
            self.db.report(tomorrow, today)
        out = Path(self.temp.name) / 'lines.csv'
        self.db.export_lines(out, today, today)
        with out.open(encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 4)
        self.assertEqual({r['Person'] for r in rows}, {'Raviraj Shetty', 'Rishabh Shetty'})
        # Currencies are never mixed.
        eid = self.db.event(dict(name='UAE', day=self.start, place='Dubai', currency='AED'))
        sid = self.db.seva(dict(event_id=eid, name='Pooja', price='50', kind='Seva'))
        self.db.pay(self.db.book(dict(request_key='aed', event_id=eid, devotee='A', items=[dict(seva_id=sid, quantity=1)]), 'Admin'), 'C')
        rep = self.db.report(today, today)
        self.assertEqual((rep['collected']['AED'], rep['collected']['INR']), (5000, 50000))

    def test_mobile_register_and_daily_booking(self):
        self.db.add_staff('Admin', 'Admin', '4821')
        self.db.add_staff('Desk', 'Reception', '5930')
        cert, key = security.ensure_certificate(Path(self.temp.name) / 'tls', ['127.0.0.1'])
        server, info = start(self.db, 0, cert, key)
        base = f'https://127.0.0.1:{server.server_port}'
        context = ssl.create_default_context(cafile=str(cert))
        req = Request(base + '/api/login', data=json.dumps(dict(code=info['code'].lower(), name='Desk', pin='5930')).encode(),
                      headers={'Content-Type': 'application/json'})
        with urlopen(req, timeout=5, context=context) as response:
            reception = json.load(response)['token']
        def call(path, data=None):
            req = Request(base + path, data=json.dumps(data).encode() if data else None,
                          headers={'Authorization': 'Bearer ' + reception, 'Content-Type': 'application/json'})
            with urlopen(req, timeout=3, context=context) as response:
                return json.load(response)
        try:
            self.db.set_active('events', self.db.event(dict(name='Old', day='2020-01-01', place='X', currency='AED')), False)
            cat = call('/api/catalog')
            self.assertEqual([e['id'] for e in cat['events']], [self.daily])
            found = call('/api/devotees', dict(operator='Desk', q='shetty'))
            self.assertEqual(found[0]['members'][1]['name'], 'Rishabh Shetty')
            self.assertEqual(call('/api/devotees', dict(operator='Desk', q='s')), [])
            left = call('/api/availability', dict(operator='Desk', event_id=self.daily, service_date=self.monday))
            self.assertEqual(left[str(self.abhisheka)], 3)
            data = self.booking('mob', members=(self.son,))
            data['operator'] = 'Desk'
            bid = call('/api/book', data)['id']
            self.assertEqual(self.db.detail(bid)['items'][0]['person'], 'Rishabh Shetty')
            with self.assertRaises(HTTPError) as ex:
                call('/api/book', dict(self.booking('bad', next_weekday(2)), operator='Desk'))
            self.assertEqual(ex.exception.code, 400)
        finally:
            server.shutdown()
            server.server_close()


class RealBackupUpgrade(unittest.TestCase):
    """Upgrades a copy of the user's v0.4 backup, if present next to the tests."""
    SOURCE = Path(__file__).with_name('fixtures') / 'seva-backup-2026-09-16.sqlite3'

    @unittest.skipUnless(SOURCE.exists(), 'user backup fixture not available')
    def test_upgrade_preserves_bookings(self):
        with tempfile.TemporaryDirectory() as folder:
            for suffix in ('', '-wal', '-shm'):
                src = Path(str(self.SOURCE) + suffix)
                if src.exists():
                    shutil.copy(src, Path(folder) / ('db.sqlite3' + suffix))
            path = Path(folder) / 'db.sqlite3'
            before = sqlite3.connect(path).execute('SELECT id,devotee,total,status FROM bookings ORDER BY id').fetchall()
            store = Store(path)
            after = [(b['id'], b['devotee'], b['total'], b['status']) for b in reversed(store.bookings())]
            self.assertEqual(before, after)
            for bid, *_ in before:
                b = store.detail(bid)
                self.assertEqual(b['service_date'], b['event']['day'])
                self.assertTrue(all(i['person'] == b['devotee'] for i in b['items']))
                receipt(b)
            self.assertTrue(store.schedule('2026-10-25'))
            Store(path)  # reopening is safe


if __name__ == '__main__':
    unittest.main()
