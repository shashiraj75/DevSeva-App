import concurrent.futures
import json
from pathlib import Path
import sqlite3
import ssl
import tempfile
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from core import Store, money, receipt, person_name, email_address
from mobile import start
import security


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.db=Store(Path(self.temp.name)/'test.db')
        self.e=self.db.event(dict(name='UAE Pooja',kannada='ಪೂಜೆ',day='2026-12-01',place='Dubai',currency='AED'))
        self.s=self.db.seva(dict(event_id=self.e,name='Satyanarayana',kannada='ಸತ್ಯನಾರಾಯಣ',price='50',kind='Seva'))

    def tearDown(self):self.temp.cleanup()

    def data(self,key='test',quantity=5,amount='50'):
        return dict(request_key=key,event_id=self.e,devotee='Test <devotee>',rashi='Mesha',nakshatra='Ashwini',items=[dict(seva_id=self.s,quantity=quantity,amount=amount)])

    def test_five_slips_one_summary(self):
        bid=self.db.book(self.data(),'Test operator');b=self.db.detail(bid)
        self.assertEqual(b['total'],25000);self.assertEqual(len(b['items']),5)
        rendered=receipt(b);self.assertEqual(rendered.count('<section>'),6)
        self.assertNotIn('UNPAID',rendered);self.assertNotIn('Not received',rendered)
        self.assertEqual(b['status'],'UNPAID');self.assertIn('&lt;Devotee&gt;',rendered)
        self.assertIn('ಸತ್ಯನಾರಾಯಣ',rendered)

    def test_devotee_names_are_title_cased(self):
        self.assertEqual(person_name('  prasad   shetty  '), 'Prasad Shetty')
        self.assertEqual(person_name("mary o'connor"), "Mary O'Connor")
        self.assertEqual(person_name('ಶೋಭ ಶೆಟ್ಟಿ'), 'ಶೋಭ ಶೆಟ್ಟಿ')
        booking = self.data('title-name', quantity=1)
        booking['devotee'] = 'prasad shetty'
        bid = self.db.book(booking, 'Test operator')
        self.assertEqual(self.db.detail(bid)['devotee'], 'Prasad Shetty')
        fid = self.db.family({'head': 'shobha shetty'})
        self.assertEqual(self.db.family_detail(fid)['head'], 'Shobha Shetty')

    def test_email_address_is_required_to_be_well_formed_when_present(self):
        self.assertEqual(email_address('  PRASAD.SHETTY@EXAMPLE.COM '), 'prasad.shetty@example.com')
        with self.assertRaisesRegex(ValueError, 'valid email'):
            email_address('therehhhhree')
        booking = self.data('bad-email', quantity=1)
        booking['email'] = 'not-an-email'
        with self.assertRaisesRegex(ValueError, 'valid email'):
            self.db.book(booking, 'Test operator')

    def test_retries_and_parallel_entry(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            ids=list(pool.map(lambda _:self.db.book(self.data(),'Test operator'),range(20)))
        self.assertEqual(len(set(ids)),1);self.assertEqual(len(self.db.queue()),1)
        with self.assertRaises(ValueError):self.db.book(self.data(quantity=2),'Test operator')
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            ids=list(pool.map(lambda n:self.db.book(self.data(str(n)),'Test operator'),range(20)))
        self.assertEqual(len(set(ids)),20)

    def test_master_changes_preserve_history(self):
        bid=self.db.book(self.data(),'Test operator')
        self.db.seva(dict(event_id=self.e,name='New name',kannada='',price='100',kind='Seva'),self.s)
        self.db.event(dict(name='Next event',kannada='',day='2027-01-01',place='Elsewhere',currency='INR'),self.e)
        b=self.db.detail(bid);self.assertEqual(b['event']['currency'],'AED');self.assertEqual(b['items'][0]['price'],5000)

    def test_payment_and_cancellation(self):
        bid=self.db.book(self.data(),'Test operator');self.db.pay(bid,'Cashier')
        with self.assertRaises(ValueError):self.db.pay(bid,'Cashier')
        with self.assertRaises(ValueError):self.db.void(bid,'Mistake')
        bid2=self.db.book(self.data('second'),'Test operator');self.db.void(bid2,'Duplicate visitor request')
        with self.assertRaises(ValueError):self.db.pay(bid2,'Cashier')

    def test_money_and_price_permissions(self):
        for bad in ('NaN','Infinity','-1','1.001','10000001','abc'):
            with self.assertRaises(ValueError):money(bad)
        with self.assertRaises(ValueError):self.db.book(self.data(amount='30'),'Reception')
        bid=self.db.book(self.data(amount='30'),'Admin',True);self.assertEqual(self.db.detail(bid)['total'],15000)

    def test_in_kind_and_sponsorship(self):
        for kind,price in [('In-kind','0'),('Sponsorship','1000')]:
            sid=self.db.seva(dict(event_id=self.e,name=kind,kannada='',price='0',kind=kind))
            d=self.data(kind,1,price);d['items'][0]['seva_id']=sid
            b=self.db.detail(self.db.book(d,'Reception'));self.assertEqual(b['total'],money(price))
            if kind=='In-kind':
                self.assertIn('NO CASH DUE',receipt(b))
                with self.assertRaises(ValueError):self.db.pay(b['id'],'Cashier')

    def test_event_mismatch_and_limits(self):
        d=self.data();d['event_id']=999
        with self.assertRaises(ValueError):self.db.book(d,'Reception')
        with self.assertRaises(ValueError):self.db.book(self.data(quantity=101),'Reception')
        with self.assertRaises(ValueError):self.db.book(self.data(quantity=1.5),'Reception')

    def test_backup_export_and_queue(self):
        bid=self.db.book(self.data(),'Test operator')
        self.db.printed(bid);self.assertFalse(self.db.queue())
        dest=Path(self.temp.name)/'backup.db';self.db.backup(dest)
        self.assertEqual(Store(dest).detail(bid)['total'],25000)
        export=Path(self.temp.name)/'export.csv';self.db.export(export);self.assertIn('AED',export.read_text(encoding='utf-8-sig'))

    def test_mobile_permissions_and_booking(self):
        self.db.add_staff('Admin One','Admin','4821');self.db.add_staff('Desk 1','Reception','5930');self.db.add_staff('Cashier 1','Cashier','7162')
        cert,key=security.ensure_certificate(Path(self.temp.name)/'tls',['127.0.0.1'])
        server,info=start(self.db,0,cert,key)
        base=f'https://127.0.0.1:{server.server_port}'
        context=ssl.create_default_context(cafile=str(cert))
        def login(name,pin):
            req=Request(base+'/api/login',data=json.dumps(dict(code=info['code'],name=name,pin=pin)).encode(),headers={'Content-Type':'application/json'})
            with urlopen(req,timeout=5,context=context) as response:return json.load(response)['token']
        def call(path,token,data=None):
            req=Request(base+path,data=json.dumps(data).encode() if data else None,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
            with urlopen(req,timeout=3,context=context) as response:return json.load(response)
        try:
            reception=login('desk 1','5930');cashier=login('Cashier 1','7162')
            with self.assertRaises(HTTPError) as ex:login('Desk 1','0000')
            self.assertEqual(ex.exception.code,400)
            with self.assertRaises(HTTPError) as ex:
                req=Request(base+'/api/login',data=json.dumps(dict(code='WRONG',name='Desk 1',pin='5930')).encode(),headers={'Content-Type':'application/json'})
                urlopen(req,timeout=5,context=context)
            self.assertEqual(ex.exception.code,401)
            with self.assertRaises(HTTPError) as ex:call('/api/catalog','bad')
            self.assertEqual(ex.exception.code,401)
            result=call('/api/transliterate',reception,dict(operator='Desk 1',text='Satyanarayana Pooja'))
            self.assertEqual(result['suggestion'],'ಸತ್ಯನಾರಾಯಣ ಪೂಜೆ')
            self.assertEqual(len(call('/api/catalog',reception)['nakshatras']),27)
            d=self.data();d['operator']='Desk 1';bid=call('/api/book',reception,d)['id']
            with self.assertRaises(HTTPError) as ex:call('/api/pay',reception,dict(id=999,operator='Desk 1'))
            self.assertEqual(ex.exception.code,400)
            call('/api/pay',cashier,dict(id=bid,operator='Cashier 1'))
            self.assertEqual(self.db.detail(bid)['status'],'PAID')
            self.assertEqual(self.db.detail(bid)['paid_by'],'Cashier: Cashier 1 (phone)')
            self.assertEqual(self.db.detail(bid)['operator'],'Reception: Desk 1 (phone)')
        finally:server.shutdown();server.server_close()


if __name__=='__main__':unittest.main()
