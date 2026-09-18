# DevSeva — © 2026 Raviraj Shetty. All rights reserved.
"""DevSeva event-day screens: the counter tab and the booking import window.

Mixed into the App class in app.py (uses self.store, self.actor, self.need, self.safe, ...).
"""
import datetime as dt
import json
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox, filedialog
import importer
from core import receipt, fmt, METHODS
from kannada import RASHIS, NAKSHATRAS, pick_choice
from widgets import AutoComplete, tip, dialog_keys

NOT_USED = '— not used —'
STATUS_COLOURS = {'Ready': '#e3f4e6', 'Check': '#fff1cc', 'Update': '#dcebff', 'Duplicate': '#eeeeee',
                  'Skip': '#eeeeee', 'Error': '#ffd9d9', 'Imported': '#c8ecd0'}


class EventDayMixin:
    # ------------------------------------------------------------ counter tab
    def build_counter(self):
        tab = ttk.Frame(self.tabs, padding=6)
        self.tabs.add(tab, text='Event-day counter / ಕೌಂಟರ್')
        top = ttk.Frame(tab)
        top.pack(fill='x')
        ttk.Label(top, text='Event:').pack(side='left')
        if not hasattr(self, 'counter_event'):
            self.counter_event = tk.StringVar(value='')  # set to the next upcoming festival on first refresh
        self.counter_combo = ttk.Combobox(top, textvariable=self.counter_event, state='readonly', width=34)
        self.counter_combo.pack(side='left', padx=4)
        ttk.Label(top, text='  Show:').pack(side='left')
        self.counter_show = tk.StringVar(value='All')
        for label in ('All', 'Unpaid', 'Paid'):
            ttk.Radiobutton(top, text=label, value=label, variable=self.counter_show,
                            command=lambda: self.safe(self.refresh_counter)).pack(side='left')
        self.requests_button = ttk.Button(top, text='Print requests from phones (0)',
                                          command=lambda: self.safe(self.print_request_window))
        self.requests_button.pack(side='right')
        search = ttk.Frame(tab)
        search.pack(fill='x', pady=8)
        ttk.Label(search, text='Search / ಹುಡುಕಿ:', font=('', 16, 'bold')).pack(side='left')
        self.counter_query = tk.StringVar()
        self.counter_entry = ttk.Entry(search, textvariable=self.counter_query, font=('', 18), width=34)
        self.counter_entry.pack(side='left', padx=8)
        ttk.Button(search, text='Clear', command=lambda: (self.counter_query.set(''), self.counter_entry.focus_set())).pack(side='left')
        ttk.Label(search, text='name · phone · email · booking no.', foreground='#555').pack(side='left', padx=8)
        self.counter_query.trace_add('write', lambda *_: self.safe(self.refresh_counter))
        self.counter_event.trace_add('write', lambda *_: self.safe(self.refresh_counter))
        self.counter_entry.bind('<Return>', lambda _: self.safe(self.counter_pick_first))
        self.counter_entry.bind('<Down>', lambda _: self.safe(self.counter_pick_first))
        self.counter_entry.bind('<Escape>', lambda _: self.counter_query.set(''))
        tip(self.counter_entry, 'Type part of a name, phone number, email or booking number. Enter or ↓ selects the first result; Esc clears.')
        body = ttk.Frame(tab)
        body.pack(fill='both', expand=True)
        left = ttk.Frame(body)
        left.pack(side='left', fill='both', expand=True)
        self.counter_tree = self.table(left, ('ref', 'id', 'name', 'phone', 'sevas', 'total', 'status', 'printed'),
                                       ('Booking no.', 'DevSeva #', 'Devotee', 'Phone', 'Slips', 'Total', 'Payment', 'Slips printed'),
                                       widths={'ref': 90, 'id': 80, 'name': 200, 'sevas': 50, 'total': 110, 'status': 150, 'printed': 90})
        # Aqua's dark appearance keeps Treeview text white even when a tag
        # requests a dark foreground. Use dark status fills instead, so the
        # native white text stays high-contrast and readable on every Mac.
        for status, colour in (('UNPAID', '#72520a'), ('PAID', '#1f613e'), ('VOID', '#55575a'), ('REFUNDED', '#55575a')):
            self.counter_tree.tag_configure(status, background=colour, foreground='white')
        self.counter_tree.bind('<<TreeviewSelect>>', lambda _: self.safe(self.counter_show_detail))
        self.counter_tree.bind('<Double-1>', lambda _: self.safe(self.counter_print))
        self.counter_tree.bind('<Return>', lambda _: self.safe(self.counter_print))
        self.counter_tree.bind('<Escape>', lambda _: self.counter_entry.focus_set())
        right = ttk.Frame(body)
        right.pack(side='left', fill='y', padx=(8, 0))
        style = ttk.Style()
        style.configure('Big.TButton', font=('', 14, 'bold'), padding=8)
        actions = ttk.Frame(right)
        actions.pack(side='top', fill='x')
        details_button = ttk.Button(actions, text='View full details', style='Big.TButton',
                                    command=lambda: self.safe(self.counter_details_popup))
        details_button.pack(fill='x', pady=(0, 6))
        tip(details_button, 'Open the selected booking with complete devotee, seva, total and payment details.')
        if False:  # Payment and printing actions are available in the details popup.
            pass
            '''
                               ('Collect cash only', lambda: self.counter_collect('Cash', False)),
                               ('Print slips only', self.counter_print),
                               ('Paid by UPI / card / bank…', self.counter_collect_other)):
            button = ttk.Button(actions, text=title, style='Big.TButton', command=lambda c=command: self.safe(c))
            button.pack(fill='x', pady=2)
            tip(button, {'Collect cash + print slips': 'Mark the selected unpaid booking PAID in cash, then print its slips.',
                         'Collect cash only': 'Mark the selected booking PAID in cash without printing.',
                         'Print slips only': 'Print the slips (for bookings already paid, or in-kind). Double-click or Enter does the same.',
                         'Paid by UPI / card / bank…': 'Record a non-cash payment, then optionally print.'}[title])
            '''
        self.counter_last = ttk.Label(tab, text='', font=('', 14, 'bold'), foreground='#1b6b34')
        self.counter_last.pack(anchor='w', pady=(6, 0))
        self.counter_status = ttk.Label(tab, text='')
        self.counter_status.pack(anchor='w')
        self.counter_mine = ttk.Label(tab, text='')
        self.counter_mine.pack(anchor='w')

    def default_counter_event(self):
        today = dt.date.today().isoformat()
        events = [e for e in self.store.catalog(active_only=True)['events'] if e['recurrence'] == 'Once' and e['day'] >= today]
        if events:
            e = min(events, key=lambda x: x['day'])
            return f"{e['id']} · {e['name']} ({e['currency']})"
        return 'All events'

    def refresh_counter(self):
        if not self.user:
            return
        choices = list(self.event_choices(active_only=False, include_all=True))
        self.counter_combo.config(values=choices)
        if self.counter_event.get() not in choices:
            self.counter_event.set(self.default_counter_event())
            return  # the trace refreshes again
        if hasattr(self, 'update_banner'):
            self.update_banner()
        event_id = self.event_choices(active_only=False, include_all=True).get(self.counter_event.get())
        status = {'Unpaid': ('UNPAID',), 'Paid': ('PAID',)}.get(self.counter_show.get())
        query = self.counter_query.get().strip()
        rows, more = self.store.bookings_page(query, 200, 0, event_id, status)
        values = []
        for b in rows:
            e = json.loads(b['snapshot'])
            paid = b['status'] if b['status'] != 'PAID' else f"PAID · {b['payment_method']}"
            if b['status'] == 'UNPAID' and not b['total']:
                paid = 'In-kind (no cash)'
            values.append((b['id'], (b['external_ref'] or '—', b['id'], b['devotee'], b['phone'], b['slips'],
                                     f"{e['currency']} {fmt(b['total'])}", paid, 'No' if b['print_pending'] else 'Yes')))
        keep = self.counter_tree.selection()
        self.counter_tree.delete(*self.counter_tree.get_children())
        for iid, vals in values:
            status_tag = next((r['status'] for r in rows if r['id'] == iid), '')
            self.counter_tree.insert('', 'end', iid=str(iid), values=vals, tags=(status_tag,))
        if keep and self.counter_tree.exists(keep[0]):
            self.counter_tree.selection_set(keep[0])
        elif len(values) == 1 and query:
            self.counter_tree.selection_set(str(values[0][0]))
        requests = self.store.print_requests()
        self.requests_button.config(text=f'Print requests from phones ({len(requests)})')
        unpaid = sum(1 for r in self.store.bookings_page('', 100000, 0, event_id, ('UNPAID',))[0] if r['total'])
        self.counter_status.config(text=f"{len(values)} shown{' (first 200 — type to narrow)' if more else ''} · "
                                        f"{unpaid} unpaid bookings in {'this event' if event_id else 'all events'}")
        rep = self.store.report(dt.date.today().isoformat(), dt.date.today().isoformat(), event_id)
        mine = [(cur, method, v) for (cur, who, method), v in rep['by_collector'].items() if who.split(' (')[0] == self.actor]
        text = ' · '.join(f'{method} {cur} {fmt(v)}' for cur, method, v in sorted(mine)) or 'nothing yet'
        self.counter_mine.config(text=f'Collected today by {self.user["name"]}: {text}')

    def counter_pick_first(self):
        children = self.counter_tree.get_children()
        if children:
            self.counter_tree.selection_set(children[0])
            self.counter_tree.focus(children[0])

    def counter_booking(self):
        return self.store.detail(self.selected(self.counter_tree, 'booking'))

    def counter_show_detail(self):
        return
        # Full booking details are shown in the popup only.
        chosen = self.counter_tree.selection()
        self.counter_detail.config(state='normal')
        self.counter_detail.delete('1.0', 'end')
        if chosen:
            b = self.store.detail(int(chosen[0]))
            cur = b['event']['currency']
            lines = [f"{b['devotee']}  {b.get('devotee_kn') or ''}",
                     f"Booking no.: {b.get('external_ref') or '—'}   (DevSeva #{b['id']:06d})",
                     f"{b['event']['name']} · {b['service_date']}",
                     f"Phone: {b['phone'] or '—'}   Email: {b.get('email') or '—'}", '']
            for item in b['items']:
                who = f" — {item['person']}" if item['person'] != b['devotee'] else ''
                lines.append(f"• {item['name']}{who}   {cur} {fmt(item['price'])}")
            lines += ['', f"TOTAL {cur} {fmt(b['total'])}"]
            if b['status'] == 'PAID':
                lines.append(f"PAID by {b['payment_method']} ({b['paid_by']})")
            elif b['status'] == 'UNPAID':
                lines.append('NOT PAID — collect ' + f"{cur} {fmt(b['total'])}" if b['total'] else 'In-kind — no cash due')
            else:
                lines.append(b['status'])
            if b['refunded']:
                lines.append(f"Refunded {cur} {fmt(b['refunded'])}")
            if b['note']:
                lines += ['', 'Notes: ' + b['note']]
            self.counter_detail.insert('end', '\n'.join(lines))
        self.counter_detail.config(state='disabled')

    def counter_details_popup(self):
        """Show the selected booking in a readable window with all counter actions."""
        b = self.counter_booking()
        win = tk.Toplevel(self.root)
        win.title(f"Booking #{b['id']:06d} — {b['devotee']}")
        win.transient(self.root)
        win.geometry('760x640')
        win.minsize(620, 480)
        outer = ttk.Frame(win, padding=16)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text=b['devotee'], font=('', 18, 'bold')).pack(anchor='w')
        if b.get('devotee_kn'):
            ttk.Label(outer, text=b['devotee_kn'], font=('', 14)).pack(anchor='w')
        ttk.Label(outer, text=f"Booking #{b['id']:06d}   ·   {b.get('external_ref') or 'No external booking number'}   ·   {b['service_date']}").pack(anchor='w', pady=(2, 0))
        ttk.Label(outer, text=f"{b['event']['name']}   ·   {b['event']['currency']}").pack(anchor='w')
        contact = f"Phone: {b.get('phone') or '—'}    Email: {b.get('email') or '—'}"
        ttk.Label(outer, text=contact).pack(anchor='w', pady=(2, 10))
        ttk.Separator(outer).pack(fill='x', pady=4)
        ttk.Label(outer, text='Sevas / sponsorships', font=('', 13, 'bold')).pack(anchor='w', pady=(6, 2))
        listing = tk.Text(outer, height=10, wrap='word', font=('', 12), borderwidth=1, relief='solid')
        listing.pack(fill='both', expand=True)
        grouped = {}
        order = []
        for item in b['items']:
            key = (item['name'], item.get('person') or b['devotee'], item['price'])
            if key not in grouped:
                grouped[key] = 0
                order.append(key)
            grouped[key] += 1
        cur = b['event']['currency']
        for name, person, price in order:
            qty = grouped[(name, person, price)]
            who = f" — {person}" if person != b['devotee'] else ''
            listing.insert('end', f"{qty} × {name}{who}    {cur} {fmt(price * qty)}\n")
        listing.insert('end', f"\nTOTAL    {cur} {fmt(b['total'])}\n")
        if b['status'] == 'PAID':
            listing.insert('end', f"PAID by {b['payment_method']} ({b.get('paid_by') or '—'})")
        elif b['status'] == 'UNPAID':
            listing.insert('end', f"NOT PAID — collect {cur} {fmt(b['total'])}" if b['total'] else 'In-kind — no cash due')
        else:
            listing.insert('end', b['status'])
        listing.config(state='disabled')
        if b.get('note'):
            ttk.Label(outer, text=f"Notes: {b['note']}", wraplength=700).pack(anchor='w', pady=(8, 0))
        action_row = ttk.Frame(outer)
        action_row.pack(fill='x', pady=(12, 0))
        ttk.Button(action_row, text='Collect cash + print slips', command=lambda: self.safe(lambda: self.counter_collect('Cash', True))).pack(side='left', padx=2)
        ttk.Button(action_row, text='Collect cash only', command=lambda: self.safe(lambda: self.counter_collect('Cash', False))).pack(side='left', padx=2)
        ttk.Button(action_row, text='Paid by UPI / card / bank…', command=lambda: self.safe(self.counter_collect_other)).pack(side='left', padx=2)
        ttk.Button(action_row, text='Print slips only', command=lambda: self.safe(self.counter_print)).pack(side='left', padx=2)
        ttk.Button(action_row, text='Close', command=win.destroy).pack(side='right', padx=2)
        # Keep keyboard behavior consistent with every other DevSeva dialog:
        # Esc closes this popup, Enter activates the focused action, and
        # Cmd/Ctrl+W closes it without affecting the counter behind it.
        dialog_keys(win, cancel=win.destroy)

    def counter_print(self):
        self.need('print')
        b = self.counter_booking()
        if b['status'] in ('VOID', 'REFUNDED'):
            raise ValueError(f"This booking is {b['status']}. No slips are printed.")
        self.open_html(receipt(b, int(self.width.get())), 'devseva-receipt-')
        if messagebox.askyesno('Slips printed?', f"Print from the browser window, then confirm.\n\n"
                                                 f"Did all {len(b['items'])} slip(s) and the summary print correctly for {b['devotee']}?",
                               parent=self.root):
            self.store.printed(b['id'], self.actor)
            self.counter_last.config(text=f"✔ Slips printed for {b['devotee']}")
        self.refresh()

    def counter_collect(self, method, then_print):
        self.need('pay')
        b = self.counter_booking()
        cur = b['event']['currency']
        if b['status'] == 'PAID':
            if then_print or messagebox.askyesno('Already paid', f"{b['devotee']} already paid by {b['payment_method']}. Print the slips?", parent=self.root):
                return self.counter_print()
            return
        if b['status'] != 'UNPAID':
            raise ValueError(f"This booking is {b['status']}.")
        if not b['total']:
            raise ValueError('No cash is due (in-kind contribution). Just print the slips.')
        if not messagebox.askyesno('Collect payment', f"Collect {cur} {fmt(b['total'])} by {method} from\n\n{b['devotee']}"
                                   f"{'  (' + b['external_ref'] + ')' if b.get('external_ref') else ''}?\n\n"
                                   f"Press Yes only after the money is in hand.", parent=self.root):
            return
        self.store.pay(b['id'], self.actor, method)
        self.counter_last.config(text=f"✔ {b['devotee']} marked PAID — {method} {cur} {fmt(b['total'])}")
        self.refresh()
        if then_print:
            self.counter_tree.selection_set(str(b['id']))
            self.counter_print()

    def counter_collect_other(self):
        self.need('pay')
        b = self.counter_booking()
        win = tk.Toplevel(self.root)
        win.title('Payment method')
        dialog_keys(win)
        win.transient(self.root)
        frame = ttk.Frame(win, padding=16)
        frame.pack()
        ttk.Label(frame, text=f"How did {b['devotee']} pay?").pack(anchor='w')
        method = tk.StringVar(value='UPI')
        for m in METHODS:
            if m != 'Cash':
                ttk.Radiobutton(frame, text=m, value=m, variable=method).pack(anchor='w')
        print_too = tk.BooleanVar(value=True)
        ttk.Checkbutton(frame, text='Print slips afterwards', variable=print_too).pack(anchor='w', pady=6)
        def go():
            win.destroy()
            self.safe(lambda: self.counter_collect(method.get(), print_too.get()))
        ttk.Button(frame, text='Continue', command=go).pack(anchor='e')
        dialog_keys(win, go)
        return win

    def print_request_window(self):
        self.need('print')
        win = tk.Toplevel(self.root)
        win.title('Print requests from phones')
        dialog_keys(win)
        win.geometry('760x380')
        frame = ttk.Frame(win, padding=10)
        frame.pack(fill='both', expand=True)
        tree = self.table(frame, ('id', 'ref', 'name', 'status', 'by', 'at'),
                          ('DevSeva #', 'Booking no.', 'Devotee', 'Payment', 'Requested by', 'Time'), widths={'id': 80})
        def load():
            self.fill(tree, [(r['booking_id'], (r['booking_id'], r['external_ref'] or '—', r['devotee'], r['status'],
                                                r['requested_by'], (r['requested_at'] or '')[11:16] + ' UTC'))
                             for r in self.store.print_requests()])
        def print_selected():
            bid = self.selected(tree, 'request')
            b = self.store.detail(bid)
            self.open_html(receipt(b, int(self.width.get())), 'devseva-receipt-')
            if messagebox.askyesno('Slips printed?', f"Did the slips for {b['devotee']} print correctly?", parent=win):
                self.store.printed(bid, self.actor)
            load()
            self.refresh()
        ttk.Button(frame, text='Print selected', command=lambda: self.safe(print_selected, win)).pack(anchor='e', pady=6)
        tree.bind('<Double-1>', lambda _: self.safe(print_selected, win))
        load()
        return win

    # ---------------------------------------------------------- import window
    def import_bookings(self):
        self.need('import')
        cat = self.store.catalog(active_only=True)
        events = {f"{e['id']} · {e['name']} · {e['day']} ({e['currency']})": e for e in cat['events']
                  if any(s['event_id'] == e['id'] for s in cat['sevas'])}
        if not events:
            raise ValueError('Create the event and its sevas in Masters first.')
        win = tk.Toplevel(self.root)
        win.title('Import bookings — Excel, CSV, WhatsApp, PDF, paper')
        dialog_keys(win)
        win.geometry('1240x760')
        win.minsize(980, 600)
        st = {'headers': [], 'rows': [], 'file_records': [], 'extra': [], 'plan': [], 'ticks': {}, 'path': None,
              'mapping': {}, 'sheets': [], 'sheet': None}
        outer = ttk.Frame(win, padding=10)
        outer.pack(fill='both', expand=True)

        opts = ttk.Frame(outer)
        opts.pack(fill='x')
        event_var = tk.StringVar(value=next((k for k, e in events.items() if f"{e['id']} · {e['name']} ({e['currency']})" == self.counter_event.get()),
                                            next(iter(events))))
        seva_var, method_var = tk.StringVar(), tk.StringVar(value='Bank transfer')
        register_var = tk.BooleanVar(value=True)
        ttk.Label(opts, text='Import into event:').grid(row=0, column=0, sticky='w')
        ttk.Combobox(opts, textvariable=event_var, values=list(events), state='readonly', width=48).grid(row=0, column=1, sticky='w', padx=4)
        ttk.Label(opts, text='If a row does not say which seva:').grid(row=0, column=2, sticky='w', padx=(16, 0))
        seva_combo = ttk.Combobox(opts, textvariable=seva_var, state='readonly', width=30)
        seva_combo.grid(row=0, column=3, sticky='w', padx=4)
        ttk.Label(opts, text='Paid rows with no method:').grid(row=1, column=0, sticky='w', pady=4)
        ttk.Combobox(opts, textvariable=method_var, values=list(METHODS), state='readonly', width=16).grid(row=1, column=1, sticky='w', padx=4)
        ttk.Checkbutton(opts, text='Also add new devotees to the Devotee register', variable=register_var).grid(row=1, column=2, columnspan=2, sticky='w', padx=(16, 0))

        sources = ttk.Frame(outer)
        sources.pack(fill='x', pady=8)
        file_label = ttk.Label(sources, text='No file opened.', foreground='#555')
        sheet_var = tk.StringVar()
        sheet_combo = ttk.Combobox(sources, textvariable=sheet_var, state='readonly', width=22)

        mapping_frame = ttk.LabelFrame(outer, text='Columns in the file (adjust if a guess is wrong)', padding=6)
        mapping_frame.pack(fill='x')
        map_vars = {}
        for i, name in enumerate(importer.FIELDS):
            ttk.Label(mapping_frame, text=importer.FIELD_LABELS[name]).grid(row=i // 5 * 2, column=i % 5, sticky='w', padx=4)
            var = tk.StringVar(value=NOT_USED)
            combo = ttk.Combobox(mapping_frame, textvariable=var, state='readonly', width=24)
            combo.grid(row=i // 5 * 2 + 1, column=i % 5, sticky='w', padx=4, pady=(0, 4))
            map_vars[name] = (var, combo)

        bottom = ttk.Frame(outer)
        bottom.pack(side='bottom', fill='x', pady=(4, 0))
        tree_frame = ttk.Frame(outer)
        tree_frame.pack(fill='both', expand=True, pady=6)
        columns = ('tick', 'n', 'status', 'ref', 'name', 'phone', 'email', 'sevas', 'total', 'paid', 'problem')
        labels = ('Import', 'Row', 'Status', 'Booking no.', 'Devotee', 'Phone', 'Email', 'Sevas', 'Total', 'Payment', 'What to check')
        tree = ttk.Treeview(tree_frame, columns=columns, show='headings', selectmode='extended')
        widths = {'tick': 55, 'n': 45, 'status': 75, 'ref': 85, 'name': 150, 'phone': 120, 'email': 160, 'sevas': 190,
                  'total': 80, 'paid': 120, 'problem': 330}
        for c, label in zip(columns, labels):
            tree.heading(c, text=label)
            tree.column(c, width=widths[c], stretch=c == 'problem')
        for status, colour in STATUS_COLOURS.items():
            tree.tag_configure(status, background=colour)
        scroll = ttk.Scrollbar(tree_frame, orient='vertical', command=tree.yview)
        hscroll = ttk.Scrollbar(tree_frame, orient='horizontal', command=tree.xview)
        tree.configure(yscrollcommand=scroll.set, xscrollcommand=hscroll.set)
        scroll.pack(side='right', fill='y')
        hscroll.pack(side='bottom', fill='x')
        tree.pack(fill='both', expand=True)
        counts = ttk.Label(bottom, text='', font=('', 12, 'bold'))
        counts.pack(anchor='w')

        def event():
            return events[event_var.get()]

        def event_sevas():
            return [s for s in self.store.catalog(active_only=True)['sevas'] if s['event_id'] == event()['id']]

        def refresh_sevas(*_):
            options = {f"{s['name']} ({s['kind']}, {fmt(s['price'])})": s['id'] for s in event_sevas()}
            seva_combo.config(values=list(options))
            st['seva_options'] = options
            if seva_var.get() not in options:
                seva_var.set(next((k for k, v in options.items() if k.split(' (')[1].startswith('Seva')), next(iter(options), '')))
            replan()

        def mapping_from_vars():
            index = {h: i for i, h in enumerate(st['headers'])}
            return {name: index[var.get()] for name, (var, _) in map_vars.items() if var.get() in index}

        def reread(*_):
            if not st['headers']:
                return
            st['mapping'] = mapping_from_vars()
            st['file_records'] = importer.rows_from_table(st['headers'], st['rows'], st['mapping'])
            st['ticks'] = {k: v for k, v in st['ticks'].items() if k >= len(st['file_records']) + 10 ** 6}
            replan()

        def all_records():
            return st['file_records'] + st['extra']

        def replan(*_):
            if 'seva_options' not in st:
                return
            known = self.store.known_imports(event()['id'])
            st['plan'] = importer.plan_rows(all_records(), event_sevas(), st['seva_options'].get(seva_var.get()),
                                            method_var.get(), known)
            for i, row in enumerate(st['plan']):
                tick = st['ticks'].get(key_of(i))
                if tick is not None and row.status in ('Ready', 'Check', 'Update') and not row.blocking:
                    row.include = tick
            draw()

        def key_of(i):
            # File rows and added rows keep separate tick memories.
            return i if i < len(st['file_records']) else 10 ** 6 + (i - len(st['file_records']))

        def draw():
            keep = tree.selection()
            tree.delete(*tree.get_children())
            for i, row in enumerate(st['plan']):
                paid = f'PAID · {row.method}' if row.paid else ('No cash' if not row.total and row.items else 'Unpaid')
                tree.insert('', 'end', iid=str(i), tags=(row.status,), values=(
                    '☑' if row.include else '☐', row.number, row.status, row.ref, row.name, row.phone, row.email,
                    row.summary(), f'{row.total / 100:,.2f}', paid, row.problem))
            for iid in keep:
                if tree.exists(iid):
                    tree.selection_add(iid)
            n = {s: sum(1 for r in st['plan'] if r.status == s) for s in STATUS_COLOURS}
            ticked = [r for r in st['plan'] if r.include]
            money = sum(r.total for r in ticked)
            counts.config(text=f"{len(st['plan'])} rows · ready {n['Ready']} · to check {n['Check']} · payment updates {n['Update']} · "
                               f"already imported {n['Duplicate']} · repeated {n['Skip']} · errors {n['Error']}      "
                               f"→ {len(ticked)} ticked, {event()['currency']} {fmt(money)}")
            import_button.config(text=f'Import {len(ticked)} ticked row(s)')

        def open_file():
            path = filedialog.askopenfilename(parent=win, title='Choose the booking list',
                                              filetypes=[('Excel or CSV', '*.xlsx *.xlsm *.csv *.tsv *.txt'), ('All files', '*')])
            if not path:
                return
            load_file(path)

        def load_file(path, sheet=None):
            headers, rows, sheets, chosen = importer.read_table(path, sheet)
            st.update(headers=headers, rows=rows, path=path, sheets=sheets, sheet=chosen, ticks={})
            guess = importer.guess_mapping(headers)
            for name, (var, combo) in map_vars.items():
                combo.config(values=[NOT_USED] + headers)
                var.set(headers[guess[name]] if name in guess else NOT_USED)
            file_label.config(text=f"{Path(path).name} — {len(rows)} rows" + (f", sheet “{chosen}”" if chosen else ''))
            if len(sheets) > 1:
                sheet_combo.config(values=sheets)
                sheet_var.set(chosen)
                sheet_combo.pack(side='left', padx=4)
            else:
                sheet_combo.pack_forget()
            reread()

        def change_sheet(*_):
            if st['path'] and sheet_var.get() and sheet_var.get() != st['sheet']:
                self.safe(lambda: load_file(st['path'], sheet_var.get()), win)

        def paste_text():
            pw = tk.Toplevel(win)
            pw.title('Paste booking text')
            dialog_keys(pw)
            pw.geometry('720x560')
            f = ttk.Frame(pw, padding=10)
            f.pack(fill='both', expand=True)
            ttk.Label(f, text='Paste WhatsApp messages (or an exported chat), text copied from PDF receipts, or text copied from a '
                              'photo of a paper form (in Photos or Preview, select the text in the picture and copy). '
                              'Leave a blank line between bookings.', wraplength=680).pack(anchor='w')
            box = tk.Text(f, wrap='word', font=('', 13))
            box.pack(fill='both', expand=True, pady=6)
            box.focus_set()
            def load_txt():
                path = filedialog.askopenfilename(parent=pw, filetypes=[('Text', '*.txt'), ('All files', '*')])
                if path:
                    box.insert('end', Path(path).read_text(encoding='utf-8', errors='replace'))
            def read():
                found = importer.parse_text(box.get('1.0', 'end'))
                if not found:
                    raise ValueError('No bookings were recognised. Check that the text includes names, phone numbers or amounts, '
                                     'or add the booking by hand.')
                st['extra'].extend(found)
                pw.destroy()
                replan()
                messagebox.showinfo('Text read', f'{len(found)} booking(s) found. They are marked "Check": '
                                    'open each one (double-click), correct it if needed and save, or tick it.', parent=win)
            buttons = ttk.Frame(f)
            buttons.pack(fill='x')
            ttk.Button(buttons, text='Open exported chat (.txt)…', command=lambda: self.safe(load_txt, pw)).pack(side='left')
            ttk.Button(buttons, text='Read bookings', command=lambda: self.safe(read, pw)).pack(side='right')

        def edit_row(index=None):
            if index is None:
                chosen = tree.selection()
                if len(chosen) != 1:
                    raise ValueError('Select one row to open.')
                index = int(chosen[0])
            records = all_records()
            record = records[index] if index is not None and index >= 0 else {'_source': 'Typed from a paper form'}
            plan_row = st['plan'][index] if index is not None and index >= 0 else None
            ew = tk.Toplevel(win)
            ew.title('Booking row' if plan_row else 'Add booking from a paper form')
            ew.transient(win)
            f = ttk.Frame(ew, padding=14)
            f.pack(fill='both', expand=True)
            paid_now = 'Paid' if (plan_row.paid if plan_row else False) else 'Unpaid'
            fields = [('ref', 'Booking number', record.get('ref', ''), None),
                      ('name', 'Devotee name *', plan_row.name if plan_row else '', None),
                      ('name_kn', 'Kannada name', record.get('name_kn', ''), None),
                      ('phone', 'Phone', plan_row.phone if plan_row else '', None),
                      ('email', 'Email', record.get('email', ''), None),
                      ('sevas', 'Sevas (e.g. "Pooja x2, Flowers AED 100")',
                       plan_row.summary().replace(' @ ', ' AED ') if plan_row and plan_row.items and record.get('_sevas_from_text') else record.get('sevas', ''), None),
                      ('quantity', 'Number of poojas (if one seva)', record.get('quantity', ''), None),
                      ('amount', 'Total amount *', record.get('amount', '') or (f'{plan_row.total / 100:.2f}' if plan_row and plan_row.total else ''), None),
                      ('paid', 'Payment status', paid_now, ['Unpaid', 'Paid']),
                      ('method', 'Paid by', (plan_row.method if plan_row and plan_row.method else method_var.get()), list(METHODS)),
                      ('gotra', 'Gotra', record.get('gotra', ''), None),
                      ('rashi', 'Rashi', record.get('rashi', ''), [''] + RASHIS),
                      ('nakshatra', 'Nakshatra', record.get('nakshatra', ''), [''] + NAKSHATRAS),
                      ('note', 'Notes', record.get('note', ''), None)]
            vars_ = {}
            for r, (key, label, value, choices) in enumerate(fields):
                ttk.Label(f, text=label).grid(row=r, column=0, sticky='w', pady=3)
                var = tk.StringVar(value=str(value or ''))
                vars_[key] = var
                if choices and len(choices) > 10:
                    w = AutoComplete(f, choices, textvariable=var, width=49)
                elif choices:
                    w = ttk.Combobox(f, textvariable=var, values=choices, state='readonly', width=46)
                else:
                    w = ttk.Entry(f, textvariable=var, width=49)
                w.grid(row=r, column=1, sticky='w', pady=3)
                if r == 1:
                    w.focus_set()
            if record.get('_source'):
                ttk.Label(f, text='Original: ' + record['_source'], wraplength=520, foreground='#555').grid(
                    row=len(fields), column=0, columnspan=2, sticky='w', pady=8)
            if plan_row and plan_row.problem:
                ttk.Label(f, text='To check: ' + plan_row.problem, wraplength=520, foreground='#8a5a00').grid(
                    row=len(fields) + 1, column=0, columnspan=2, sticky='w')
            def save():
                values = {k: v.get().strip() for k, v in vars_.items()}
                values['rashi'] = pick_choice(values['rashi'], RASHIS, 'Rashi')
                values['nakshatra'] = pick_choice(values['nakshatra'], NAKSHATRAS, 'Nakshatra')
                if not values['name']:
                    raise ValueError('Enter the devotee name.')
                values['paid'] = values['paid'].lower()
                if values['paid'] != 'paid':
                    values['method'] = ''
                new = dict(record)
                new.update(values)
                new['_from_text'] = False  # a person has now checked this row
                new['_sevas_from_text'] = False
                if index is not None and index >= 0:
                    if index < len(st['file_records']):
                        st['file_records'][index] = new
                    else:
                        st['extra'][index - len(st['file_records'])] = new
                    st['ticks'][key_of(index)] = True
                else:
                    st['extra'].append(new)
                    st['ticks'][key_of(len(all_records()) - 1)] = True
                ew.destroy()
                replan()
            ttk.Button(f, text='Save row', command=lambda: self.safe(save, ew)).grid(row=len(fields) + 2, column=1, sticky='e', pady=10)
            ttk.Button(f, text='Cancel', command=ew.destroy).grid(row=len(fields) + 2, column=0, sticky='w', pady=10)
            dialog_keys(ew, lambda: self.safe(save, ew))
            return ew

        def toggle():
            chosen = tree.selection()
            if not chosen:
                raise ValueError('Select one or more rows first.')
            blocked = []
            for iid in chosen:
                i = int(iid)
                row = st['plan'][i]
                if row.status in ('Duplicate', 'Skip', 'Error', 'Imported') or row.blocking:
                    blocked.append(row.number)
                    continue
                st['ticks'][key_of(i)] = not row.include
            replan()
            if blocked:
                messagebox.showinfo('Some rows not ticked', 'Rows ' + ', '.join(map(str, blocked)) +
                                    ' need correcting first (double-click to open) or are already imported/repeated.', parent=win)

        def remove():
            chosen = sorted((int(i) for i in tree.selection()), reverse=True)
            if not chosen:
                raise ValueError('Select rows to remove from this import.')
            for i in chosen:
                if i < len(st['file_records']):
                    st['file_records'][i] = {'_source': 'removed', '_removed': True}
                    st['ticks'][key_of(i)] = False
                else:
                    del st['extra'][i - len(st['file_records'])]
                    st['ticks'] = {k: v for k, v in st['ticks'].items() if k < 10 ** 6}
            replan()

        def do_import():
            self.need('import')
            ticked = [r for r in st['plan'] if r.include]
            if not ticked:
                raise ValueError('Tick at least one row. Rows marked "Check" need to be opened and saved, or ticked after checking.')
            e = event()
            new = sum(1 for r in ticked if r.status != 'Update')
            paid = sum(1 for r in ticked if r.paid)
            if not messagebox.askyesno('Import bookings', f"Import into {e['name']} ({e['day']}):\n\n"
                                       f"• {new} new booking(s), {paid} of them already paid\n"
                                       f"• {sum(1 for r in ticked if r.status == 'Update')} existing booking(s) to mark paid\n\n"
                                       'A safety backup is saved first. Continue?', parent=win):
                return
            self.store.auto_backup(self.backups_folder(), prefix='before-import', keep=10)
            created, marked, failed = self.store.import_rows(e['id'], st['plan'], self.actor, register_var.get())
            for i, row in enumerate(st['plan']):
                st['ticks'].pop(key_of(i), None)
            draw()
            self.refresh()
            messagebox.showinfo('Import finished', f'{created} booking(s) created, {marked} marked paid'
                                + (f', {failed} could not be imported (see "What to check").' if failed else '.') +
                                '\n\nReception can now find them on the Event-day counter tab.', parent=win)

        for title, command in (('Open Excel / CSV file…', open_file), ('Paste text (WhatsApp, PDF, photo)…', paste_text),
                               ('Add a paper form by hand…', lambda: edit_row(-1))):
            ttk.Button(sources, text=title, command=lambda c=command: self.safe(c, win)).pack(side='left', padx=3)
        file_label.pack(side='left', padx=10)
        actions = ttk.Frame(bottom)
        actions.pack(fill='x', pady=4)
        import_button = ttk.Button(actions, text='Import 0 ticked row(s)', style='Big.TButton', command=lambda: self.safe(do_import, win))
        import_button.pack(side='right')
        for title, command in (('Open / correct row…', edit_row), ('Tick / untick', toggle), ('Remove from import', remove)):
            ttk.Button(actions, text=title, command=lambda c=command: self.safe(c, win)).pack(side='left', padx=3)
        ttk.Label(bottom, text='Green = ready · Yellow = check first (double-click to open) · Blue = will be marked paid · '
                  'Grey = already in DevSeva or repeated · Space bar ticks/unticks', foreground='#555').pack(anchor='w')
        tree.bind('<Double-1>', lambda _: self.safe(edit_row, win))
        tree.bind('<space>', lambda _: self.safe(toggle, win))
        event_var.trace_add('write', refresh_sevas)
        seva_var.trace_add('write', replan)
        method_var.trace_add('write', replan)
        sheet_var.trace_add('write', change_sheet)
        for var, _ in map_vars.values():
            var.trace_add('write', reread)
        refresh_sevas()
        win.import_state = st          # for tests and support
        win.import_actions = {'load_file': load_file, 'paste': st['extra'], 'replan': replan, 'toggle': toggle,
                              'import': do_import, 'edit_row': edit_row, 'tree': tree, 'event_var': event_var}
        return win
