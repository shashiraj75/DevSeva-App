# DevSeva — © 2026 Raviraj Shetty. All rights reserved.
"""DevSeva offline data layer. Money is stored in integer minor units (fils/paise).

Version 0.7 adds importing bookings (Excel/CSV/pasted text) with email and booking
numbers, event-day counter search, phone print requests and cash handover totals.
Version 0.6 added staff PIN logins, refunds and corrections, per-member gotra,
linking older bookings to the register, paged booking lists and in-app restore.
Version 0.5 added a devotee register (families and members), daily/recurring
poojas with service dates and optional per-day limits, per-person seva slips,
a day-wise pooja schedule and collection reports. All schema changes are
additive so existing bookings and receipts are preserved.
"""
import csv
import re
import os
import time
from pathlib import Path
import datetime as dt
import html
import json
import sqlite3
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from kannada import normalize_label
import security

APP_NAME = 'DevSeva'
APP_NAME_KN = 'ದೇವಸೇವೆ'
VERSION = '0.8'
COPYRIGHT_HOLDER = 'Raviraj Shetty'
COPYRIGHT_YEAR = '2026'
COPYRIGHT = f'© {COPYRIGHT_YEAR} {COPYRIGHT_HOLDER}. All rights reserved.'
CURRENCIES = ('AED', 'INR')
KINDS = ('Seva', 'Sponsorship', 'In-kind')
METHODS = ('Cash', 'Bank transfer', 'Card', 'UPI')
RECURRENCES = ('Once', 'Daily')
DAY_NAMES = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')
RELATIONS = ('Self', 'Spouse', 'Son', 'Daughter', 'Father', 'Mother', 'Brother', 'Sister',
             'Grandson', 'Granddaughter', 'Grandfather', 'Grandmother', 'Relative', 'Other')
ADMIN = 'Laptop administrator'


def money(value):
    try:
        amount = Decimal(str(value).strip())
        if not amount.is_finite() or amount < 0 or amount > 10000000:
            raise ValueError('Amount must be between 0 and 10,000,000.')
        if amount != amount.quantize(Decimal('.01')):
            raise ValueError('Use at most two decimal places.')
        return int(amount * 100)
    except InvalidOperation:
        raise ValueError('Enter a valid amount.')


def required(value, label, limit=200):
    value = str(value or '').strip()
    if not value or len(value) > limit:
        raise ValueError(f'{label} is required (maximum {limit} characters).')
    return value


def optional(value, limit=200):
    return str(value or '').strip()[:limit]


def person_name(value, label='Devotee name', limit=200):
    """Normalise a person's English name for lists, slips and the register.

    ``str.title`` leaves scripts without letter case (such as Kannada) intact,
    while making everyday entries such as ``prasad shetty`` consistent.
    """
    return ' '.join(word.title() for word in required(value, label, limit).split())


def email_address(value, label='Email'):
    """Return a normalised optional email address, or explain what is missing."""
    email = optional(value, 120).casefold()
    if email and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email):
        raise ValueError(f'Enter a valid {label.lower()} address, for example name@example.com.')
    return email


def iso_date(value, label='Date'):
    try:
        return dt.date.fromisoformat(str(value).strip()).isoformat()
    except ValueError:
        raise ValueError(f'{label} must be a valid date in YYYY-MM-DD format.')


def parse_weekdays(text):
    """'All', '' or 'Mon, Tue' -> '0123456' / '01'."""
    text = str(text or '').strip()
    if not text or text.casefold() in ('all', 'every day', 'daily'):
        return '0123456'
    lookup = {name.casefold(): str(i) for i, name in enumerate(DAY_NAMES)}
    days = set()
    for part in text.replace(';', ',').split(','):
        key = part.strip().casefold()[:3]
        if key not in lookup:
            raise ValueError('Days must be "All" or a list such as "Mon, Tue, Fri".')
        days.add(lookup[key])
    return ''.join(sorted(days))


def weekday_text(digits):
    digits = digits or '0123456'
    return 'All' if digits == '0123456' else ', '.join(DAY_NAMES[int(d)] for d in digits)


def local_date(timestamp):
    """UTC ISO timestamp -> the laptop's local calendar date (Dubai/India desk time)."""
    if not timestamp:
        return ''
    return dt.datetime.fromisoformat(timestamp).astimezone().date().isoformat()


def fmt(minor):
    return f'{minor / 100:,.2f}'


def phone_key(phone):
    """Comparable form of a mobile number: its last 9 digits (050 123 4567 == +971 50 123 4567)."""
    digits = ''.join(ch for ch in str(phone or '') if ch.isdigit())
    return digits[-9:] if len(digits) >= 7 else ''


def safe_csv(row):
    return [("'" + v if isinstance(v, str) and v.startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else v) for v in row]


