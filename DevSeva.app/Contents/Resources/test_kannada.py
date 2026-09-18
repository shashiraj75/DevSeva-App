import sqlite3
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from kannada import suggest, bind_suggestion, translate_label, RASHIS, NAKSHATRAS
from core import Store, receipt


class KannadaTests(unittest.TestCase):
    def test_category_meanings_and_unknown_labels(self):
        self.assertEqual(translate_label('Consumables'),'ಬಳಕೆ ಸಾಮಗ್ರಿಗಳು')
        self.assertEqual(translate_label(' Flowers AND fruits '),'ಹೂವುಗಳು ಮತ್ತು ಹಣ್ಣುಗಳು')
        self.assertEqual(translate_label('Stage setup'),'ವೇದಿಕೆ ಸಿದ್ಧತೆ')
        self.assertEqual(translate_label('Unlisted complex description'),'')
        self.assertEqual(translate_label('ಪೂಜೆ'),'ಪೂಜೆ')
        interp=tk.Tcl();source=tk.StringVar(interp,value='Consumables');target=tk.StringVar(interp)
        bind_suggestion(source,target,translate_label)
        source.set('Unlisted complex description')
        self.assertEqual(target.get(),'')

    def test_saved_category_corrections(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'labels.db';store=Store(path)
            eid=store.event(dict(name='Pooja',day='2026-12-01',place='Dubai',currency='AED'))
            values=dict(event_id=eid,name='Consumables',price='0',kind='Sponsorship',kannada='ಪೂಜಾ ಸಾಮಗ್ರಿಗಳು')
            sid=store.seva(values)
            self.assertEqual(translate_label('consumables',Store(path).label_dictionary()),'ಪೂಜಾ ಸಾಮಗ್ರಿಗಳು')
            # No retroactive updates to other masters or stored booking snapshots.
            bid=store.book(dict(request_key='one',event_id=eid,devotee='Test',items=[dict(seva_id=sid,quantity=1)]),'Admin')
            values['kannada']='ಬಳಕೆ ಸಾಮಗ್ರಿಗಳು';store.seva(values,sid)
            self.assertEqual(store.detail(bid)['items'][0]['kannada'],'ಪೂಜಾ ಸಾಮಗ್ರಿಗಳು')
            self.assertEqual(translate_label('consumables',store.label_dictionary()),'ಬಳಕೆ ಸಾಮಗ್ರಿಗಳು')
            # Previously stored guesses are not imported on unrelated edits.
            with store.connect() as db:
                db.execute('DELETE FROM kannada_labels')
            values['price']='1';store.seva(values,sid)
            self.assertEqual(store.label_dictionary(),{})

    def test_common_words_and_unicode(self):
        self.assertEqual(suggest('Satyanarayana Pooja'),'ಸತ್ಯನಾರಾಯಣ ಪೂಜೆ')
        self.assertEqual(suggest('Raviraj Shetty'),'ರವಿರಾಜ್ ಶೆಟ್ಟಿ')
        self.assertEqual(suggest('ಪೂಜೆ 2026 / Pooja'),'ಪೂಜೆ 2026 / ಪೂಜೆ')
        self.assertEqual(suggest(''),'')
        self.assertEqual(suggest('raama'),'ರಾಮ')
        self.assertEqual(suggest('amma'),'ಅಮ್ಮ')
        self.assertEqual(len(RASHIS),12)
        self.assertEqual(len(NAKSHATRAS),27)

    def test_manual_correction_survives_typing(self):
        interp=tk.Tcl()
        source=tk.StringVar(interp,value='Pooja');target=tk.StringVar(interp)
        reset=bind_suggestion(source,target)
        self.assertEqual(target.get(),'ಪೂಜೆ')
        source.set('Seva');self.assertEqual(target.get(),'ಸೇವಾ')
        target.set('ಸೇವೆ');source.set('Annadana')
        self.assertEqual(target.get(),'ಸೇವೆ')
        reset();self.assertEqual(target.get(),'ಅನ್ನದಾನ')
        source.set('Pooja');self.assertEqual(target.get(),'ಪೂಜೆ')

    def test_existing_saved_kannada_preserved(self):
        interp=tk.Tcl();source=tk.StringVar(interp,value='Pooja')
        target=tk.StringVar(interp,value='ಕುಟುಂಬ ಪೂಜೆ')
        bind_suggestion(source,target);source.set('Family Pooja')
        self.assertEqual(target.get(),'ಕುಟುಂಬ ಪೂಜೆ')

    def test_old_database_upgrade_and_new_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'old.db';store=Store(path)
            eid=store.event(dict(name='Pooja',day='2026-12-01',place='Dubai',currency='AED'))
            sid=store.seva(dict(event_id=eid,name='Pooja',price='50',kind='Seva'))
            data=dict(request_key='old',event_id=eid,devotee='Old devotee',items=[dict(seva_id=sid,quantity=1)])
            old=store.book(data,'Admin');store.pay(old,'Cashier')
            with sqlite3.connect(path) as db:
                db.execute('ALTER TABLE bookings DROP COLUMN devotee_kn')
            upgraded=Store(path)
            self.assertEqual(upgraded.detail(old)['status'],'PAID')
            self.assertEqual(upgraded.detail(old)['devotee_kn'],'')
            data.update(request_key='new',devotee='Raviraj Shetty',devotee_kn='ರವಿರಾಜ್ ಶೆಟ್ಟಿ')
            new=upgraded.book(data,'Admin')
            self.assertEqual(receipt(upgraded.detail(new)).count('ರವಿರಾಜ್ ಶೆಟ್ಟಿ'),2)
            self.assertEqual(upgraded.detail(old)['total'],5000)
            # Reopening the migrated DB is safe and preserves the new name.
            self.assertEqual(Store(path).detail(new)['devotee_kn'],'ರವಿರಾಜ್ ಶೆಟ್ಟಿ')


if __name__=='__main__':unittest.main()
