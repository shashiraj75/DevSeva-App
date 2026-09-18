# DevSeva — © 2026 Raviraj Shetty. All rights reserved.
"""DevSeva booking importer: Excel (.xlsx), CSV and pasted text (WhatsApp, PDF, photo text).

Standard library only, fully offline. The flow is:
    rows = read_table(path) or parse_text(text)        -> list of {field: value}
    plan = plan_rows(rows, sevas, options, known_refs) -> list of ImportRow (preview)
    Store.import_rows(event_id, plan, actor)           -> bookings
Nothing is written to the database until the operator confirms the preview.
"""
import csv
import hashlib
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

FIELDS = ('ref', 'name', 'name_kn', 'phone', 'email', 'amount', 'sevas', 'quantity', 'paid', 'method', 'gotra',
          'rashi', 'nakshatra', 'note')
FIELD_LABELS = {
    'ref': 'Booking number', 'name': 'Devotee name', 'name_kn': 'Kannada name', 'phone': 'Phone', 'email': 'Email',
    'amount': 'Total amount', 'sevas': 'Pooja / seva / sponsorship', 'quantity': 'Quantity', 'paid': 'Payment status',
    'method': 'Payment method', 'gotra': 'Gotra', 'rashi': 'Rashi', 'nakshatra': 'Nakshatra', 'note': 'Notes',
}
# Header words that identify each field (checked in this order, most specific first).
HEADER_HINTS = [
    ('email', ('email', 'e-mail', 'mail id', 'mail')),
    ('name_kn', ('kannada',)),
    ('ref', ('booking no', 'booking number', 'booking id', 'booking ref', 'booking #', 'bookingno', 'ref no', 'reference',
             'receipt no', 'receipt number', 'order no', 'order id', 'token', 'ref')),
    ('phone', ('phone', 'mobile', 'contact', 'whatsapp', 'cell', 'tel')),
    ('method', ('payment method', 'payment mode', 'mode of payment', 'paid by', 'paid via', 'method', 'mode')),
    ('paid', ('payment status', 'paid?', 'paid', 'payment', 'status', 'received')),
    ('quantity', ('quantity', 'qty', 'no. of', 'number of', 'count', 'nos')),
    ('amount', ('total amount', 'amount', 'total', 'aed', 'inr', 'rs', 'price', 'fee', 'contribution', 'donation')),
    ('sevas', ('seva', 'pooja', 'puja', 'sponsor', 'item', 'booking for', 'category', 'type', 'offering', 'particular')),
    ('gotra', ('gotra', 'gothra')),
    ('rashi', ('rashi', 'raashi', 'rasi')),
    ('nakshatra', ('nakshatra', 'nakshathra', 'star')),
    ('name', ('devotee', 'full name', 'name', 'family')),
    ('note', ('note', 'remark', 'comment', 'address', 'message')),
]
PAID_WORDS = ('paid', 'yes', 'y', 'received', 'done', 'complete', 'completed', 'confirmed', 'true', '1', '✓', '✔', 'ok',
              'transferred', 'credited', 'settled')
UNPAID_WORDS = ('unpaid', 'no', 'n', 'pending', 'due', 'not paid', 'false', '0', 'to pay', 'cash on day', 'pay at venue',
                'awaiting', 'not received')
METHOD_WORDS = [
    ('UPI', ('upi', 'gpay', 'google pay', 'phonepe', 'paytm', 'bhim')),
    ('Card', ('card', 'visa', 'master', 'amex', 'pos', 'debit', 'credit')),
    ('Bank transfer', ('bank', 'transfer', 'neft', 'imps', 'rtgs', 'wire', 'online', 'deposit', 'iban', 'cheque', 'check')),
    ('Cash', ('cash',)),
]
STOPWORDS = {'sri', 'shri', 'shree', 'seva', 'seve', 'booking', 'the', 'and', 'for', 'of', 'a', 'sponsorship', 'sponsor',
             'contribution', 'donation', 'x', 'nos', 'no', 'qty'}

EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+')
PHONE_RE = re.compile(r'(?<![\w/])(?:\+|00)?\d[\d\s().-]{7,17}\d(?![\w/])')
AMOUNT_BEFORE_RE = re.compile(r'(?:\baed|\bdhs?|\bdirhams?|\binr|\brs\.?|₹)\s*([0-9][0-9,]*(?:\.\d{1,2})?)', re.I)
AMOUNT_AFTER_RE = re.compile(r'\b([0-9][0-9,]*(?:\.\d{1,2})?)\s*(?:/-\s*)?(?:aed|dhs?|dirhams?|inr|rs\.?|rupees|₹)(?!\w)', re.I)


class _AmountRE:
    """Prefer "AED 50" over "50 AED", so the end of a phone number before "AED 50" is never read as the amount."""
    def search(self, text):
        return AMOUNT_BEFORE_RE.search(text) or AMOUNT_AFTER_RE.search(text)

    def sub(self, repl, text):
        return AMOUNT_AFTER_RE.sub(repl, AMOUNT_BEFORE_RE.sub(repl, text))


AMOUNT_RE = _AmountRE()
NAME_STOP = {'pooja', 'puja', 'seva', 'booking', 'book', 'paid', 'aed', 'rs', 'inr', 'dhs', 'amount', 'please', 'for', 'hi',
             'hello', 'namaskara', 'namaste', 'thanks', 'thank', 'you', 'total', 'cash', 'bank', 'transfer', 'upi', 'card',
             'satyanarayana', 'sri', 'shri', 'flowers', 'fruits', 'prasada', 'maha', 'consumables', 'receipt', 'mobile',
             'phone', 'email', 'will', 'pay', 'on', 'the', 'day', 'ref', 'no', 'and', 'x', 'nos', 'family', 'families',
             'via', 'by', 'gpay', 'phonepe', 'transferred', 'sent', 'done'}
LABEL_RE = re.compile(r'^\s*([A-Za-z][A-Za-z .#/()-]{1,30}?)\s*[:=\-–]\s*(.+?)\s*$')
REF_RE = re.compile(r'\b(?:booking|bkg|ref(?:erence)?|receipt|order|token)\s*(?:no\.?|number|num|id|#)?\s*[:#.\-]?\s*'
                    r'#?\s*([A-Za-z]{0,6}[-/]?\d[\w/-]{0,19})', re.I)
WA_LINE_RE = re.compile(r'^\[?(\d{1,4}[./-]\d{1,2}[./-]\d{1,4}),?\s+(\d{1,2}[:.]\d{2}(?:[:.]\d{2})?\s*(?:[APap]\.?[Mm]\.?)?)\]?\s*[-–]?\s*([^:]{1,60}):\s*(.*)$')