class Store:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS kannada_labels(english TEXT PRIMARY KEY, kannada TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, name TEXT NOT NULL,
              kannada TEXT NOT NULL, day TEXT NOT NULL, place TEXT NOT NULL, currency TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sevas(id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL REFERENCES events(id),
              name TEXT NOT NULL, kannada TEXT NOT NULL, price INTEGER NOT NULL, kind TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS bookings(id INTEGER PRIMARY KEY AUTOINCREMENT,
              request_key TEXT UNIQUE NOT NULL, payload TEXT NOT NULL, event_id INTEGER NOT NULL REFERENCES events(id),
              created TEXT NOT NULL, operator TEXT NOT NULL, devotee TEXT NOT NULL, phone TEXT NOT NULL,
              rashi TEXT NOT NULL, nakshatra TEXT NOT NULL, note TEXT NOT NULL,
              snapshot TEXT NOT NULL, total INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'UNPAID',
              payment_method TEXT, paid_at TEXT, paid_by TEXT, void_reason TEXT);
            CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY AUTOINCREMENT,
              booking_id INTEGER NOT NULL REFERENCES bookings(id), name TEXT NOT NULL,
              kannada TEXT NOT NULL, kind TEXT NOT NULL, price INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, at TEXT NOT NULL,
              actor TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS print_jobs(id INTEGER PRIMARY KEY AUTOINCREMENT,
              booking_id INTEGER NOT NULL REFERENCES bookings(id), status TEXT NOT NULL DEFAULT 'PENDING');
            CREATE TABLE IF NOT EXISTS families(id INTEGER PRIMARY KEY AUTOINCREMENT,
              head TEXT NOT NULL, phone TEXT NOT NULL DEFAULT '', gotra TEXT NOT NULL DEFAULT '',
              address TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', created TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS members(id INTEGER PRIMARY KEY AUTOINCREMENT,
              family_id INTEGER NOT NULL REFERENCES families(id), name TEXT NOT NULL,
              kannada TEXT NOT NULL DEFAULT '', relation TEXT NOT NULL DEFAULT 'Self',
              rashi TEXT NOT NULL DEFAULT '', nakshatra TEXT NOT NULL DEFAULT '',
              active INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS staff(id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL UNIQUE COLLATE NOCASE, role TEXT NOT NULL, salt TEXT NOT NULL,
              pin_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, created TEXT NOT NULL,
              failures INTEGER NOT NULL DEFAULT 0, locked_until REAL NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS refunds(id INTEGER PRIMARY KEY AUTOINCREMENT,
              booking_id INTEGER NOT NULL REFERENCES bookings(id), at TEXT NOT NULL, actor TEXT NOT NULL,
              amount INTEGER NOT NULL, method TEXT NOT NULL, reason TEXT NOT NULL);
            ''')
            # Additive migrations: retain existing bookings and historical receipts.
            self._add_columns(db, 'bookings', {
                'devotee_kn': "TEXT NOT NULL DEFAULT ''",
                'service_date': "TEXT NOT NULL DEFAULT ''",
                'family_id': 'INTEGER',
                'gotra': "TEXT NOT NULL DEFAULT ''",
                'refunded': 'INTEGER NOT NULL DEFAULT 0',
                'email': "TEXT NOT NULL DEFAULT ''",
                'external_ref': "TEXT NOT NULL DEFAULT ''",
                'import_key': "TEXT NOT NULL DEFAULT ''",
            })
            self._add_columns(db, 'members', {'gotra': "TEXT NOT NULL DEFAULT ''"})
            self._add_columns(db, 'families', {'email': "TEXT NOT NULL DEFAULT ''"})
            if 'printed_count' not in {r['name'] for r in db.execute('PRAGMA table_info(print_jobs)')}:
                self._add_columns(db, 'print_jobs', {'printed_count': 'INTEGER NOT NULL DEFAULT 0'})
                db.execute("UPDATE print_jobs SET printed_count=1 WHERE status='CONFIRMED'")
            self._add_columns(db, 'print_jobs', {'requested_at': 'TEXT', 'requested_by': 'TEXT'})
            self._add_columns(db, 'events', {
                'recurrence': "TEXT NOT NULL DEFAULT 'Once'",
                'weekdays': "TEXT NOT NULL DEFAULT '0123456'",
                'end_day': "TEXT NOT NULL DEFAULT ''",
                'active': 'INTEGER NOT NULL DEFAULT 1',
            })
            self._add_columns(db, 'sevas', {
                'daily_limit': 'INTEGER NOT NULL DEFAULT 0',
                'active': 'INTEGER NOT NULL DEFAULT 1',
            })
            self._add_columns(db, 'items', {
                'seva_id': 'INTEGER',
                'member_id': 'INTEGER',
                'person': "TEXT NOT NULL DEFAULT ''",
                'person_kn': "TEXT NOT NULL DEFAULT ''",
                'rashi': "TEXT NOT NULL DEFAULT ''",
                'nakshatra': "TEXT NOT NULL DEFAULT ''",
                'gotra': "TEXT NOT NULL DEFAULT ''",
            })
            # 0.7: the register uses the usual Kannada name Karkataka (printed slips keep their wording).
            db.execute("UPDATE members SET rashi='Karkataka / ಕರ್ಕಾಟಕ' WHERE rashi='Karka / ಕರ್ಕ'")
            # Older bookings were always for the event's own date.
            for row in db.execute("SELECT id, snapshot FROM bookings WHERE service_date=''").fetchall():
                db.execute('UPDATE bookings SET service_date=? WHERE id=?', (json.loads(row['snapshot']).get('day', ''), row['id']))
            db.executescript('''
            CREATE INDEX IF NOT EXISTS bookings_service ON bookings(service_date);
            CREATE INDEX IF NOT EXISTS bookings_family ON bookings(family_id);
            CREATE INDEX IF NOT EXISTS items_booking ON items(booking_id);
            CREATE INDEX IF NOT EXISTS members_family ON members(family_id);
            CREATE INDEX IF NOT EXISTS refunds_booking ON refunds(booking_id);
            CREATE INDEX IF NOT EXISTS bookings_import ON bookings(event_id, import_key);
            CREATE INDEX IF NOT EXISTS print_jobs_booking ON print_jobs(booking_id);
            ''')

    @staticmethod
    def _add_columns(db, table, columns):
        existing = {row['name'] for row in db.execute(f'PRAGMA table_info({table})')}
        for name, spec in columns.items():
            if name not in existing:
                db.execute(f'ALTER TABLE {table} ADD COLUMN {name} {spec}')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    def log(self, db, actor, action, detail):
        db.execute('INSERT INTO audit(at,actor,action,detail) VALUES(?,?,?,?)',
                   (dt.datetime.now(dt.timezone.utc).isoformat(), actor, action, json.dumps(detail, ensure_ascii=False)))

    # ------------------------------------------------------------------ masters
    def catalog(self, active_only=False):
        where = ' WHERE active=1' if active_only else ''
        with self.connect() as db:
            events = [dict(r) for r in db.execute(f'SELECT * FROM events{where} ORDER BY id')]
            ids = {e['id'] for e in events}
            sevas = [dict(r) for r in db.execute(f'SELECT * FROM sevas{where} ORDER BY id') if r['event_id'] in ids]
            return {'events': events, 'sevas': sevas}

    def label_dictionary(self):
        with self.connect() as db:
            return dict(db.execute('SELECT english,kannada FROM kannada_labels').fetchall())

    def remember_label(self, db, english, kannada, previous, actor=ADMIN):
        if kannada.strip() and (not previous or previous['kannada'] != kannada):
            db.execute('INSERT INTO kannada_labels(english,kannada) VALUES(?,?) ON CONFLICT(english) DO UPDATE SET kannada=excluded.kannada',
                       (normalize_label(english), kannada.strip()))
            self.log(db, actor, 'Kannada wording saved', {'english': english, 'kannada': kannada})

    def event(self, values, ident=None, actor=ADMIN):
        name = required(values['name'], 'Event / pooja calendar name')
        day = iso_date(required(values['day'], 'Date'), 'Start date')
        currency = values['currency']
        if currency not in CURRENCIES:
            raise ValueError('Choose AED or INR.')
        recurrence = values.get('recurrence') or 'Once'
        if recurrence not in RECURRENCES:
            raise ValueError('Type must be Once (festival/event) or Daily (regular poojas).')
        weekdays = parse_weekdays(values.get('weekdays', 'All')) if recurrence == 'Daily' else '0123456'
        end_day = optional(values.get('end_day'), 10)
        if end_day:
            if recurrence != 'Daily':
                end_day = ''
            else:
                end_day = iso_date(end_day, 'End date')
                if end_day < day:
                    raise ValueError('End date cannot be before the start date.')
        row = (name, optional(values.get('kannada')), day, required(values['place'], 'Place'), currency,
               recurrence, weekdays, end_day)
        with self.connect() as db:
            previous = db.execute('SELECT kannada,day,recurrence,currency FROM events WHERE id=?', (ident,)).fetchone() if ident else None
            if ident and not previous:
                raise ValueError('Event not found.')
            self.remember_label(db, name, row[1], previous, actor)
            if ident:
                db.execute('UPDATE events SET name=?,kannada=?,day=?,place=?,currency=?,recurrence=?,weekdays=?,end_day=? WHERE id=?', (*row, ident))
                if recurrence == 'Once' and previous['day'] != day:
                    # A postponed festival: move its bookings so the priest sheet stays correct.
                    moved = db.execute("UPDATE bookings SET service_date=? WHERE event_id=? AND service_date=? AND status NOT IN ('VOID','REFUNDED')",
                                       (day, ident, previous['day'])).rowcount
                    self.log(db, actor, 'event date changed', {'id': ident, 'from': previous['day'], 'to': day, 'bookings_moved': moved})
            else:
                ident = db.execute('INSERT INTO events(name,kannada,day,place,currency,recurrence,weekdays,end_day) VALUES(?,?,?,?,?,?,?,?)', row).lastrowid
            self.log(db, actor, 'event saved', {'id': ident, 'values': row})
        return ident

    def set_active(self, table, ident, active, actor=ADMIN):
        if table not in ('events', 'sevas'):
            raise ValueError('Invalid master.')
        with self.connect() as db:
            if db.execute(f'UPDATE {table} SET active=? WHERE id=?', (1 if active else 0, ident)).rowcount != 1:
                raise ValueError('Record not found.')
            self.log(db, actor, f'{table[:-1]} {"restored" if active else "archived"}', {'id': ident})

    def delete_master(self, table, ident, actor=ADMIN):
        """Permanently remove an unused event or seva master.

        Historical records are protected: once a master is referenced by a
        booking, it must be archived so receipts and reports remain intact.
        """
        if table not in ('events', 'sevas'):
            raise ValueError('Only event and seva masters can be deleted.')
        ident = int(ident)
        with self.connect() as db:
            row = db.execute(f'SELECT * FROM {table} WHERE id=?', (ident,)).fetchone()
            if not row:
                raise ValueError('Master record not found.')
            if table == 'events':
                seva_count = db.execute('SELECT COUNT(*) FROM sevas WHERE event_id=?', (ident,)).fetchone()[0]
                booking_count = db.execute('SELECT COUNT(*) FROM bookings WHERE event_id=?', (ident,)).fetchone()[0]
                if seva_count or booking_count:
                    raise ValueError('This event has sevas or bookings attached. Archive it instead so history is preserved.')
            else:
                item_count = db.execute('SELECT COUNT(*) FROM items WHERE seva_id=?', (ident,)).fetchone()[0]
                if item_count:
                    raise ValueError('This seva has booking history. Archive it instead so receipts and reports remain intact.')
            db.execute(f'DELETE FROM {table} WHERE id=?', (ident,))
            self.log(db, actor, f'{table[:-1]} permanently deleted', {'id': ident, 'name': row['name']})

    def seva(self, values, ident=None, actor=ADMIN):
        kind = values['kind']
        if kind not in KINDS:
            raise ValueError('Invalid contribution type.')
        price = money(values['price'])
        if kind == 'In-kind' and price:
            raise ValueError('In-kind contributions have zero cash amount. Describe goods in notes.')
        limit_text = str(values.get('daily_limit', '0') or '0').strip()
        if not limit_text.isdigit() or int(limit_text) > 10000:
            raise ValueError('Per-day limit must be a whole number (0 = no limit).')
        row = (int(values['event_id']), required(values['name'], 'Seva name'), optional(values.get('kannada')),
               price, kind, int(limit_text))
        with self.connect() as db:
            if not db.execute('SELECT 1 FROM events WHERE id=?', (row[0],)).fetchone():
                raise ValueError('Choose an existing event.')
            previous = db.execute('SELECT kannada FROM sevas WHERE id=?', (ident,)).fetchone() if ident else None
            if ident and not previous:
                raise ValueError('Seva not found.')
            self.remember_label(db, row[1], row[2], previous, actor)
            if ident:
                db.execute('UPDATE sevas SET event_id=?,name=?,kannada=?,price=?,kind=?,daily_limit=? WHERE id=?', (*row, ident))
            else:
                ident = db.execute('INSERT INTO sevas(event_id,name,kannada,price,kind,daily_limit) VALUES(?,?,?,?,?,?)', row).lastrowid
            self.log(db, actor, 'seva saved', {'id': ident, 'values': row})
        return ident

    # -------------------------------------------------------- devotee register
    def family(self, values, ident=None, actor=ADMIN, db=None):
        email = email_address(values.get('email'))
        row = (person_name(values.get('head'), 'Family / devotee name'), optional(values.get('phone'), 80),
               optional(values.get('gotra'), 100), optional(values.get('address'), 500), optional(values.get('notes'), 1000), email)
        def write(db):
            nonlocal ident
            other = self.family_by_phone(db, row[1], exclude=ident)
            if other:
                raise ValueError(f"Mobile number {row[1]} is already registered to family #{other['id']} ({other['head']}). "
                                 'Open that family and add this person as a member instead.')
            if ident:
                if db.execute('UPDATE families SET head=?,phone=?,gotra=?,address=?,notes=?,email=? WHERE id=?', (*row, ident)).rowcount != 1:
                    raise ValueError('Family not found.')
            else:
                ident = db.execute('INSERT INTO families(head,phone,gotra,address,notes,email,created) VALUES(?,?,?,?,?,?,?)',
                                   (*row, dt.datetime.now(dt.timezone.utc).isoformat())).lastrowid
            self.log(db, actor, 'devotee family saved', {'id': ident, 'head': row[0]})
            return ident
        if db is not None:
            return write(db)
        with self.connect() as db:
            return write(db)

    @staticmethod
    def family_by_phone(db, phone, exclude=None):
        key = phone_key(phone)
        if not key:
            return None
        for f in db.execute('SELECT id, head, phone FROM families WHERE id IS NOT ? ORDER BY id', (exclude,)):
            if phone_key(f['phone']) == key:
                return f
        return None

    def duplicate_families(self):
        """Groups of family ids that share a mobile number (from before duplicates were blocked)."""
        groups = defaultdict(list)
        with self.connect() as db:
            for f in db.execute('SELECT id, head, phone FROM families ORDER BY id'):
                key = phone_key(f['phone'])
                if key:
                    groups[key].append(dict(f))
        return [g for g in groups.values() if len(g) > 1]

    def merge_families(self, keep_id, remove_id, actor):
        """Move members and bookings of remove_id into keep_id, then delete remove_id."""
        if int(keep_id) == int(remove_id):
            raise ValueError('Choose two different families.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            keep = db.execute('SELECT * FROM families WHERE id=?', (keep_id,)).fetchone()
            gone = db.execute('SELECT * FROM families WHERE id=?', (remove_id,)).fetchone()
            if not keep or not gone:
                raise ValueError('Family not found.')
            existing = {' '.join(m['name'].casefold().split()): m['id']
                        for m in db.execute('SELECT id, name FROM members WHERE family_id=?', (keep_id,))}
            moved = merged = 0
            for m in db.execute('SELECT * FROM members WHERE family_id=?', (remove_id,)).fetchall():
                same = existing.get(' '.join(m['name'].casefold().split()))
                if same:
                    # Same person twice: keep one record, fill its blanks, point old slips at it.
                    target = db.execute('SELECT * FROM members WHERE id=?', (same,)).fetchone()
                    for col in ('kannada', 'rashi', 'nakshatra', 'gotra'):
                        if not target[col] and m[col]:
                            db.execute(f'UPDATE members SET {col}=? WHERE id=?', (m[col], same))
                    db.execute('UPDATE items SET member_id=? WHERE member_id=?', (same, m['id']))
                    db.execute('DELETE FROM members WHERE id=?', (m['id'],))
                    merged += 1
                else:
                    db.execute('UPDATE members SET family_id=? WHERE id=?', (keep_id, m['id']))
                    moved += 1
            for col in ('phone', 'gotra', 'address', 'notes', 'email'):
                if not keep[col] and gone[col]:
                    db.execute(f'UPDATE families SET {col}=? WHERE id=?', (gone[col], keep_id))
            bookings = db.execute('UPDATE bookings SET family_id=? WHERE family_id=?', (keep_id, remove_id)).rowcount
            db.execute('DELETE FROM families WHERE id=?', (remove_id,))
            self.log(db, actor, 'families merged', {'kept': int(keep_id), 'removed': int(remove_id), 'head': gone['head'],
                                                    'members_moved': moved, 'members_combined': merged, 'bookings_moved': bookings})
        return moved, merged, bookings

    def delete_family(self, ident, actor=ADMIN):
        """Permanently delete an unused devotee family; preserve any booking history."""
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            family = db.execute('SELECT * FROM families WHERE id=?', (int(ident),)).fetchone()
            if not family:
                raise ValueError('Devotee family not found.')
            bookings = db.execute('SELECT COUNT(*) FROM bookings WHERE family_id=?', (int(ident),)).fetchone()[0]
            if bookings:
                raise ValueError('This family has booking history. It cannot be permanently deleted; keep it for receipts and reports.')
            db.execute('DELETE FROM members WHERE family_id=?', (int(ident),))
            db.execute('DELETE FROM families WHERE id=?', (int(ident),))
            self.log(db, actor, 'devotee family permanently deleted', {'id': int(ident), 'head': family['head']})

    def delete_member(self, ident, actor=ADMIN):
        """Permanently delete a member only when no historical slip refers to them."""
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            member = db.execute('SELECT * FROM members WHERE id=?', (int(ident),)).fetchone()
            if not member:
                raise ValueError('Devotee member not found.')
            slips = db.execute('SELECT COUNT(*) FROM items WHERE member_id=?', (int(ident),)).fetchone()[0]
            if slips:
                raise ValueError('This member appears on booking slips. It cannot be permanently deleted; mark it inactive instead.')
            db.execute('DELETE FROM members WHERE id=?', (int(ident),))
            self.log(db, actor, 'devotee member permanently deleted', {'id': int(ident), 'name': member['name']})

    # -------------------------------------------------------------- settings
    SETTING_LIMITS = {'org_name': 120, 'org_name_kn': 120, 'org_place': 120}

    def settings(self):
        with self.connect() as db:
            return dict(db.execute('SELECT key, value FROM settings').fetchall())

    def save_settings(self, values, actor):
        with self.connect() as db:
            for key, limit in self.SETTING_LIMITS.items():
                if key in values:
                    db.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                               (key, optional(values[key], limit)))
            self.log(db, actor, 'settings saved', {k: values[k] for k in self.SETTING_LIMITS if k in values})

    def stats(self):
        with self.connect() as db:
            count = lambda t: db.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
            return {t: count(t) for t in ('events', 'sevas', 'bookings', 'families', 'members', 'staff', 'audit')}

    def factory_reset(self, actor='Developer'):
        """Erase every table (bookings, devotees, staff, settings, audit...) and start fresh.

        The caller saves any final backup first. The schema is rebuilt empty.
        """
        db = sqlite3.connect(self.path, timeout=20)
        try:
            db.execute('PRAGMA foreign_keys=OFF')
            tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            with db:
                for table in tables:
                    db.execute(f'DROP TABLE IF EXISTS "{table}"')
            db.execute('VACUUM')
        finally:
            db.close()
        fresh = Store(self.path)
        with fresh.connect() as conn:
            fresh.log(conn, actor, 'factory reset', {'tables_cleared': len(tables)})
        return len(tables)

    def log_session(self, user, action):
        with self.connect() as db:
            self.log(db, f"{user['role']}: {user['name']}", action, {})

    def member(self, values, ident=None, actor=ADMIN, db=None):
        relation = values.get('relation') or 'Self'
        if relation not in RELATIONS:
            raise ValueError('Choose a relation from the list.')
        row = (int(values['family_id']), person_name(values.get('name'), 'Member name'), optional(values.get('kannada')),
               relation, optional(values.get('rashi'), 100), optional(values.get('nakshatra'), 100),
               optional(values.get('gotra'), 100),
               0 if str(values.get('active', '1')) in ('0', 'False', 'No') else 1)
        def write(db):
            nonlocal ident
            if not db.execute('SELECT 1 FROM families WHERE id=?', (row[0],)).fetchone():
                raise ValueError('Family not found.')
            if ident:
                if db.execute('UPDATE members SET family_id=?,name=?,kannada=?,relation=?,rashi=?,nakshatra=?,gotra=?,active=? WHERE id=?', (*row, ident)).rowcount != 1:
                    raise ValueError('Member not found.')
            else:
                ident = db.execute('INSERT INTO members(family_id,name,kannada,relation,rashi,nakshatra,gotra,active) VALUES(?,?,?,?,?,?,?,?)', row).lastrowid
            self.log(db, actor, 'devotee member saved', {'id': ident, 'family': row[0], 'name': row[1]})
            return ident
        if db is not None:
            return write(db)
        with self.connect() as db:
            return write(db)

    def families(self, query='', limit=500):
        query = str(query or '').strip().casefold()
        with self.connect() as db:
            fams = [dict(r) for r in db.execute('SELECT * FROM families ORDER BY head COLLATE NOCASE, id')]
            members = defaultdict(list)
            for m in db.execute('SELECT * FROM members ORDER BY id'):
                members[m['family_id']].append(dict(m))
        result = []
        digits = ''.join(ch for ch in query if ch.isdigit())
        for f in fams:
            f['members'] = members[f['id']]
            haystack = ' '.join([f['head'], f['gotra'], f['address'], f['email']] + [' '.join((m['name'], m['kannada'], m['gotra'])) for m in f['members']]).casefold()
            phone = ''.join(ch for ch in f['phone'] if ch.isdigit())
            if not query or query in haystack or (len(digits) >= 3 and digits in phone) or query == str(f['id']):
                result.append(f)
            if len(result) >= limit:
                break
        return result

    def family_detail(self, fid):
        with self.connect() as db:
            row = db.execute('SELECT * FROM families WHERE id=?', (fid,)).fetchone()
            if not row:
                raise ValueError('Family not found.')
            family = dict(row)
            family['members'] = [dict(m) for m in db.execute('SELECT * FROM members WHERE family_id=? ORDER BY id', (fid,))]
            family['bookings'] = [dict(b) for b in db.execute('SELECT * FROM bookings WHERE family_id=? ORDER BY id DESC', (fid,))]
            return family

    # ---------------------------------------------------------------- bookings
    @staticmethod
    def check_service_date(event, service_date):
        if event['recurrence'] != 'Daily':
            return event['day']
        day = iso_date(service_date or '', 'Pooja date')
        if day < event['day']:
            raise ValueError(f"{event['name']} bookings start from {event['day']}.")
        if event['end_day'] and day > event['end_day']:
            raise ValueError(f"{event['name']} bookings end on {event['end_day']}.")
        if str(dt.date.fromisoformat(day).weekday()) not in (event['weekdays'] or '0123456'):
            raise ValueError(f"{event['name']} is only performed on: {weekday_text(event['weekdays'])}.")
        return day

    def booked_count(self, db, seva_id, service_date):
        return db.execute('''SELECT COUNT(*) FROM items JOIN bookings ON bookings.id=items.booking_id
            WHERE items.seva_id=? AND bookings.service_date=? AND bookings.status NOT IN ('VOID','REFUNDED') ''', (seva_id, service_date)).fetchone()[0]

    def availability(self, event_id, service_date):
        """{seva_id: remaining slots or None for unlimited} for a date."""
        with self.connect() as db:
            event = db.execute('SELECT * FROM events WHERE id=?', (event_id,)).fetchone()
            if not event:
                raise ValueError('Choose an existing event.')
            day = self.check_service_date(event, service_date)
            result = {}
            for s in db.execute('SELECT id,daily_limit FROM sevas WHERE event_id=?', (event_id,)).fetchall():
                result[s['id']] = None if not s['daily_limit'] else max(0, s['daily_limit'] - self.booked_count(db, s['id'], day))
            return result

    def book(self, data, actor, allow_override=False):
        key = required(data.get('request_key'), 'Request ID', 100)
        payload = json.dumps(data, sort_keys=True, ensure_ascii=False)
        name = person_name(data.get('devotee'), 'Devotee name')
        event_id = int(data['event_id'])
        lines = data.get('items', [])
        if not isinstance(lines, list) or not lines or len(lines) > 100:
            raise ValueError('Add between 1 and 100 seva lines.')
        family_id = data.get('family_id') or None
        family_id = int(family_id) if family_id is not None else None
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT id,payload FROM bookings WHERE request_key=?', (key,)).fetchone()
            if existing:
                if existing['payload'] != payload:
                    raise ValueError('This request ID was already used for different details.')
                return existing['id']
            event = db.execute('SELECT * FROM events WHERE id=?', (event_id,)).fetchone()
            if not event:
                raise ValueError('Choose an existing event.')
            if not event['active']:
                raise ValueError('This event is archived. Restore it in masters before booking.')
            service_date = self.check_service_date(event, data.get('service_date'))
            devotee = dict(name=name, kn=optional(data.get('devotee_kn')), rashi=optional(data.get('rashi'), 100),
                           nakshatra=optional(data.get('nakshatra'), 100))
            gotra = optional(data.get('gotra'), 100)
            phone = optional(data.get('phone'), 80)
            email = email_address(data.get('email'))
            # A fully identified devotee must not be entered twice for the
            # same event/date. Blank email or phone values remain valid for
            # walk-in bookings.
            if phone and email:
                name_key = ' '.join(name.casefold().split())
                phone_key_value = phone_key(phone)
                for prior in db.execute("""SELECT id, devotee, phone, email FROM bookings
                        WHERE event_id=? AND service_date=? AND status NOT IN ('VOID','REFUNDED')""",
                                        (event_id, service_date)):
                    if (name_key == ' '.join(prior['devotee'].casefold().split())
                            and phone_key_value == phone_key(prior['phone'])
                            and email.casefold() == prior['email'].casefold()):
                        raise ValueError(f"This devotee already has booking #{prior['id']:06d} for this event/date. "
                                         'Open that booking to change it instead of creating a duplicate.')
            members = {}
            if family_id is not None:
                fam = db.execute('SELECT * FROM families WHERE id=?', (family_id,)).fetchone()
                if not fam:
                    raise ValueError('Selected devotee family was not found.')
                members = {m['id']: m for m in db.execute('SELECT * FROM members WHERE family_id=?', (family_id,))}
                # Phones see masked numbers, so a blank phone means "use the register's".
                phone = phone or fam['phone']
                gotra = gotra or fam['gotra']
                email = email or fam['email']
            elif data.get('save_devotee'):
                known = self.family_by_phone(db, phone)
                if known:
                    # Never create a second family for the same mobile number: use the registered one.
                    family_id = known['id']
                    names = {' '.join(r['name'].casefold().split()) for r in db.execute('SELECT name FROM members WHERE family_id=?', (family_id,))}
                    if ' '.join(name.casefold().split()) not in names:
                        self.member(dict(family_id=family_id, name=name, kannada=devotee['kn'], relation='Relative', gotra=gotra,
                                         rashi=devotee['rashi'], nakshatra=devotee['nakshatra']), actor=actor, db=db)
                else:
                    family_id = self.family(dict(head=name, phone=phone, gotra=gotra, email=email), actor=actor, db=db)
                    self.member(dict(family_id=family_id, name=name, kannada=devotee['kn'], relation='Self', gotra=gotra,
                                     rashi=devotee['rashi'], nakshatra=devotee['nakshatra']), actor=actor, db=db)
            expanded, per_seva = [], defaultdict(int)
            for line in lines:
                seva = db.execute('SELECT * FROM sevas WHERE id=? AND event_id=?', (int(line['seva_id']), event_id)).fetchone()
                if not seva:
                    raise ValueError('Seva does not belong to this event.')
                if not seva['active']:
                    raise ValueError(f"{seva['name']} is archived and cannot be booked.")
                qty = int(line['quantity'])
                if str(qty) != str(line['quantity']) or not 1 <= qty <= 100:
                    raise ValueError('Quantity must be a whole number from 1 to 100.')
                price = money(line.get('amount', str(Decimal(seva['price']) / 100)))
                if seva['kind'] == 'In-kind' and price:
                    raise ValueError('In-kind entries cannot include cash.')
                if seva['kind'] == 'Seva' and price != seva['price'] and not allow_override:
                    raise ValueError('Only the laptop administrator can override a fixed seva price.')
                member_id = line.get('member_id') or None
                if member_id is not None:
                    m = members.get(int(member_id))
                    if not m:
                        raise ValueError('A selected family member does not belong to this devotee family.')
                    person = (m['id'], m['name'], m['kannada'], m['rashi'], m['nakshatra'], m['gotra'] or gotra)
                else:
                    person = (None, devotee['name'], devotee['kn'], devotee['rashi'], devotee['nakshatra'], gotra)
                per_seva[seva['id']] += qty
                expanded.extend([(seva['id'], seva['name'], seva['kannada'], seva['kind'], price, *person)] * qty)
            if len(expanded) > 100:
                raise ValueError('Maximum 100 slips in one booking.')
            for sid, qty in per_seva.items():
                seva = db.execute('SELECT name,daily_limit FROM sevas WHERE id=?', (sid,)).fetchone()
                if seva['daily_limit']:
                    left = seva['daily_limit'] - self.booked_count(db, sid, service_date)
                    if qty > left:
                        raise ValueError(f"{seva['name']} is full on {service_date}: {max(left, 0)} of {seva['daily_limit']} slots left.")
            now = dt.datetime.now(dt.timezone.utc).isoformat()
            bid = db.execute('''INSERT INTO bookings(request_key,payload,event_id,created,operator,devotee,
                phone,rashi,nakshatra,note,snapshot,total,devotee_kn,service_date,family_id,gotra,email,external_ref,import_key)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (key, payload, event_id, now, actor, name, phone, devotee['rashi'], devotee['nakshatra'],
                 optional(data.get('note'), 1000), json.dumps(dict(event), ensure_ascii=False),
                 sum(x[4] for x in expanded), devotee['kn'], service_date, family_id, gotra, email,
                 optional(data.get('external_ref'), 40), optional(data.get('import_key'), 80))).lastrowid
            db.executemany('''INSERT INTO items(booking_id,seva_id,name,kannada,kind,price,member_id,person,person_kn,rashi,nakshatra,gotra)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''', [(bid, *x) for x in expanded])
            db.execute('INSERT INTO print_jobs(booking_id) VALUES(?)', (bid,))
            self.log(db, actor, 'booking created', {'id': bid, 'slips': len(expanded), 'service_date': service_date})
            return bid

    def bookings(self):
        with self.connect() as db:
            return [dict(x) for x in db.execute('SELECT * FROM bookings ORDER BY id DESC')]

    def detail(self, bid):
        with self.connect() as db:
            row = db.execute('SELECT * FROM bookings WHERE id=?', (bid,)).fetchone()
            if not row:
                raise ValueError('Booking not found.')
            booking = dict(row)
            booking['event'] = json.loads(booking['snapshot'])
            booking['items'] = [dict(x) for x in db.execute('SELECT * FROM items WHERE booking_id=? ORDER BY id', (bid,))]
            for item in booking['items']:
                # Slips created before v0.5 have no per-person snapshot.
                if not item['person']:
                    item.update(person=booking['devotee'], person_kn=booking['devotee_kn'],
                                rashi=booking['rashi'], nakshatra=booking['nakshatra'])
                elif item['person'] == booking['devotee']:
                    # Older bookings stored the main devotee name but omitted
                    # the astrology snapshot on each slip.  Keep receipts and
                    # correction screens consistent with the booking header.
                    item['person_kn'] = item['person_kn'] or booking['devotee_kn']
                    item['rashi'] = item['rashi'] or booking['rashi']
                    item['nakshatra'] = item['nakshatra'] or booking['nakshatra']
                item['gotra'] = item['gotra'] or booking['gotra']
            booking['refunds'] = [dict(x) for x in db.execute('SELECT * FROM refunds WHERE booking_id=? ORDER BY id', (bid,))]
            booking['org'] = dict(db.execute("SELECT key, value FROM settings WHERE key IN ('org_name','org_name_kn')").fetchall())
            booking['print_confirmed'] = bool(db.execute(
                "SELECT 1 FROM print_jobs WHERE booking_id=? AND (printed_count>0 OR status='CONFIRMED')", (bid,)).fetchone())
            return booking

    def pay(self, bid, actor, method='Cash'):
        if method not in METHODS:
            raise ValueError('Invalid payment method.')
        with self.connect() as db:
            row = db.execute('SELECT status,total FROM bookings WHERE id=?', (bid,)).fetchone()
            if not row or row['status'] != 'UNPAID':
                raise ValueError('Only unpaid bookings can be marked paid.')
            if row['total'] <= 0:
                raise ValueError('No cash is due on this booking. Use its in-kind acknowledgement.')
            changed = db.execute("UPDATE bookings SET status='PAID',payment_method=?,paid_at=?,paid_by=? WHERE id=? AND status='UNPAID'",
                                 (method, dt.datetime.now(dt.timezone.utc).isoformat(), actor, bid)).rowcount
            if changed != 1:
                raise ValueError('Payment was already recorded. Refresh the list.')
            self.log(db, actor, 'payment received', {'id': bid, 'method': method, 'amount': row['total']})

    def void(self, bid, reason, actor=ADMIN):
        reason = required(reason, 'Cancellation reason', 500)
        with self.connect() as db:
            if db.execute("UPDATE bookings SET status='VOID',void_reason=? WHERE id=? AND status='UNPAID'", (reason, bid)).rowcount != 1:
                raise ValueError('Only unpaid bookings can be cancelled. Paid refunds are not implemented.')
            self.log(db, actor, 'booking voided', {'id': bid, 'reason': reason})

    def queue(self):
        with self.connect() as db:
            return [dict(x) for x in db.execute("SELECT * FROM print_jobs WHERE status='PENDING' ORDER BY id")]

    def request_print(self, bid, actor):
        """A phone asks the laptop to print this booking's slips."""
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        with self.connect() as db:
            row = db.execute('SELECT status FROM bookings WHERE id=?', (bid,)).fetchone()
            if not row:
                raise ValueError('Booking not found.')
            if row['status'] in ('VOID', 'REFUNDED'):
                raise ValueError('Cancelled or refunded bookings are not printed.')
            if db.execute("UPDATE print_jobs SET status='PENDING',requested_at=?,requested_by=? WHERE booking_id=?",
                          (now, actor, bid)).rowcount == 0:
                db.execute("INSERT INTO print_jobs(booking_id,status,requested_at,requested_by) VALUES(?, 'PENDING', ?, ?)", (bid, now, actor))
            self.log(db, actor, 'print requested', {'id': bid})

    def print_requests(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('''SELECT print_jobs.booking_id, print_jobs.requested_at, print_jobs.requested_by,
                bookings.devotee, bookings.external_ref, bookings.status FROM print_jobs JOIN bookings ON bookings.id=print_jobs.booking_id
                WHERE print_jobs.status='PENDING' AND print_jobs.requested_at IS NOT NULL ORDER BY print_jobs.requested_at''')]

    def printed(self, bid, actor=ADMIN):
        with self.connect() as db:
            db.execute("UPDATE print_jobs SET status='CONFIRMED', printed_count=printed_count+1 WHERE booking_id=?", (bid,))
            self.log(db, actor, 'print manually confirmed', {'id': bid})

    def backup(self, destination):
        with self.connect() as source, sqlite3.connect(str(destination)) as target:
            source.backup(target)

    def export(self, destination):
        with open(destination, 'w', newline='', encoding='utf-8-sig') as handle:
            writer = csv.writer(handle)
            writer.writerow(['Booking', 'Booking no.', 'Date UTC', 'Pooja date', 'Event', 'Currency', 'Devotee', 'Phone', 'Email', 'Gotra', 'Family ID',
                             'Total', 'Refunded', 'Status', 'Method', 'Operator', 'Payment recorded by'])
            for b in self.bookings():
                event = json.loads(b['snapshot'])
                writer.writerow(safe_csv([b['id'], b['external_ref'], b['created'], b['service_date'], event['name'], event['currency'], b['devotee'],
                                          b['phone'], b['email'],
                                          b['gotra'], b['family_id'] or '', f"{b['total'] / 100:.2f}", f"{b['refunded'] / 100:.2f}", b['status'],
                                          b['payment_method'] or '', b['operator'], b['paid_by'] or '']))

    # -------------------------------------------------------------- staff PINs
    def has_staff(self):
        with self.connect() as db:
            return bool(db.execute('SELECT 1 FROM staff WHERE active=1 LIMIT 1').fetchone())

    def staff_list(self, active_only=False):
        with self.connect() as db:
            sql = 'SELECT id,name,role,active,created FROM staff' + (' WHERE active=1' if active_only else '')
            return [dict(r) for r in db.execute(sql + ' ORDER BY name COLLATE NOCASE')]

    def add_staff(self, name, role, pin, actor=ADMIN):
        name = required(name, 'Staff name', 60)
        if role not in security.ROLES:
            raise ValueError('Choose a role: ' + ', '.join(security.ROLES))
        salt, digest = security.hash_pin(security.check_pin(pin))
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            first = not db.execute('SELECT 1 FROM staff LIMIT 1').fetchone()
            if first and role != 'Admin':
                raise ValueError('The first staff login must be an Admin.')
            try:
                ident = db.execute('INSERT INTO staff(name,role,salt,pin_hash,created) VALUES(?,?,?,?,?)',
                                   (name, role, salt, digest, dt.datetime.now(dt.timezone.utc).isoformat())).lastrowid
            except sqlite3.IntegrityError:
                raise ValueError(f'A staff login named {name} already exists.')
            self.log(db, actor, 'staff added', {'id': ident, 'name': name, 'role': role})
            return ident

    def update_staff(self, ident, role, active, actor=ADMIN):
        if role not in security.ROLES:
            raise ValueError('Choose a valid role.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM staff WHERE id=?', (ident,)).fetchone()
            if not row:
                raise ValueError('Staff login not found.')
            if row['role'] == 'Admin' and row['active'] and (role != 'Admin' or not active):
                admins = db.execute("SELECT COUNT(*) FROM staff WHERE role='Admin' AND active=1").fetchone()[0]
                if admins <= 1:
                    raise ValueError('Keep at least one active Admin login.')
            db.execute('UPDATE staff SET role=?,active=? WHERE id=?', (role, 1 if active else 0, ident))
            self.log(db, actor, 'staff updated', {'id': ident, 'name': row['name'], 'role': role, 'active': bool(active)})

    def set_pin(self, ident, pin, actor=ADMIN):
        salt, digest = security.hash_pin(security.check_pin(pin))
        with self.connect() as db:
            if db.execute('UPDATE staff SET salt=?,pin_hash=?,failures=0,locked_until=0 WHERE id=?', (salt, digest, ident)).rowcount != 1:
                raise ValueError('Staff login not found.')
            self.log(db, actor, 'staff PIN changed', {'id': ident})

    def login(self, name, pin):
        """Returns {'id','name','role'} or raises ValueError. Locks a login after repeated failures."""
        name = str(name or '').strip()
        with self.connect() as db:
            row = db.execute('SELECT * FROM staff WHERE name=? COLLATE NOCASE AND active=1', (name,)).fetchone()
            now = time.time()
            if not row:
                security.hash_pin(pin or '0', '00' * 16)  # similar timing for unknown names
                raise ValueError('Name or PIN is not correct.')
            if row['locked_until'] > now:
                minutes = int((row['locked_until'] - now) // 60) + 1
                raise ValueError(f'Too many wrong PINs. Try again in {minutes} minute(s) or ask an Admin to reset the PIN.')
            if security.pin_matches(str(pin or ''), row['salt'], row['pin_hash']):
                db.execute('UPDATE staff SET failures=0,locked_until=0 WHERE id=?', (row['id'],))
                return {'id': row['id'], 'name': row['name'], 'role': row['role']}
            failures = row['failures'] + 1
            locked = now + security.LOCK_MINUTES * 60 if failures >= security.MAX_FAILURES else 0
            db.execute('UPDATE staff SET failures=?,locked_until=? WHERE id=?', (0 if locked else failures, locked, row['id']))
            self.log(db, row['name'], 'login failed', {'locked': bool(locked)})
        # Raised after the block so the failure count is committed, not rolled back.
        raise ValueError('Name or PIN is not correct.' + (' This login is now locked for 5 minutes.' if locked else ''))

    # --------------------------------------------------- refunds, corrections
    def refund(self, bid, actor, amount, method, reason):
        reason = required(reason, 'Refund reason', 500)
        if method not in METHODS:
            raise ValueError('Invalid refund method.')
        amount = money(amount)
        if amount <= 0:
            raise ValueError('Refund amount must be more than zero.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT status,total,refunded FROM bookings WHERE id=?', (bid,)).fetchone()
            if not row or row['status'] != 'PAID':
                raise ValueError('Only paid bookings can be refunded.')
            left = row['total'] - row['refunded']
            if amount > left:
                raise ValueError(f'Refund cannot be more than the remaining paid amount ({fmt(left)}).')
            full = amount == left
            db.execute('INSERT INTO refunds(booking_id,at,actor,amount,method,reason) VALUES(?,?,?,?,?,?)',
                       (bid, dt.datetime.now(dt.timezone.utc).isoformat(), actor, amount, method, reason))
            db.execute('UPDATE bookings SET refunded=refunded+?, status=? WHERE id=?', (amount, 'REFUNDED' if full else 'PAID', bid))
            self.log(db, actor, 'refund recorded', {'id': bid, 'amount': amount, 'method': method, 'reason': reason, 'full': full})
            return full

    def correct_payment(self, bid, method, reason, actor):
        reason = required(reason, 'Correction reason', 500)
        if method not in METHODS:
            raise ValueError('Invalid payment method.')
        with self.connect() as db:
            row = db.execute('SELECT status,payment_method FROM bookings WHERE id=?', (bid,)).fetchone()
            if not row or row['status'] not in ('PAID', 'REFUNDED'):
                raise ValueError('Only paid bookings have a payment method to correct.')
            if row['payment_method'] == method:
                raise ValueError('That is already the recorded payment method.')
            db.execute('UPDATE bookings SET payment_method=? WHERE id=?', (method, bid))
            self.log(db, actor, 'payment method corrected', {'id': bid, 'from': row['payment_method'], 'to': method, 'reason': reason})

    CORRECTABLE = ('devotee', 'devotee_kn', 'phone', 'email', 'gotra', 'rashi', 'nakshatra', 'note')
    ITEM_FIELDS = ('person', 'person_kn', 'rashi', 'nakshatra', 'gotra')

    def correct_details(self, bid, values, reason, actor):
        """Fix typos in names/astrology details or move a daily pooja to another date.

        Amounts and sevas never change here: refund and re-book instead.
        """
        reason = required(reason, 'Correction reason', 500)
        limits = {'devotee': 200, 'devotee_kn': 200, 'phone': 80, 'email': 120, 'gotra': 100, 'rashi': 100, 'nakshatra': 100, 'note': 1000,
                  'person': 200, 'person_kn': 200}
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM bookings WHERE id=?', (bid,)).fetchone()
            if not row:
                raise ValueError('Booking not found.')
            if row['status'] in ('VOID', 'REFUNDED'):
                raise ValueError('Cancelled or fully refunded bookings cannot be corrected.')
            before, after = {}, {}
            updates = {}
            for key in self.CORRECTABLE:
                if key in values:
                    new = optional(values[key], limits[key])
                    if key == 'devotee':
                        new = person_name(new, 'Devotee name')
                    if key == 'email':
                        new = email_address(new)
                    if new != row[key]:
                        updates[key] = new
                        before[key], after[key] = row[key], new
            if 'service_date' in values and str(values['service_date']).strip() != row['service_date']:
                event = db.execute('SELECT * FROM events WHERE id=?', (row['event_id'],)).fetchone()
                if event['recurrence'] != 'Daily':
                    raise ValueError('Festival bookings follow the event date. Change the event date in Masters instead.')
                day = self.check_service_date(event, values['service_date'])
                counts = defaultdict(int)
                for item in db.execute('SELECT seva_id FROM items WHERE booking_id=? AND seva_id IS NOT NULL', (bid,)):
                    counts[item['seva_id']] += 1
                for sid, qty in counts.items():
                    seva = db.execute('SELECT name,daily_limit FROM sevas WHERE id=?', (sid,)).fetchone()
                    if seva and seva['daily_limit'] and qty > seva['daily_limit'] - self.booked_count(db, sid, day):
                        raise ValueError(f"{seva['name']} is full on {day}.")
                updates['service_date'] = day
                before['service_date'], after['service_date'] = row['service_date'], day
            for key, new in updates.items():
                db.execute(f'UPDATE bookings SET {key}=? WHERE id=?', (new, bid))
            for item_id, fields in (values.get('items') or {}).items():
                item = db.execute('SELECT * FROM items WHERE id=? AND booking_id=?', (int(item_id), bid)).fetchone()
                if not item:
                    raise ValueError('A slip does not belong to this booking.')
                changed = {}
                for key in self.ITEM_FIELDS:
                    if key in fields:
                        new = optional(fields[key], limits.get(key, 100))
                        if key == 'person':
                            new = person_name(new, 'Slip name')
                        if new != item[key]:
                            changed[key] = new
                for key, new in changed.items():
                    db.execute(f'UPDATE items SET {key}=? WHERE id=?', (new, item['id']))
                if changed:
                    before[f'slip {item["id"]}'] = {k: item[k] for k in changed}
                    after[f'slip {item["id"]}'] = changed
            if not after:
                raise ValueError('Nothing was changed.')
            self.log(db, actor, 'booking corrected', {'id': bid, 'reason': reason, 'before': before, 'after': after})

    # ------------------------------------------------- linking older bookings
    def link_booking(self, bid, fid, actor):
        with self.connect() as db:
            if not db.execute('SELECT 1 FROM families WHERE id=?', (fid,)).fetchone():
                raise ValueError('Family not found.')
            row = db.execute('SELECT family_id FROM bookings WHERE id=?', (bid,)).fetchone()
            if not row:
                raise ValueError('Booking not found.')
            if row['family_id'] == fid:
                raise ValueError('This booking is already linked to that family.')
            db.execute('UPDATE bookings SET family_id=? WHERE id=?', (fid, bid))
            self.log(db, actor, 'booking linked to family', {'id': bid, 'family': fid, 'previous': row['family_id']})

    def unlink_booking(self, bid, actor):
        with self.connect() as db:
            row = db.execute('SELECT family_id FROM bookings WHERE id=?', (bid,)).fetchone()
            if not row or row['family_id'] is None:
                raise ValueError('This booking is not linked to a family.')
            db.execute('UPDATE bookings SET family_id=NULL WHERE id=?', (bid,))
            self.log(db, actor, 'booking unlinked from family', {'id': bid, 'previous': row['family_id']})

    def link_suggestions(self, fid):
        """Unlinked bookings whose devotee name or phone matches this family."""
        fam = self.family_detail(fid)
        names = {' '.join(x.casefold().split()) for x in [fam['head']] + [m['name'] for m in fam['members']] if x}
        digits = lambda text: ''.join(c for c in str(text) if c.isdigit())[-8:]
        phone = digits(fam['phone'])
        with self.connect() as db:
            rows = [dict(r) for r in db.execute('SELECT * FROM bookings WHERE family_id IS NULL ORDER BY id DESC')]
        out = []
        for b in rows:
            by_name = ' '.join(b['devotee'].casefold().split()) in names
            by_phone = len(phone) >= 6 and digits(b['phone']) == phone
            if by_name or by_phone:
                b['match'] = 'name and phone' if by_name and by_phone else ('name' if by_name else 'phone')
                out.append(b)
        return out

    # ------------------------------------------------------------- importing
    def known_imports(self, event_id):
        """{import key: booking} for bookings already imported (or entered with a booking number) for an event."""
        import importer
        out = {}
        with self.connect() as db:
            for r in db.execute('SELECT id,status,total,external_ref,import_key FROM bookings WHERE event_id=?', (int(event_id),)):
                for key in (r['import_key'], importer.normal_ref(r['external_ref']) if r['external_ref'] else ''):
                    if key:
                        out.setdefault(key, dict(r))
        return out

    def import_rows(self, event_id, rows, actor, save_devotees=False):
        """Create (or mark paid) the ticked preview rows. Each row is its own transaction.

        Returns (created, marked_paid, failed) counts; each row's status/problem is updated in place.
        """
        import importer
        created = marked = failed = 0
        for row in rows:
            if not row.include or row.status in ('Imported', 'Duplicate', 'Skip', 'Error'):
                continue
            key = importer.normal_ref(row.ref) if row.ref else importer.fingerprint(row)
            try:
                prepaid_by = f'Paid before event (imported by {actor})'
                if row.status == 'Update' and row.existing_id:
                    self.pay(row.existing_id, prepaid_by, row.method or 'Bank transfer')
                    self._note_import_payment(row.existing_id, actor)
                    row.status, row.problem, row.include = 'Imported', f'#{row.existing_id:06d} marked paid.', False
                    marked += 1
                    continue
                data = dict(request_key=f'import:{int(event_id)}:{key}', event_id=int(event_id), devotee=row.name,
                            devotee_kn=row.name_kn, phone=row.phone, email=row.email, gotra=row.gotra, rashi=row.rashi,
                            nakshatra=row.nakshatra, note=row.note, external_ref=row.ref, import_key=key,
                            save_devotee=bool(save_devotees),
                            items=[{k: line[k] for k in ('seva_id', 'quantity', 'amount')} for line in row.items])
                bid = self.book(data, f'{actor} (import)', allow_override=True)
                row.existing_id = bid
                if row.paid:
                    self.pay(bid, prepaid_by, row.method or 'Bank transfer')
                    self._note_import_payment(bid, actor)
                row.status, row.include = 'Imported', False
                row.problem = f"Booking #{bid:06d} created" + (' and marked paid.' if row.paid else ' (unpaid).')
                created += 1
            except Exception as ex:
                row.status, row.problem, row.include = 'Check', f'Not imported: {ex}', False
                failed += 1
        return created, marked, failed

    def _note_import_payment(self, bid, actor):
        with self.connect() as db:
            self.log(db, actor, 'payment imported', {'id': bid, 'note': 'Paid before the event according to the imported list'})

    # -------------------------------------------------------- paging and sync
    def data_version(self):
        with self.connect() as db:
            row = db.execute('SELECT MAX(id), COUNT(*) FROM audit').fetchone()
            jobs = db.execute("SELECT COUNT(*) FROM print_jobs WHERE status='PENDING'").fetchone()[0]
            return (row[0], row[1], jobs)

    def bookings_page(self, query='', limit=200, offset=0, event_id=None, status=None):
        query = str(query or '').strip()
        digits = ''.join(c for c in query if c.isdigit())
        where, args = [], []
        if event_id:
            where.append('event_id=?')
            args.append(int(event_id))
        if status:
            where.append('status IN (%s)' % ','.join('?' * len(status)))
            args += list(status)
        if query:
            like = '%' + query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
            where.append("(devotee LIKE ? ESCAPE '\\' OR devotee_kn LIKE ? ESCAPE '\\' OR email LIKE ? ESCAPE '\\'"
                         " OR external_ref LIKE ? ESCAPE '\\'"
                         " OR EXISTS(SELECT 1 FROM items WHERE items.booking_id=bookings.id AND items.person LIKE ? ESCAPE '\\')")
            args += [like, like, like, like, like]
            if query.isdigit():
                where[-1] += ' OR id=?'
                args.append(int(query))
            phone_like = len(digits) >= 4 and not any(ch.isalpha() for ch in query)
            if phone_like:  # "SSP-001" is a booking number, not part of a phone number
                where[-1] += (" OR replace(replace(replace(replace(replace(phone,' ',''),'-',''),'+',''),'(',''),')','') LIKE ?")
                args.append('%' + digits + '%')
            where[-1] += ')'
        sql = '''SELECT bookings.*, (SELECT COUNT(*) FROM items WHERE booking_id=bookings.id) AS slips,
            (SELECT group_concat(CASE WHEN quantity > 1 THEN quantity || ' × ' || name ELSE name END, ', ')
             FROM (SELECT name, COUNT(*) AS quantity, MIN(id) AS first_id FROM items
                   WHERE booking_id=bookings.id GROUP BY name, kannada, kind, price ORDER BY first_id)) AS items_summary,
            EXISTS(SELECT 1 FROM print_jobs WHERE booking_id=bookings.id AND status='PENDING') AS print_pending
            FROM bookings''' + (' WHERE ' + ' AND '.join(where) if where else '') + ' ORDER BY id DESC LIMIT ? OFFSET ?'
        with self.connect() as db:
            rows = [dict(r) for r in db.execute(sql, args + [int(limit) + 1, int(offset)])]
        return rows[:limit], len(rows) > limit

    def unpaid_total(self):
        totals = defaultdict(int)
        with self.connect() as db:
            for r in db.execute("SELECT snapshot,total FROM bookings WHERE status='UNPAID' AND total>0"):
                totals[json.loads(r['snapshot'])['currency']] += r['total']
        return dict(totals)

    # --------------------------------------------------------- backup/restore
    @staticmethod
    def check_backup(path):
        try:
            source = sqlite3.connect(f'file:{Path(path).resolve().as_posix()}?mode=ro', uri=True)
            try:
                if source.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('The backup file is damaged.')
                tables = {r[0] for r in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not {'bookings', 'events', 'sevas', 'items'} <= tables:
                    raise ValueError('That file is not a DevSeva / Seva Desk backup.')
                return source.execute('SELECT COUNT(*) FROM bookings').fetchone()[0]
            finally:
                source.close()
        except sqlite3.DatabaseError:
            raise ValueError('That file is not a readable DevSeva backup.')

    def restore(self, source_path, safety_folder, actor=ADMIN):
        """Replace the live data with a backup. A safety copy of the current data is kept first."""
        if Path(source_path).resolve() == Path(self.path).resolve():
            raise ValueError('Choose a backup file, not the live database.')
        count = self.check_backup(source_path)
        safety = self.auto_backup(safety_folder, prefix='before-restore', keep=None)
        source = sqlite3.connect(f'file:{Path(source_path).resolve().as_posix()}?mode=ro', uri=True)
        try:
            with self.connect() as live:
                source.backup(live)
        finally:
            source.close()
        restored = Store(self.path)  # upgrade an older backup in place
        with restored.connect() as db:
            restored.log(db, actor, 'database restored', {'from': Path(source_path).name, 'bookings': count, 'safety_copy': safety.name})
        return safety

    def auto_backup(self, folder, prefix='auto', keep=10):
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().strftime('%Y%m%d-%H%M%S')
        dest = folder / f'devseva-{prefix}-{stamp}.sqlite3'
        n = 1
        while dest.exists():
            n += 1
            dest = folder / f'devseva-{prefix}-{stamp}-{n}.sqlite3'
        self.backup(dest)
        if keep:
            old = sorted(folder.glob(f'devseva-{prefix}-*.sqlite3'))
            for extra in old[:-keep]:
                try:
                    os.remove(extra)
                except OSError:
                    pass
        return dest

    # --------------------------------------------------- schedule and reports
    def schedule(self, day, event_id=None):
        """Every non-cancelled slip to be performed on a date, for the priest's sheet."""
        day = iso_date(day)
        with self.connect() as db:
            sql = '''SELECT items.*, items.gotra AS item_gotra, bookings.id AS booking, bookings.status, bookings.gotra, bookings.event_id,
                bookings.snapshot, bookings.devotee, bookings.devotee_kn, bookings.rashi AS b_rashi,
                bookings.nakshatra AS b_nakshatra, bookings.phone
                FROM items JOIN bookings ON bookings.id=items.booking_id
                WHERE bookings.service_date=? AND bookings.status NOT IN ('VOID','REFUNDED') '''
            args = [day]
            if event_id:
                sql += ' AND bookings.event_id=?'
                args.append(int(event_id))
            rows = []
            for r in db.execute(sql + ' ORDER BY items.name COLLATE NOCASE, bookings.id, items.id', args):
                r = dict(r)
                r['event'] = json.loads(r.pop('snapshot'))['name']
                if not r['person']:
                    r.update(person=r['devotee'], person_kn=r['devotee_kn'], rashi=r['b_rashi'], nakshatra=r['b_nakshatra'])
                r['gotra'] = r['item_gotra'] or r['gotra']
                rows.append(r)
            return rows

    def _lines(self, start, end, event_id=None):
        start, end = iso_date(start, 'From date'), iso_date(end, 'To date')
        if end < start:
            raise ValueError('The "to" date cannot be before the "from" date.')
        with self.connect() as db:
            sql = '''SELECT items.id AS item, items.name AS seva, items.kind, items.price, items.person,
                bookings.id AS booking, bookings.created, bookings.paid_at, bookings.service_date, bookings.status,
                bookings.payment_method, bookings.operator, bookings.paid_by, bookings.external_ref, bookings.devotee, bookings.snapshot, bookings.event_id
                FROM items JOIN bookings ON bookings.id=items.booking_id'''
            args = []
            if event_id:
                sql += ' WHERE bookings.event_id=?'
                args.append(int(event_id))
            lines = []
            for r in db.execute(sql + ' ORDER BY bookings.id, items.id', args):
                r = dict(r)
                event = json.loads(r.pop('snapshot'))
                r.update(event=event['name'], currency=event['currency'], booked_on=local_date(r['created']),
                         paid_on=local_date(r['paid_at']), person=r['person'] or r['devotee'])
                lines.append(r)
        return start, end, lines

    def report(self, start, end, event_id=None):
        """Collections are counted on the date cash was received; bookings on the date entered."""
        start, end, lines = self._lines(start, end, event_id)
        inside = lambda d: bool(d) and start <= d <= end
        rep = {'start': start, 'end': end, 'collected': defaultdict(int), 'by_method': defaultdict(int),
               'by_seva': defaultdict(lambda: [0, 0]), 'by_day': defaultdict(int), 'booked': defaultdict(lambda: [0, 0]),
               'outstanding': defaultdict(int), 'in_kind': 0,
               'refunded': defaultdict(int), 'refund_by_method': defaultdict(int), 'refund_list': [],
               'by_collector': defaultdict(int), 'bookings': set(), 'void': set(), 'performed': defaultdict(int)}
        for r in lines:
            cur = r['currency']
            if r['status'] in ('PAID', 'REFUNDED') and inside(r['paid_on']):
                rep['collected'][cur] += r['price']
                rep['by_method'][(cur, r['payment_method'])] += r['price']
                rep['by_seva'][(cur, r['seva'])][0] += 1
                rep['by_seva'][(cur, r['seva'])][1] += r['price']
                rep['by_day'][(cur, r['paid_on'])] += r['price']
                rep['by_collector'][(cur, r['paid_by'] or '', r['payment_method'])] += r['price']
            if inside(r['booked_on']):
                if r['status'] == 'VOID':
                    rep['void'].add(r['booking'])
                    continue
                rep['bookings'].add(r['booking'])
                rep['booked'][cur][0] += 1
                rep['booked'][cur][1] += r['price']
                if r['kind'] == 'In-kind':
                    rep['in_kind'] += 1
            if r['status'] not in ('VOID', 'REFUNDED') and inside(r['service_date']):
                rep['performed'][r['seva']] += 1
            if r['status'] == 'UNPAID' and r['booked_on'] <= end:
                rep['outstanding'][cur] += r['price']
        with self.connect() as db:
            sql = 'SELECT refunds.*, bookings.snapshot, bookings.event_id FROM refunds JOIN bookings ON bookings.id=refunds.booking_id'
            args = []
            if event_id:
                sql += ' WHERE bookings.event_id=?'
                args.append(int(event_id))
            for r in db.execute(sql, args):
                day = local_date(r['at'])
                if inside(day):
                    cur = json.loads(r['snapshot'])['currency']
                    rep['refunded'][cur] += r['amount']
                    rep['refund_by_method'][(cur, r['method'])] += r['amount']
                    rep['by_collector'][(cur, r['actor'], r['method'] + ' refund')] -= r['amount']
                    rep['refund_list'].append((day, r['booking_id'], cur, r['amount'], r['method'], r['reason'], r['actor']))
        rep['net'] = {cur: rep['collected'].get(cur, 0) - rep['refunded'].get(cur, 0)
                      for cur in set(rep['collected']) | set(rep['refunded'])}
        rep['bookings'], rep['void'] = len(rep['bookings']), len(rep['void'])
        return rep

    def export_lines(self, destination, start, end, event_id=None):
        start, end, lines = self._lines(start, end, event_id)
        with open(destination, 'w', newline='', encoding='utf-8-sig') as handle:
            writer = csv.writer(handle)
            writer.writerow(['Booking', 'Booking no.', 'Slip', 'Booked on', 'Pooja date', 'Paid on', 'Event', 'Seva', 'Type', 'Person',
                             'Currency', 'Amount', 'Status', 'Method', 'Operator', 'Payment recorded by'])
            for r in lines:
                if any(start <= d <= end for d in (r['booked_on'], r['paid_on'], r['service_date']) if d):
                    writer.writerow(safe_csv([r['booking'], r['external_ref'], r['item'], r['booked_on'], r['service_date'], r['paid_on'],
                                              r['event'], r['seva'], r['kind'], r['person'], r['currency'],
                                              f"{r['price'] / 100:.2f}", r['status'], r['payment_method'] or '', r['operator'], r['paid_by'] or '']))


def report_text(rep):
    out = [f"Period: {rep['start']} to {rep['end']}", '']
    out.append('CASH COLLECTED (by date payment was received)')
    if not rep['collected']:
        out.append('  No payments received in this period.')
    for cur, amount in sorted(rep['collected'].items()):
        out.append(f'  {cur} {fmt(amount)}')
        for (c, method), value in sorted(rep['by_method'].items()):
            if c == cur:
                out.append(f'      {method:<16} {fmt(value):>14}')
    if rep['refunded']:
        out += ['', 'REFUNDS (by date refunded)']
        for cur, amount in sorted(rep['refunded'].items()):
            out.append(f'  {cur} -{fmt(amount)}')
            for (c, method), value in sorted(rep['refund_by_method'].items()):
                if c == cur:
                    out.append(f'      {method:<16} {"-" + fmt(value):>14}')
        for day, bid, cur, amount, method, reason, actor in sorted(rep['refund_list']):
            out.append(f'  {day}  #{bid:06d}  {cur} {fmt(amount)}  {method}  {reason[:40]}  ({actor})')
        out += ['', 'NET COLLECTION (collected minus refunds)']
        for cur, value in sorted(rep['net'].items()):
            out.append(f'  {cur} {fmt(value)}')
    if rep.get('by_collector'):
        out += ['', 'CASH HANDOVER — by person who recorded the payment']
        for (cur, who, method), value in sorted(rep['by_collector'].items()):
            out.append(f'  {(who or "unknown")[:34]:<34} {method:<22} {cur} {fmt(value):>12}')
    out += ['', 'COLLECTED BY SEVA (gross)']
    for (cur, seva), (count, value) in sorted(rep['by_seva'].items()):
        out.append(f'  {seva[:34]:<34} {count:>4} × {cur} {fmt(value):>12}')
    out += ['', 'DAILY COLLECTIONS (gross)']
    for (cur, day), value in sorted(rep['by_day'].items(), key=lambda x: (x[0][1], x[0][0])):
        out.append(f'  {day}   {cur} {fmt(value):>12}')
    out += ['', 'BOOKINGS ENTERED IN PERIOD',
            f"  {rep['bookings']} bookings · {rep['void']} cancelled · {rep['in_kind']} in-kind slips"]
    for cur, (count, value) in sorted(rep['booked'].items()):
        out.append(f'  {cur}: {count} slips worth {fmt(value)}')
    out += ['', 'UNPAID BALANCE (all bookings entered up to the end date)']
    if not any(rep['outstanding'].values()):
        out.append('  Nothing outstanding.')
    for cur, value in sorted(rep['outstanding'].items()):
        if value:
            out.append(f'  {cur} {fmt(value)}')
    out += ['', 'SEVAS SCHEDULED IN PERIOD (by pooja date)']
    for seva, count in sorted(rep['performed'].items()):
        out.append(f'  {seva[:40]:<40} {count:>5}')
    out += ['', 'AED and INR are never converted or added together.']
    return '\n'.join(out)


PAGE_STYLE = """body{font:14px 'Noto Sans Kannada','Nirmala UI','Kannada Sangam MN',system-ui,sans-serif;margin:24px;color:#222}
h1{font-size:22px;margin:0}h2{font-size:17px;margin:22px 0 6px;border-bottom:2px solid #7a2e0e;color:#7a2e0e}
table{border-collapse:collapse;width:100%}th,td{border-bottom:1px solid #ccc;padding:5px 6px;text-align:left;vertical-align:top}
th{background:#f6eee4}td.n{text-align:right}pre{font:13px ui-monospace,Menlo,monospace;white-space:pre-wrap}
button{padding:10px 16px}@media print{nav{display:none}body{margin:8mm}}"""


def schedule_html(day, rows):
    e = html.escape
    groups = defaultdict(list)
    for r in rows:
        groups[(r['event'], r['name'], r['kannada'])].append(r)
    body = []
    for (event, name, kn), items in sorted(groups.items()):
        people = defaultdict(list)
        for r in items:
            people[(r['person'], r['person_kn'], r['gotra'], r['rashi'], r['nakshatra'], r['booking'], r['status'])].append(r)
        trs = ''.join(
            f"<tr><td>{i}</td><td><b>{e(person[0])}</b>{' × ' + str(len(person_rows)) if len(person_rows) > 1 else ''}<br><span lang='kn'>{e(person[1])}</span></td>"
            f"<td>{e(person[2])}</td><td>{e(person[3])}</td><td>{e(person[4])}</td>"
            f"<td>#{person[5]:06d}<br>{'Paid' if person[6] == 'PAID' else ''}</td></tr>"
            for i, (person, person_rows) in enumerate(sorted(people.items()), 1))
        body.append(f"<h2>{e(name)} <span lang='kn'>{e(kn)}</span> — {len(items)} slips</h2><small>{e(event)}</small>"
                    f"<table><tr><th>#</th><th>Name / ಹೆಸರು</th><th>Gotra / ಗೋತ್ರ</th><th>Rashi / ರಾಶಿ</th>"
                    f"<th>Nakshatra / ನಕ್ಷತ್ರ</th><th>Booking</th></tr>{trs}</table>")
    weekday = DAY_NAMES[dt.date.fromisoformat(day).weekday()]
    return (f"<!doctype html><html lang='en'><meta charset='utf-8'><title>{APP_NAME} schedule {day}</title><style>{PAGE_STYLE}</style>"
            f"<nav><button onclick='window.print()'>Print / ಮುದ್ರಿಸಿ</button></nav>"
            f"<h1>{APP_NAME} · Pooja schedule / ಪೂಜಾ ಪಟ್ಟಿ</h1><p><b>{day}</b> ({weekday}) · {len(rows)} sevas</p>"
            + (''.join(body) or '<p>No sevas booked for this date.</p>') + '</html>')


def report_html(rep, title='Collection report'):
    return (f"<!doctype html><html lang='en'><meta charset='utf-8'><title>{APP_NAME} {html.escape(title)}</title><style>{PAGE_STYLE}</style>"
            f"<nav><button onclick='window.print()'>Print</button></nav><h1>{APP_NAME} · {html.escape(title)}</h1>"
            f"<pre>{html.escape(report_text(rep))}</pre></html>")


def receipt(booking, width=80):
    if width not in (58, 80):
        raise ValueError('Paper width must be 58 or 80 mm.')
    e = html.escape
    event = booking['event']
    service = booking.get('service_date') or event['day']
    org = booking.get('org') or {}
    org_html = ''.join(f"<div class='org'>{e(org[k])}</div>" for k in ('org_name', 'org_name_kn') if org.get(k))
    header = (f"{org_html}<h2>{e(event['name'])}</h2><div lang='kn'>{e(event['kannada'])}</div>"
              f"<p>Pooja date / ದಿನಾಂಕ: <b>{e(service)}</b><br>{e(event['place'])}</p>")
    status = booking['status'] if booking['total'] else ('VOID' if booking['status'] == 'VOID' else 'IN-KIND / NO CASH DUE')
    status_html = f'<h2>{e(status)}</h2>' if status != 'UNPAID' else ''
    payment_html = f"<p>Payment: {e(booking['payment_method'])}</p>" if booking['status'] in ('PAID', 'REFUNDED') and booking.get('payment_method') else ''
    reprint = "<h3>REPRINT / ನಕಲು ಪ್ರತಿ</h3>" if booking.get('print_confirmed') else ''
    ref = f"<br>Booking no.: <b>{e(booking['external_ref'])}</b>" if booking.get('external_ref') else ''

    def person(name, kn, rashi, nakshatra, gotra):
        gotra_html = f"<br>Gotra / ಗೋತ್ರ: {e(gotra)}" if gotra else ''
        return (f"<p><b>{e(name)}</b><br><span lang='kn'>{e(kn)}</span>{gotra_html}<br>Rashi / ರಾಶಿ: {e(rashi)}"
                f"<br>Nakshatra / ನಕ್ಷತ್ರ: {e(nakshatra)}</p>")
    sections = []
    for item in booking['items']:
        who = person(item.get('person') or booking['devotee'], item.get('person_kn') or booking.get('devotee_kn', ''),
                     item.get('rashi') or booking['rashi'], item.get('nakshatra') or booking['nakshatra'],
                     item.get('gotra') or booking.get('gotra', ''))
        sections.append(f"<section>{header}<h3>Seva slip / ಸೇವಾ ಚೀಟಿ</h3>{reprint}<b>#{booking['id']:06d}-{item['id']:06d}</b>{ref}{status_html}{who}"
                        f"<h3>{e(item['name'])}</h3><div lang='kn'>{e(item['kannada'])}</div>"
                        f"<p>{e(item['kind'])} · {event['currency']} {item['price'] / 100:.2f}</p><p>{e(booking['note'])}</p></section>")

    # The cashier summary is intentionally consolidated: one booking can
    # contain many identical pooja slips (including one per family member),
    # while the individual slip sections above remain unchanged for printing.
    grouped = {}
    for item in booking['items']:
        key = (item['name'], item['kannada'], item['kind'], item['price'])
        if key not in grouped:
            grouped[key] = {'name': item['name'], 'kannada': item['kannada'],
                            'kind': item['kind'], 'price': item['price'], 'quantity': 0}
        grouped[key]['quantity'] += 1
    def row(x):
        quantity = f"{x['quantity']} × " if x['quantity'] > 1 else ''
        line_total = x['price'] * x['quantity'] / 100
        kind = f"<br><small>{e(x['kind'])}</small>" if x['kind'] != 'Seva' else ''
        return f"<tr><td><b>{quantity}{e(x['name'])}</b><br>{e(x['kannada'])}{kind}</td><td>{line_total:.2f}</td></tr>"
    rows = ''.join(row(x) for x in grouped.values())
    main = person(booking['devotee'], booking.get('devotee_kn', ''), booking['rashi'], booking['nakshatra'], booking.get('gotra', ''))
    refund_html = ''.join(f"<p>Refunded {event['currency']} {r['amount'] / 100:.2f} ({e(r['method'])}, {e(local_date(r['at']))}): {e(r['reason'])}</p>"
                          for r in booking.get('refunds', []))
    if booking.get('refunds'):
        refund_html += f"<p><b>Net paid: {event['currency']} {(booking['total'] - booking.get('refunded', 0)) / 100:.2f}</b></p>"
    sections.append(f"<section>{header}<h3>Cashier summary / ನಗದು ಸಾರಾಂಶ</h3>{reprint}<b>Booking #{booking['id']:06d}</b>{ref}{status_html}{main}"
                    f"<table>{rows}</table><h2>Total: {event['currency']} {booking['total'] / 100:.2f}</h2>{payment_html}{refund_html}"
                    f"<p>Entered by: {e(booking['operator'])}</p><p>{e(booking['note'])}</p>"
                    f"<p class='brand'>{APP_NAME} · {e(COPYRIGHT)}</p></section>")
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><title>{APP_NAME} — booking {booking['id']}</title>
    <style>body{{font:14px 'Noto Sans Kannada','Nirmala UI','Kannada Sangam MN',sans-serif;margin:16px;background:#eee}}
    section{{box-sizing:border-box;width:{width-8}mm;background:white;padding:3mm;margin:10px auto;overflow-wrap:anywhere;break-after:page}}
    h2{{font-size:18px}}h3{{font-size:15px}}.org{{font-size:12px;font-weight:600;text-align:center}}.brand{{font-size:9px;color:#555;text-align:center;margin-top:8px}}table{{width:100%;font-size:12px}}td{{border-bottom:1px dashed #888;padding:5px 0}}td:last-child{{text-align:right}}button{{padding:12px}}nav{{text-align:center}}
    @page{{size:{width}mm auto;margin:3mm}}@media print{{body{{background:white;margin:0}}nav{{display:none}}section{{margin:0;padding:0;box-shadow:none}}section:last-child{{break-after:auto}}}}</style>
    <nav><button onclick="window.print()">Print / ಮುದ್ರಿಸಿ</button><p>Select {width} mm paper in your printer settings. Disable browser headers and footers.</p></nav>{''.join(sections)}</html>"""
