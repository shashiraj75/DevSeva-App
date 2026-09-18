"""Seva Desk offline prototype. Money is stored in integer minor units."""
import csv
import datetime as dt
import html
import io
import json
import sqlite3
from decimal import Decimal, InvalidOperation
from kannada import normalize_label


def money(value):
    try:
        amount = Decimal(str(value))
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
            ''')
            # Additive migration: retain existing bookings and historical receipts.
            columns = {row['name'] for row in db.execute('PRAGMA table_info(bookings)')}
            if 'devotee_kn' not in columns:
                db.execute("ALTER TABLE bookings ADD COLUMN devotee_kn TEXT NOT NULL DEFAULT ''")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    def log(self, db, actor, action, detail):
        db.execute('INSERT INTO audit(at,actor,action,detail) VALUES(?,?,?,?)',
                   (dt.datetime.now(dt.timezone.utc).isoformat(), actor, action, json.dumps(detail, ensure_ascii=False)))

    def catalog(self):
        with self.connect() as db:
            return {table: [dict(r) for r in db.execute(f'SELECT * FROM {table} ORDER BY id')] for table in ('events', 'sevas')}

    def label_dictionary(self):
        with self.connect() as db:
            return dict(db.execute('SELECT english,kannada FROM kannada_labels').fetchall())

    def remember_label(self, db, english, kannada, previous):
        if kannada.strip() and (not previous or previous['kannada'] != kannada):
            db.execute('INSERT INTO kannada_labels(english,kannada) VALUES(?,?) ON CONFLICT(english) DO UPDATE SET kannada=excluded.kannada',
                       (normalize_label(english),kannada.strip()))
            self.log(db,'Laptop administrator','Kannada wording saved',{'english':english,'kannada':kannada})

    def event(self, values, ident=None):
        name = required(values['name'], 'Event name')
        day = required(values['day'], 'Date')
        dt.date.fromisoformat(day)
        currency = values['currency']
        if currency not in ('AED', 'INR'):
            raise ValueError('Choose AED or INR.')
        row = (name, str(values.get('kannada', ''))[:200], day, required(values['place'], 'Place'), currency)
        with self.connect() as db:
            previous=db.execute('SELECT kannada FROM events WHERE id=?',(ident,)).fetchone() if ident else None
            self.remember_label(db, name, row[1], previous)
            if ident:
                db.execute('UPDATE events SET name=?,kannada=?,day=?,place=?,currency=? WHERE id=?', (*row, ident))
            else:
                ident = db.execute('INSERT INTO events(name,kannada,day,place,currency) VALUES(?,?,?,?,?)', row).lastrowid
            self.log(db, 'Laptop administrator', 'event saved', {'id': ident, 'values': row})
        return ident

    def seva(self, values, ident=None):
        kind = values['kind']
        if kind not in ('Seva', 'Sponsorship', 'In-kind'):
            raise ValueError('Invalid contribution type.')
        price = money(values['price'])
        if kind == 'In-kind' and price:
            raise ValueError('In-kind contributions have zero cash amount. Describe goods in notes.')
        row = (int(values['event_id']), required(values['name'], 'Seva name'), str(values.get('kannada', ''))[:200], price, kind)
        with self.connect() as db:
            previous=db.execute('SELECT kannada FROM sevas WHERE id=?',(ident,)).fetchone() if ident else None
            self.remember_label(db, row[1], row[2], previous)
            if ident:
                db.execute('UPDATE sevas SET event_id=?,name=?,kannada=?,price=?,kind=? WHERE id=?', (*row, ident))
            else:
                ident = db.execute('INSERT INTO sevas(event_id,name,kannada,price,kind) VALUES(?,?,?,?,?)', row).lastrowid
            self.log(db, 'Laptop administrator', 'seva saved', {'id': ident, 'values': row})
        return ident

    def book(self, data, actor, allow_override=False):
        key = required(data.get('request_key'), 'Request ID', 100)
        payload = json.dumps(data, sort_keys=True, ensure_ascii=False)
        name = required(data.get('devotee'), 'Devotee name')
        event_id = int(data['event_id'])
        lines = data.get('items', [])
        if not lines or len(lines) > 100:
            raise ValueError('Add between 1 and 100 seva lines.')
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
            expanded = []
            for line in lines:
                seva = db.execute('SELECT * FROM sevas WHERE id=? AND event_id=?', (int(line['seva_id']), event_id)).fetchone()
                if not seva:
                    raise ValueError('Seva does not belong to this event.')
                qty = int(line['quantity'])
                if str(qty) != str(line['quantity']) or not 1 <= qty <= 100:
                    raise ValueError('Quantity must be a whole number from 1 to 100.')
                price = money(line.get('amount', str(Decimal(seva['price']) / 100)))
                if seva['kind'] == 'In-kind' and price:
                    raise ValueError('In-kind entries cannot include cash.')
                if seva['kind'] == 'Seva' and price != seva['price'] and not allow_override:
                    raise ValueError('Only the laptop administrator can override a fixed seva price.')
                expanded.extend([(seva['name'], seva['kannada'], seva['kind'], price)] * qty)
            if len(expanded) > 100:
                raise ValueError('Maximum 100 slips in one booking.')
            now = dt.datetime.now(dt.timezone.utc).isoformat()
            bid = db.execute('''INSERT INTO bookings(request_key,payload,event_id,created,operator,devotee,
                phone,rashi,nakshatra,note,snapshot,total) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                (key,payload,event_id,now,actor,name,str(data.get('phone',''))[:80],str(data.get('rashi',''))[:100],
                 str(data.get('nakshatra',''))[:100],str(data.get('note',''))[:1000],json.dumps(dict(event), ensure_ascii=False),
                 sum(x[3] for x in expanded))).lastrowid
            db.execute('UPDATE bookings SET devotee_kn=? WHERE id=?', (str(data.get('devotee_kn', ''))[:200], bid))
            db.executemany('INSERT INTO items(booking_id,name,kannada,kind,price) VALUES(?,?,?,?,?)', [(bid,*x) for x in expanded])
            db.execute('INSERT INTO print_jobs(booking_id) VALUES(?)', (bid,))
            self.log(db, actor, 'booking created', {'id':bid, 'slips':len(expanded)})
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
            return booking

    def pay(self, bid, actor, method='Cash'):
        if method not in ('Cash', 'Bank transfer', 'Card', 'UPI'):
            raise ValueError('Invalid payment method.')
        with self.connect() as db:
            row = db.execute('SELECT status,total FROM bookings WHERE id=?', (bid,)).fetchone()
            if not row or row['status'] != 'UNPAID':
                raise ValueError('Only unpaid bookings can be marked paid.')
            if row['total'] <= 0:
                raise ValueError('No cash is due on this booking. Use its in-kind acknowledgement.')
            changed = db.execute("UPDATE bookings SET status='PAID',payment_method=?,paid_at=?,paid_by=? WHERE id=? AND status='UNPAID'",
                (method,dt.datetime.now(dt.timezone.utc).isoformat(),actor,bid)).rowcount
            if changed != 1:
                raise ValueError('Payment was already recorded. Refresh the list.')
            self.log(db, actor, 'payment received', {'id':bid,'method':method,'amount':row['total']})

    def void(self, bid, reason):
        reason = required(reason, 'Cancellation reason', 500)
        with self.connect() as db:
            if db.execute("UPDATE bookings SET status='VOID',void_reason=? WHERE id=? AND status='UNPAID'", (reason,bid)).rowcount != 1:
                raise ValueError('Only unpaid bookings can be cancelled. Paid refunds are not implemented.')
            self.log(db,'Laptop administrator','booking voided',{'id':bid,'reason':reason})

    def queue(self):
        with self.connect() as db:
            return [dict(x) for x in db.execute("SELECT * FROM print_jobs WHERE status='PENDING' ORDER BY id")]

    def printed(self, bid):
        with self.connect() as db:
            db.execute("UPDATE print_jobs SET status='CONFIRMED' WHERE booking_id=?", (bid,))
            self.log(db,'Laptop administrator','print manually confirmed',{'id':bid})

    def backup(self, destination):
        with self.connect() as source, sqlite3.connect(str(destination)) as target:
            source.backup(target)

    def export(self, destination):
        with open(destination, 'w', newline='', encoding='utf-8-sig') as handle:
            writer = csv.writer(handle)
            writer.writerow(['Booking','Date UTC','Event','Currency','Devotee','Total','Status','Method','Operator'])
            for b in self.bookings():
                event = json.loads(b['snapshot'])
                row = [b['id'],b['created'],event['name'],event['currency'],b['devotee'],f"{b['total']/100:.2f}",b['status'],b['payment_method'] or '',b['operator']]
                writer.writerow([("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r','\n')) else v) for v in row])


def receipt(booking, width=80):
    if width not in (58, 80):
        raise ValueError('Paper width must be 58 or 80 mm.')
    e = html.escape
    event = booking['event']
    header = f"<h2>{e(event['name'])}</h2><div lang='kn'>{e(event['kannada'])}</div><p>{e(event['day'])} · {e(event['place'])}</p>"
    status = booking['status'] if booking['total'] else ('VOID' if booking['status']=='VOID' else 'IN-KIND / NO CASH DUE')
    status_html = f'<h2>{e(status)}</h2>' if status != 'UNPAID' else ''
    payment_html = f"<p>Payment: {e(booking['payment_method'])}</p>" if booking['status'] == 'PAID' and booking.get('payment_method') else ''
    common = f"<p><b>{e(booking['devotee'])}</b><br><span lang='kn'>{e(booking.get('devotee_kn', ''))}</span><br>Rashi / ರಾಶಿ: {e(booking['rashi'])}<br>Nakshatra / ನಕ್ಷತ್ರ: {e(booking['nakshatra'])}</p>"
    sections = []
    for item in booking['items']:
        sections.append(f"<section>{header}<h3>Seva slip / ಸೇವಾ ಚೀಟಿ</h3><b>#{booking['id']:06d}-{item['id']:06d}</b>{status_html}{common}<h3>{e(item['name'])}</h3><div lang='kn'>{e(item['kannada'])}</div><p>{e(item['kind'])} · {event['currency']} {item['price']/100:.2f}</p><p>{e(booking['note'])}</p></section>")
    rows = ''.join(f"<tr><td>{e(x['name'])}<br>{e(x['kannada'])}</td><td>{x['price']/100:.2f}</td></tr>" for x in booking['items'])
    sections.append(f"<section>{header}<h3>Cashier summary / ನಗದು ಸಾರಾಂಶ</h3><b>Booking #{booking['id']:06d}</b>{status_html}{common}<table>{rows}</table><h2>Total: {event['currency']} {booking['total']/100:.2f}</h2>{payment_html}<p>Entered by: {e(booking['operator'])}</p><p>{e(booking['note'])}</p></section>")
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><title>Seva Desk — booking {booking['id']}</title>
    <style>body{{font:14px 'Noto Sans Kannada','Nirmala UI','Kannada Sangam MN',sans-serif;margin:16px;background:#eee}}
    section{{box-sizing:border-box;width:{width-8}mm;background:white;padding:3mm;margin:10px auto;overflow-wrap:anywhere;break-after:page}}
    h2{{font-size:18px}}h3{{font-size:15px}}table{{width:100%;font-size:12px}}td{{border-bottom:1px dashed #888;padding:5px 0}}td:last-child{{text-align:right}}button{{padding:12px}}nav{{text-align:center}}
    @page{{size:{width}mm auto;margin:3mm}}@media print{{body{{background:white;margin:0}}nav{{display:none}}section{{margin:0;padding:0;box-shadow:none}}section:last-child{{break-after:auto}}}}</style>
    <nav><button onclick="window.print()">Print / ಮುದ್ರಿಸಿ</button><p>Select {width} mm paper in your printer settings. Disable browser headers and footers.</p></nav>{''.join(sections)}</html>"""