# ------------------------------------------------------------ reading files
def read_table(path, sheet=None):
    """Returns (headers, rows as lists, sheet_names). Supports .xlsx, .xlsm, .csv, .tsv, .txt."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in ('.xlsx', '.xlsm'):
        sheets = read_xlsx(path)
        if not sheets:
            raise ValueError('The Excel file has no sheets.')
        names = list(sheets)
        chosen = sheet if sheet in sheets else max(names, key=lambda n: len(sheets[n]))
        table = sheets[chosen]
    elif suffix == '.xls':
        raise ValueError('Old .xls files are not supported. In Excel or Numbers choose File > Save As / Export > '
                         '"Excel Workbook (.xlsx)" or CSV, then import that file.')
    elif suffix == '.numbers':
        raise ValueError('Numbers files are not supported directly. In Numbers choose File > Export To > Excel or CSV.')
    elif suffix in ('.csv', '.tsv', '.txt'):
        table = read_csv_bytes(path.read_bytes())
        names, chosen = [], None
    else:
        raise ValueError('Choose an Excel (.xlsx) or CSV file. For WhatsApp, PDF or photos use "Paste text".')
    table = [[_cell_text(c) for c in row] for row in table]
    table = [row for row in table if any(c.strip() for c in row)]
    if not table:
        raise ValueError('No rows were found in the file.')
    header_index = _find_header(table)
    headers = [h.strip() or f'Column {i + 1}' for i, h in enumerate(table[header_index])]
    width = max(len(r) for r in table)
    headers += [f'Column {i + 1}' for i in range(len(headers), width)]
    rows = [row + [''] * (width - len(row)) for row in table[header_index + 1:]]
    return headers, rows, names, chosen


def _find_header(table):
    best, best_score = 0, -1
    for i, row in enumerate(table[:10]):
        score = sum(1 for c in row if guess_field(c))
        if score > best_score:
            best, best_score = i, score
    return best


def _cell_text(value):
    if value is None:
        return ''
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else f'{value:.2f}'.rstrip('0').rstrip('.')
    return str(value).strip()


def read_csv_bytes(data):
    encodings = ('utf-16',) if data[:2] in (b'\xff\xfe', b'\xfe\xff') else ('utf-8-sig', 'cp1252', 'latin-1')
    text = ''
    for encoding in encodings:
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=',;\t|')
    except csv.Error:
        dialect = csv.excel_tab if sample.count('\t') > sample.count(',') else csv.excel
    return [row for row in csv.reader(io.StringIO(text), dialect)]


NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
      'rel': 'http://schemas.openxmlformats.org/package/2006/relationships'}


def read_xlsx(path):
    """Minimal .xlsx reader: {sheet name: [[cell values]]} with shared/inline strings and numbers."""
    try:
        book = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        raise ValueError('This file is not a valid .xlsx workbook (it may be password-protected or an old .xls).')
    with book:
        names = set(book.namelist())
        shared = []
        if 'xl/sharedStrings.xml' in names:
            for si in ET.fromstring(book.read('xl/sharedStrings.xml')).findall('m:si', NS):
                shared.append(''.join(t.text or '' for t in si.iter(f"{{{NS['m']}}}t")))
        workbook = ET.fromstring(book.read('xl/workbook.xml'))
        rels = ET.fromstring(book.read('xl/_rels/workbook.xml.rels'))
        targets = {r.get('Id'): r.get('Target') for r in rels.findall('rel:Relationship', NS)}
        sheets = {}
        for sheet in workbook.find('m:sheets', NS).findall('m:sheet', NS):
            if sheet.get('state') in ('hidden', 'veryHidden'):
                continue
            target = targets.get(sheet.get(f"{{{NS['r']}}}id"), '')
            target = target.lstrip('/')
            part = target if target.startswith('xl/') else 'xl/' + target
            if part not in names:
                continue
            rows = []
            root = ET.fromstring(book.read(part))
            for row in root.iter(f"{{{NS['m']}}}row"):
                values = {}
                for cell in row.findall('m:c', NS):
                    col = _column_index(cell.get('r', '')) if cell.get('r') else len(values)
                    kind = cell.get('t')
                    v = cell.find('m:v', NS)
                    if kind == 's' and v is not None:
                        value = shared[int(v.text)]
                    elif kind == 'inlineStr':
                        value = ''.join(t.text or '' for t in cell.iter(f"{{{NS['m']}}}t"))
                    elif kind in ('str', 'e') and v is not None:
                        value = v.text or ''
                    elif kind == 'b' and v is not None:
                        value = 'TRUE' if v.text == '1' else 'FALSE'
                    elif v is not None and v.text is not None:
                        try:
                            value = float(v.text)
                        except ValueError:
                            value = v.text
                    else:
                        value = ''
                    values[col] = value
                if values:
                    width = max(values) + 1
                    rows.append([values.get(i, '') for i in range(width)])
            sheets[sheet.get('name')] = rows
        return sheets


def _column_index(ref):
    letters = ''.join(ch for ch in ref if ch.isalpha()).upper()
    index = 0
    for ch in letters:
        index = index * 26 + (ord(ch) - 64)
    return index - 1


# ----------------------------------------------------------- column guesses
def _norm(text):
    return ' '.join(re.sub(r'[^\w#?]+', ' ', str(text).casefold()).split())


def guess_field(header):
    h = _norm(header)
    if not h:
        return None
    for name, hints in HEADER_HINTS:
        for hint in hints:
            hint_n = _norm(hint)
            if h == hint_n or re.search(r'(^|\s)' + re.escape(hint_n) + r'($|\s)', h):
                return name
    return None


def guess_mapping(headers):
    """{field: column index}; each column used once, first match wins."""
    mapping = {}
    for i, header in enumerate(headers):
        name = guess_field(header)
        if name and name not in mapping:
            mapping[name] = i
    # Serial-number columns ("Sl No") are deliberately NOT used as booking numbers:
    # another list may reuse 1, 2, 3..., which would look like duplicates.
    return mapping


def rows_from_table(headers, rows, mapping):
    out = []
    for n, row in enumerate(rows, 1):
        record = {name: (row[i].strip() if i is not None and i < len(row) else '') for name, i in mapping.items()}
        record['_source'] = f'Row {n + 1}: ' + ' | '.join(f'{h}={v}' for h, v in zip(headers, row) if str(v).strip())[:400]
        out.append(record)
    return out


# -------------------------------------------------------------- pasted text
def parse_text(text):
    """Extract booking records from WhatsApp messages, PDF text or text copied from photos."""
    text = str(text or '').replace('\r\n', '\n').replace('‎', '').replace(' ', ' ')
    records = []
    lines = text.split('\n')
    if sum(1 for line in lines if WA_LINE_RE.match(line)) >= 1:
        current = None
        for line in lines:
            m = WA_LINE_RE.match(line)
            if m:
                if current:
                    records.append(current)
                current = {'sender': m.group(3).strip(), 'body': [m.group(4)]}
            elif current is not None:
                current['body'].append(line)
        if current:
            records.append(current)
        blocks = [(r['sender'], '\n'.join(r['body'])) for r in records]
    else:
        chunks = [c for c in re.split(r'\n\s*\n', text) if c.strip()]
        if len(chunks) == 1:
            single = [line for line in chunks[0].split('\n') if line.strip()]
            labelled = sum(1 for line in single if LABEL_RE.match(line))
            if labelled < 2 and sum(1 for line in single if PHONE_RE.search(line) or AMOUNT_RE.search(line)) > 1:
                chunks = single  # one booking per line (e.g. a pasted list)
        blocks = [('', c) for c in chunks]
    out = []
    for sender, body in blocks:
        record = extract_record(body, sender)
        if record:
            out.append(record)
    return out


LABELS = {
    'name': ('name', 'devotee', 'devotee name', 'full name', 'naam'),
    'phone': ('phone', 'mobile', 'mob', 'contact', 'whatsapp', 'ph', 'tel', 'cell'),
    'email': ('email', 'e-mail', 'mail'),
    'ref': ('booking', 'booking no', 'booking number', 'booking id', 'ref', 'ref no', 'reference', 'receipt',
            'receipt no', 'order', 'order no', 'token', 'token no'),
    'amount': ('amount', 'total', 'total amount', 'amt', 'paid amount', 'fee'),
    'sevas': ('seva', 'sevas', 'pooja', 'puja', 'booking for', 'sponsorship', 'sponsor', 'item', 'items', 'offering'),
    'quantity': ('qty', 'quantity', 'no of poojas', 'number of poojas', 'poojas', 'count'),
    'paid': ('paid', 'payment', 'payment status', 'status'),
    'method': ('mode', 'payment mode', 'method', 'paid by', 'paid via'),
    'gotra': ('gotra', 'gothra'),
    'rashi': ('rashi', 'rasi'),
    'nakshatra': ('nakshatra', 'star'),
    'note': ('note', 'notes', 'remarks', 'address'),
}


def extract_record(body, sender=''):
    record = {k: '' for k in FIELDS}
    rest = []
    for line in body.split('\n'):
        m = LABEL_RE.match(line)
        key = _norm(m.group(1)) if m else ''
        target = next((f for f, words in LABELS.items() if key in words), None) if m else None
        if target and not record[target]:
            record[target] = m.group(2).strip()
        else:
            rest.append(line)
    loose = '\n'.join(rest)
    whole = body
    if not record['email']:
        m = EMAIL_RE.search(whole)
        record['email'] = m.group(0) if m else ''
    if not record['ref']:
        m = REF_RE.search(whole)
        record['ref'] = m.group(1) if m else ''
    if not record['amount']:
        m = AMOUNT_RE.search(loose)
        if m:
            record['amount'] = m.group(1)
    if not record['phone']:
        cleaned = EMAIL_RE.sub(' ', loose)
        if record['ref']:
            cleaned = cleaned.replace(record['ref'], ' ')
        for m in PHONE_RE.finditer(cleaned):
            digits = re.sub(r'\D', '', m.group(0))
            if 9 <= len(digits) <= 15:
                record['phone'] = m.group(0).strip()
                break
    lower = whole.casefold()
    if not record['paid']:
        if re.search(r'\b(not paid|unpaid|will pay|pay (?:at|on) (?:the )?(?:venue|day|event)|pending)\b', lower):
            record['paid'] = 'unpaid'
        elif re.search(r'\b(paid|transferred|payment done|sent the amount|amount sent|credited)\b', lower):
            record['paid'] = 'paid'
    if not record['method']:
        record['method'] = next((method for method, words in METHOD_WORDS
                                 if any(re.search(r'\b' + re.escape(w) + r'\b', lower) for w in words)), '') if record['paid'] == 'paid' else ''
    if not record['quantity']:
        m = re.search(r'\b(\d{1,2})\s*(?:x\s*)?(?:nos?\.?\s*)?(?:poojas?|pujas?|bookings?|families|family|persons?|people)\b', lower)
        if m:
            record['quantity'] = m.group(1)
    if not record['sevas']:
        record['sevas'] = loose  # matched against the event's sevas later
        record['_sevas_from_text'] = True
    if not record['name']:
        candidates = []
        for line in rest:
            plain = AMOUNT_RE.sub(' ', EMAIL_RE.sub(' ', line))
            plain = PHONE_RE.sub(' ', REF_RE.sub(' ', plain))
            words = re.sub(r'[^A-Za-z\u0c80-\u0cff.]', ' ', plain).split()
            words = [w.strip('.') for w in words if w.strip('.') and w.strip('.').casefold() not in NAME_STOP]
            if 2 <= len(words) <= 4 and all(w[0].isupper() or not w[0].isascii() for w in words):
                candidates.append(' '.join(words))
        sender_is_name = sender and not re.fullmatch(r'[\d\s+().-]+', sender) and sender.casefold() not in ('you', 'me')
        for_name = re.search(r'\b(?:for|name is|this is|from)\s+((?:(?:Mr|Mrs|Ms|Dr|Smt|Sri|Shri)\.?\s+)?[A-Z][a-z]+(?:\s+[A-Z][a-z.]+){1,3})', loose)
        if for_name and not _tokens(for_name.group(1)) & {'satyanarayana', 'pooja', 'puja', 'prasada', 'flowers', 'fruits'}:
            record['name'] = for_name.group(1).strip()
        elif candidates:
            record['name'] = candidates[0]
        elif sender_is_name:
            record['name'] = sender
    if not record['phone'] and sender and re.fullmatch(r'[\d\s+().-]{9,}', sender):
        record['phone'] = sender.strip()
    if not any(record[k] for k in ('name', 'phone', 'email', 'ref', 'amount')):
        return None
    record['_source'] = (f'{sender}: ' if sender else '') + ' '.join(body.split())[:400]
    record['_from_text'] = True
    return record


# ------------------------------------------------------------------ planning
@dataclass
class ImportRow:
    number: int
    ref: str = ''
    name: str = ''
    name_kn: str = ''
    phone: str = ''
    email: str = ''
    amount: str = ''
    sevas_text: str = ''
    quantity: str = ''
    paid: bool = False
    method: str = ''
    gotra: str = ''
    rashi: str = ''
    nakshatra: str = ''
    note: str = ''
    source: str = ''
    from_text: bool = False
    items: list = field(default_factory=list)   # [{'seva_id', 'quantity', 'amount', 'label'}]
    total: int = 0
    status: str = 'Ready'                        # Ready | Check | Duplicate | Update | Skip | Imported | Error
    problem: str = ''
    existing_id: int = None
    include: bool = True
    blocking: bool = False                       # a real problem (not just "read from text") that must be fixed

    def summary(self):
        return '; '.join(f"{l['quantity']}× {l['label']}" + (f" @ {int(Decimal(l['amount'])):,}" if l['kind'] != 'Seva' else '')
                         for l in self.items)


def to_minor(text):
    text = str(text or '').strip()
    if not text:
        return None
    m = re.search(r'-?[0-9][0-9,]*(?:\.\d+)?', text.replace(' ', ''))
    if not m:
        return None
    try:
        value = Decimal(m.group(0).replace(',', ''))
    except InvalidOperation:
        return None
    if value < 0:
        return None
    return int((value * 100).quantize(Decimal('1')))


def paid_state(text, total=None):
    """True / False / None (unclear)."""
    raw = str(text or '').strip()
    if raw in ('✓', '✔', '✅', '☑'):
        return True
    if raw in ('✗', '✘', '❌', '-', '—'):
        return False
    t = _norm(text)
    if not t:
        return False
    number = to_minor(t) if re.fullmatch(r'[0-9.,]+', t.replace(' ', '')) else None
    if number is not None and t not in ('0', '1'):
        if total is None:
            return None
        return True if number >= total and total > 0 else (False if number == 0 else None)
    if t in UNPAID_WORDS or any(t.startswith(w) for w in ('not ', 'un', 'pending', 'due')):
        return False
    if t in PAID_WORDS or any(w in t.split() for w in ('paid', 'received', 'transferred')):
        return True
    return None


def payment_method(text, default):
    t = str(text or '').casefold()
    for method, words in METHOD_WORDS:
        if any(re.search(r'\b' + re.escape(w) + r'\b', t) for w in words):
            return method
    return default


def _tokens(text):
    return {w for w in re.findall(r'[a-zಀ-೿]+', str(text).casefold()) if w not in STOPWORDS and len(w) > 1}


def match_sevas(text, sevas):
    """Find sevas mentioned in free text. Returns [(seva, quantity or None, amount or None)]."""
    found = []
    parts = [p for p in re.split(r'[,;+\n&]|\band\b', str(text or ''), flags=re.I) if p.strip()]
    for part in parts:
        p_tokens = _tokens(part)
        if not p_tokens:
            continue
        scored = []
        for s in sevas:
            s_tokens = _tokens(s['name']) | _tokens(s.get('kannada', ''))
            common = p_tokens & s_tokens
            if common:
                scored.append((len(common) / len(s_tokens or {1}), -len(s_tokens), s))
            elif s['name'].casefold() in part.casefold():
                scored.append((1, 0, s))
        if not scored:
            continue
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        if len(scored) > 1 and scored[0][:2] == scored[1][:2]:
            continue  # ambiguous part, leave for review
        seva = scored[0][2]
        qm = re.search(r'(?:\b(\d{1,3})\s*(?:x|×|nos?\.?|\*)\s*\w)|(?:(?:x|×|\*)\s*(\d{1,3})\b)|\((\d{1,3})\)|(?:\bqty\s*[:=]?\s*(\d{1,3}))', part, re.I)
        qty = int(next(g for g in qm.groups() if g)) if qm else None
        am = AMOUNT_RE.search(part)
        amount = to_minor(am.group(1)) if am else None
        if any(f[0]['id'] == seva['id'] for f in found):
            continue
        found.append((seva, qty, amount))
    return found


def plan_rows(records, sevas, default_seva_id=None, default_method='Bank transfer', known=None, start=1):
    """Turn raw records into ImportRow previews.

    sevas: active sevas of the chosen event (dicts with id, name, kannada, price, kind).
    known: {normalised ref: {'id', 'status', 'total'}} for bookings already in DevSeva.
    """
    known = known or {}
    by_id = {s['id']: s for s in sevas}
    plans, seen = [], set()
    for n, rec in enumerate(records, start):
        row = ImportRow(number=n, ref=str(rec.get('ref', '')).strip()[:40], name=' '.join(str(rec.get('name', '')).split())[:200],
                        name_kn=str(rec.get('name_kn', '')).strip()[:200], phone=tidy_phone(rec.get('phone', '')),
                        email=str(rec.get('email', '')).strip()[:120], amount=str(rec.get('amount', '')).strip(),
                        sevas_text=str(rec.get('sevas', '')).strip(), quantity=str(rec.get('quantity', '')).strip(),
                        gotra=str(rec.get('gotra', '')).strip()[:100], rashi=str(rec.get('rashi', '')).strip()[:100],
                        nakshatra=str(rec.get('nakshatra', '')).strip()[:100], note=str(rec.get('note', '')).strip()[:1000],
                        source=rec.get('_source', ''), from_text=bool(rec.get('_from_text')))
        paid_text = rec.get('paid', '')
        method_text = rec.get('method', '') or paid_text
        if rec.get('_removed'):
            row.status, row.problem, row.include, row.blocking = 'Skip', 'Removed from this import.', False, True
            plans.append(row)
            continue
        plan_one(row, by_id, default_seva_id, paid_text, method_text, default_method, rec.get('_sevas_from_text'))
        key = normal_ref(row.ref) if row.ref else fingerprint(row)
        if key in seen and row.status not in ('Error',):
            row.status, row.problem, row.include = 'Skip', 'Same booking appears earlier in this file.', False
        seen.add(key)
        existing = known.get(key)
        if existing and row.status != 'Skip':
            row.existing_id = existing['id']
            if row.paid and existing['status'] == 'UNPAID':
                row.status, row.problem = 'Update', f"Already imported as #{existing['id']:06d} (unpaid); file says paid — will mark it paid."
            else:
                row.status, row.include = 'Duplicate', False
                row.problem = f"Already in DevSeva as #{existing['id']:06d} ({existing['status']}). Not imported again."
        plans.append(row)
    return plans


def tidy_phone(value):
    text = str(value or '').strip()[:80]
    digits = re.sub(r'\D', '', text)
    if text == digits and len(digits) >= 11 and digits.startswith(('971', '91', '966', '974', '968', '965', '973', '44', '1')):
        return '+' + digits  # Excel stored the number without its "+"
    return text


def normal_ref(ref):
    return re.sub(r'[^0-9a-z]', '', str(ref).casefold())


def fingerprint(row):
    digits = re.sub(r'\D', '', row.phone)[-8:]
    base = '|'.join((_norm(row.name), digits, row.email.casefold(), str(to_minor(row.amount) or '')))
    return 'auto-' + hashlib.sha1(base.encode()).hexdigest()[:12]


def plan_one(row, by_id, default_seva_id, paid_text, method_text, default_method, sevas_from_text=False):
    """(Re)compute items, total, status and problem for one row."""
    row.items, row.total, row.problem, row.status, row.include, row.blocking = [], 0, '', 'Ready', True, False
    problems = []
    if not row.name:
        problems.append('No devotee name.')
    amount = to_minor(row.amount)
    qty_hint = None
    if row.quantity:
        try:
            qty_hint = int(Decimal(row.quantity))
            if not 1 <= qty_hint <= 100:
                raise ValueError
        except (InvalidOperation, ValueError):
            problems.append('Quantity is not a whole number from 1 to 100.')
            qty_hint = None
    matches = match_sevas(row.sevas_text, list(by_id.values())) if row.sevas_text else []
    if not matches:
        if row.sevas_text and not sevas_from_text:
            problems.append(f'"{row.sevas_text[:40]}" does not match a seva of this event.')
        if default_seva_id in by_id:
            matches = [(by_id[default_seva_id], None, None)]
        else:
            problems.append('Choose which seva these bookings are for.')
    fixed = [(s, q, a) for s, q, a in matches if s['kind'] == 'Seva']
    variable = [(s, q, a) for s, q, a in matches if s['kind'] != 'Seva']
    lines = []
    fixed_total = 0
    for s, q, a in fixed:
        if q is None and len(matches) == 1:
            if qty_hint:
                q = qty_hint
            elif amount and s['price'] and amount % s['price'] == 0:
                q = amount // s['price']
            elif amount is None or amount == s['price']:
                q = 1
            else:
                problems.append(f"Amount {amount / 100:,.2f} is not a whole number of {s['name']} at {s['price'] / 100:,.2f}.")
                q = 1
        q = q or 1
        if not 1 <= q <= 100:
            problems.append('Too many slips for one booking (maximum 100).')
            q = min(max(q, 1), 100)
        lines.append({'seva_id': s['id'], 'quantity': q, 'amount': f"{s['price'] / 100:.2f}", 'label': s['name'], 'kind': 'Seva'})
        fixed_total += q * s['price']
    remainder = None if amount is None else amount - fixed_total
    stated = [(s, q, a) for s, q, a in variable if a is not None or s['kind'] == 'In-kind']
    open_ = [(s, q, a) for s, q, a in variable if a is None and s['kind'] != 'In-kind']
    for s, q, a in stated:
        value = 0 if s['kind'] == 'In-kind' else a
        lines.append({'seva_id': s['id'], 'quantity': 1, 'amount': f'{value / 100:.2f}', 'label': s['name'], 'kind': s['kind']})
        if remainder is not None:
            remainder -= value
    if open_:
        if len(open_) == 1 and remainder is not None and remainder >= 0:
            s = open_[0][0]
            lines.append({'seva_id': s['id'], 'quantity': 1, 'amount': f'{remainder / 100:.2f}', 'label': s['name'], 'kind': s['kind']})
            remainder = 0
        else:
            for s, q, a in open_:
                lines.append({'seva_id': s['id'], 'quantity': 1, 'amount': f"{s['price'] / 100:.2f}", 'label': s['name'], 'kind': s['kind']})
            problems.append('Enter each sponsorship amount (the total could not be split automatically).')
            remainder = None
    total = sum(Decimal(l['amount']) * 100 * l['quantity'] for l in lines)
    row.total = int(total)
    if amount is not None and lines and remainder not in (None, 0) and not problems:
        problems.append(f'File total {amount / 100:,.2f} differs from the seva prices ({row.total / 100:,.2f}).')
    if sum(l['quantity'] for l in lines) > 100:
        problems.append('Too many slips for one booking (maximum 100).')
    row.items = lines
    paid = paid_state(paid_text, amount if amount is not None else row.total)
    if paid is None:
        problems.append(f'Payment status "{paid_text}" is unclear — set Paid yes/no.')
        paid = False
    row.paid = bool(paid) and row.total > 0
    row.method = payment_method(method_text, default_method) if row.paid else ''
    row.blocking = bool(problems) or not row.items
    if row.from_text and not problems:
        problems.append('Read from pasted text — check the details, then tick it.')
    if problems:
        row.status, row.problem, row.include = 'Check', ' '.join(problems), False
    if not row.items:
        row.status, row.include = 'Error', False
    return row
