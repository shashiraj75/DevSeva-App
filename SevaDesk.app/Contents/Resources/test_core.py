import concurrent.futures
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from core import Store, money, receipt
from mobile import start


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
        self.assertEqual(b['status'],'UNPAID');self.assertIn('&lt;devotee&gt;',rendered)
        self.assertIn('ಸತ್ಯನಾರಾಯಣ',rendered)

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
        server,tokens=start(self.db,0)
        reception=next(k for k,v in tokens.items() if v=='Reception');cashier=next(k for k,v in tokens.items() if v=='Cashier')
        base=f'http://127.0.0.1:{server.server_port}'
        def call(path,token,data=None):
            req=Request(base+path,data=json.dumps(data).encode() if data else None,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
            with urlopen(req,timeout=3) as response:return json.load(response)
        try:
            with self.assertRaises(HTTPError) as ex:call('/api/catalog','bad')
            self.assertEqual(ex.exception.code,401)
            result=call('/api/transliterate',reception,dict(operator='Desk 1',text='Satyanarayana Pooja'))
            self.assertEqual(result['suggestion'],'ಸತ್ಯನಾರಾಯಣ ಪೂಜೆ')
            self.assertEqual(len(call('/api/catalog',reception)['nakshatras']),27)
            d=self.data();d['operator']='Desk 1';bid=call('/api/book',reception,d)['id']
            with self.assertRaises(HTTPError) as ex:call('/api/pay',reception,dict(id=bid,operator='Desk 1'))
            self.assertEqual(ex.exception.code,403)
            call('/api/pay',cashier,dict(id=bid,operator='Cashier 1'))
            self.assertEqual(self.db.detail(bid)['status'],'PAID')
        finally:server.shutdown();server.server_close()


if __name__=='__main__':unittest.main()
