"""Version 0.6: staff PINs, refunds and corrections, per-member gotra, linking,
paging, restore and the encrypted phone connection."""
import datetime as dt
import json
import shutil
import sqlite3
import ssl
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import security
from core import Store, receipt, report_text, local_date
from mobile import start, masked


def next_weekday(weekday, after=None):
    day = after or dt.date.today()
    while day.weekday() != weekday:
        day += dt.timedelta(days=1)
    return day.isoformat()


TODAY = local_date(dt.datetime.now(dt.timezone.utc).isoformat())


class V06Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.db = Store(self.folder / 'v06.db')
        self.eid = self.db.event(dict(name='Daily', day=dt.date.today().isoformat(), place='Temple', currency='INR',
                                      recurrence='Daily', weekdays='All'))
        self.sid = self.db.seva(dict(event_id=self.eid, name='Archana', price='100', kind='Seva', daily_limit='2'))
        self.fam = self.db.family(dict(head='Shetty family', phone='+971 50 765 4321', gotra='Kashyapa'))
        self.mom = self.db.member(dict(family_id=self.fam, name='Shashikala Shetty', relation='Self', gotra='Kashyapa'))
        self.daughter = self.db.member(dict(family_id=self.fam, name='Anu Rao', relation='Daughter', gotra='Bharadwaja'))

    def tearDown(self):
        self.temp.cleanup()

    def book(self, key, day=None, members=(None,), **extra):
        data = dict(request_key=key, event_id=self.eid, service_date=day or next_weekday(0), devotee='Shashikala Shetty',
                    family_id=self.fam, items=[dict(seva_id=self.sid, quantity=1, member_id=m) for m in members])
        data.update(extra)
        return self.db.book(data, 'Admin', True)

    # ------------------------------------------------------------------ staff
    def test_staff_roles_and_lockout(self):
        with self.assertRaises(ValueError):
            self.db.add_staff('Desk', 'Reception', '5930')  # first login must be Admin
        admin = self.db.add_staff('Ravi', 'Admin', '4821')
        self.assertTrue(self.db.has_staff())
        with self.assertRaises(ValueError):
            self.db.add_staff('ravi', 'Cashier', '5930')  # duplicate name, any case
        for weak in ('1111', '1234', '12', 'abcd'):
            with self.assertRaises(ValueError):
                self.db.add_staff('Weak', 'Cashier', weak)
        desk = self.db.add_staff('Desk', 'Reception', '5930')
        self.assertEqual(self.db.login(' desk ', '5930')['role'], 'Reception')
        with self.assertRaises(ValueError):
            self.db.login('Nobody', '5930')
        for _ in range(security.MAX_FAILURES):
            with self.assertRaises(ValueError):
                self.db.login('Desk', '0000')
        with self.assertRaisesRegex(ValueError, 'Too many'):
            self.db.login('Desk', '5930')  # locked even with the right PIN
        self.db.set_pin(desk, '6048', 'Ravi')  # admin reset unlocks
        self.assertEqual(self.db.login('Desk', '6048')['name'], 'Desk')
        with self.assertRaises(ValueError):
            self.db.update_staff(admin, 'Cashier', True)  # last admin
        with self.assertRaises(ValueError):
            self.db.update_staff(admin, 'Admin', False)
        self.db.update_staff(desk, 'Reception', False)
        with self.assertRaises(ValueError):
            self.db.login('Desk', '6048')
        with self.db.connect() as db:
            pins = [r[0] for r in db.execute('SELECT pin_hash FROM staff')]
        self.assertTrue(all('6048' not in p and len(p) == 64 for p in pins))

    def test_permissions(self):
        self.assertTrue(security.can('Cashier', 'pay'))
        self.assertTrue(security.can('Reception', 'pay'))  # event-day counters collect cash
        self.assertFalse(security.can('Reception', 'refund'))
        self.assertFalse(security.can('Cashier', 'refund'))
        self.assertTrue(security.can('Supervisor', 'refund'))
        self.assertFalse(security.can('Supervisor', 'masters'))
        with self.assertRaises(PermissionError):
            security.require('Reception', 'void')

    # ---------------------------------------------------------------- refunds
    def test_partial_then_full_refund(self):
        bid = self.book('r', members=(self.mom, self.daughter))
        with self.assertRaises(ValueError):
            self.db.refund(bid, 'Sup', '50', 'Cash', 'Not paid yet')
        self.db.pay(bid, 'Cashier', 'Card')
        with self.assertRaises(ValueError):
            self.db.refund(bid, 'Sup', '250', 'Cash', 'Too much')
        with self.assertRaises(ValueError):
            self.db.refund(bid, 'Sup', '50', 'Cash', ' ')
        self.assertFalse(self.db.refund(bid, 'Sup', '50', 'Cash', 'One person could not attend'))
        b = self.db.detail(bid)
        self.assertEqual((b['status'], b['refunded']), ('PAID', 5000))
        page = receipt(b)
        self.assertIn('Refunded INR 50.00', page)
        self.assertIn('Net paid: INR 150.00', page)
        day = b['service_date']
        self.assertEqual(len(self.db.schedule(day)), 2)  # partial refund keeps the sevas
        self.assertTrue(self.db.refund(bid, 'Sup', '150', 'Card', 'Pooja cancelled'))
        b = self.db.detail(bid)
        self.assertEqual(b['status'], 'REFUNDED')
        self.assertIn('REFUNDED', receipt(b))
        self.assertEqual(self.db.schedule(day), [])  # full refund removes them
        self.assertEqual(self.db.availability(self.eid, day)[self.sid], 2)  # and frees the slots
        with self.assertRaises(ValueError):
            self.db.refund(bid, 'Sup', '1', 'Cash', 'Again')
        rep = self.db.report(TODAY, TODAY)
        self.assertEqual(rep['collected']['INR'], 20000)
        self.assertEqual(rep['refunded']['INR'], 20000)
        self.assertEqual(rep['net']['INR'], 0)
        self.assertEqual(rep['refund_by_method'][('INR', 'Cash')], 5000)
        text = report_text(rep)
        self.assertIn('NET COLLECTION', text)
        self.assertIn('Pooja cancelled', text)
        tomorrow = (dt.date.fromisoformat(TODAY) + dt.timedelta(days=1)).isoformat()
        self.assertEqual(dict(self.db.report(tomorrow, tomorrow)['refunded']), {})

    def test_payment_method_correction(self):
        bid = self.book('m')
        with self.assertRaises(ValueError):
            self.db.correct_payment(bid, 'UPI', 'Wrong', 'Sup')
        self.db.pay(bid, 'Cashier', 'Cash')
        with self.assertRaises(ValueError):
            self.db.correct_payment(bid, 'Cash', 'Same', 'Sup')
        self.db.correct_payment(bid, 'UPI', 'Cashier pressed the wrong option', 'Sup')
        self.assertEqual(self.db.detail(bid)['payment_method'], 'UPI')
        self.assertEqual(self.db.report(TODAY, TODAY)['by_method'][('INR', 'UPI')], 10000)
        with self.db.connect() as db:
            entry = db.execute("SELECT * FROM audit WHERE action='payment method corrected'").fetchone()
        self.assertEqual(json.loads(entry['detail'])['from'], 'Cash')
        self.assertEqual(entry['actor'], 'Sup')

    def test_detail_corrections_and_reschedule(self):
        monday, tuesday = next_weekday(0), next_weekday(1)
        bid = self.book('c', monday, members=(self.daughter,))
        self.db.pay(bid, 'Cashier')
        item = self.db.detail(bid)['items'][0]
        with self.assertRaises(ValueError):
            self.db.correct_details(bid, {'devotee': 'Shashikala Shetty'}, 'no change', 'Sup')
        with self.assertRaises(ValueError):
            self.db.correct_details(bid, {'devotee': '  '}, 'blank', 'Sup')
        self.db.correct_details(bid, {'devotee': 'Shashikala S. Shetty', 'service_date': tuesday,
                                      'items': {item['id']: {'person': 'Anupama Rao', 'nakshatra': 'Rohini / ರೋಹಿಣಿ'}}},
                                'Spelling and new date requested', 'Sup')
        b = self.db.detail(bid)
        self.assertEqual((b['devotee'], b['service_date'], b['total'], b['status']), ('Shashikala S. Shetty', tuesday, 10000, 'PAID'))
        self.assertEqual((b['items'][0]['person'], b['items'][0]['nakshatra']), ('Anupama Rao', 'Rohini / ರೋಹಿಣಿ'))
        self.assertEqual(len(self.db.schedule(tuesday)), 1)
        self.assertEqual(self.db.schedule(monday), [])
        # Full day: moving another booking there is refused.
        self.book('t1', tuesday)
        other = self.book('m1', monday)
        with self.assertRaisesRegex(ValueError, 'full'):
            self.db.correct_details(other, {'service_date': tuesday}, 'move', 'Sup')
        with self.assertRaises(ValueError):
            self.db.correct_details(other, {'service_date': 'soon'}, 'move', 'Sup')
        with self.assertRaises(ValueError):
            self.db.correct_details(other, {'items': {999: {'person': 'X'}}}, 'bad slip', 'Sup')
        # Festival bookings follow the event date.
        fest = self.db.event(dict(name='Fest', day='2026-12-01', place='Hall', currency='AED'))
        fs = self.db.seva(dict(event_id=fest, name='Pooja', price='50', kind='Seva'))
        fb = self.db.book(dict(request_key='f', event_id=fest, devotee='F', items=[dict(seva_id=fs, quantity=1)]), 'Admin')
        with self.assertRaises(ValueError):
            self.db.correct_details(fb, {'service_date': '2026-12-02'}, 'move', 'Sup')
        with self.db.connect() as db:
            entry = json.loads(db.execute("SELECT detail FROM audit WHERE action='booking corrected'").fetchone()[0])
        self.assertEqual(entry['before']['devotee'], 'Shashikala Shetty')
        self.assertEqual(entry['after'][f"slip {item['id']}"]['person'], 'Anupama Rao')

    def test_reprint_marker(self):
        bid = self.book('p')
        self.assertNotIn('REPRINT', receipt(self.db.detail(bid)))
        self.db.printed(bid, 'Desk')
        self.assertEqual(receipt(self.db.detail(bid)).count('REPRINT'), 2)

    # -------------------------------------------------------- gotra and links
    def test_member_gotra_on_slips(self):
        bid = self.book('g', members=(self.mom, self.daughter))
        b = self.db.detail(bid)
        self.assertEqual([i['gotra'] for i in b['items']], ['Kashyapa', 'Bharadwaja'])
        self.assertEqual(b['phone'], '+971 50 765 4321')  # blank phone filled from register
        self.assertEqual(b['gotra'], 'Kashyapa')
        page = receipt(b)
        self.assertIn('Bharadwaja', page)
        self.assertEqual({r['gotra'] for r in self.db.schedule(b['service_date'])}, {'Kashyapa', 'Bharadwaja'})
        self.assertEqual([f['id'] for f in self.db.families('bharadwaja')], [self.fam])

    def test_link_older_bookings(self):
        old = self.db.book(dict(request_key='o1', event_id=self.eid, service_date=next_weekday(0), devotee='shashikala  shetty',
                                items=[dict(seva_id=self.sid, quantity=1)]), 'Admin')
        by_phone = self.db.book(dict(request_key='o2', event_id=self.eid, service_date=next_weekday(1), devotee='S Shetty',
                                     phone='050-765-4321', items=[dict(seva_id=self.sid, quantity=1)]), 'Admin')
        self.db.book(dict(request_key='o3', event_id=self.eid, service_date=next_weekday(1), devotee='Someone Else',
                          items=[dict(seva_id=self.sid, quantity=1)]), 'Admin')
        linked = self.book('l')
        found = {b['id']: b['match'] for b in self.db.link_suggestions(self.fam)}
        self.assertEqual(found, {old: 'name', by_phone: 'phone'})
        self.db.link_booking(old, self.fam, 'Sup')
        with self.assertRaises(ValueError):
            self.db.link_booking(old, self.fam, 'Sup')
        self.assertEqual({b['id'] for b in self.db.family_detail(self.fam)['bookings']}, {old, linked})
        self.db.unlink_booking(old, 'Sup')
        with self.assertRaises(ValueError):
            self.db.unlink_booking(old, 'Sup')
        with self.assertRaises(ValueError):
            self.db.link_booking(old, 999, 'Sup')

    # ------------------------------------------------------- paging and sync
    def test_paging_search_and_change_detection(self):
        version = self.db.data_version()
        ids = [self.db.book(dict(request_key=f'k{n}', event_id=self.eid, service_date=next_weekday(n % 7),
                                 devotee=f'Devotee {n:03d}', phone=f'+971 55 000 {n:04d}',
                                 items=[dict(seva_id=self.sid, quantity=1)]), 'Admin') for n in range(12)]
        self.assertNotEqual(self.db.data_version(), version)
        rows, more = self.db.bookings_page('', 5)
        self.assertEqual([r['id'] for r in rows], ids[::-1][:5])
        self.assertTrue(more)
        rows, more = self.db.bookings_page('', 5, 10)
        self.assertEqual(len(rows), 2)
        self.assertFalse(more)
        self.assertEqual([r['id'] for r in self.db.bookings_page('devotee 007')[0]], [ids[7]])
        self.assertEqual([r['id'] for r in self.db.bookings_page('55 000 0011')[0]], [ids[11]])
        self.assertEqual([r['id'] for r in self.db.bookings_page(str(ids[3]))[0]][-1], ids[3])
        self.assertEqual(self.db.bookings_page('100%_')[0], [])
        self.assertEqual(self.db.bookings_page('')[0][0]['slips'], 1)
        self.assertTrue(self.db.bookings_page('')[0][0]['print_pending'])
        v = self.db.data_version()
        self.assertEqual(v, self.db.data_version())
        self.db.printed(ids[0], 'Desk')
        self.assertNotEqual(v, self.db.data_version())
        self.assertEqual(self.db.unpaid_total(), {'INR': 120000})

    # --------------------------------------------------------- backup/restore
    def test_restore_and_auto_backup(self):
        keep = self.book('before')
        backup = self.folder / 'good.sqlite3'
        self.db.backup(backup)
        self.book('after')
        with self.assertRaises(ValueError):
            self.db.restore(self.folder / 'v06.db', self.folder / 'safety')
        junk = self.folder / 'junk.sqlite3'
        junk.write_bytes(b'not a database at all' * 100)
        with self.assertRaises(ValueError):
            self.db.restore(junk, self.folder / 'safety')
        other = self.folder / 'other.sqlite3'
        sqlite3.connect(other).execute('CREATE TABLE x(y)').connection.close()
        with self.assertRaises(ValueError):
            self.db.restore(other, self.folder / 'safety')
        self.assertEqual(len(self.db.bookings()), 2)  # failed restores changed nothing
        safety = self.db.restore(backup, self.folder / 'safety')
        self.assertEqual([b['id'] for b in self.db.bookings()], [keep])
        self.assertEqual(len(Store(safety).bookings()), 2)
        with self.db.connect() as db:
            self.assertTrue(db.execute("SELECT 1 FROM audit WHERE action='database restored'").fetchone())
        for n in range(13):
            with mock.patch('core.dt') as fake:
                fake.datetime.now.return_value = dt.datetime(2026, 1, 1, 0, 0, n)
                self.db.auto_backup(self.folder / 'auto')
        names = sorted(p.name for p in (self.folder / 'auto').glob('*.sqlite3'))
        self.assertEqual(len(names), 10)
        self.assertEqual(names[0], 'devseva-auto-20260101-000003.sqlite3')

    SOURCE = Path(__file__).with_name('fixtures') / 'seva-backup-2026-09-16.sqlite3'

    @unittest.skipUnless(SOURCE.exists(), 'user backup fixture not available')
    def test_restore_real_v04_backup_with_wal(self):
        src = self.folder / 'userbackup'
        src.mkdir()
        for suffix in ('', '-wal', '-shm'):
            if Path(str(self.SOURCE) + suffix).exists():
                shutil.copy(str(self.SOURCE) + suffix, src / ('b.sqlite3' + suffix))
        self.db.restore(src / 'b.sqlite3', self.folder / 'safety')
        names = sorted(b['devotee'] for b in self.db.bookings())
        self.assertEqual(names, ['Raviraj Shashikala Shetty', 'Raviraj Shetty'])
        self.assertEqual(len(self.db.schedule('2026-10-25')), 4)

    # ------------------------------------------------------ encrypted phones
    def test_https_phone_login_and_masked_register(self):
        self.db.add_staff('Ravi', 'Admin', '4821')
        self.db.add_staff('Desk', 'Reception', '5930')
        cert, key = security.ensure_certificate(self.folder / 'tls', ['127.0.0.1'])
        server, info = start(self.db, 0, cert, key)
        self.assertTrue(info['encrypted'])
        base = f'https://127.0.0.1:{server.server_port}'
        context = ssl.create_default_context(cafile=str(cert))  # the phone "trusts" our certificate
        def call(path, data=None, token=''):
            req = Request(base + path, data=json.dumps(data).encode() if data is not None else None,
                          headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
            with urlopen(req, timeout=5, context=context) as response:
                return json.load(response)
        try:
            with self.assertRaises(Exception):  # a phone that has not accepted the certificate
                urlopen(base + '/', timeout=5, context=ssl.create_default_context())
            self.assertIn('DevSeva', urlopen(base + '/', timeout=5, context=context).read().decode())
            token = call('/api/login', dict(code=info['code'], name='Desk', pin='5930'))['token']
            cat = call('/api/catalog', token=token)
            self.assertEqual((cat['role'], cat['can_pay']), ('Reception', True))
            fam = call('/api/devotees', dict(q='shetty'), token)[0]
            self.assertEqual(fam['phone'], '•••• 4321')
            self.assertEqual(fam['members'][1]['gotra'], 'Bharadwaja')
            data = dict(request_key='https', event_id=self.eid, service_date=next_weekday(0), family_id=fam['id'],
                        devotee='Shashikala Shetty', phone='', items=[dict(seva_id=self.sid, quantity=1, member_id=self.daughter)])
            bid = call('/api/book', data, token)['id']
            b = self.db.detail(bid)
            self.assertEqual(b['phone'], '+971 50 765 4321')
            self.assertEqual(b['operator'], 'Reception: Desk (phone)')
            self.assertEqual([r['id'] for r in call('/api/unpaid', token=token)], [bid])
            with self.assertRaises(HTTPError) as ex:  # fixed price cannot be changed from reception
                call('/api/book', dict(data, request_key='cheap', items=[dict(seva_id=self.sid, quantity=1, amount='1')]), token)
            self.assertEqual(ex.exception.code, 400)
            call('/api/logout', {}, token)
            with self.assertRaises(HTTPError) as ex:
                call('/api/catalog', token=token)
            self.assertEqual(ex.exception.code, 401)
            for _ in range(25):  # guessing access codes gets the phone blocked
                try:
                    call('/api/login', dict(code='0000-0000-0000', name='Desk', pin='5930'))
                except HTTPError as err:
                    last = err.code
            self.assertEqual(last, 429)
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(masked('12'), '')
        self.assertEqual(len(security.fingerprint(cert).split()), 32)

    def test_http_fallback_without_openssl(self):
        with mock.patch('security.find_openssl', return_value=None):
            with self.assertRaises(RuntimeError):
                security.ensure_certificate(self.folder / 'tls2', ['10.0.0.5'])
        server, info = start(self.db, 0)
        try:
            self.assertEqual((info['encrypted'], info['scheme']), (False, 'http'))
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
