"""Version 0.7: importing bookings and the event-day counter."""
import datetime as dt
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen
import importer
import security
from core import Store, receipt, report_text, local_date
from mobile import start

HERE = Path(__file__).parent
# Tests live in tests/ while the app ships sample import files from samples/.
SAMPLES = HERE.parent / 'samples'
TODAY = local_date(dt.datetime.now(dt.timezone.utc).isoformat())


def event_store(folder):
    """A copy of the 25 Oct 2026 Sri Satyanarayana Pooja set-up (same sevas as the real backup)."""
    db = Store(Path(folder) / 'v07.db')
    eid = db.event(dict(name='Sri Satyanarayana Pooja', day='2026-10-25', place='JSS School Al Safa', currency='AED'))
    ids = {'pooja': db.seva(dict(event_id=eid, name='Pooja Booking', price='50', kind='Seva'))}
    for name in ('Maha Prasada', 'Flowers', 'Fruits', 'Consumables'):
        ids[name] = db.seva(dict(event_id=eid, name=name, price='0', kind='Sponsorship'))
    return db, eid, ids


class ReaderTests(unittest.TestCase):
    def test_header_guessing(self):
        headers = ['Timestamp', 'Booking No', 'Devotee Name', 'Mobile Number', 'Email Address', 'Booking For',
                   'Number of Poojas', 'Amount (AED)', 'Payment Status', 'Payment Mode', 'Sl No']
        m = importer.guess_mapping(headers)
        self.assertEqual({k: headers[v] for k, v in m.items()}, {
            'ref': 'Booking No', 'name': 'Devotee Name', 'phone': 'Mobile Number', 'email': 'Email Address',
            'sevas': 'Booking For', 'quantity': 'Number of Poojas', 'amount': 'Amount (AED)',
            'paid': 'Payment Status', 'method': 'Payment Mode'})
        self.assertNotIn('ref', importer.guess_mapping(['Sl No', 'Name', 'Amount']))

    def test_xlsx_reader(self):
        headers, rows, sheets, chosen = importer.read_table(SAMPLES / 'sample-google-form-bookings.xlsx')
        self.assertEqual(chosen, 'Form Responses 1')
        self.assertEqual(headers[2], 'Devotee Name')
        self.assertEqual(len(rows), 10)
        self.assertEqual(rows[2][3], '971502223344')  # numeric cell, no ".0"
        self.assertEqual(rows[0][7], '50')
        with self.assertRaises(ValueError):
            importer.read_table(HERE / 'README.md')
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / 'bad.xlsx'
            bad.write_bytes(b'not a zip')
            with self.assertRaisesRegex(ValueError, 'not a valid'):
                importer.read_table(bad)
            old = Path(tmp) / 'old.xls'
            old.write_bytes(b'x')
            with self.assertRaisesRegex(ValueError, 'Save As'):
                importer.read_table(old)
            # A workbook with inline strings, a hidden sheet and gaps between cells.
            book = Path(tmp) / 'inline.xlsx'
            with zipfile.ZipFile(book, 'w') as z:
                z.writestr('xl/workbook.xml', '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                           'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                           '<sheet name="Hidden" sheetId="1" state="hidden" r:id="rId1"/>'
                           '<sheet name="List" sheetId="2" r:id="rId2"/></sheets></workbook>')
                z.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                           '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Target="/xl/worksheets/sheet2.xml"/></Relationships>')
                z.writestr('xl/worksheets/sheet1.xml', '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData/></worksheet>')
                z.writestr('xl/worksheets/sheet2.xml', '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                           '<row r="1"><c r="A1" t="inlineStr"><is><t>Name</t></is></c><c r="C1" t="inlineStr"><is><t>Amount</t></is></c></row>'
                           '<row r="2"><c r="A2" t="inlineStr"><is><t>ಶ್ರೀ Devi</t></is></c><c r="C2"><v>100.5</v></c></row>'
                           '</sheetData></worksheet>')
            headers, rows, sheets, chosen = importer.read_table(book)
            self.assertEqual((sheets, chosen), (['List'], 'List'))
            self.assertEqual(headers, ['Name', 'Column 2', 'Amount'])
            self.assertEqual(rows, [['ಶ್ರೀ Devi', '', '100.5']])

    def test_csv_reader_encodings(self):
        with tempfile.TemporaryDirectory() as tmp:
            for encoding, name in (('utf-8-sig', 'a.csv'), ('utf-16', 'b.csv'), ('cp1252', 'c.csv')):
                path = Path(tmp) / name
                path.write_bytes('Name,Amount\nRénuka Shetty,50\n'.encode(encoding))
                headers, rows, _, _ = importer.read_table(path)
                self.assertEqual(rows[0][0], 'Rénuka Shetty', encoding)
            tab = Path(tmp) / 't.tsv'
            tab.write_text('Name\tMobile\nA B\t050 1234567\n')
            self.assertEqual(importer.read_table(tab)[1], [['A B', '050 1234567']])

    def test_text_extraction(self):
        wa = importer.parse_text((SAMPLES / 'sample-whatsapp.txt').read_text())
        self.assertEqual(len(wa), 2)
        self.assertEqual((wa[0]['name'], wa[0]['phone'], wa[0]['email'], wa[0]['ref'], wa[0]['amount'], wa[0]['paid']),
                         ('Harish Kumar', '+971 55 987 6543', 'harish.k@example.com', 'SSP-010', '100', 'paid'))
        self.assertEqual(wa[0]['method'], 'Bank transfer')
        self.assertEqual(wa[0]['quantity'], '2')
        self.assertEqual((wa[1]['name'], wa[1]['phone'], wa[1]['paid'], wa[1]['amount']),
                         ('Deepa Acharya', '+971 50 765 4321', 'unpaid', '50'))
        pdf = importer.parse_text((SAMPLES / 'sample-pdf-receipt-text.txt').read_text())
        self.assertEqual((pdf[0]['ref'], pdf[0]['name'], pdf[0]['phone'], pdf[0]['amount']),
                         ('SSP-011', 'Kavitha Rai', '050 444 5566', 'AED 50.00'))
        lines = importer.parse_text('Ramesh Pai 050 111 2222 AED 50\nSavitha Rao 050 333 4444 AED 100 paid\n')
        self.assertEqual([(r['name'], r['amount'], r['paid']) for r in lines],
                         [('Ramesh Pai', '50', ''), ('Savitha Rao', '100', 'paid')])
        self.assertEqual(importer.parse_text('hello there'), [])
        # Android WhatsApp export format
        android = importer.parse_text('12/10/2026, 21:05 - Shobha Shenoy: Book 1 pooja please. Rs. 500 transferred via PhonePe')
        self.assertEqual((android[0]['name'], android[0]['amount'], android[0]['method']), ('Shobha Shenoy', '500', 'UPI'))

    def test_paid_and_method_words(self):
        for text, total, expected in (('Paid', 5000, True), ('yes', 5000, True), ('✓', 5000, True), ('Pending', 5000, False),
                                      ('Not paid', 5000, False), ('', 5000, False), ('50', 5000, True), ('0', 5000, False),
                                      ('25', 5000, None), ('maybe', 5000, None), ('Paid (Card)', 5000, True)):
            self.assertEqual(importer.paid_state(text, total), expected, text)
        self.assertEqual(importer.payment_method('Google Pay', 'Cash'), 'UPI')
        self.assertEqual(importer.payment_method('NEFT', 'Cash'), 'Bank transfer')
        self.assertEqual(importer.payment_method('', 'Cash'), 'Cash')
        self.assertEqual(importer.tidy_phone('971502223344'), '+971502223344')
        self.assertEqual(importer.tidy_phone('0502223344'), '0502223344')


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db, self.eid, self.ids = event_store(self.temp.name)
        self.sevas = [s for s in self.db.catalog(True)['sevas'] if s['event_id'] == self.eid]

    def tearDown(self):
        self.temp.cleanup()

    def plan_sample(self):
        headers, rows, _, _ = importer.read_table(SAMPLES / 'sample-google-form-bookings.xlsx')
        records = importer.rows_from_table(headers, rows, importer.guess_mapping(headers))
        return importer.plan_rows(records, self.sevas, self.ids['pooja'], 'Bank transfer', self.db.known_imports(self.eid))

    def test_plan_statuses(self):
        plan = self.plan_sample()
        self.assertEqual([r.status for r in plan],
                         ['Ready', 'Ready', 'Ready', 'Ready', 'Ready', 'Check', 'Skip', 'Check', 'Check', 'Ready'])
        by_ref = {r.ref: r for r in plan if r.status != 'Skip'}
        self.assertEqual((by_ref['SSP-002'].total, by_ref['SSP-002'].items[0]['quantity']), (15000, 3))
        self.assertEqual(by_ref['SSP-003'].summary(), '2× Pooja Booking; 1× Flowers @ 100')
        self.assertEqual((by_ref['SSP-003'].paid, by_ref['SSP-003'].method), (True, 'UPI'))
        self.assertEqual(by_ref['SSP-003'].phone, '+971502223344')
        self.assertEqual((by_ref['SSP-004'].total, by_ref['SSP-004'].paid), (50000, False))
        self.assertIn('not a whole number', by_ref['SSP-006'].problem)
        self.assertIn('No devotee name', by_ref['SSP-007'].problem)
        self.assertIn('sponsorship amount', by_ref['SSP-008'].problem)
        self.assertFalse(any(r.include for r in plan if r.status != 'Ready'))

    def test_import_then_reimport_is_safe(self):
        plan = self.plan_sample()
        created, marked, failed = self.db.import_rows(self.eid, plan, 'Admin: Ravi', save_devotees=True)
        self.assertEqual((created, marked, failed), (6, 0, 0))
        self.assertEqual(sum(r.status == 'Imported' for r in plan), 6)
        bookings = {b['external_ref']: b for b in self.db.bookings()}
        self.assertEqual(set(bookings), {'SSP-001', 'SSP-002', 'SSP-003', 'SSP-004', 'SSP-005', 'SSP-009'})
        b3 = self.db.detail(bookings['SSP-003']['id'])
        self.assertEqual((b3['status'], b3['payment_method'], b3['total'], len(b3['items'])), ('PAID', 'UPI', 20000, 3))
        self.assertEqual((b3['email'], b3['service_date'], b3['operator']), ('ganesh.bhat@example.com', '2026-10-25', 'Admin: Ravi (import)'))
        self.assertIn('SSP-003', receipt(b3))
        self.assertEqual(self.db.detail(bookings['SSP-002']['id'])['status'], 'UNPAID')
        self.assertEqual(len(self.db.schedule('2026-10-25')), 2 + 3 + 2 + 1 + 1 + 2)
        self.assertTrue(self.db.families('ganesh.bhat@example.com'))
        # The same file again: nothing new.
        again = self.plan_sample()
        self.assertEqual([r.status for r in again].count('Duplicate'), 6)
        self.assertEqual(self.db.import_rows(self.eid, again, 'Admin: Ravi'), (0, 0, 0))
        # An updated sheet where Latha has now paid by bank transfer, plus the fixed rows.
        headers, rows, _, _ = importer.read_table(SAMPLES / 'sample-google-form-bookings.xlsx')
        rows[1][8], rows[1][9] = 'Paid', 'Bank transfer'
        rows[5][7] = '100'
        rows[7][2] = 'Kiran Shetty'
        rows[8][7] = '250'
        records = importer.rows_from_table(headers, rows, importer.guess_mapping(headers))
        updated = importer.plan_rows(records, self.sevas, self.ids['pooja'], 'Bank transfer', self.db.known_imports(self.eid))
        self.assertEqual([r.status for r in updated],
                         ['Duplicate', 'Update', 'Duplicate', 'Duplicate', 'Duplicate', 'Ready', 'Skip', 'Ready', 'Ready', 'Duplicate'])
        self.assertEqual(self.db.import_rows(self.eid, updated, 'Admin: Ravi'), (3, 1, 0))
        latha = self.db.detail(bookings['SSP-002']['id'])
        self.assertEqual((latha['status'], latha['payment_method']), ('PAID', 'Bank transfer'))
        self.assertEqual(self.db.detail(next(b['id'] for b in self.db.bookings() if b['external_ref'] == 'SSP-008'))['items'][0]['price'], 25000)

    def test_rows_without_booking_numbers_and_text(self):
        records = importer.parse_text((SAMPLES / 'sample-whatsapp.txt').read_text())
        plan = importer.plan_rows(records, self.sevas, self.ids['pooja'])
        self.assertTrue(all(r.status == 'Check' and not r.include for r in plan))
        self.assertEqual(self.db.import_rows(self.eid, plan, 'Sup'), (0, 0, 0))  # nothing until ticked
        for r in plan:
            r.include = True  # operator checked them
        self.assertEqual(self.db.import_rows(self.eid, plan, 'Sup'), (2, 0, 0))
        deepa = next(b for b in self.db.bookings() if b['devotee'] == 'Deepa Acharya')
        self.assertTrue(deepa['import_key'].startswith('auto-'))
        again = importer.plan_rows(importer.parse_text((SAMPLES / 'sample-whatsapp.txt').read_text()), self.sevas,
                                   self.ids['pooja'], known=self.db.known_imports(self.eid))
        self.assertEqual([r.status for r in again], ['Duplicate', 'Duplicate'])

    def test_edit_row_and_failures(self):
        plan = self.plan_sample()
        meena = next(r for r in plan if r.ref == 'SSP-006')
        meena.amount = '100'
        importer.plan_one(meena, {s['id']: s for s in self.sevas}, self.ids['pooja'], 'no', '', 'Cash')
        self.assertEqual((meena.status, meena.total, meena.include), ('Ready', 10000, True))
        # A seva archived after planning makes that row fail cleanly; others still import.
        self.db.set_active('sevas', self.ids['Fruits'], False)
        created, marked, failed = self.db.import_rows(self.eid, plan, 'Sup')
        self.assertEqual((created, failed), (6, 1))
        fruits = next(r for r in plan if r.ref == 'SSP-005')
        self.assertEqual(fruits.status, 'Check')
        self.assertIn('archived', fruits.problem)

    def test_counter_search_print_requests_and_handover(self):
        plan = self.plan_sample()
        self.db.import_rows(self.eid, plan, 'Admin: Ravi')
        rows, _ = self.db.bookings_page('latha', event_id=self.eid)
        self.assertEqual([r['external_ref'] for r in rows], ['SSP-002'])
        self.assertEqual([r['external_ref'] for r in self.db.bookings_page('ssp-004')[0]], ['SSP-004'])
        self.assertEqual([r['external_ref'] for r in self.db.bookings_page('prakash@example')[0]], ['SSP-005'])
        # A booking number never matches phone digits (050 404 0010 contains "001").
        self.db.book(dict(request_key='p', event_id=self.eid, devotee='Phone Match', phone='050 404 0010',
                          items=[dict(seva_id=self.ids['pooja'], quantity=1)]), 'A')
        self.assertEqual([r['external_ref'] for r in self.db.bookings_page('SSP-001')[0]], ['SSP-001'])
        self.assertEqual([r['devotee'] for r in self.db.bookings_page('4040010')[0]], ['Phone Match'])
        self.assertEqual(len(self.db.bookings_page('', event_id=self.eid, status=('UNPAID',))[0]), 3)
        latha = rows[0]['id']
        self.db.pay(latha, 'Reception: Desk 1', 'Cash')
        self.db.request_print(latha, 'Reception: Desk 1 (phone)')
        self.assertEqual([r['booking_id'] for r in self.db.print_requests()], [latha])
        self.db.printed(latha, 'Cashier: Laptop')
        self.assertEqual(self.db.print_requests(), [])
        self.db.request_print(latha, 'Reception: Desk 1 (phone)')  # reprint request
        self.assertEqual(len(self.db.print_requests()), 1)
        self.assertIn('REPRINT', receipt(self.db.detail(latha)))
        rep = self.db.report(TODAY, TODAY, self.eid)
        self.assertEqual(rep['by_collector'][('AED', 'Reception: Desk 1', 'Cash')], 15000)
        self.assertEqual(rep['by_collector'][('AED', 'Paid before event (imported by Admin: Ravi)', 'UPI')], 30000)
        self.assertNotIn(('AED', 'Admin: Ravi', 'UPI'), rep['by_collector'])
        self.assertIn('CASH HANDOVER', report_text(rep))
        void = self.db.book(dict(request_key='v', event_id=self.eid, devotee='V', items=[dict(seva_id=self.ids['pooja'], quantity=1)]), 'A')
        self.db.void(void, 'x')
        with self.assertRaises(ValueError):
            self.db.request_print(void, 'A')

    def test_phone_counter(self):
        self.db.import_rows(self.eid, self.plan_sample(), 'Admin: Ravi')
        self.db.add_staff('Ravi', 'Admin', '4821')
        self.db.add_staff('Desk', 'Reception', '5930')
        cert, key = security.ensure_certificate(Path(self.temp.name) / 'tls', ['127.0.0.1'])
        server, info = start(self.db, 0, cert, key)
        import ssl
        context = ssl.create_default_context(cafile=str(cert))
        base = f'https://127.0.0.1:{server.server_port}'
        def call(path, data, token=''):
            req = Request(base + path, data=json.dumps(data).encode(),
                          headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
            with urlopen(req, timeout=5, context=context) as response:
                return json.load(response)
        try:
            token = call('/api/login', dict(code=info['code'], name='Desk', pin='5930'))['token']
            self.assertEqual(call('/api/find', dict(q='l'), token), [])
            found = call('/api/find', dict(q='latha'), token)
            self.assertEqual((found[0]['ref'], found[0]['status'], found[0]['sevas'], found[0]['phone']),
                             ('SSP-002', 'UNPAID', '3× Pooja Booking', '•••• 3344'))
            self.assertNotIn('email', found[0])
            call('/api/pay', dict(id=found[0]['id'], method='Cash'), token)
            call('/api/print', dict(id=found[0]['id']), token)
            again = call('/api/find', dict(q='SSP-002'), token)[0]
            self.assertEqual(again['status'], 'PAID')
            self.assertEqual(self.db.detail(found[0]['id'])['paid_by'], 'Reception: Desk (phone)')
            self.assertEqual(self.db.print_requests()[0]['requested_by'], 'Reception: Desk (phone)')
        finally:
            server.shutdown()
            server.server_close()


class DuplicateDevoteeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db, self.eid, self.ids = event_store(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_same_mobile_is_blocked_in_any_format(self):
        first = self.db.family(dict(head='Raviraj Shetty', phone='0556001015'))
        for phone in ('0556001015', '+971 55 600 1015', '971-55-6001015'):
            with self.assertRaisesRegex(ValueError, f'already registered to family #{first}'):
                self.db.family(dict(head='Raviraj Shetty', phone=phone))
        other = self.db.family(dict(head='Someone', phone='0501112222'))
        with self.assertRaises(ValueError):  # editing another family onto the same number
            self.db.family(dict(head='Someone', phone='055 600 1015'), other)
        self.db.family(dict(head='Raviraj S. Shetty', phone='0556001015', email='r@example.com'), first)  # editing itself is fine
        self.db.family(dict(head='No phone A'))
        self.db.family(dict(head='No phone B'))  # families without a number are not blocked
        with self.assertRaisesRegex(ValueError, 'email'):
            self.db.family(dict(head='Bad email', email='not-an-email'))

    def test_walk_in_save_reuses_registered_family(self):
        fid = self.db.family(dict(head='Raviraj Shetty', phone='0556001015'))
        self.db.member(dict(family_id=fid, name='Raviraj Shetty', relation='Self'))
        def walk_in(key, name):
            return self.db.book(dict(request_key=key, event_id=self.eid, devotee=name, phone='+971556001015',
                                     save_devotee=True, items=[dict(seva_id=self.ids['pooja'], quantity=1)]), 'Desk')
        b1 = walk_in('w1', 'raviraj  shetty')
        b2 = walk_in('w2', 'Shashikala Shetty')
        self.assertEqual(len(self.db.families()), 1)
        fam = self.db.family_detail(fid)
        self.assertEqual(sorted(m['name'] for m in fam['members']), ['Raviraj Shetty', 'Shashikala Shetty'])
        self.assertEqual({b['id'] for b in fam['bookings']}, {b1, b2})

    def test_merge_existing_duplicates(self):
        with self.db.connect() as db:  # duplicates created by an older version
            for head in ('Raviraj Shetty', 'Raviraj Shetty'):
                db.execute("INSERT INTO families(head,phone,created) VALUES(?, '0556001015', 'x')", (head,))
        keep, gone = [f['id'] for f in self.db.families()]
        self.db.member(dict(family_id=keep, name='Raviraj Shetty', relation='Self'))
        dup = self.db.member(dict(family_id=gone, name='Raviraj Shetty', relation='Self', rashi='Mesha / ಮೇಷ', gotra='Kashyapa'))
        son = self.db.member(dict(family_id=gone, name='Rishabh Shetty', relation='Son'))
        bid = self.db.book(dict(request_key='m', event_id=self.eid, devotee='Raviraj Shetty', family_id=gone,
                                items=[dict(seva_id=self.ids['pooja'], quantity=1, member_id=dup)]), 'Desk')
        self.assertEqual([[f['id'] for f in g] for g in self.db.duplicate_families()], [[keep, gone]])
        with self.assertRaises(ValueError):
            self.db.merge_families(keep, keep, 'Admin')
        self.assertEqual(self.db.merge_families(keep, gone, 'Admin'), (1, 1, 1))
        fam = self.db.family_detail(keep)
        self.assertEqual(sorted(m['name'] for m in fam['members']), ['Raviraj Shetty', 'Rishabh Shetty'])
        me = next(m for m in fam['members'] if m['relation'] == 'Self')
        self.assertEqual((me['rashi'], me['gotra']), ('Mesha / ಮೇಷ', 'Kashyapa'))
        self.assertEqual([b['id'] for b in fam['bookings']], [bid])
        with self.db.connect() as db:
            self.assertEqual(db.execute('SELECT member_id FROM items WHERE booking_id=?', (bid,)).fetchone()[0], me['id'])
        self.assertEqual(self.db.detail(bid)['items'][0]['person'], 'Raviraj Shetty')  # printed history unchanged
        self.assertEqual(self.db.duplicate_families(), [])
        self.assertEqual(len(self.db.families()), 1)
        self.assertIn(son, [m['id'] for m in fam['members']])


class QrTests(unittest.TestCase):
    def test_link_keeps_code_out_of_the_request(self):
        import qr
        link = qr.access_link('https', '192.168.1.120', 8765, '0006-9F2A-256F')
        self.assertEqual(link, 'https://192.168.1.120:8765/#code=0006-9F2A-256F')
        self.assertEqual(link.split('#')[0], 'https://192.168.1.120:8765/')  # browsers never send the fragment

    def test_png_scans_back(self):
        import qr
        import shutil
        import subprocess
        png = qr.png('https://10.0.0.7:8765/#code=AB12-CD34-EF56', scale=6)
        self.assertTrue(png.startswith(b'\x89PNG'))
        grid = qr.matrix('https://10.0.0.7:8765/#code=AB12-CD34-EF56')
        self.assertEqual(len(grid), len(grid[0]))
        if not shutil.which('zbarimg'):
            self.skipTest('zbarimg not installed')
        with tempfile.TemporaryDirectory() as tmp:
            for link in ('https://10.0.0.7:8765/#code=AB12-CD34-EF56', 'http://192.168.100.254:8765/#code=0000-0000-0000'):
                path = Path(tmp) / 'q.png'
                path.write_bytes(qr.png(link))
                out = subprocess.run(['zbarimg', '-q', '--raw', str(path)], capture_output=True, text=True).stdout.strip()
                self.assertEqual(out, link)

    def test_printable_sheet(self):
        try:
            import app
        except ImportError:
            self.skipTest('Tk not available')
        with tempfile.TemporaryDirectory() as tmp:
            db, eid, _ = event_store(tmp)
            page = app.qr_sheet_html('https://192.168.1.120:8765/#code=0006-9F2A-256F',
                                     {'code': '0006-9F2A-256F'}, db)
        self.assertIn('data:image/png;base64,', page)
        self.assertIn('0006-9F2A-256F', page)
        self.assertIn('https://192.168.1.120:8765', page)
        self.assertIn('Sri Satyanarayana Pooja', page)


class RealBackup(unittest.TestCase):
    SOURCE = HERE / 'fixtures' / 'seva-backup-2026-09-16.sqlite3'

    @unittest.skipUnless(SOURCE.exists(), 'user backup fixture not available')
    def test_import_into_real_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            for suffix in ('', '-wal', '-shm'):
                shutil.copy(str(self.SOURCE) + suffix, Path(tmp) / ('db' + suffix))
            db = Store(Path(tmp) / 'db')
            sevas = [s for s in db.catalog(True)['sevas'] if s['event_id'] == 1]
            headers, rows, _, _ = importer.read_table(SAMPLES / 'sample-google-form-bookings.xlsx')
            plan = importer.plan_rows(importer.rows_from_table(headers, rows, importer.guess_mapping(headers)),
                                      sevas, 1, known=db.known_imports(1))
            self.assertEqual(db.import_rows(1, plan, 'Admin'), (6, 0, 0))
            self.assertEqual(len(db.bookings()), 8)  # the 2 existing + 6 imported
            self.assertEqual(len(db.schedule('2026-10-25')), 4 + 11)


if __name__ == '__main__':
    unittest.main()
