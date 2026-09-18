# DevSeva — © 2026 Raviraj Shetty. All rights reserved.
"""DevSeva desktop app. Run with Python 3.10+ on macOS or Windows: python3 app.py"""
import datetime as dt
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import uuid
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from core import (Store, receipt, schedule_html, report_html, report_text, money, fmt, weekday_text, person_name, email_address,
                  APP_NAME, APP_NAME_KN, VERSION, COPYRIGHT, CURRENCIES, KINDS, METHODS, RECURRENCES, RELATIONS)
from mobile import start
import security
from eventday import EventDayMixin
from kannada import bind_suggestion, translate_label, suggest, pick_choice, RASHIS, NAKSHATRAS
from widgets import AutoComplete, tip, dialog_keys, ACCEL
import qr
import icons
import developer
import base64
import shutil
import html as html_lib

MAX_ROWS = 1000
PAGE_SIZE = 300
IDLE_LOCK_MINUTES = 15
AUTO_BACKUPS_KEPT = 10
BRAND = '#7a1f1f'       # temple maroon
BRAND_DARK = '#5a1414'
GOLD = '#f2c14e'
NAV_BG = '#f5f1eb'
NAV_IDLE = '#ebe5dc'
NAV_ACTIVE = '#fffdf9'
DEV_CLICKS = 5
THIRD_PARTY = ('QR Code generator library (qrcodegen.py) — Copyright © Project Nayuki. MIT License.\n'
               'Python and Tcl/Tk — used under their own open-source licences.')

# Each workspace has one job. Keeping this language in one place makes the
# navigation, tooltip and on-screen guide agree with each other.
WORKSPACE_ITEMS = (
    ('Counter\nಕೌಂಟರ್', 'Event-day counter', 'COUNTER · EVENT DAY',
     'Find an existing booking, receive payment and print its slips. Use this at the counter; it does not create or redesign bookings.'),
    ('Bookings\nನೋಂದಣಿ', 'Bookings and cashier', 'BOOKINGS · RECORD DESK',
     'Create and find bookings at any time. Reprint slips, correct details, cancel unpaid bookings or refund paid ones here.'),
    ('Schedule\nಪೂಜಾ ಪಟ್ಟಿ', 'Pooja schedule', 'SCHEDULE · PRIEST LIST',
     'View or print the sevas due on one date for the priest. This is a work list, not a payment or booking screen.'),
    ('Devotees\nಭಕ್ತರು', 'Devotee register', 'DEVOTEES · FAMILY REGISTER',
     'Maintain families and members: contact details, gotra, rashi and nakshatra. Start a prefilled booking from a family when needed.'),
    ('Reports\nವರದಿ', 'Reports', 'REPORTS · REVIEW & EXPORT',
     'Review collections, payments and activity by date or event, then print or export. Reports do not change data.'),
    ('Masters\nವಿವರಗಳು', 'Events, sevas and settings', 'MASTERS · ADMIN SETUP',
     'Set up events, regular pooja calendars, seva offerings, prices and organisation details before taking bookings.'),
)


def fit_to_screen(window, margin=24, vertical_margin=96):
    """Size a window to the usable display area and keep it centred."""
    window.update_idletasks()
    screen_width, screen_height = window.winfo_screenwidth(), window.winfo_screenheight()
    width = max(760, screen_width - margin * 2)
    height = max(560, screen_height - vertical_margin)
    window.minsize(min(980, width), min(700, height))
    x = max(0, (screen_width - width) // 2)
    y = max(0, (screen_height - height - vertical_margin // 2) // 2)
    window.geometry(f'{width}x{height}+{x}+{y}')


def data_folder():
    # Kept from Seva Desk so upgrades keep using the existing database.
    if sys.platform == 'win32':
        base = Path(os.environ.get('LOCALAPPDATA', str(Path.home())))
    elif sys.platform == 'darwin':
        base = Path.home() / 'Library' / 'Application Support'
    else:
        base = Path.home() / '.local' / 'share'
    folder = base / 'SevaDeskPrototype'
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def today():
    return dt.date.today().isoformat()


def qr_sheet_html(link, info, store):
    """A printable A4 sheet with the phone QR code for the counter table."""
    image = base64.b64encode(qr.png(link, scale=10)).decode()
    today_events = [e for e in store.catalog(active_only=True)['events'] if e['recurrence'] == 'Once' and e['day'] >= today()]
    event = min(today_events, key=lambda e: e['day']) if today_events else None
    title = html_lib.escape(f"{event['name']} · {event['day']}" if event else 'Temple counter')
    host = html_lib.escape(link.split('/#')[0])
    code = html_lib.escape(info['code'])
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><title>DevSeva phone QR</title>
<style>body{{font:16px/1.45 -apple-system,system-ui,'Noto Sans Kannada',sans-serif;margin:0;color:#2f2118}}
.sheet{{max-width:180mm;margin:12mm auto;text-align:center}}h1{{margin:0;font-size:30px;color:#7a2e0e}}h2{{margin:4px 0 14px;font-size:18px;font-weight:600}}
img{{width:110mm;height:110mm;image-rendering:pixelated;border:1px solid #ddd}}ol{{text-align:left;max-width:150mm;margin:14px auto;font-size:17px}}
li{{margin:6px 0}}.code{{font:700 26px Menlo,Courier,monospace;letter-spacing:2px}}.muted{{color:#6b5a4a;font-size:13px}}
nav{{text-align:center;margin:10px}}button{{padding:10px 18px;font-size:15px}}@media print{{nav{{display:none}}.sheet{{margin:0 auto}}}}</style>
<nav><button onclick="window.print()">Print</button></nav>
<div class="sheet"><h1>DevSeva / ದೇವಸೇವೆ</h1><h2>{title} — volunteer phone login</h2>
<img src="data:image/png;base64,{image}" alt="QR code">
<ol><li>Join the counter Wi-Fi, open the camera and scan this code. / ವೈ-ಫೈ ಸೇರಿ, ಕ್ಯಾಮೆರಾದಿಂದ ಸ್ಕ್ಯಾನ್ ಮಾಡಿ.</li>
<li>If the phone says the connection is not private, tap <b>Advanced → Proceed</b> (first time only).</li>
<li>Enter your own <b>name and PIN</b>. / ನಿಮ್ಮ ಹೆಸರು ಮತ್ತು ಪಿನ್ ನಮೂದಿಸಿ.</li></ol>
<p class="muted">No camera? Open <b>{host}</b> and type the access code:</p><p class="code">{code}</p>
<p class="muted">This sheet works only until phone entry is stopped on the laptop. Do not share it outside the counter team.</p><p class="muted">{APP_NAME} · {COPYRIGHT}</p></div></html>"""


class App(EventDayMixin):
    def __init__(self, root, folder=None):
        self.root = root
        self.folder = Path(folder) if folder else data_folder()
        self.db_path = self.folder / 'seva-desk.sqlite3'
        self.store = Store(self.db_path)
        self.server = None
        self.server_info = None
        self.previews = []
        self.user = None
        self.last_activity = time.monotonic()
        self.version_seen = None
        self.page_limit = PAGE_SIZE
        self.dev_clicks = []
        self.set_title()
        fit_to_screen(root)
        self.style = ttk.Style()
        self.style.configure('TButton', padding=6)
        self.style.configure('Action.TButton', padding=6, foreground='#f4f0f5')
        self.style.map('Action.TButton',
                       foreground=[('disabled', '#b9b3bd'), ('pressed', '#ffffff'), ('active', '#ffffff'), ('!disabled', '#f4f0f5')])
        # Use a strong, accessible selection colour for every data table.
        # The native Aqua blue is too pale against white rows and can make
        # the selected booking look unreadable.
        self.style.configure('DevSeva.Treeview', rowheight=30)
        self.style.map('DevSeva.Treeview',
                       background=[('selected', '#1565c0')],
                       foreground=[('selected', '#ffffff')])
        # The workspace navigation below owns tab selection.  Keeping the native
        # notebook pages lets each screen retain its existing lifecycle, while
        # removing the duplicate, platform-dependent tab strip.
        try:
            self.style.layout('DevSeva.TNotebook.Tab', [])
        except tk.TclError:
            pass
        try:
            self.logo_small = tk.PhotoImage(data=base64.b64encode(icons.desktop_png(44)))
            self.logo_large = tk.PhotoImage(data=base64.b64encode(icons.desktop_png(96)))
            root.iconphoto(True, self.logo_large)
        except Exception:
            self.logo_small = self.logo_large = None
        self.body = ttk.Frame(root)
        self.counter_event = tk.StringVar(value='')  # the event shown in the banner and on the counter
        self.build_header()
        self.build_banner()
        self.build_action_bar()
        self.tabs = ttk.Notebook(self.body, style='DevSeva.TNotebook')
        self.build_counter()
        self.build_bookings()
        self.build_schedule()
        self.build_devotees()
        self.build_reports()
        self.build_masters()
        self.build_workspace_nav()
        foot = ttk.Frame(self.body)
        foot.pack(fill='x', side='bottom', padx=15, pady=(2, 6))
        self.version_label = self.brand_footer(foot)
        key = '⌘' if sys.platform == 'darwin' else 'Ctrl+'
        self.status = ttk.Label(foot, text=f'{key}N new booking · {key}F search · {key}L log out · Enter = OK · Esc = close', foreground='#555')
        tip(self.status, f'Logs out after {IDLE_LOCK_MINUTES} idle minutes. A backup is saved automatically when you quit.')
        self.status.pack(side='left')
        self.tabs.pack(fill='both', expand=True, padx=15, pady=5)
        self.gate = tk.Frame(root, background='#f5f1eb', padx=24, pady=20)
        root.protocol('WM_DELETE_WINDOW', self.close)
        for sequence in ('<Any-KeyPress>', '<Any-ButtonPress>', '<Motion>'):
            root.bind_all(sequence, self.touch, add='+')
        for key, action in (('n', lambda: self.booking()), ('l', self.logout), ('f', self.focus_search)):
            root.bind_all(f'<{ACCEL}-{key}>', lambda e, a=action: (self.safe(a) if self.user else None) or 'break')
        for index in range(6):
            root.bind_all(f'<{ACCEL}-{index + 1}>',
                          lambda e, i=index: (self.select_workspace(i) if self.user else None) or 'break')
        for sequence in (f'<{ACCEL}-Shift-D>', f'<{ACCEL}-Shift-d>'):
            root.bind_all(sequence, lambda e: self.safe(self.developer_tools) or 'break')
        if sys.platform == 'darwin':
            try:
                root.createcommand('tkAboutDialog', lambda: self.safe(self.about))
            except tk.TclError:
                pass
        self.counter_event.trace_add('write', lambda *_: self.safe(self.update_banner))
        self.show_gate()
        self.poll()

    # ------------------------------------------------------- login and locking
    @property
    def actor(self):
        return f"{self.user['role']}: {self.user['name']}" if self.user else 'Nobody'

    def need(self, action):
        if not self.user:
            raise PermissionError('Log in first.')
        security.require(self.user['role'], action)

    def allowed(self, action):
        return bool(self.user) and security.can(self.user['role'], action)

    def touch(self, _event=None):
        self.last_activity = time.monotonic()

    def close_windows(self):
        for w in self.root.winfo_children():
            if isinstance(w, tk.Toplevel):
                w.destroy()
        self.root.focus_set()

    def logout(self, reason='logged out'):
        if self.user:
            try:
                self.store.log_session(self.user, reason)
            except Exception:
                pass
        self.close_windows()
        self.user = None
        self.show_gate()

    def lock(self):
        self.logout('logged out (idle or restore)')

    def focus_search(self):
        if self.tabs.index('current') == 0:
            self.counter_entry.focus_set()
        elif self.tabs.index('current') == 1:
            self.booking_search.focus_set()
        elif self.tabs.index('current') == 3:
            self.dev_search.focus_set()
        else:
            self.tabs.select(0)
            self.counter_entry.focus_set()

    def configure_login_styles(self):
        """Use portable ttk elements only for login controls, including in macOS dark mode."""
        def layout(nodes):
            result = []
            for element, options in nodes:
                target = 'Login.' + element
                if target not in self.style.element_names():
                    self.style.element_create(target, 'from', 'clam', element)
                options = dict(options)
                if 'children' in options:
                    options['children'] = layout(options['children'])
                result.append((target, options))
            return result
        original_theme = self.style.theme_use()
        try:
            self.style.theme_use('clam')
            layouts = {widget: self.style.layout(widget) for widget in ('TButton', 'TCombobox')}
        finally:
            self.style.theme_use(original_theme)
        for widget, nodes in layouts.items():
            self.style.layout('Login.' + widget, layout(nodes))
        self.style.configure('Login.TButton', background='#087f8c', foreground='white',
                             padding=(16, 11), font=('', 13, 'bold'), borderwidth=0)
        self.style.map('Login.TButton', background=[('pressed', '#075362'), ('active', '#096878')],
                       foreground=[('disabled', '#cbd5d8'), ('!disabled', 'white')])
        self.style.configure('Login.TCombobox', fieldbackground='white', foreground='#302a25',
                             background='#edf4f5', arrowcolor='#173f50', padding=7,
                             bordercolor='#a4b8bf', lightcolor='#a4b8bf', darkcolor='#a4b8bf')
        self.style.map('Login.TCombobox', fieldbackground=[('!disabled', 'white')],
                       foreground=[('!disabled', '#302a25')])

    def show_gate(self):
        self.body.pack_forget()
        for w in self.gate.winfo_children():
            w.destroy()
        self.gate.pack(fill='both', expand=True)
        self.set_title()
        self.configure_login_styles()
        foot = tk.Frame(self.gate, background='#f5f1eb')
        foot.pack(side='bottom', fill='x')
        self.brand_footer(foot, background='#f5f1eb')
        box = tk.Frame(self.gate, background='#ffffff', padx=32, pady=26,
                       highlightbackground='#cedbdd', highlightthickness=1)
        box.place(relx=0.5, rely=0.47, anchor='center')
        box.columnconfigure(1, weight=1)
        label = lambda parent, **kw: tk.Label(parent, background='#ffffff',
            **dict({'foreground': '#302a25', 'font': ('', 12), 'wraplength': 520,
                    'justify': 'left'}, **kw))
        field = lambda parent, **kw: tk.Entry(parent, background='white',
            foreground='#302a25', insertbackground='#302a25', font=('', 13),
            relief='flat', borderwidth=6, highlightthickness=1,
            highlightbackground='#a4b8bf', highlightcolor='#176d87', **kw)
        top = tk.Frame(box, background='#ffffff')
        top.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 10))
        tk.Frame(top, background='#087f8c', height=3).pack(fill='x', pady=(0, 18))
        if self.logo_large:
            label(top, image=self.logo_small).pack()
        label(top, text=APP_NAME, font=('', 24, 'bold'), foreground='#173f50').pack()
        label(top, text=APP_NAME_KN, font=('', 13), foreground='#173f50').pack()
        org = self.org()
        first = not self.store.has_staff()
        name, pin, pin2, org_name = tk.StringVar(), tk.StringVar(), tk.StringVar(), tk.StringVar(value=org.get('org_name', ''))
        message = label(box, text='', foreground='#b00020', wraplength=420)
        if first:
            label(box, text='Welcome. Create the Administrator login for this laptop.\n'
                      'Use a PIN of 4–12 digits that others cannot guess. Keep it safe: '
                      'only an Admin can add staff or reset PINs.', wraplength=420, justify='center').grid(row=1, column=0, columnspan=2, pady=12)
            label(box, text='Temple / organisation').grid(row=2, column=0, sticky='w', pady=5)
            org_entry = tip(field(box, textvariable=org_name, width=28),
                            'Shown on receipts. You can change it later in Masters.')
            org_entry.grid(row=2, column=1, pady=5)
            label(box, text='Admin name').grid(row=3, column=0, sticky='w', pady=5)
            name_entry = field(box, textvariable=name, width=28)
            name_entry.grid(row=3, column=1, pady=5)
            entry = org_entry if not org_name.get() else name_entry
            label(box, text='PIN').grid(row=4, column=0, sticky='w', pady=5)
            field(box, textvariable=pin, show='•', width=28).grid(row=4, column=1, pady=5)
            label(box, text='Repeat PIN').grid(row=5, column=0, sticky='w', pady=5)
            last = field(box, textvariable=pin2, show='•', width=28)
            last.grid(row=5, column=1, pady=5)
            def go(*_):
                try:
                    if not org_name.get().strip():
                        raise ValueError('Enter the temple or organisation name.')
                    if pin.get() != pin2.get():
                        raise ValueError('The two PINs do not match.')
                    self.store.add_staff(name.get(), 'Admin', pin.get(), 'First-time setup')
                    self.store.save_settings({'org_name': org_name.get(),
                                              }, 'First-time setup')
                    self.unlock(self.store.login(name.get(), pin.get()))
                except Exception as ex:
                    message.config(text=str(ex))
            button = self.login_action_button(box, 'Create Admin and start', go)
        else:
            label(box, text='Welcome back\nSign in to your seva desk', font=('', 14), justify='center', wraplength=360).grid(row=1, column=0, columnspan=2, pady=12)
            names = [x['name'] for x in self.store.staff_list(active_only=True)]
            label(box, text='Name / ಹೆಸರು').grid(row=2, column=0, columnspan=2, sticky='w', pady=(8, 4))
            entry = ttk.Combobox(box, textvariable=name, values=names, width=30, style='Login.TCombobox', font=('', 13))
            entry.grid(row=3, column=0, columnspan=2, sticky='ew', pady=(0, 10))
            if len(names) == 1:
                name.set(names[0])
            label(box, text='PIN / ಪಿನ್').grid(row=4, column=0, columnspan=2, sticky='w', pady=(0, 4))
            last = field(box, textvariable=pin, show='•', width=28)
            last.grid(row=5, column=0, columnspan=2, sticky='ew')
            def go(*_):
                try:
                    self.unlock(self.store.login(name.get(), pin.get()))
                except Exception as ex:
                    pin.set('')
                    message.config(text=str(ex))
            button = self.login_action_button(box, 'Sign in', go)
            if self.server:
                label(box, text='Mobile access is still running for phones.', foreground='#625448').grid(row=9, column=0, columnspan=2, pady=4)
        button.grid(row=7, column=0, columnspan=2, sticky='ew', pady=(18, 6))
        message.grid(row=8, column=0, columnspan=2, sticky='ew')
        last.bind('<Return>', go)
        (last if name.get() and not first else entry).focus_set()
        self.login_widgets = {'name': name, 'pin': pin, 'pin2': pin2, 'org': org_name, 'go': go, 'message': message}
        self.login_theme_button = self.login_action_button(self.gate, 'Light mode', self.toggle_login_theme)
        self.login_theme_button.place(relx=1, x=-8, y=0, anchor='ne')
        if not hasattr(self, 'login_dark'):
            try:
                self.login_dark = json.loads((self.folder / 'appearance.json').read_text()).get('login_dark', True)
            except (OSError, ValueError, AttributeError):
                self.login_dark = True
        self.apply_login_theme()

    @staticmethod
    def login_action_button(parent, text, command):
        """Create a readable login action even when Aqua ignores ttk colours."""
        button = tk.Button(parent, text=text, command=command,
                         background='#d7eef0', foreground='#173f50',
                         activebackground='#b9e0e4', activeforeground='#173f50',
                         disabledforeground='#6c7f86', relief='raised', borderwidth=1,
                         highlightthickness=0, font=('', 13, 'bold'), padx=16, pady=11)
        button._login_action = True
        return button


    def toggle_login_theme(self):
        self.login_dark = not self.login_dark
        self.apply_login_theme()
        try:
            (self.folder / 'appearance.json').write_text(json.dumps({'login_dark': self.login_dark}))
        except OSError:
            pass  # Appearance still works for this session on a read-only disk.

    def apply_login_theme(self):
        """Recolour existing login widgets without clearing typed names or PINs."""
        pairs = {'#f5f1eb': '#111b24', '#ffffff': '#1c2b36',
                 '#302a25': '#edf4f6', '#173f50': '#edf4f6',
                 '#625448': '#b8c7ce', '#cedbdd': '#344c5b',
                 '#a4b8bf': '#587180', '#176d87': '#59d1da',
                 '#b00020': '#ff9cae', '#7a1f1f': '#75d8de'}
        def recolour(widget):
            if not isinstance(widget, ttk.Widget):
                if getattr(widget, '_login_action', False):
                    # Keep action labels dark on Aqua's native light button
                    # face in both login appearances.
                    widget.configure(background='#d7eef0', foreground='#173f50',
                                     activebackground='#b9e0e4', activeforeground='#173f50')
                    for child in widget.winfo_children():
                        recolour(child)
                    return
                if not hasattr(widget, '_login_colours'):
                    widget._login_colours = {key: widget.cget(key) for key in
                        ('background', 'foreground', 'insertbackground', 'highlightbackground', 'highlightcolor')
                        if key in widget.keys()}
                colours = {key: pairs.get(str(value).lower(), value) if self.login_dark else value
                           for key, value in widget._login_colours.items()}
                # Entry backgrounds use the named colour "white".
                if isinstance(widget, tk.Entry):
                    colours['background'] = '#14212b' if self.login_dark else 'white'
                # Keep the blue emblem readable on a small light tile.
                if isinstance(widget, tk.Label) and widget.cget('image'):
                    colours['background'] = '#ffffff'
                widget.configure(**colours)
            for child in widget.winfo_children():
                recolour(child)
        recolour(self.gate)
        field = '#14212b' if self.login_dark else 'white'
        text = '#edf4f6' if self.login_dark else '#302a25'
        self.style.configure('Login.TCombobox', fieldbackground=field, foreground=text,
                             background=field, arrowcolor=text,
                             selectbackground='#087f8c', selectforeground='white')
        self.style.map('Login.TCombobox', fieldbackground=[('!disabled', field)],
                       foreground=[('!disabled', text)], background=[('!disabled', field)],
                       arrowcolor=[('!disabled', text)])
        # Keep both login actions readable in either appearance. Native Aqua
        # can otherwise retain a light button face while the label remains
        # white, which makes the controls look blank.
        self.style.configure('Login.TButton', background='#087f8c', foreground='#ffffff',
                             borderwidth=0, padding=(16, 11), font=('', 13, 'bold'))
        self.style.map('Login.TButton',
                       background=[('pressed', '#075362'), ('active', '#096878'), ('!disabled', '#087f8c')],
                       foreground=[('disabled', '#cbd5d8'), ('!disabled', '#ffffff')])
        for button in (getattr(self, 'login_theme_button', None),):
            if button is not None and button.winfo_exists():
                button.configure(background='#d7eef0', foreground='#173f50',
                                 activebackground='#b9e0e4', activeforeground='#173f50')
        # The combobox list is a separate Tk popdown, not a child of the card.
        def popdowns(widget):
            if isinstance(widget, ttk.Combobox):
                pop = self.root.tk.call('ttk::combobox::PopdownWindow', str(widget))
                self.root.tk.call(str(pop) + '.f.l', 'configure', '-background', field,
                    '-foreground', text, '-selectbackground', '#087f8c', '-selectforeground', 'white')
            for child in widget.winfo_children():
                popdowns(child)
        popdowns(self.gate)
        self.login_theme_button.configure(text='Light mode' if self.login_dark else 'Dark mode')

    def unlock(self, user):
        self.user = user
        self.touch()
        self.gate.pack_forget()
        self.body.pack(fill='both', expand=True)
        self.who.config(text=f"{user['name']} · {user['role']}")
        self.refresh_action_bar()
        try:
            self.store.log_session(user, 'logged in')
        except Exception:
            pass
        self.root.after(50, self.counter_entry.focus_set)
        self.page_limit = PAGE_SIZE
        self.version_seen = None
        self.refresh()
        self.refresh_devotees()

    def change_my_pin(self):
        current = simpledialog.askstring('Change my PIN', 'Current PIN:', show='•', parent=self.root)
        if current is None:
            return
        self.store.login(self.user['name'], current)
        new = simpledialog.askstring('Change my PIN', 'New PIN (4–12 digits):', show='•', parent=self.root)
        if new is None:
            return
        if new != simpledialog.askstring('Change my PIN', 'Repeat new PIN:', show='•', parent=self.root):
            raise ValueError('The two PINs do not match. Nothing changed.')
        self.store.set_pin(self.user['id'], new, self.actor)
        messagebox.showinfo(APP_NAME, 'Your PIN has been changed.', parent=self.root)

    # ------------------------------------------------ brand, event banner, about
    def org(self):
        try:
            return self.store.settings()
        except Exception:
            return {}

    def banner_event(self):
        """The event chosen in the banner / counter, or None for 'All events'."""
        ident = self.event_choices(active_only=False, include_all=True).get(self.counter_event.get())
        return next((e for e in self.store.catalog()['events'] if e['id'] == ident), None) if ident else None

    def change_banner_event(self):
        """Choose the event used by the banner and counter without repeating its name in the header."""
        choices = list(self.event_choices(active_only=False, include_all=True))
        if len(choices) < 2:
            return
        win = tk.Toplevel(self.root)
        win.title('Change event / ಕಾರ್ಯಕ್ರಮ ಬದಲಿಸಿ')
        win.transient(self.root)
        win.resizable(False, False)
        frame = ttk.Frame(win, padding=14)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Event / ಕಾರ್ಯಕ್ರಮ').pack(anchor='w')
        choice = tk.StringVar(value=self.counter_event.get())
        combo = ttk.Combobox(frame, textvariable=choice, values=choices, state='readonly', width=52)
        combo.pack(fill='x', pady=(4, 12))
        buttons = ttk.Frame(frame)
        buttons.pack(fill='x')
        ttk.Button(buttons, text='Cancel', command=win.destroy).pack(side='right')
        ttk.Button(buttons, text='Use event', command=lambda: (self.counter_event.set(choice.get()), win.destroy())).pack(side='right', padx=6)
        win.bind('<Return>', lambda _e: (self.counter_event.set(choice.get()), win.destroy()))
        win.bind('<Escape>', lambda _e: win.destroy())
        win.protocol('WM_DELETE_WINDOW', win.destroy)
        combo.focus_set()

    def set_title(self, event=None):
        if event:
            self.root.title(f"{event['name']} ({event['day']}) — {APP_NAME}")
        else:
            self.root.title(f'{APP_NAME} / {APP_NAME_KN}')

    def build_header(self):
        """Compact native branding; account actions stay available in one menu."""
        ivory = '#fff8eb'
        head = tk.Frame(self.body, background=ivory, highlightbackground='#dbc59a',
                        highlightthickness=1)
        head.pack(fill='x', padx=15, pady=(6, 0))
        tk.Frame(head, background=GOLD, height=2).pack(fill='x')
        inner = tk.Frame(head, background=ivory)
        inner.pack(fill='x', padx=12, pady=6)
        inner.columnconfigure(0, weight=1)
        brand = tk.Frame(inner, background=ivory)
        brand.grid(row=0, column=0, sticky='w')
        if self.logo_small:
            self.logo_header = tk.PhotoImage(data=base64.b64encode(icons.desktop_png(28)))
            tk.Label(brand, image=self.logo_header, background=ivory,
                     borderwidth=0).pack(side='left', padx=(0, 8))
        tk.Label(brand, text=APP_NAME, font=('', 17, 'bold'),
                 foreground=BRAND_DARK, background=ivory).pack(side='left')
        tk.Label(brand, text=APP_NAME_KN, font=('', 14),
                 foreground=BRAND, background=ivory).pack(side='left', padx=(8, 0))
        tip(brand, f'{APP_NAME} {VERSION} — offline temple desk. {COPYRIGHT}')
        utility = tk.Frame(inner, background=ivory)
        utility.grid(row=0, column=1, sticky='e', padx=(12, 0))
        self.who = ttk.Menubutton(utility, text='Account', direction='below')
        self.who.pack(side='left')
        self.account_menu = tk.Menu(self.who, tearoff=False)
        self.account_menu.add_command(label='Change my PIN',
                                      command=lambda: self.safe(self.change_my_pin))
        self.account_menu.add_separator()
        self.account_menu.add_command(label='Log out / ಲಾಗ್ ಔಟ್', command=self.logout,
                                      accelerator=f'{ACCEL}+L')
        self.who.configure(menu=self.account_menu)
        tip(self.who, f'Account: change your PIN or log out ({ACCEL}+L).')

    def build_banner(self):
        band = tk.Frame(self.body, background=BRAND)
        band.pack(fill='x', padx=15, pady=(0, 4))
        inner = tk.Frame(band, background=BRAND)
        inner.pack(fill='x', padx=16, pady=10)
        text = tk.Frame(inner, background=BRAND)
        text.pack(side='left', fill='x', expand=True)
        label = lambda parent, **kw: tk.Label(parent, background=BRAND, anchor='w', justify='left', **kw)
        self.banner_caption = label(text, text='EVENT / ಕಾರ್ಯಕ್ರಮ', foreground=GOLD, font=('', 11, 'bold'))
        self.banner_caption.pack(anchor='w')
        names = tk.Frame(text, background=BRAND)
        names.pack(anchor='w', fill='x')
        self.banner_name = label(names, text='', foreground='white', font=('', 26, 'bold'))
        self.banner_name.pack(side='left')
        self.banner_kn = label(names, text='', foreground='#ffe7b0', font=('', 20))
        self.banner_kn.pack(side='left', padx=(14, 0))
        details = tk.Frame(text, background=BRAND)
        details.pack(anchor='w', pady=(2, 0))
        self.banner_when = label(details, text='', foreground='white', font=('', 13))
        self.banner_when.pack(side='left')
        self.banner_badge = tk.Label(details, text='', background=GOLD, foreground=BRAND_DARK, font=('', 12, 'bold'), padx=8, pady=1)
        self.banner_badge.pack(side='left', padx=(12, 0))
        side = tk.Frame(inner, background=BRAND)
        side.pack(side='right', anchor='n')
        self.change_event_button = ttk.Button(side, text='Change event…', command=lambda: self.safe(self.change_banner_event))
        self.change_event_button.pack(anchor='e', pady=(0, 4))
        tip(self.change_event_button, 'Choose a different event for the banner and counter.')
        self.mobile_state = label(side, text='📵 Phone entry off', foreground='#f3d6d6', font=('', 11))
        self.mobile_state.pack(anchor='e')
        self.mobile_state.bind('<Button-1>', lambda _: self.safe(self.mobile) if self.user else None)
        tip(self.mobile_state, 'Click to open phone entry (QR code) — Supervisor/Admin.')

    # ---------------------------------------------------------- primary actions
    def build_action_bar(self):
        """Keep daily work visible; place infrequent, role-specific work in one menu."""
        self.action_bar = ttk.Frame(self.body)
        self.action_bar.pack(fill='x', padx=15, pady=8)
        self.new_booking_button = tip(
            ttk.Button(self.action_bar, text='New booking / ನೋಂದಣಿ', command=lambda: self.safe(self.booking)),
            f'Register a devotee and their sevas ({ACCEL}+N).')
        self.new_booking_button.pack(side='left', padx=(8, 4))
        self.mobile_button = tip(
            ttk.Button(self.action_bar, text='Mobile access', command=lambda: self.safe(self.mobile)),
            'Let counter volunteers use their phones on this Wi-Fi (Supervisor/Admin).')
        self.masters_action_button = ttk.Button(self.action_bar, text='Masters / ವಿವರಗಳು',
                                                command=lambda: self.select_workspace(5))
        tip(self.masters_action_button, 'Administrator-only event, seva and organisation setup.')
        self.more_actions = (
            ('Import bookings…', self.import_bookings, 'import'),
            ('Backup database…', self.backup, 'backup'),
            ('Restore backup…', self.restore, 'restore'),
            ('Export register CSV…', self.export, 'reports'),
            ('Staff logins…', self.staff, 'staff'),
        )
        self.width = tk.StringVar(value='80')
        paper = ttk.Frame(self.action_bar)
        paper.pack(side='right')
        ttk.Label(paper, text='Slip paper mm:').pack(side='left', padx=(0, 6))
        tip(ttk.Combobox(paper, textvariable=self.width, values=['58', '80'], width=4, state='readonly'),
            'Width of the thermal slip paper.').pack(side='left')
        self.refresh_action_bar()

    def refresh_action_bar(self):
        """Show only controls the signed-in role can use; permissions remain enforced in actions."""
        mobile_allowed = self.allowed('mobile')
        if mobile_allowed:
            if not self.mobile_button.winfo_manager():
                self.mobile_button.pack(side='left', padx=4)
        else:
            self.mobile_button.pack_forget()
        available = [(title, command) for title, command, permission in self.more_actions if self.allowed(permission)]
        # Put role-specific actions in the same SAP-style menu as workspaces,
        # avoiding two competing dropdowns in the top bar.
        if hasattr(self, 'workspace_menu'):
            end = getattr(self, 'workspace_menu_base', len(self.workspace_items))
            last = self.workspace_menu.index('end')
            if last is not None and last >= end:
                self.workspace_menu.delete(end, 'end')
            if available:
                self.workspace_menu.add_separator()
                self.workspace_menu.add_command(label='ACTIONS', state='disabled')
                for title, command in available:
                    self.workspace_menu.add_command(label=title, command=lambda c=command: self.safe(c))
        if hasattr(self, 'masters_action_button'):
            if self.allowed('masters'):
                if not self.masters_action_button.winfo_manager():
                    self.masters_action_button.pack(side='right', padx=(0, 8))
            else:
                self.masters_action_button.pack_forget()

    # --------------------------------------------------------- workspace navigation
    def build_workspace_nav(self):
        """Compact SAP-style workspace menu with the active area kept visible."""
        self.workspace_items = WORKSPACE_ITEMS
        self.workspace_nav = tk.Frame(self.body, background=NAV_BG,
                                      highlightbackground='#d9d0c5', highlightthickness=1)
        self.workspace_nav.pack(fill='x', padx=15, pady=(0, 4))
        tk.Label(self.workspace_nav, text='MENU', background=NAV_BG, foreground='#6a5c50',
                 font=('', 10, 'bold'), padx=10, pady=4).pack(side='left')
        self.workspace_buttons = [object() for _ in self.workspace_items]
        self.workspace_menu_button = ttk.Menubutton(self.workspace_nav, text='Workspace', direction='below')
        self.workspace_menu_button.pack(side='left', padx=(0, 8), pady=3)
        self.workspace_menu = tk.Menu(self.workspace_menu_button, tearoff=False)
        for index, (label, description, _title, _hint) in enumerate(self.workspace_items):
            if index == 5:  # Masters is exposed separately to Admins only.
                continue
            self.workspace_menu.add_command(label=label.replace('\n', ' / '),
                                            command=lambda i=index: self.select_workspace(i),
                                            accelerator=f'{ACCEL}+{index + 1}')
        self.workspace_menu_base = self.workspace_menu.index('end') + 1
        self.workspace_menu_button.configure(menu=self.workspace_menu)
        tip(self.workspace_menu_button, 'Open a DevSeva workspace. Keyboard shortcuts: ⌘+1…⌘+6.')
        # Keep navigation controls on the compact utility row; the hint stays
        # below it so the work area starts as high as possible.
        self.workspace_nav.pack_forget()
        # Navigation is the first control in the utility row.  This keeps the
        # workspace switcher in a predictable place while the primary booking
        # action follows immediately beside it.
        self.workspace_nav.pack(in_=self.action_bar, side='left', before=self.new_booking_button,
                                padx=(0, 8), pady=0)
        self.workspace_hint = tk.Frame(self.body, background='#fff8eb', highlightbackground='#dbc59a', highlightthickness=1)
        self.workspace_hint.pack(fill='x', padx=15, pady=(0, 4))
        self.workspace_hint_title = tk.Label(self.workspace_hint, background='#fff8eb', foreground=BRAND_DARK,
                                             font=('', 10, 'bold'), padx=10, pady=5)
        self.workspace_hint_title.pack(side='left')
        self.workspace_hint_text = tk.Label(self.workspace_hint, background='#fff8eb', foreground='#4a3d34',
                                            anchor='w', justify='left', padx=2, pady=5)
        self.workspace_hint_text.pack(side='left', fill='x', expand=True)
        guide_button = tk.Button(self.workspace_hint, text='How these areas work…', command=self.workspace_guide,
                                 background='#fff8eb', activebackground='#f2e5c0', foreground=BRAND_DARK,
                                 borderwidth=0, cursor='hand2', padx=10, pady=4)
        tip(guide_button, 'Open a quick guide to the purpose of every workspace.')
        guide_button.pack(side='right', padx=4)
        self.tabs.bind('<<NotebookTabChanged>>', self.workspace_changed, add='+')
        self.root.after_idle(self.sync_workspace_nav)

    def select_workspace(self, index):
        """Select a workspace module while preserving all existing tab pages."""
        if index == 5 and not self.allowed('masters'):
            return
        if 0 <= index < len(self.workspace_buttons):
            self.tabs.select(index)
            self.root.after_idle(self.sync_workspace_nav)

    def workspace_changed(self, _event=None):
        self.sync_workspace_nav(animate=True)

    def workspace_guide(self):
        """Show the division of work so staff choose the right screen."""
        win = tk.Toplevel(self.root)
        win.title('How the DevSeva workspaces fit together')
        win.transient(self.root)
        win.geometry('820x600')
        frame = ttk.Frame(win, padding=16)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Choose the workspace by the job you are doing',
                  font=('', 16, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='The same booking can appear in Counter, Bookings and Schedule, but each screen has a different purpose. '
                  'Using the right screen keeps records, money and priest lists clear.', wraplength=780,
                  justify='left').pack(anchor='w', pady=(4, 10))
        for _label, _description, title, hint in self.workspace_items:
            row = ttk.Frame(frame)
            row.pack(fill='x', pady=3)
            ttk.Label(row, text=title, width=25, font=('', 10, 'bold')).pack(side='left', anchor='nw')
            ttk.Label(row, text=hint, wraplength=545, justify='left').pack(side='left', fill='x', expand=True)
        ttk.Separator(frame).pack(fill='x', pady=10)
        ttk.Label(frame, text='Recommended order: Masters → Devotees (optional) → Bookings → Counter → Schedule / Reports.',
                  wraplength=780, justify='left', font=('', 10, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='On an event day, the counter team normally stays in Counter; the administrator uses Bookings only for exceptions.',
                  wraplength=780, justify='left', foreground='#555').pack(anchor='w', pady=(4, 10))
        ttk.Button(frame, text='Close', command=win.destroy).pack(anchor='e')
        dialog_keys(win, win.destroy)
        return win

    def sync_workspace_nav(self, animate=False):
        if not getattr(self, 'workspace_items', None):
            return
        try:
            index = self.tabs.index('current')
        except tk.TclError:
            return
        if index >= len(self.workspace_items):
            return
        label, _description, title, hint = self.workspace_items[index]
        self.workspace_menu_button.config(text=label.replace('\n', ' / '))
        self.workspace_hint_title.config(text=title)
        self.workspace_hint_text.config(text=hint)

    @staticmethod
    def countdown(event, today_iso=None):
        today_date = dt.date.fromisoformat(today_iso or today())
        start = dt.date.fromisoformat(event['day'])
        end = dt.date.fromisoformat(event['end_day']) if event.get('end_day') else start
        if event['recurrence'] == 'Daily':
            if today_date < start:
                return f'Starts in {(start - today_date).days} days'
            return 'Ended' if event.get('end_day') and today_date > end else 'Daily — running'
        if start <= today_date <= end:
            return 'TODAY' if start == end else f'ON NOW · day {(today_date - start).days + 1} of {(end - start).days + 1}'
        days = (start - today_date).days
        if days == 1:
            return 'Tomorrow'
        if days > 1:
            return f'in {days} days'
        return 'Finished' if days == -1 else f'Finished {-days} days ago'

    def update_banner(self):
        if not hasattr(self, 'banner_name'):
            return
        choices = list(self.event_choices(active_only=False, include_all=True))
        self.change_event_button.configure(state='normal' if len(choices) > 1 else 'disabled')
        event = self.banner_event()
        org = self.org()
        self.set_title(event)
        if not event:
            self.banner_caption.config(text='ALL EVENTS / ಎಲ್ಲಾ ಕಾರ್ಯಕ್ರಮಗಳು')
            self.banner_name.config(text=org.get('org_name') or 'All events')
            self.banner_kn.config(text=org.get('org_name_kn', ''))
            self.banner_when.config(text='Choose an event on the right to show it here and on the counter.')
            self.banner_badge.config(text='')
            self.banner_badge.pack_forget()
            return
        when = dt.date.fromisoformat(event['day'])
        if event['recurrence'] == 'Daily':
            dates = f"Daily poojas · {weekday_text(event['weekdays'])} · from {when.strftime('%d %b %Y')}"
        else:
            dates = when.strftime('%A, %d %B %Y')
            if event.get('end_day') and event['end_day'] != event['day']:
                dates += ' – ' + dt.date.fromisoformat(event['end_day']).strftime('%A, %d %B %Y')
        self.banner_caption.config(text='DAILY POOJAS / ನಿತ್ಯ ಪೂಜೆ' if event['recurrence'] == 'Daily' else 'EVENT / ಕಾರ್ಯಕ್ರಮ')
        self.banner_name.config(text=event['name'])
        self.banner_kn.config(text=event.get('kannada') or '')
        self.banner_when.config(text=f"📅 {dates}" + (f"   📍 {event['place']}" if event.get('place') else ''))
        self.banner_badge.config(text=self.countdown(event))
        self.banner_badge.pack(side='left', padx=(12, 0))

    def brand_footer(self, parent, background=None):
        """Version + copyright at the bottom right. Clicking the version 5 times opens developer tools."""
        box = tk.Frame(parent, background=background) if background else ttk.Frame(parent)
        box.pack(side='right')
        footer_label = (lambda parent, **kw: tk.Label(parent, background=background, **kw)) if background else ttk.Label
        about = footer_label(box, text='About', foreground=BRAND, cursor='hand2')
        about.pack(side='right', padx=(10, 0))
        about.bind('<Button-1>', lambda _: self.safe(self.about))
        label = footer_label(box, text=f'{APP_NAME} {VERSION} · {COPYRIGHT}', foreground='#625448' if background else '#666')
        label.pack(side='right')
        label.bind('<Button-1>', self.version_click)
        return label

    def version_click(self, _event=None):
        now = time.monotonic()
        self.dev_clicks = [t for t in self.dev_clicks if now - t < 3] + [now]
        if len(self.dev_clicks) >= DEV_CLICKS:
            self.dev_clicks = []
            self.safe(self.developer_tools)

    def about(self):
        win = tk.Toplevel(self.root)
        win.title(f'About {APP_NAME}')
        win.transient(self.root)
        win.resizable(False, False)
        dialog_keys(win, win.destroy)
        frame = ttk.Frame(win, padding=24)
        frame.pack()
        if self.logo_large:
            ttk.Label(frame, image=self.logo_large).pack()
        ttk.Label(frame, text=f'{APP_NAME} / {APP_NAME_KN}', font=('', 22, 'bold'), foreground=BRAND).pack(pady=(8, 0))
        ttk.Label(frame, text=f'Version {VERSION} · Offline temple desk').pack()
        ttk.Label(frame, text='Daily poojas · Festival sevas · Devotee register · Event-day counter', foreground='#555').pack(pady=(2, 10))
        org = self.org().get('org_name')
        if org:
            ttk.Label(frame, text=f'Licensed for use by: {org}').pack()
        ttk.Label(frame, text=COPYRIGHT, font=('', 12, 'bold')).pack(pady=(10, 2))
        ttk.Label(frame, text='This software is proprietary. Copying, resale or distribution without the '
                  'copyright holder\'s written permission is not allowed.', wraplength=420, justify='center').pack()
        ttk.Label(frame, text=THIRD_PARTY, wraplength=420, justify='center', foreground='#666').pack(pady=(10, 0))
        ttk.Button(frame, text='OK', command=win.destroy).pack(pady=(14, 0))
        win.focus_force()
        return win

    def org_settings(self):
        self.need('masters')
        org = self.org()
        fields = [('org_name', 'Temple / organisation name', org.get('org_name', ''), None,
                   'Shown under DevSeva at the top, on the login screen and on every receipt.'),
                  ('org_name_kn', 'Kannada name / ಕನ್ನಡ ಹೆಸರು', org.get('org_name_kn', ''), None),
                  ('org_place', 'Place / city (optional)', org.get('org_place', ''), None)]
        def save(v):
            if not v['org_name'].strip():
                raise ValueError('Enter the temple or organisation name.')
            self.store.save_settings(v, self.actor)
            self.update_banner()
        return self.form('Temple / organisation details', fields, save, kannada=('org_name', 'org_name_kn', 'name'))

    # --------------------------------------------------------- developer tools
    def developer_tools(self):
        """Hidden developer area (Cmd/Ctrl+Shift+D, or click the version 5 times). Needs the developer passphrase."""
        guard = developer.Guard(self.folder)
        if getattr(self, 'dev_win', None) is not None and self.dev_win.winfo_exists():
            self.dev_win.lift()
            return self.dev_win
        if not developer.has_key(guard.path):
            if getattr(sys, 'frozen', False):
                raise ValueError('This standalone copy was built without a developer key.')
            if not messagebox.askyesno('Developer tools — first use',
                                       'This copy of DevSeva has no developer passphrase yet.\n\n'
                                       'Create one now? Keep it secret: it unlocks the factory reset and customer '
                                       'Admin PIN reset. Set it BEFORE you share or sell any copy.', icon='warning'):
                return
            first = simpledialog.askstring('Developer passphrase', f'New passphrase (at least {developer.MIN_LENGTH} characters):',
                                           show='•', parent=self.root)
            if not first:
                return
            if first != simpledialog.askstring('Developer passphrase', 'Repeat the passphrase:', show='•', parent=self.root):
                raise ValueError('The two passphrases do not match. Nothing was saved.')
            guard.set_key(first)
            messagebox.showinfo('Developer tools', 'Developer passphrase saved inside this copy of DevSeva.', parent=self.root)
        else:
            phrase = simpledialog.askstring('Developer tools', 'Developer passphrase:', show='•', parent=self.root)
            if not phrase:
                return
            guard.verify(phrase)
        return self.developer_window(guard)

    def developer_window(self, guard):
        win = tk.Toplevel(self.root)
        self.dev_win = win
        win.title('Developer tools')
        win.transient(self.root)
        win.resizable(False, False)
        dialog_keys(win)
        frame = ttk.Frame(win, padding=20)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Developer tools', font=('', 20, 'bold'), foreground=BRAND).pack(anchor='w')
        ttk.Label(frame, text='For the software developer only. Everything here is recorded in the audit log.',
                  foreground='#555').pack(anchor='w')
        info = ttk.Label(frame, text='', justify='left', font=('Menlo' if sys.platform == 'darwin' else 'Courier', 11))
        info.pack(anchor='w', pady=10)

        def load():
            st = self.store.stats()
            org = self.org().get('org_name') or '(not set)'
            info.config(text=f"{APP_NAME} {VERSION}\nLicensed to : {org}\nData folder : {self.folder}\n"
                             f"Developer key: {guard.path}\n\n"
                             + '   '.join(f'{k}: {v}' for k, v in st.items()))
        load()
        ttk.Separator(frame).pack(fill='x', pady=6)
        rows = [('Reset a customer Admin PIN…', lambda: self.dev_reset_pin(win),
                 'For a customer who forgot their Admin PIN. Existing data stays.'),
                ('Change developer passphrase…', lambda: self.dev_change_passphrase(guard, win),
                 'Needs the current passphrase.'),
                ('Factory reset…', lambda: self.factory_reset(win),
                 'Erase ALL data (bookings, devotees, staff, events, settings) so this copy can be given to a new temple.')]
        for title, command, help_text in rows:
            line = ttk.Frame(frame)
            line.pack(fill='x', pady=3)
            ttk.Button(line, text=title, width=30, command=lambda c=command: (self.safe(c, win), win.winfo_exists() and load())).pack(side='left')
            ttk.Label(line, text=help_text, wraplength=380, foreground='#8a1c1c' if 'Factory' in title else '#444').pack(side='left', padx=10)
        ttk.Button(frame, text='Close', command=win.destroy).pack(anchor='e', pady=(12, 0))
        win.focus_force()
        return win

    def dev_reset_pin(self, parent):
        staff = [x for x in self.store.staff_list() if x['role'] == 'Admin']
        if not staff:
            raise ValueError('There is no Admin login. A factory reset starts the Admin setup again.')
        options = {f"{x['name']} ({'active' if x['active'] else 'disabled'})": x['id'] for x in staff}
        def save(v):
            if v['pin'] != v['pin2']:
                raise ValueError('The two PINs do not match.')
            ident = options[v['who']]
            self.store.set_pin(ident, v['pin'], 'Developer')
            self.store.update_staff(ident, 'Admin', True, 'Developer')
            messagebox.showinfo('Developer tools', 'Admin PIN reset and login unlocked.', parent=parent)
        w = self.form('Reset Admin PIN', [('who', 'Admin login', next(iter(options)), list(options)),
                                          ('pin', 'New PIN (4–12 digits)', '', None), ('pin2', 'Repeat PIN', '', None)], save, parent=parent)
        self.mask_pins(w)
        return w

    def dev_change_passphrase(self, guard, parent):
        current = simpledialog.askstring('Change developer passphrase', 'Current passphrase:', show='•', parent=parent)
        if not current:
            return
        new = simpledialog.askstring('Change developer passphrase', f'New passphrase (at least {developer.MIN_LENGTH} characters):',
                                     show='•', parent=parent)
        if not new:
            return
        if new != simpledialog.askstring('Change developer passphrase', 'Repeat the new passphrase:', show='•', parent=parent):
            raise ValueError('The two passphrases do not match. Nothing changed.')
        guard.set_key(new, current)
        messagebox.showinfo('Developer tools', 'Developer passphrase changed.', parent=parent)

    def factory_reset(self, parent, confirm=None, backup_to=None, wipe_extras=None):
        """confirm/backup_to/wipe_extras are for automated tests; normally the developer is asked."""
        st = self.store.stats()
        win = parent
        if confirm is None:
            if not messagebox.askyesno('Factory reset', 'This ERASES everything on this laptop:\n\n'
                                       f"• {st['bookings']} bookings and all payments\n• {st['families']} devotee families\n"
                                       f"• {st['events']} events and {st['sevas']} sevas\n• {st['staff']} staff logins, settings and the audit log\n\n"
                                       'A final backup is saved first. Continue?', icon='warning', parent=win):
                return
            backup_to = filedialog.asksaveasfilename(parent=win, title='Save a final backup before the reset',
                                                     defaultextension='.sqlite3',
                                                     initialfile=f"devseva-before-reset-{dt.datetime.now():%Y%m%d-%H%M}.sqlite3")
            if not backup_to:
                if not messagebox.askyesno('No backup', 'No backup location was chosen. Reset WITHOUT a final backup?',
                                           icon='warning', parent=win):
                    return
            wipe_extras = messagebox.askyesno('Factory reset', 'Also delete the automatic backups and the phone-entry '
                                              'certificate on this laptop?\n\nChoose Yes when giving this laptop or copy to '
                                              'another temple.', parent=win)
            confirm = simpledialog.askstring('Factory reset', 'Type RESET (capital letters) to erase all data:', parent=win)
        if confirm != 'RESET':
            if confirm is not None:
                messagebox.showinfo('Factory reset', 'Nothing was erased.', parent=win)
            return
        if backup_to:
            self.store.backup(backup_to)
        self.stop_mobile()
        cleared = self.store.factory_reset('Developer')
        if wipe_extras:
            for folder in (self.backups_folder(), self.folder / 'tls'):
                shutil.rmtree(folder, ignore_errors=True)
        self.store = Store(self.db_path)
        self.counter_event.set('')
        self.user = None
        self.close_windows()
        self.update_banner()
        self.show_gate()
        messagebox.showinfo('Factory reset complete',
                            f'All data was erased ({cleared} tables).' + (f'\nFinal backup: {backup_to}' if backup_to else '')
                            + '\n\nDevSeva is ready for first-time setup.', parent=self.root)
        return cleared

    # ----------------------------------------------------------------- helpers
    def safe(self, command, parent=None):
        try:
            return command()
        except Exception as ex:
            messagebox.showerror(APP_NAME, str(ex), parent=parent or self.root)

    def button_row(self, parent, buttons):
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=6)
        for title, command in buttons:
            button = self.action_button(row, title, command)
            button.pack(side='left', padx=3)
        return row

    @staticmethod
    def action_button(parent, title, command):
        """High-contrast action button that keeps labels visible on macOS Aqua."""
        return tk.Button(parent, text=title, command=command,
                         background='#f0edf2', foreground='#211d26',
                         activebackground='#ddd7e2', activeforeground='#211d26',
                         disabledforeground='#77727d', relief='raised', borderwidth=1,
                         highlightthickness=0, font=('', 12), padx=12, pady=4)

    def table(self, parent, columns, labels, height=12, widths=None, expand=True):
        frame = ttk.Frame(parent)
        frame.pack(fill='both', expand=expand, pady=4)
        tree = ttk.Treeview(frame, columns=columns, show='headings', height=height,
                            selectmode='browse', style='DevSeva.Treeview')
        for i, (column, label) in enumerate(zip(columns, labels)):
            tree.heading(column, text=label)
            tree.column(column, width=(widths or {}).get(column, 120), minwidth=40, stretch=True)
        scroll = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        tree.pack(fill='both', expand=True)
        return tree

    def selected(self, tree=None, what='row'):
        chosen = (tree or self.tree).selection()
        if not chosen:
            raise ValueError(f'Select a {what} first.')
        return int(chosen[0])

    @staticmethod
    def select_first(tree):
        children = tree.get_children()
        if children:
            current = tree.selection()
            target = current[0] if current else children[0]
            tree.selection_set(target)
            tree.focus(target)
            tree.see(target)
            tree.focus_set()
        return 'break'

    @staticmethod
    def fill(tree, rows):
        keep = tree.selection()
        tree.delete(*tree.get_children())
        for iid, values in rows:
            tree.insert('', 'end', iid=str(iid), values=values)
        if keep and tree.exists(keep[0]):
            tree.selection_set(keep[0])

    def open_html(self, content, prefix='devseva-'):
        handle, path = tempfile.mkstemp(prefix=prefix, suffix='.html')
        with os.fdopen(handle, 'w', encoding='utf-8') as f:
            f.write(content)
        self.previews.append(path)
        webbrowser.open(Path(path).as_uri())

    def event_choices(self, active_only=True, include_all=False):
        events = self.store.catalog(active_only)['events']
        options = {'All events': None} if include_all else {}
        options.update({f"{e['id']} · {e['name']} ({e['currency']})": e['id'] for e in events})
        return options

    def form(self, title, fields, on_save, kannada=None, parent=None):
        """fields: (key, label, value, choices). kannada: (source, target, 'label' | 'name')."""
        win = tk.Toplevel(parent or self.root)
        win.title(title)
        win.transient(parent or self.root)
        frame = ttk.Frame(win, padding=18)
        frame.pack(fill='both', expand=True)
        values = {}
        searchable, first = {}, None
        for i, field in enumerate(fields):
            key, label, value, choices = field[:4]
            ttk.Label(frame, text=label).grid(row=i, column=0, sticky='w', padx=4, pady=6)
            var = tk.StringVar(value=str(value))
            values[key] = var
            if choices and len(choices) > 10:
                widget = AutoComplete(frame, choices, textvariable=var, width=43)
                searchable[key] = (choices, label.split(' /')[0].split(' (')[0])
            elif choices:
                widget = ttk.Combobox(frame, textvariable=var, values=choices, state='readonly', width=40)
            else:
                widget = ttk.Entry(frame, textvariable=var, width=43)
            widget.grid(row=i, column=1, sticky='ew', padx=4, pady=6)
            if len(field) > 4 and field[4]:
                tip(widget, field[4])
            if first is None and not isinstance(widget, ttk.Combobox):
                first = widget
            if 'PIN' in label and not choices:
                widget.configure(show='•')
        n = len(fields)
        if kannada:
            source, target, mode = kannada
            if mode == 'label':
                saved = self.store.label_dictionary()
                # Use curated/saved wording when available, then fall back to
                # the same offline phonetic generator used for names. This
                # keeps new seva and pooja labels from being left blank while
                # still making it clear that the result should be reviewed.
                convert = lambda text: translate_label(text, saved) or suggest(text)
            else:
                convert = suggest
            reset = bind_suggestion(values[source], values[target], convert)
            ttk.Button(frame, text='Use Kannada glossary' if mode == 'label' else 'Regenerate Kannada',
                       command=reset).grid(row=n + 1, column=1, sticky='e')
            hint = ttk.Label(frame, text='', wraplength=460)
            hint.grid(row=n + 2, column=0, columnspan=2, pady=8)
            def explain(*_):
                if mode != 'label':
                    hint.config(text='Phonetic suggestion only. Check the Kannada spelling with the devotee.')
                elif translate_label(values[source].get(), saved):
                    hint.config(text='Offline glossary available. Review the Kannada wording. Corrections are remembered when saved.')
                else:
                    hint.config(text='Phonetic Kannada suggestion shown. Review it; corrections are remembered when saved.')
            values[source].trace_add('write', explain)
            explain()
        def save():
            try:
                data = {k: v.get() for k, v in values.items()}
                for key, (choices, label) in searchable.items():
                    data[key] = pick_choice(data[key], choices, label)
                    values[key].set(data[key])
                on_save(data)
                if win.winfo_exists():
                    win.destroy()
                self.refresh()
                self.refresh_devotees()
            except Exception as ex:
                messagebox.showerror(title, str(ex), parent=win)
        buttons = ttk.Frame(frame)
        buttons.grid(row=n + 3, column=1, sticky='e', pady=12)
        tip(ttk.Button(buttons, text='Cancel', command=win.destroy), 'Close without saving (Esc).').pack(side='left', padx=4)
        tip(ttk.Button(buttons, text='Save / ಉಳಿಸಿ', command=save), 'Save (Enter).').pack(side='left')
        dialog_keys(win, save)
        if first is not None:
            first.focus_set()
            if isinstance(first, ttk.Entry):
                first.icursor('end')
        return win

    # ---------------------------------------------------------------- bookings
    def build_bookings(self):
        tab = ttk.Frame(self.tabs, padding=6)
        self.tabs.add(tab, text='Bookings & cashier / ನೋಂದಣಿ')
        top = ttk.Frame(tab)
        top.pack(fill='x')
        ttk.Label(top, text='Search name, slip name, booking no. or phone:').pack(side='left')
        self.booking_filter = tk.StringVar()
        self.booking_search = ttk.Entry(top, textvariable=self.booking_filter, width=30)
        self.booking_search.pack(side='left', padx=6)
        self.booking_search.bind('<Return>', lambda e: self.select_first(self.tree))
        self.booking_search.bind('<Escape>', lambda e: self.booking_filter.set(''))
        self.booking_filter.trace_add('write', lambda *_: self.safe(self.search_bookings))
        self.more_button = ttk.Button(top, text='Show more', command=lambda: self.safe(self.more_bookings))
        self.more_button.pack(side='right')
        self.tree = self.table(tab, ('id', 'date', 'items', 'devotee', 'slips', 'currency', 'amount', 'status', 'print'),
                               ('Booking', 'Pooja date', 'Sevas / sponsorships', 'Devotee', 'Slips', 'Cur.', 'Total', 'Payment', 'Print queue'),
                               widths={'id': 70, 'slips': 50, 'currency': 50, 'date': 95, 'items': 300, 'devotee': 220})
        self.tree.bind('<Double-1>', lambda _: self.safe(self.preview))
        self.tree.bind('<Return>', lambda _: self.safe(self.preview))
        self.button_row(tab, [('Preview / print slips', self.preview), ('Confirm printed', self.printed),
                              ('Receive payment', self.pay), ('Cancel unpaid booking', self.void), ('Refresh', self.refresh)])
        self.button_row(tab, [('Refund…', self.refund), ('Correct details / date…', self.correct_details),
                              ('Correct payment method…', self.correct_payment),
                              ('Link to devotee family…', self.link_booking), ('Unlink family', self.unlink_booking)])
        self.summary = ttk.Label(tab, text='')
        self.summary.pack(anchor='w', pady=6)

    def search_bookings(self):
        self.page_limit = PAGE_SIZE
        self.refresh_bookings()

    def more_bookings(self):
        self.page_limit += PAGE_SIZE
        self.refresh_bookings()

    def refresh_bookings(self):
        rows, more = self.store.bookings_page(self.booking_filter.get(), self.page_limit)
        values = []
        for b in rows:
            e = json.loads(b['snapshot'])
            status = b['status'] + (f" (−{fmt(b['refunded'])})" if b['status'] == 'PAID' and b['refunded'] else '')
            values.append((b['id'], (b['id'], b['service_date'], b.get('items_summary') or '—', b['devotee'], b['slips'], e['currency'],
                                     fmt(b['total']), status, 'Pending' if b['print_pending'] else 'Confirmed')))
        self.fill(self.tree, values)
        if more:
            self.more_button.state(['!disabled'])
        else:
            self.more_button.state(['disabled'])
        parts = []
        if self.allowed('reports'):
            rep = self.store.report(today(), today())
            net = ' · '.join(f'{c} {fmt(v)}' for c, v in sorted(rep['net'].items())) or 'nothing yet'
            unpaid = ' · '.join(f'{c} {fmt(v)}' for c, v in sorted(self.store.unpaid_total().items()) if v) or 'none'
            parts += [f'Net collected today: {net}', f'Unpaid (all dates): {unpaid}']
        parts.append(f'Showing {len(rows)} booking(s)' + (' — click Show more for older ones' if more else ''))
        self.summary.config(text='     |     '.join(parts))

    def selected_booking(self):
        return self.store.detail(self.selected(what='booking'))

    def preview(self):
        self.open_html(receipt(self.selected_booking(), int(self.width.get())), 'devseva-receipt-')

    def printed(self):
        self.need('print')
        bid = self.selected(what='booking')
        if messagebox.askyesno('Confirm printing', 'Have all seva slips and the cashier summary physically printed?\n'
                               'Any later print of this booking will be marked REPRINT.'):
            self.store.printed(bid, self.actor)
            self.refresh()

    def pay(self):
        self.need('pay')
        b = self.selected_booking()
        if b['status'] != 'UNPAID':
            raise ValueError('Select an unpaid booking.')
        if b['total'] <= 0:
            raise ValueError('No cash is due on this booking.')
        def save(v):
            if not messagebox.askyesno('Confirm payment', f"Have you received {b['event']['currency']} {fmt(b['total'])} from {b['devotee']}?"):
                raise ValueError('Payment not recorded.')
            self.store.pay(b['id'], self.actor, v['method'])
        self.form('Receive payment', [('method', 'Payment method', 'Cash', list(METHODS))], save)

    def void(self):
        self.need('void')
        bid = self.selected(what='booking')
        reason = simpledialog.askstring('Cancel unpaid booking', 'Reason (record stays in the audit log):', parent=self.root)
        if reason:
            self.store.void(bid, reason, self.actor)
            self.refresh()

    def refund(self):
        self.need('refund')
        b = self.selected_booking()
        if b['status'] != 'PAID':
            raise ValueError('Select a paid booking. Unpaid bookings are cancelled instead of refunded.')
        left = b['total'] - b['refunded']
        cur = b['event']['currency']
        def save(v):
            amount = money(v['amount'])
            kind = 'FULL refund — the sevas will be removed from the schedule' if amount == left else 'PARTIAL refund — the sevas stay booked'
            if not messagebox.askyesno('Confirm refund', f"Give back {cur} {fmt(amount)} to {b['devotee']} by {v['method']}?\n\n{kind}."):
                raise ValueError('Refund not recorded.')
            self.store.refund(b['id'], self.actor, v['amount'], v['method'], v['reason'])
        self.form(f"Refund booking #{b['id']:06d}",
                  [('amount', f'Amount to refund ({cur}, up to {fmt(left)})', f'{left / 100:.2f}', None),
                   ('method', 'Refund paid by', b['payment_method'] or 'Cash', list(METHODS)),
                   ('reason', 'Reason (required)', '', None)], save)

    def correct_payment(self):
        self.need('correct')
        b = self.selected_booking()
        if b['status'] not in ('PAID', 'REFUNDED'):
            raise ValueError('Select a paid booking.')
        self.form(f"Correct payment method #{b['id']:06d}",
                  [('method', f"Actual method (recorded: {b['payment_method']})", b['payment_method'], list(METHODS)),
                   ('reason', 'Reason (required)', '', None)],
                  lambda v: self.store.correct_payment(b['id'], v['method'], v['reason'], self.actor))

    def correct_details(self):
        self.need('correct')
        b = self.selected_booking()
        if b['status'] in ('VOID', 'REFUNDED'):
            raise ValueError('Cancelled or fully refunded bookings cannot be corrected.')
        win = tk.Toplevel(self.root)
        win.title(f"Correct booking #{b['id']:06d}")
        win.transient(self.root)
        outer = ttk.Frame(win, padding=14)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='Fix spelling or astrology details, or move a daily pooja to another date. '
                  'Amounts and sevas cannot change here — refund and book again instead. Every change is audited.',
                  wraplength=720).grid(row=0, column=0, columnspan=6, sticky='w', pady=(0, 8))
        v = {k: tk.StringVar(value=str(b.get(k) or '')) for k in ('devotee', 'devotee_kn', 'phone', 'email', 'gotra', 'rashi', 'nakshatra', 'note', 'service_date')}
        fields = [('devotee', 'Devotee name', None), ('devotee_kn', 'Kannada name', None), ('phone', 'Phone', None),
                  ('email', 'Email', None),
                  ('gotra', 'Gotra', None), ('rashi', 'Rashi', [''] + RASHIS), ('nakshatra', 'Nakshatra', [''] + NAKSHATRAS),
                  ('note', 'Notes', None)]
        daily = b['event'].get('recurrence') == 'Daily'
        if daily:
            fields.append(('service_date', 'Pooja date YYYY-MM-DD', None))
        r = 1
        for key, label, choices in fields:
            ttk.Label(outer, text=label).grid(row=r, column=0, sticky='w', pady=3)
            widget = AutoComplete(outer, choices, textvariable=v[key], width=43) if choices \
                else ttk.Entry(outer, textvariable=v[key], width=43)
            widget.grid(row=r, column=1, columnspan=3, sticky='w', pady=3)
            r += 1
        ttk.Label(outer, text='Slips', font=('', 12, 'bold')).grid(row=r, column=0, sticky='w', pady=(10, 2))
        r += 1
        for c, label in enumerate(('Seva', 'Name on slip', 'Kannada', 'Rashi', 'Nakshatra', 'Gotra')):
            ttk.Label(outer, text=label).grid(row=r, column=c, sticky='w')
        r += 1
        slips = {}
        for item in b['items']:
            ttk.Label(outer, text=f"#{item['id']} {item['name']}").grid(row=r, column=0, sticky='w')
            main_slip = item.get('person') == b.get('devotee') or not item.get('person')
            sv = {k: tk.StringVar(value=(item.get(k) or (b.get(k) if main_slip else '') or ''))
                  for k in ('person', 'person_kn', 'rashi', 'nakshatra', 'gotra')}
            ttk.Entry(outer, textvariable=sv['person'], width=18).grid(row=r, column=1, padx=2, pady=2)
            ttk.Entry(outer, textvariable=sv['person_kn'], width=16).grid(row=r, column=2, padx=2)
            AutoComplete(outer, RASHIS, textvariable=sv['rashi'], width=16).grid(row=r, column=3, padx=2)
            AutoComplete(outer, NAKSHATRAS, textvariable=sv['nakshatra'], width=20).grid(row=r, column=4, padx=2)
            ttk.Entry(outer, textvariable=sv['gotra'], width=12).grid(row=r, column=5, padx=2)
            slips[item['id']] = sv
            r += 1
        reason = tk.StringVar()
        ttk.Label(outer, text='Reason (required)').grid(row=r, column=0, sticky='w', pady=(10, 0))
        ttk.Entry(outer, textvariable=reason, width=60).grid(row=r, column=1, columnspan=4, sticky='w', pady=(10, 0))
        def save():
            for var, choices, label in [(v['rashi'], RASHIS, 'Rashi'), (v['nakshatra'], NAKSHATRAS, 'Nakshatra')] + \
                    [(sv[k], c, lab) for sv in slips.values() for k, c, lab in (('rashi', RASHIS, 'Rashi'), ('nakshatra', NAKSHATRAS, 'Nakshatra'))]:
                if var.get() and var.get() in (b.get('rashi'), b.get('nakshatra')) + tuple(i.get('rashi') for i in b['items']) + tuple(i.get('nakshatra') for i in b['items']):
                    continue  # unchanged historical wording (e.g. an older spelling) is kept as it is
                var.set(pick_choice(var.get(), choices, label))
            values = {k: var.get() for k, var in v.items() if k != 'service_date' or daily}
            values['items'] = {iid: {k: var.get() for k, var in sv.items()} for iid, sv in slips.items()}
            self.store.correct_details(b['id'], values, reason.get(), self.actor)
            win.destroy()
            self.refresh()
            messagebox.showinfo('Correction saved', 'Saved. Print the booking again if the paper slips need replacing; they will show REPRINT.', parent=self.root)
        ttk.Button(outer, text='Save correction', command=lambda: self.safe(save, win)).grid(row=r + 1, column=4, columnspan=2, sticky='e', pady=12)
        ttk.Button(outer, text='Cancel', command=win.destroy).grid(row=r + 1, column=3, sticky='e', pady=12)
        dialog_keys(win, lambda: self.safe(save, win))
        return win

    def link_booking(self):
        self.need('link')
        bid = self.selected(what='booking')
        def chosen(fid):
            self.store.link_booking(bid, fid, self.actor)
            self.refresh()
            self.refresh_devotees()
            messagebox.showinfo(APP_NAME, f'Booking #{bid:06d} is now in that family\'s history.', parent=self.root)
        self.pick_family(self.root, lambda fid: self.safe(lambda: chosen(fid)))

    def unlink_booking(self):
        self.need('link')
        bid = self.selected(what='booking')
        if messagebox.askyesno('Unlink', 'Remove this booking from its devotee family history? The booking itself is not changed.'):
            self.store.unlink_booking(bid, self.actor)
            self.refresh()
            self.refresh_devotees()

    # ------------------------------------------------------------ new booking
    def booking(self, family_id=None):
        self.need('book')
        override = self.allowed('override_price')
        cat = self.store.catalog(active_only=True)
        if not cat['sevas']:
            raise ValueError('Create an event or daily pooja calendar and its sevas in Masters first.')
        events = {e['id']: e for e in cat['events']}
        labels = {f"{e['id']} · {e['name']} ({e['currency']})": e['id'] for e in cat['events']
                  if any(s['event_id'] == e['id'] for s in cat['sevas'])}
        fixed_event = len(labels) == 1 and events[next(iter(labels.values()))]['recurrence'] == 'Once'
        win = tk.Toplevel(self.root)
        win.title('New booking / ಸೇವಾ ನೋಂದಣಿ')
        fit_to_screen(win, margin=40, vertical_margin=120)
        footer = ttk.Frame(win, padding=(12, 8))
        footer.pack(side='bottom', fill='x')
        viewport = ttk.Frame(win)
        viewport.pack(fill='both', expand=True)
        canvas = tk.Canvas(viewport, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(viewport, orient='vertical', command=canvas.yview)
        scrollbar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        frame = ttk.Frame(canvas, padding=14)
        content = canvas.create_window((0, 0), window=frame, anchor='nw')
        frame.bind('<Configure>', lambda _: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(content, width=e.width))
        for column in range(6):
            frame.columnconfigure(column, weight=1, uniform='booking')
        def scroll(event):
            if canvas.bbox('all') and frame.winfo_height() > canvas.winfo_height():
                delta = (-1 if event.num == 4 else 1) if getattr(event, 'num', None) in (4, 5) else (-event.delta if sys.platform == 'darwin' else -event.delta / 120)
                if delta:
                    canvas.yview_scroll(int(delta) or (1 if delta > 0 else -1), 'units')
                    return 'break'
        win.bind('<MouseWheel>', scroll, add='+')
        win.bind('<Button-4>', scroll, add='+')
        win.bind('<Button-5>', scroll, add='+')
        def reveal(event):
            widget = event.widget
            if not str(widget).startswith(str(frame) + '.'):
                return
            win.update_idletasks()
            top = widget.winfo_rooty() - frame.winfo_rooty()
            bottom = top + widget.winfo_height()
            visible = canvas.canvasy(0)
            height = canvas.winfo_height()
            if top < visible:
                canvas.yview_moveto(max(0, top - 12) / max(1, frame.winfo_height()))
            elif bottom > visible + height:
                canvas.yview_moveto((bottom - height + 12) / max(1, frame.winfo_height()))
        win.bind('<FocusIn>', reveal, add='+')
        fields = []
        v = {k: tk.StringVar() for k in ('event', 'date', 'family', 'devotee', 'devotee_kn', 'phone', 'gotra',
                                          'rashi', 'nakshatra', 'note', 'seva', 'person', 'qty', 'amount', 'email')}
        save_new = tk.BooleanVar(value=False)
        state = {'family_id': None, 'members': {}, 'lines': []}
        r = 0
        def row(label, widget, extra=None):
            nonlocal r
            caption = ttk.Label(frame, text=label)
            caption.grid(row=r, column=0, sticky='w', pady=4)
            fields.append((caption, widget))
            widget.grid(row=r, column=1, sticky='ew', pady=4)
            if extra:
                extra.grid(row=r, column=2, sticky='w', padx=6)
            r += 1
            return widget
        if len(labels) == 1:
            event_widget = ttk.Label(frame, textvariable=v['event'], anchor='w', relief='sunken', padding=(6, 3))
        else:
            event_widget = ttk.Combobox(frame, textvariable=v['event'], values=list(labels), state='readonly')
        row('Event / pooja calendar', event_widget)
        date_entry = row('Pooja date YYYY-MM-DD', ttk.Entry(frame, textvariable=v['date']))
        self.style.configure('BookingHint.TLabel', foreground=self.style.lookup('TLabel', 'foreground') or 'SystemTextColor')
        date_hint = ttk.Label(frame, text='', style='BookingHint.TLabel')
        date_hint.grid(row=r, column=1, sticky='w')
        r += 1
        fam_buttons = ttk.Frame(frame)
        register_entry = row('Devotee register', ttk.Entry(frame, textvariable=v['family']), fam_buttons)
        tip(register_entry, 'Search the devotee register: type part of a name, phone number or gotra and press Enter (or click Find). '
                            'Leave empty for a walk-in devotee; Find also uses the name typed below.')
        devotee_entry = row('Devotee name (English)', ttk.Entry(frame, textvariable=v['devotee']))
        row('Kannada name (editable)', ttk.Entry(frame, textvariable=v['devotee_kn']))
        row('Phone (optional)', ttk.Entry(frame, textvariable=v['phone']))
        email_entry = row('Email (optional)', ttk.Entry(frame, textvariable=v['email']))
        row('Gotra / ಗೋತ್ರ (optional)', ttk.Entry(frame, textvariable=v['gotra']))
        tip(row('Rashi / ರಾಶಿ', AutoComplete(frame, RASHIS, textvariable=v['rashi'])),
            'Start typing, e.g. "kar" for Karkataka. ↑/↓ to move, Enter to pick.')
        tip(row('Nakshatra / ನಕ್ಷತ್ರ', AutoComplete(frame, NAKSHATRAS, textvariable=v['nakshatra'])),
            'Start typing, e.g. "ash" for Ashwini or Ashlesha. ↑/↓ to move, Enter to pick.')
        row('Notes / in-kind details', ttk.Entry(frame, textvariable=v['note']))
        save_check = ttk.Checkbutton(frame, text='Save this new devotee to the register', variable=save_new)
        save_check.grid(row=r, column=1, sticky='w')
        reset_kn = bind_suggestion(v['devotee'], v['devotee_kn'])

        def format_devotee_name(_event=None):
            """Make the entered name immediately readable before booking is saved."""
            if v['devotee'].get().strip():
                v['devotee'].set(person_name(v['devotee'].get()))
            # Enter stays in the field; Tab formats first, then moves to the
            # next field as users expect from a data-entry form.
            return 'break' if getattr(_event, 'keysym', '') in ('Return', 'KP_Enter') else None

        devotee_entry.bind('<Return>', format_devotee_name)
        devotee_entry.bind('<Tab>', format_devotee_name)

        def validate_email(_event=None):
            try:
                v['email'].set(email_address(v['email'].get()))
            except ValueError as ex:
                messagebox.showerror('Email', str(ex), parent=win)
                return 'break'  # keep focus here until the address is corrected
            return 'break' if getattr(_event, 'keysym', '') in ('Return', 'KP_Enter') else None

        email_entry.bind('<Return>', validate_email)
        email_entry.bind('<Tab>', validate_email)
        regenerate = ttk.Button(frame, text='Regenerate Kannada', command=reset_kn)
        regenerate.grid(row=r, column=2, sticky='w', padx=6)
        r += 1
        divider = ttk.Separator(frame)
        divider.grid(row=r, column=0, columnspan=3, sticky='ew', pady=10)
        r += 1
        seva_combo = row('Seva', ttk.Combobox(frame, textvariable=v['seva'], state='readonly'))
        avail = ttk.Label(frame, text='', style='BookingHint.TLabel')
        avail.grid(row=r, column=1, sticky='w')
        r += 1
        person_combo = row('Slip for (family member)', ttk.Combobox(frame, textvariable=v['person'], state='readonly'))
        qty_entry = row('Quantity (one slip each)', ttk.Entry(frame, textvariable=v['qty']))
        amount_entry = row('Amount each' + (' (you may change it)' if override else ' (fixed; sponsorships editable)'),
                           ttk.Entry(frame, textvariable=v['amount']))
        choices = {}
        MAIN = 'Main devotee (details above)'

        def current_event():
            return events[labels[v['event'].get()]]

        def set_family(fid):
            fam = self.store.family_detail(fid)
            active = [m for m in fam['members'] if m['active']]
            state['family_id'] = fid
            state['members'] = {f"{m['name']} ({m['relation']})": m for m in active}
            main = next((m for m in active if m['relation'] == 'Self'), active[0] if active else None)
            v['family'].set(f"#{fid} · {fam['head']} · {len(active)} member(s)")
            state['family_label'] = v['family'].get()
            v['devotee'].set(main['name'] if main else fam['head'])
            v['devotee_kn'].set(main['kannada'] if main else '')
            v['rashi'].set(main['rashi'] if main else '')
            v['nakshatra'].set(main['nakshatra'] if main else '')
            v['phone'].set(fam['phone'])
            v['email'].set(fam.get('email', ''))
            v['gotra'].set((main['gotra'] if main else '') or fam['gotra'])
            save_new.set(False)
            save_check.state(['disabled'])
            person_combo.config(values=[MAIN] + list(state['members']))
            v['person'].set(MAIN)
            if state['lines'] and any(l.get('member_id') for l in state['lines']):
                clear()

        def clear_family():
            if state.get('family_id'):
                for k in ('devotee', 'devotee_kn', 'phone', 'email', 'gotra', 'rashi', 'nakshatra'):
                    v[k].set('')  # these came from the family that is being removed
            state['family_id'] = None
            state['members'] = {}
            v['family'].set('')
            state['family_label'] = None
            save_check.state(['!disabled'])
            person_combo.config(values=[MAIN])
            v['person'].set(MAIN)
            if any(l.get('member_id') for l in state['lines']):
                clear()

        def find_family():
            typed = v['family'].get().strip()
            if not typed or typed == state.get('family_label'):
                typed = v['devotee'].get().strip() or v['phone'].get().strip()
            matches = self.store.families(typed, 3) if len(typed) >= 2 else []
            if len(matches) == 1 and typed:
                set_family(matches[0]['id'])  # only one devotee matches: use it straight away
                return
            self.pick_family(win, set_family, typed,
                             lambda name: (clear_family(), v['devotee'].set(person_name(name))))

        tip(ttk.Button(fam_buttons, text='Find…', command=lambda: self.safe(find_family, win)),
            'Find this devotee in the register using the text typed on the left (or the name below).').pack(side='left')
        tip(ttk.Button(fam_buttons, text='Clear', command=clear_family), 'Book as a walk-in devotee instead.').pack(side='left')
        register_entry.bind('<Return>', lambda e: self.safe(find_family, win) or 'break')

        def update_availability(*_):
            s = choices.get(v['seva'].get())
            if not s or not s['daily_limit']:
                avail.config(text='')
                return
            try:
                left = self.store.availability(s['event_id'], v['date'].get())[s['id']]
                pending = sum(l['quantity'] for l in state['lines'] if l['seva_id'] == s['id'])
                avail.config(text=f"{left - pending} of {s['daily_limit']} slots free on {v['date'].get()}")
            except (ValueError, KeyError):
                avail.config(text=f"Limit {s['daily_limit']} per day — enter a valid pooja date")

        def price(*_):
            s = choices.get(v['seva'].get())
            if s:
                v['amount'].set(f"{s['price'] / 100:.2f}")
                editable = override or s['kind'] == 'Sponsorship'
                amount_entry.state(['!disabled'] if editable else ['disabled'])
            update_availability()

        def event_changed(*_):
            clear()
            e = current_event()
            choices.clear()
            kind_order = {'Seva': 0, 'Sponsorship': 1, 'In-kind': 2}
            event_sevas = sorted((s for s in cat['sevas'] if s['event_id'] == e['id']),
                                 key=lambda s: (kind_order.get(s['kind'], 9), s['name'].casefold()))
            choices.update({f"{s['name']} / {s['kannada']}  ·  {s['kind']}": s for s in event_sevas})
            seva_combo.config(values=list(choices))
            v['seva'].set(next(iter(choices), ''))
            if e['recurrence'] == 'Daily':
                date_entry.state(['!disabled', '!readonly'])
                if not v['date'].get() or v['date'].get() < e['day']:
                    v['date'].set(max(today(), e['day']))
                end = f" until {e['end_day']}" if e['end_day'] else ''
                date_hint.config(text=f"Daily pooja · days: {weekday_text(e['weekdays'])} · from {e['day']}{end}")
            else:
                v['date'].set(e['day'])
                date_entry.state(['!disabled', 'readonly'])
                date_hint.config(text=f"Festival / event on {e['day']} at {e['place']}")
            price()

        cart = tk.Listbox(frame, height=3, exportselection=False)
        total = ttk.Label(footer, text='', font=('', 13, 'bold'))

        def redraw():
            cart.delete(0, 'end')
            for l in state['lines']:
                cart.insert('end', f"{l['quantity']} × {l['label']}  —  for {l['who']}  =  {fmt(money(l['amount']) * l['quantity'])}")
            amount = sum(money(l['amount']) * l['quantity'] for l in state['lines'])
            total.config(text=f"Total: {current_event()['currency']} {fmt(amount)}" if state['lines'] else '')
            update_availability()

        def add():
            s = choices.get(v['seva'].get())
            if not s:
                raise ValueError('Choose a seva.')
            text = v['qty'].get().strip()
            if not text.isdigit():
                raise ValueError('Quantity must be a whole number.')
            q, p = int(text), money(v['amount'].get())
            if q < 1 or sum(l['quantity'] for l in state['lines']) + q > 100:
                raise ValueError('Use 1–100 total slips.')
            if s['kind'] == 'In-kind' and p:
                raise ValueError('In-kind contributions must have zero cash amount.')
            member = state['members'].get(v['person'].get())
            state['lines'].append({'seva_id': s['id'], 'quantity': q, 'amount': f'{p / 100:.2f}',
                                   'member_id': member['id'] if member else None, 'label': s['name'],
                                   'who': member['name'] if member else (v['devotee'].get() or 'main devotee')})
            v['qty'].set('1')
            redraw()

        def remove():
            chosen = cart.curselection()
            if not chosen:
                raise ValueError('Select a line in the list to remove.')
            del state['lines'][chosen[0]]
            redraw()

        def clear():
            state['lines'].clear()
            redraw()

        buttons = ttk.Frame(frame)
        buttons.grid(row=r, column=1, sticky='e')
        ttk.Button(buttons, text='Add seva line', command=lambda: self.safe(add, win)).pack(side='left', padx=3)
        all_button = ttk.Button(buttons, text='Add every family member', command=lambda: self.safe(add_all, win))
        all_button.pack(side='left', padx=3)
        tip(all_button, 'Adds this seva once for each person in the chosen register family. '
            'Choose a family with Find… first. For a walk-in or new devotee, use Add seva line.')
        state['all_button'] = all_button
        r += 1
        cart.grid(row=r, column=0, columnspan=3, sticky='ew', pady=6)
        r += 1
        total.pack(anchor='w', pady=(0, 4))
        r += 1

        def add_all():
            if not state['members']:
                raise ValueError('"Add every member" is for families already in the register — pick one with Find… first.\n\n'
                                 'For a new devotee, the "Add seva line" you already added is enough: just click Save booking.')
            before = v['person'].get()
            for label in list(state['members']):
                v['person'].set(label)
                add()
            v['person'].set(before)

        key = str(uuid.uuid4())

        def save():
            if not state['lines']:
                raise ValueError('Add at least one seva line.')
            v['rashi'].set(pick_choice(v['rashi'].get(), RASHIS, 'Rashi'))
            v['nakshatra'].set(pick_choice(v['nakshatra'].get(), NAKSHATRAS, 'Nakshatra'))
            data = {k: v[k].get() for k in ('devotee', 'devotee_kn', 'phone', 'email', 'gotra', 'rashi', 'nakshatra', 'note')}
            data.update(request_key=key, event_id=current_event()['id'], service_date=v['date'].get(),
                        family_id=state['family_id'], save_devotee=bool(save_new.get()) and not state['family_id'],
                        items=[{k: l[k] for k in ('seva_id', 'quantity', 'amount', 'member_id')} for l in state['lines']])
            bid = self.store.book(data, self.actor, override)
            win.destroy()
            self.booking_filter.set('')
            self.refresh()
            self.refresh_devotees()
            self.tabs.select(1)
            self.tree.selection_set(str(bid))
            self.tree.see(str(bid))
            self.preview()

        actions = ttk.Frame(footer)
        actions.pack(fill='x')
        ttk.Button(actions, text='Remove selected line', command=lambda: self.safe(remove, win)).pack(side='left', padx=3)
        ttk.Button(actions, text='Clear lines', command=clear).pack(side='left', padx=3)
        tip(ttk.Button(actions, text='Save and preview slips', command=lambda: self.safe(save, win)),
            f'Save the booking and open the slips for printing ({ACCEL}+Enter).').pack(side='right', padx=3)
        tip(ttk.Button(actions, text='Cancel', command=lambda: close_window()), 'Close without saving (Esc).').pack(side='right', padx=3)

        def close_window():
            if state['lines'] and not messagebox.askyesno('Close booking', 'Close without saving this booking?', parent=win):
                return
            win.destroy()

        for w in (qty_entry, amount_entry):
            w.bind('<Return>', lambda e: self.safe(add, win) or 'break')
        dialog_keys(win, None, close_window)
        win.bind(f'<{ACCEL}-Return>', lambda e: self.safe(save, win) or 'break')
        win.protocol('WM_DELETE_WINDOW', close_window)

        # Related fields share rows; labels stay above their inputs.
        positions = [(0, 0, 4), (0, 4, 2), (3, 0, 4),
                     (5, 0, 3), (5, 3, 3), (7, 0, 3), (7, 3, 3),
                     (9, 0, 2), (9, 2, 2), (9, 4, 2), (11, 0, 6),
                     (15, 0, 3), (15, 3, 3), (18, 0, 2), (18, 2, 2)]
        for (caption, widget), (line, column, span) in zip(fields, positions):
            caption.grid_configure(row=line, column=column, columnspan=span,
                                   sticky='w', padx=(0, 12), pady=(6, 2))
            caption.configure(wraplength=210)
            if isinstance(widget, (ttk.Entry, ttk.Combobox)):
                widget.configure(width=12)
            elif widget is event_widget:
                widget.configure(width=60)
            widget.grid_configure(row=line + 1, column=column, columnspan=span,
                                  sticky='ew', padx=(0, 12), pady=(0, 4))
        date_entry.configure(style='BookingDate.TEntry')
        self.style.map('BookingDate.TEntry', foreground=[('readonly', self.style.lookup('TLabel', 'foreground') or 'SystemTextColor')])
        date_hint.grid_configure(row=2, column=0, columnspan=6, sticky='w')
        date_hint.configure(wraplength=700)
        # The event/date fields above already provide this context. Hiding the
        # repeated summary keeps the complete booking workflow visible without
        # making users scroll past the seva lines and save controls.
        date_hint.grid_remove()
        row_shift = 0
        if fixed_event:
            # The active event is already selected in the main window header;
            # a one-off event also has a fixed date, so repeating both fields
            # here only consumes space and creates a second source of truth.
            event_widget.grid_remove()
            date_entry.grid_remove()
            # Their captions are part of the same rows and must be hidden too.
            for caption, widget in fields[:2]:
                caption.grid_remove()
            row_shift = -2
            for caption, widget in fields[2:]:
                info = caption.grid_info()
                if info and int(info['row']) >= 3:
                    new_row = int(info['row']) + row_shift
                    caption.grid_configure(row=new_row)
                    widget.grid_configure(row=new_row + 1)
        fam_buttons.grid_configure(row=4 + row_shift, column=4, columnspan=2, sticky='w', padx=0)
        save_check.grid_configure(row=13 + row_shift, column=0, columnspan=4, sticky='w', pady=6)
        regenerate.grid_configure(row=13 + row_shift, column=4, columnspan=2, sticky='e', padx=(0, 12))
        divider.grid_configure(row=14 + row_shift, column=0, columnspan=6, pady=8)
        avail.grid_configure(row=17 + row_shift, column=0, columnspan=6, sticky='w')
        buttons.grid_configure(row=20 + row_shift, column=0, columnspan=6, sticky='e', pady=4)
        cart.grid_configure(row=21 + row_shift, column=0, columnspan=6, sticky='ew')

        v['qty'].set('1')
        v['event'].trace_add('write', event_changed)
        v['date'].trace_add('write', update_availability)
        seva_combo.bind('<<ComboboxSelected>>', price)
        v['event'].set(next(iter(labels)))
        if family_id:
            set_family(family_id)
        else:
            clear_family()
        register_entry.focus_set()
        return win

    def pick_family(self, parent, on_pick, initial='', on_walkin=None):
        win = tk.Toplevel(parent)
        win.title('Find devotee / ಭಕ್ತರ ಹುಡುಕಾಟ')
        win.geometry('760x460')
        win.transient(parent)
        frame = ttk.Frame(win, padding=10)
        frame.pack(fill='both', expand=True)
        query = tk.StringVar(value=initial)
        top = ttk.Frame(frame)
        top.pack(fill='x')
        ttk.Label(top, text='Name, family member, gotra, email or phone digits:').pack(side='left')
        entry = ttk.Entry(top, textvariable=query, width=30)
        entry.pack(side='left', padx=6)
        count = ttk.Label(top, text='', foreground='#555')
        count.pack(side='left')
        tree = self.table(frame, ('id', 'head', 'phone', 'gotra', 'members'), ('ID', 'Family', 'Phone', 'Gotra', 'Members'),
                          widths={'id': 50, 'members': 260})
        def search(*_):
            found = self.store.families(query.get(), 200)
            self.fill(tree, [(f['id'], (f['id'], f['head'], f['phone'], f['gotra'],
                                        ', '.join(m['name'] for m in f['members'] if m['active'])))
                             for f in found])
            children = tree.get_children()
            if children and not tree.selection():
                tree.selection_set(children[0])
                tree.focus(children[0])
            count.config(text=f'{len(found)} found' if query.get().strip() else '')
        def choose(*_):
            if not tree.get_children():
                raise ValueError(f'No devotee matches "{query.get().strip()}". Change the search, '
                                 'or press Esc and book as a walk-in devotee.')
            fid = self.selected(tree, 'devotee family')
            win.destroy()
            on_pick(fid)
        def down(_):
            self.select_first(tree)
            return 'break'
        def use_walkin():
            name = query.get().strip()
            if not name:
                raise ValueError('Type a devotee name first.')
            win.destroy()
            on_walkin(name)
        query.trace_add('write', search)
        tree.bind('<Double-1>', lambda _: self.safe(choose, win))
        entry.bind('<Down>', down)
        buttons = ttk.Frame(frame)
        buttons.pack(fill='x')
        ttk.Label(buttons, text='Type to filter · ↓ to move into the list · Enter to use · Esc to close',
                  foreground='#555').pack(side='left')
        if on_walkin:
            ttk.Button(buttons, text='Use as walk-in devotee',
                       command=lambda: self.safe(use_walkin, win)).pack(side='right', padx=4)
        ttk.Button(buttons, text='Use selected devotee', command=lambda: self.safe(choose, win)).pack(side='right')
        ttk.Button(buttons, text='Cancel', command=win.destroy).pack(side='right', padx=4)
        dialog_keys(win, lambda: self.safe(choose, win))
        search()
        entry.focus_set()
        entry.icursor('end')
        return win

    # ---------------------------------------------------------------- schedule
    def build_schedule(self):
        tab = ttk.Frame(self.tabs, padding=6)
        self.tabs.add(tab, text='Pooja schedule / ಪೂಜಾ ಪಟ್ಟಿ')
        top = ttk.Frame(tab)
        top.pack(fill='x')
        self.sched_date = tk.StringVar(value=today())
        self.sched_event = tk.StringVar(value='All events')
        ttk.Label(top, text='Date:').pack(side='left')
        ttk.Button(top, text='◀', width=3, command=lambda: self.safe(lambda: self.shift_day(-1))).pack(side='left')
        ttk.Entry(top, textvariable=self.sched_date, width=12).pack(side='left', padx=3)
        ttk.Button(top, text='▶', width=3, command=lambda: self.safe(lambda: self.shift_day(1))).pack(side='left')
        ttk.Button(top, text='Today', command=lambda: self.sched_date.set(today())).pack(side='left', padx=4)
        ttk.Label(top, text='   Event:').pack(side='left')
        self.sched_combo = ttk.Combobox(top, textvariable=self.sched_event, state='readonly', width=36)
        self.sched_combo.pack(side='left', padx=4)
        ttk.Button(top, text='Print priest sheet', command=lambda: self.safe(self.print_schedule)).pack(side='left', padx=8)
        self.sched_count = ttk.Label(tab, text='')
        self.sched_count.pack(anchor='w', pady=4)
        self.sched_tree = self.table(tab, ('seva', 'person', 'kn', 'gotra', 'rashi', 'nakshatra', 'booking', 'payment'),
                                     ('Seva', 'Name', 'Kannada', 'Gotra', 'Rashi', 'Nakshatra', 'Booking', 'Payment'),
                                     widths={'booking': 70, 'payment': 70})
        self.sched_date.trace_add('write', lambda *_: self.safe_schedule())
        self.sched_event.trace_add('write', lambda *_: self.safe_schedule())

    def shift_day(self, days):
        day = dt.date.fromisoformat(self.sched_date.get().strip()) + dt.timedelta(days=days)
        self.sched_date.set(day.isoformat())

    def schedule_rows(self):
        options = self.event_choices(active_only=False, include_all=True)
        return self.store.schedule(self.sched_date.get(), options.get(self.sched_event.get()))

    @staticmethod
    def grouped_schedule_rows(rows):
        """Collapse repeated slips into one priest-sheet line per devotee and seva."""
        grouped = {}
        for row in rows:
            key = (row['event'], row['name'], row['kannada'], row['person'], row['person_kn'],
                   row['gotra'], row['rashi'], row['nakshatra'], row['booking'], row['status'], row['kind'])
            item = grouped.get(key)
            if item is None:
                item = dict(row)
                item['quantity'] = 0
                grouped[key] = item
            item['quantity'] += 1
        return list(grouped.values())

    def safe_schedule(self):
        try:
            rows = self.schedule_rows()
        except ValueError:
            self.sched_count.config(text='Enter a date as YYYY-MM-DD.')
            self.fill(self.sched_tree, [])
            return
        grouped = self.grouped_schedule_rows(rows)
        self.fill(self.sched_tree, [(r['id'], (f"{r['name']} × {r['quantity']}" if r['quantity'] > 1 else r['name'],
                                               r['person'], r['person_kn'], r['gotra'], r['rashi'], r['nakshatra'],
                                               r['booking'], 'Paid' if r['status'] == 'PAID' else ('In-kind' if r['kind'] == 'In-kind' else 'Due')))
                                    for r in grouped])
        counts = {}
        for r in rows:
            counts[r['name']] = counts.get(r['name'], 0) + 1
        day = dt.date.fromisoformat(self.sched_date.get().strip())
        self.sched_count.config(text=f"{day:%A %d %B %Y}: {len(rows)} slips · {len(grouped)} lines   " +
                                '  ·  '.join(f'{k}: {n}' for k, n in sorted(counts.items())))

    def print_schedule(self):
        self.open_html(schedule_html(self.sched_date.get().strip(), self.schedule_rows()), 'devseva-schedule-')

    # ---------------------------------------------------------------- devotees
    def build_devotees(self):
        tab = ttk.Frame(self.tabs, padding=6)
        self.tabs.add(tab, text='Devotees / ಭಕ್ತರು')
        top = ttk.Frame(tab)
        top.pack(fill='x')
        ttk.Label(top, text='Search name, member, gotra or phone:').pack(side='left')
        self.dev_query = tk.StringVar()
        self.dev_search = ttk.Entry(top, textvariable=self.dev_query, width=30)
        self.dev_search.pack(side='left', padx=6)
        self.dev_search.bind('<Return>', lambda e: self.select_first(self.fam_tree))
        self.dev_search.bind('<Escape>', lambda e: self.dev_query.set(''))
        tip(self.dev_search, 'Type part of a name, family member, gotra, email or phone. Enter jumps to the first match.')
        self.dev_query.trace_add('write', lambda *_: self.safe(self.refresh_devotees))
        self.dev_count = ttk.Label(top, text='')
        self.dev_count.pack(side='left', padx=10)
        self.dup_banner = ttk.Label(tab, text='', foreground='#a33b00', font=('', 12, 'bold'))
        self.dup_banner.pack(anchor='w')
        self.fam_tree = self.table(tab, ('id', 'head', 'phone', 'email', 'gotra', 'members', 'bookings'),
                                   ('ID', 'Family / devotee', 'Phone', 'Email', 'Gotra', 'Members', 'Bookings'), height=9,
                                   widths={'id': 50, 'members': 70, 'bookings': 70, 'head': 240, 'email': 200})
        self.fam_tree.bind('<<TreeviewSelect>>', lambda _: self.safe(self.refresh_members))
        self.fam_tree.bind('<Double-1>', lambda _: self.safe(lambda: self.edit_family(self.selected(self.fam_tree, 'family'))))
        self.fam_tree.bind('<Return>', lambda _: self.safe(lambda: self.edit_family(self.selected(self.fam_tree, 'family'))))
        row = self.button_row(tab, [('Add family / devotee', self.edit_family),
                                    ('Edit family', lambda: self.edit_family(self.selected(self.fam_tree, 'family'))),
                                    ('New booking for family', lambda: self.booking(self.selected(self.fam_tree, 'family'))),
                                    ('Booking history', self.family_history),
                                    ('Merge duplicates…', self.merge_duplicates)])
        delete_family_row = ttk.Frame(tab)
        delete_family_row.pack(fill='x', pady=(0, 4))
        self.delete_family_button = self.action_button(delete_family_row, 'Permanently delete family',
                                                       self.delete_selected_family)
        self.delete_family_button.pack(side='left', padx=3)
        for button, text in zip(row.winfo_children(), (
                'Register a new family. Each mobile number can belong to only one family.',
                'Change the family name, phone, email, gotra or address (double-click a row does the same).',
                'Open a new booking with this family already filled in.',
                'See this family\'s bookings and link older bookings that belong to them.',
                'Combine two families that are really the same (e.g. entered twice with one mobile number).')):
            tip(button, text)
        ttk.Label(tab, text='Family members — each can have their own seva slip with their rashi and nakshatra').pack(anchor='w')
        self.mem_tree = self.table(tab, ('id', 'name', 'kn', 'relation', 'gotra', 'rashi', 'nakshatra', 'active'),
                                   ('ID', 'Name', 'Kannada', 'Relation', 'Gotra', 'Rashi', 'Nakshatra', 'Active'), height=6,
                                   widths={'id': 50, 'active': 60})
        self.mem_tree.bind('<Double-1>', lambda _: self.safe(lambda: self.edit_member(self.selected(self.mem_tree, 'member'))))
        self.mem_tree.bind('<Return>', lambda _: self.safe(lambda: self.edit_member(self.selected(self.mem_tree, 'member'))))
        member_row = self.button_row(tab, [('Add member', self.edit_member),
                                           ('Edit member', lambda: self.edit_member(self.selected(self.mem_tree, 'member')))])
        delete_member_row = ttk.Frame(tab)
        delete_member_row.pack(fill='x', pady=(0, 4))
        self.delete_member_button = self.action_button(delete_member_row, 'Permanently delete member',
                                                       self.delete_selected_member)
        self.delete_member_button.pack(side='left', padx=3)
        self.refresh_devotee_delete_controls()

    def refresh_devotee_delete_controls(self):
        for button in (getattr(self, 'delete_family_button', None), getattr(self, 'delete_member_button', None)):
            if button is not None:
                if self.allowed('masters'):
                    button.pack(side='left', padx=3)
                else:
                    button.pack_forget()

    def delete_selected_family(self):
        self.need('masters')
        fid = self.selected(self.fam_tree, 'family')
        row = self.store.family_detail(fid)
        if not messagebox.askyesno('Permanently delete family',
                                   f"Permanently delete {row['head']} and its registered members?\n\n"
                                   'This is allowed only when the family has no booking history.'):
            return
        safety = self.store.auto_backup(self.backups_folder(), prefix='before-delete-family', keep=10)
        self.store.delete_family(fid, self.actor)
        self.refresh_devotees()
        messagebox.showinfo('Family deleted', f"The family was permanently deleted.\n\nSafety backup: {safety.name}", parent=self.root)

    def delete_selected_member(self):
        self.need('masters')
        mid = self.selected(self.mem_tree, 'member')
        values = self.mem_tree.item(str(mid), 'values')
        name = values[1] if values else 'this member'
        if not messagebox.askyesno('Permanently delete member',
                                   f"Permanently delete {name}?\n\nMembers used on historical slips cannot be deleted."):
            return
        safety = self.store.auto_backup(self.backups_folder(), prefix='before-delete-member', keep=10)
        self.store.delete_member(mid, self.actor)
        self.refresh_devotees()
        messagebox.showinfo('Member deleted', f"The member was permanently deleted.\n\nSafety backup: {safety.name}", parent=self.root)

    def refresh_devotees(self):
        families = self.store.families(self.dev_query.get(), MAX_ROWS)
        with self.store.connect() as db:
            counts = dict(db.execute('SELECT family_id, COUNT(*) FROM bookings WHERE family_id IS NOT NULL GROUP BY family_id').fetchall())
        self.fill(self.fam_tree, [(f['id'], (f['id'], f['head'], f['phone'], f['email'], f['gotra'],
                                             sum(1 for m in f['members'] if m['active']), counts.get(f['id'], 0)))
                                  for f in families])
        self.dev_count.config(text=f'{len(families)} families shown')
        groups = self.store.duplicate_families()
        self.dup_banner.config(text=(f'⚠ {len(groups)} mobile number(s) are registered to more than one family — '
                                     'click "Merge duplicates…" to combine them.') if groups else '')
        self.refresh_members()
        self.refresh_devotee_delete_controls()

    def refresh_members(self):
        chosen = self.fam_tree.selection()
        members = self.store.family_detail(int(chosen[0]))['members'] if chosen else []
        self.fill(self.mem_tree, [(m['id'], (m['id'], m['name'], m['kannada'], m['relation'], m['gotra'], m['rashi'], m['nakshatra'],
                                             'Yes' if m['active'] else 'No')) for m in members])

    def edit_family(self, ident=None):
        self.need('devotees')
        f = self.store.family_detail(ident) if ident else {}
        main = next((m for m in f.get('members', []) if m.get('relation') == 'Self'), {}) if f else {}
        fields = [('head', 'Devotee name (English)', f.get('head', ''), None),
                  ('head_kn', 'Kannada name (editable)', main.get('kannada', ''), None),
                  ('phone', 'Mobile number', f.get('phone', ''), None, 'Each mobile number can be registered only once.'),
                  ('email', 'Email ID', f.get('email', ''), None, 'Optional, e.g. name@example.com'),
                  ('gotra', 'Gotra / ಗೋತ್ರ', f.get('gotra', ''), None),
                  ('rashi', 'Rashi / ರಾಶಿ', main.get('rashi', ''), [''] + RASHIS),
                  ('nakshatra', 'Nakshatra / ನಕ್ಷತ್ರ', main.get('nakshatra', ''), [''] + NAKSHATRAS),
                  ('address', 'Address / place', f.get('address', ''), None),
                  ('notes', 'Notes', f.get('notes', ''), None)]
        def save(values):
            with self.store.connect() as db:
                same = self.store.family_by_phone(db, values['phone'], exclude=ident)
            if same:
                if not ident and messagebox.askyesno(
                        'Already registered',
                        f"Mobile number {values['phone']} already belongs to family #{same['id']} ({same['head']}).\n\n"
                        f"Open that family and add {values['head'] or 'this person'} as a member?"):
                    self.dev_query.set('')
                    self.refresh_devotees()
                    self.fam_tree.selection_set(str(same['id']))
                    self.fam_tree.see(str(same['id']))
                    self.refresh_members()
                    name = values['head']
                    self.root.after(100, lambda: self.safe(lambda: self.edit_member(None, name)))
                    return
                raise ValueError(f"Mobile number {values['phone']} already belongs to family #{same['id']} ({same['head']}). "
                                 'Each mobile number can be registered only once.')
            fid = self.store.family(values, ident, self.actor)
            detail = self.store.family_detail(fid)
            current_main = next((m for m in detail['members'] if m.get('relation') == 'Self'), None)
            self.store.member(dict(family_id=fid, name=values['head'],
                                   kannada=values.get('head_kn') or suggest(values['head']), relation='Self',
                                   gotra=values['gotra'], rashi=values.get('rashi', ''),
                                   nakshatra=values.get('nakshatra', ''), active='Yes'),
                               current_main['id'] if current_main else None, self.actor)
            if not ident:
                self.dev_query.set('')
                self.refresh_devotees()
                self.fam_tree.selection_set(str(fid))
                self.fam_tree.see(str(fid))
                messagebox.showinfo('Devotee saved', 'Family saved with the complete devotee registration details.')
        self.form('Devotee registration', fields, save, kannada=('head', 'head_kn', 'name'))

    def edit_member(self, ident=None, name=''):
        self.need('devotees')
        fid = self.selected(self.fam_tree, 'family')
        family = self.store.family_detail(fid)
        m = next((x for x in family['members'] if x['id'] == ident), {})
        fields = [('name', 'Name (English)', m.get('name', name), None),
                  ('kannada', 'Kannada name', m.get('kannada', ''), None, 'Suggested automatically; check the spelling.'),
                  ('relation', 'Relation', m.get('relation', 'Spouse' if not ident else 'Self'), list(RELATIONS),
                   'Type to search, e.g. "da" for Daughter.'),
                  ('gotra', 'Gotra / ಗೋತ್ರ (if different from family)', m.get('gotra', family['gotra']), None),
                  ('rashi', 'Rashi / ರಾಶಿ', m.get('rashi', ''), [''] + RASHIS, 'Type a few letters, e.g. "kar" → Karkataka.'),
                  ('nakshatra', 'Nakshatra / ನಕ್ಷತ್ರ', m.get('nakshatra', ''), [''] + NAKSHATRAS, 'Type a few letters, e.g. "rev" → Revati.'),
                  ('active', 'Active', 'Yes' if m.get('active', 1) else 'No', ['Yes', 'No'])]
        def save(values):
            values['family_id'] = fid
            self.store.member(values, ident, self.actor)
        self.form('Family member', fields, save, kannada=('name', 'kannada', 'name'))

    def merge_duplicates(self):
        self.need('correct')
        groups = self.store.duplicate_families()
        win = tk.Toplevel(self.root)
        win.title('Merge duplicate families')
        win.transient(self.root)
        frame = ttk.Frame(win, padding=14)
        frame.pack(fill='both', expand=True)
        dialog_keys(win)
        if not groups:
            ttk.Label(frame, text='No mobile number is registered to more than one family. ✔').pack(pady=10)
            ttk.Button(frame, text='Close', command=win.destroy).pack()
            return win
        ttk.Label(frame, text='These families share a mobile number. For each group choose the family to KEEP. '
                  'Members, bookings and missing details of the others are moved into it; a person entered twice '
                  'becomes one member. Printed slips are not changed. A backup is saved first.',
                  wraplength=620).pack(anchor='w', pady=(0, 8))
        choices = []
        for group in groups:
            box = ttk.LabelFrame(frame, text=f"Mobile {group[0]['phone']}", padding=8)
            box.pack(fill='x', pady=4)
            keep = tk.IntVar(value=group[0]['id'])
            for f in group:
                detail = self.store.family_detail(f['id'])
                ttk.Radiobutton(box, variable=keep, value=f['id'], text=(
                    f"Keep #{f['id']} · {f['head']} · {len(detail['members'])} member(s) · {len(detail['bookings'])} booking(s)"
                    f"{' · ' + detail['email'] if detail['email'] else ''}")).pack(anchor='w')
            choices.append((group, keep))

        def merge():
            self.store.auto_backup(self.backups_folder(), prefix='before-merge', keep=10)
            done = []
            for group, keep in choices:
                for f in group:
                    if f['id'] != keep.get():
                        moved, combined, bookings = self.store.merge_families(keep.get(), f['id'], self.actor)
                        done.append(f"#{f['id']} → #{keep.get()}: {moved} member(s) moved, {combined} combined, {bookings} booking(s) moved")
            win.destroy()
            self.refresh()
            messagebox.showinfo('Families merged', '\n'.join(done), parent=self.root)
        buttons = ttk.Frame(frame)
        buttons.pack(fill='x', pady=(10, 0))
        ttk.Button(buttons, text='Merge', command=lambda: self.safe(merge, win)).pack(side='right')
        ttk.Button(buttons, text='Cancel', command=win.destroy).pack(side='right', padx=4)
        dialog_keys(win, lambda: self.safe(merge, win))
        return win

    def family_history(self):
        fid = self.selected(self.fam_tree, 'family')
        f = self.store.family_detail(fid)
        win = tk.Toplevel(self.root)
        win.title(f"Booking history — {f['head']}")
        dialog_keys(win)
        win.geometry('880x600')
        frame = ttk.Frame(win, padding=10)
        frame.pack(fill='both', expand=True)
        columns = ('id', 'date', 'event', 'devotee', 'total', 'status')
        labels = ('Booking', 'Pooja date', 'Event', 'Devotee', 'Total', 'Payment')
        def rows(bookings, extra=None):
            out = []
            for b in bookings:
                e = json.loads(b['snapshot'])
                values = (b['id'], b['service_date'], e['name'], b['devotee'], f"{e['currency']} {fmt(b['total'])}", b['status'])
                out.append((b['id'], values + ((b['match'],) if extra else ())))
            return out
        ttk.Label(frame, text='Linked bookings', font=('', 12, 'bold')).pack(anchor='w')
        tree = self.table(frame, columns, labels, height=8)
        suggestions = self.store.link_suggestions(fid)
        ttk.Label(frame, text=f'Older unlinked bookings that look like this family ({len(suggestions)})',
                  font=('', 12, 'bold')).pack(anchor='w', pady=(10, 0))
        sug = self.table(frame, columns + ('match',), labels + ('Matched on',), height=6)
        def load():
            fresh = self.store.family_detail(fid)
            self.fill(tree, rows(fresh['bookings']))
            self.fill(sug, rows(self.store.link_suggestions(fid), True))
        def open_receipt(source):
            self.open_html(receipt(self.store.detail(self.selected(source, 'booking')), int(self.width.get())), 'devseva-receipt-')
        def link():
            self.need('link')
            self.store.link_booking(self.selected(sug, 'suggested booking'), fid, self.actor)
            load()
            self.refresh_devotees()
        def unlink():
            self.need('link')
            self.store.unlink_booking(self.selected(tree, 'linked booking'), self.actor)
            load()
            self.refresh_devotees()
        buttons = ttk.Frame(frame)
        buttons.pack(fill='x', pady=8)
        for title, command in (('Preview linked receipt', lambda: open_receipt(tree)), ('Unlink selected', unlink),
                               ('Preview suggested receipt', lambda: open_receipt(sug)), ('Link suggested booking', link)):
            ttk.Button(buttons, text=title, command=lambda c=command: self.safe(c, win)).pack(side='left', padx=3)
        ttk.Label(frame, text='Suggestions match the devotee name to any family member, or the phone number. '
                  'Check each one before linking.', foreground='#555').pack(anchor='w')
        load()
        return win

    # ----------------------------------------------------------------- reports
    def build_reports(self):
        tab = ttk.Frame(self.tabs, padding=6)
        self.tabs.add(tab, text='Reports / ವರದಿ')
        top = ttk.Frame(tab)
        top.pack(fill='x')
        self.rep_from = tk.StringVar(value=today())
        self.rep_to = tk.StringVar(value=today())
        self.rep_event = tk.StringVar(value='All events')
        for label, var in (('From', self.rep_from), ('To', self.rep_to)):
            ttk.Label(top, text=label).pack(side='left', padx=(6, 2))
            ttk.Entry(top, textvariable=var, width=12).pack(side='left')
        ttk.Label(top, text='  Event').pack(side='left')
        self.rep_combo = ttk.Combobox(top, textvariable=self.rep_event, state='readonly', width=34)
        self.rep_combo.pack(side='left', padx=4)
        quick = ttk.Frame(tab)
        quick.pack(fill='x', pady=6)
        def period(kind):
            d = dt.date.today()
            start = {'today': d, 'week': d - dt.timedelta(days=d.weekday()), 'month': d.replace(day=1), 'year': d.replace(month=1, day=1)}[kind]
            self.rep_from.set(start.isoformat())
            self.rep_to.set(d.isoformat())
            self.show_report()
        for title, kind in (('Today', 'today'), ('This week', 'week'), ('This month', 'month'), ('This year', 'year')):
            ttk.Button(quick, text=title, command=lambda k=kind: self.safe(lambda: period(k))).pack(side='left', padx=3)
        for title, command in (('Show report', self.show_report), ('Print report', self.print_report),
                               ('Export slip-level CSV', self.export_report)):
            ttk.Button(quick, text=title, command=lambda c=command: self.safe(c)).pack(side='left', padx=3)
        self.rep_text = tk.Text(tab, wrap='none', font=('Menlo' if sys.platform == 'darwin' else 'Courier', 12))
        self.rep_text.pack(fill='both', expand=True)

    def current_report(self):
        self.need('reports')
        event_id = self.event_choices(active_only=False, include_all=True).get(self.rep_event.get())
        return self.store.report(self.rep_from.get(), self.rep_to.get(), event_id), event_id

    def show_report(self):
        rep, _ = self.current_report()
        self.rep_text.config(state='normal')
        self.rep_text.delete('1.0', 'end')
        self.rep_text.insert('end', f'Event filter: {self.rep_event.get()}\n' + report_text(rep))
        self.rep_text.config(state='disabled')

    def print_report(self):
        rep, _ = self.current_report()
        self.open_html(report_html(rep, f'Collection report — {self.rep_event.get()}'), 'devseva-report-')

    def export_report(self):
        rep, event_id = self.current_report()
        dest = filedialog.asksaveasfilename(defaultextension='.csv', initialfile=f"devseva-slips-{rep['start']}-to-{rep['end']}.csv")
        if dest:
            self.store.export_lines(dest, rep['start'], rep['end'], event_id)
            messagebox.showinfo('Export', 'Slip-level report saved. A slip is included if it was booked, paid or scheduled in the period.')

    # ----------------------------------------------------------------- masters
    def build_masters(self):
        tab = ttk.Frame(self.tabs, padding=6)
        self.tabs.add(tab, text='Masters / ವಿವರಗಳು')
        org_line = ttk.Frame(tab)
        org_line.pack(fill='x', pady=(0, 8))
        tip(ttk.Button(org_line, text='Temple / organisation details…', command=lambda: self.safe(self.org_settings)),
            'The temple name shown at the top, on the login screen and on receipts (Admin).').pack(side='left')
        self.org_summary = ttk.Label(org_line, text='', foreground='#555')
        self.org_summary.pack(side='left', padx=10)
        ttk.Label(tab, text='1. Events and pooja calendars — create the festival or regular daily pooja first').pack(anchor='w')
        self.button_row(tab, [('Add event / calendar', self.edit_event),
                              ('Edit selected', lambda: self.edit_event(self.selected(self.events, 'event'))),
                              ('Archive / restore', lambda: self.toggle('events', self.events)),
                              ('Permanently delete', lambda: self.delete_selected_master('events', self.events))])
        # Action rows must appear before their tables. The window can be short
        # and a table may be long, but Add must always be immediately visible.
        self.events = self.table(tab, ('id', 'name', 'type', 'day', 'end', 'days', 'place', 'currency', 'status'),
                                 ('ID', 'Name', 'Type', 'Date / start', 'End', 'Days', 'Place', 'Cur.', 'Status'), height=4,
                                 widths={'id': 40, 'type': 60, 'currency': 50, 'status': 70, 'name': 240}, expand=False)
        ttk.Label(tab, text='2. Sevas, sponsorships and in-kind categories — choose the event/calendar for each seva').pack(anchor='w', pady=(8, 0))
        self.button_row(tab, [('Add seva / sponsorship', self.edit_seva),
                              ('Edit selected seva', lambda: self.edit_seva(self.selected(self.sevas, 'seva'))),
                              ('Archive / restore', lambda: self.toggle('sevas', self.sevas)),
                              ('View full list…', self.show_seva_list),
                              ('Permanently delete', lambda: self.delete_selected_master('sevas', self.sevas))])
        self.sevas = self.table(tab, ('id', 'event', 'name', 'kn', 'kind', 'price', 'limit', 'status'),
                                ('ID', 'Event', 'Seva', 'Kannada', 'Type', 'Default amount', 'Per-day limit', 'Status'), height=4,
                                widths={'id': 40, 'status': 70, 'limit': 90}, expand=False)
        ttk.Label(tab, text='Archived items stay in history and reports but are hidden from new bookings. Existing receipts keep their original details and rates.').pack(anchor='w')

    def show_seva_list(self):
        """Open a dedicated, filterable list so every seva remains accessible."""
        self.need('masters')
        win = tk.Toplevel(self.root)
        win.title('All sevas, poojas and contributions')
        win.geometry('1040x620')
        win.minsize(760, 420)
        win.transient(self.root)
        top = ttk.Frame(win, padding=(12, 12, 12, 6))
        top.pack(fill='x')
        ttk.Label(top, text='Event / calendar:').pack(side='left')
        event_var = tk.StringVar(value='All events')
        event_options = self.event_choices(active_only=False, include_all=True)
        event_combo = ttk.Combobox(top, textvariable=event_var, values=list(event_options), state='readonly', width=38)
        event_combo.pack(side='left', padx=(6, 14))
        ttk.Label(top, text='Status:').pack(side='left')
        status_var = tk.StringVar(value='Active')
        status_combo = ttk.Combobox(top, textvariable=status_var, values=('Active', 'Archived', 'All'), state='readonly', width=11)
        status_combo.pack(side='left', padx=6)
        count_label = ttk.Label(top, text='')
        count_label.pack(side='right')
        tree = self.table(win, ('id', 'event', 'name', 'kn', 'kind', 'price', 'limit', 'status'),
                          ('ID', 'Event / calendar', 'Seva / contribution', 'Kannada', 'Type', 'Default amount', 'Per-day limit', 'Status'),
                          height=18, widths={'id': 55, 'event': 210, 'name': 220, 'kn': 190, 'kind': 90, 'price': 110, 'limit': 110, 'status': 80})
        tree.master.pack_configure(padx=12, pady=(0, 8))

        def refresh_list(*_):
            cat = self.store.catalog()
            names = {e['id']: e['name'] for e in cat['events']}
            selected_event = event_options.get(event_var.get())
            status = status_var.get()
            rows = []
            for s in cat['sevas']:
                if selected_event is not None and s['event_id'] != selected_event:
                    continue
                if status == 'Active' and not s['active']:
                    continue
                if status == 'Archived' and s['active']:
                    continue
                rows.append((s['id'], (s['id'], names.get(s['event_id'], str(s['event_id'])), s['name'], s['kannada'],
                                       s['kind'], fmt(s['price']), s['daily_limit'] or 'No limit',
                                       'Active' if s['active'] else 'Archived')))
            self.fill(tree, rows)
            count_label.config(text=f'{len(rows)} item' + ('' if len(rows) == 1 else 's'))

        def edit_selected():
            ident = self.selected(tree, 'seva')
            self.edit_seva(ident)
            win.after(100, refresh_list)

        buttons = ttk.Frame(win, padding=(12, 0, 12, 12))
        buttons.pack(fill='x')
        ttk.Button(buttons, text='Add seva / sponsorship', command=lambda: (self.edit_seva(), win.after(100, refresh_list))).pack(side='left')
        ttk.Button(buttons, text='Edit selected', command=lambda: self.safe(edit_selected, win)).pack(side='left', padx=6)
        ttk.Button(buttons, text='Close', command=win.destroy).pack(side='right')
        event_combo.bind('<<ComboboxSelected>>', refresh_list)
        status_combo.bind('<<ComboboxSelected>>', refresh_list)
        tree.bind('<Double-1>', lambda _: self.safe(edit_selected, win))
        dialog_keys(win, lambda: self.safe(edit_selected, win))
        refresh_list()

    def refresh_masters(self):
        org = self.org()
        self.org_summary.config(text=' · '.join(x for x in (org.get('org_name'), org.get('org_name_kn'), org.get('org_place')) if x)
                                or 'Not set yet — shown on receipts and at the top of the screen.')
        cat = self.store.catalog()
        names = {e['id']: e['name'] for e in cat['events']}
        self.fill(self.events, [(e['id'], (e['id'], e['name'], e['recurrence'], e['day'], e['end_day'] or '—',
                                           weekday_text(e['weekdays']) if e['recurrence'] == 'Daily' else '—', e['place'],
                                           e['currency'], 'Active' if e['active'] else 'Archived')) for e in cat['events']])
        self.fill(self.sevas, [(s['id'], (s['id'], names.get(s['event_id'], s['event_id']), s['name'], s['kannada'], s['kind'],
                                          fmt(s['price']), s['daily_limit'] or 'No limit', 'Active' if s['active'] else 'Archived'))
                               for s in cat['sevas']])
        # Keep the first available master record visibly selected so the
        # Edit, Archive and Permanently delete actions always have an obvious
        # target. Existing selections are preserved by fill().
        for tree in (self.events, self.sevas):
            if tree.get_children() and not tree.selection():
                first = tree.get_children()[0]
                tree.selection_set(first)
                tree.focus(first)
                tree.see(first)
        choices = list(self.event_choices(active_only=False, include_all=True))
        for combo, var in ((self.sched_combo, self.sched_event), (self.rep_combo, self.rep_event)):
            combo.config(values=choices)
            if var.get() not in choices:
                var.set('All events')

    def toggle(self, table, tree):
        self.need('masters')
        ident = self.selected(tree)
        active = tree.set(str(ident), 'status') == 'Active'
        self.store.set_active(table, ident, not active, self.actor)
        self.refresh()

    def delete_selected_master(self, table, tree):
        self.need('masters')
        ident = self.selected(tree, 'master record')
        row = next((r for r in self.store.catalog()['events' if table == 'events' else 'sevas'] if r['id'] == ident), None)
        if not row:
            raise ValueError('Master record not found.')
        kind = 'event / calendar' if table == 'events' else 'seva / contribution'
        if not messagebox.askyesno('Permanently delete',
                                   f"Permanently delete this {kind}?\n\n{row['name']}\n\n"
                                   'This cannot be undone from DevSeva. A safety backup will be saved first.',
                                   icon='warning', parent=self.root):
            return
        safety = self.store.auto_backup(self.backups_folder(), prefix='before-delete', keep=10)
        self.store.delete_master(table, ident, self.actor)
        self.refresh()
        messagebox.showinfo('Deleted', f"The {kind} was permanently deleted.\n\nSafety backup: {safety.name}", parent=self.root)

    def edit_event(self, ident=None):
        self.need('masters')
        e = next((x for x in self.store.catalog()['events'] if x['id'] == ident), {})
        fields = [('name', 'Event / calendar name', e.get('name', ''), None),
                  ('kannada', 'Kannada name / ಕನ್ನಡ ಹೆಸರು', e.get('kannada', ''), None),
                  ('recurrence', 'Type', e.get('recurrence', 'Once'), list(RECURRENCES)),
                  ('day', 'Date (Once) or start date (Daily) YYYY-MM-DD', e.get('day', today()), None),
                  ('end_day', 'End date (Daily only, optional)', e.get('end_day', ''), None),
                  ('weekdays', 'Days (Daily only): All or e.g. Mon, Fri', weekday_text(e.get('weekdays')), None),
                  ('place', 'Place / ಸ್ಥಳ', e.get('place', ''), None),
                  ('currency', 'Currency', e.get('currency', 'AED'), list(CURRENCIES))]
        self.form('Event / pooja calendar', fields, lambda v: self.store.event(v, ident, self.actor), kannada=('name', 'kannada', 'label'))

    def edit_seva(self, ident=None):
        self.need('masters')
        cat = self.store.catalog()
        if not cat['events']:
            raise ValueError('Create an event or daily pooja calendar first.')
        options = {f"{e['id']} · {e['name']}": e['id'] for e in cat['events']}
        s = next((x for x in cat['sevas'] if x['id'] == ident), {})
        selected = next((k for k, val in options.items() if val == s.get('event_id')), next(iter(options)))
        fields = [('event_id', 'Event / calendar', selected, list(options)),
                  ('name', 'Seva / contribution name', s.get('name', ''), None),
                  ('kannada', 'Kannada name', s.get('kannada', ''), None),
                  ('kind', 'Type', s.get('kind', 'Seva'), list(KINDS)),
                  ('price', 'Default cash amount', f"{s.get('price', 0) / 100:.2f}", None),
                  ('daily_limit', 'Per-day limit (0 = no limit)', s.get('daily_limit', 0), None)]
        def save(v):
            v['event_id'] = options[v['event_id']]
            self.store.seva(v, ident, self.actor)
        self.form('Seva master', fields, save, kannada=('name', 'kannada', 'label'))

    # ------------------------------------------------------------------ global
    def refresh(self):
        if not self.user:
            return
        self.version_seen = self.store.data_version()
        self.refresh_counter()
        self.refresh_bookings()
        self.refresh_masters()
        self.safe_schedule()
        self.refresh_devotees()

    def poll(self):
        try:
            if self.user:
                if time.monotonic() - self.last_activity > IDLE_LOCK_MINUTES * 60:
                    self.lock()
                elif self.store.data_version() != self.version_seen:
                    self.refresh()  # only when something changed, e.g. a phone booking
        except Exception as ex:
            self.status.config(text=f'Refresh problem: {ex}')
        self.root.after(4000, self.poll)

    def backups_folder(self):
        return self.folder / 'backups'

    def backup(self):
        self.need('backup')
        dest = filedialog.asksaveasfilename(defaultextension='.sqlite3', initialfile=f'devseva-backup-{today()}.sqlite3')
        if dest:
            if Path(dest).resolve() == self.db_path.resolve():
                raise ValueError('Choose a different backup file.')
            self.store.backup(dest)
            messagebox.showinfo('Backup', 'Database backup saved. Copy it to a USB drive or other safe place.')

    def restore(self):
        self.need('restore')
        source = filedialog.askopenfilename(title='Choose a DevSeva backup to restore',
                                            initialdir=str(self.backups_folder()) if self.backups_folder().exists() else None,
                                            filetypes=[('DevSeva backup', '*.sqlite3 *.db'), ('All files', '*')])
        if not source:
            return
        count = Store.check_backup(source)
        if not messagebox.askyesno('Restore backup',
                                   f'Replace ALL current DevSeva data with this backup?\n\n{Path(source).name}\n'
                                   f'Bookings in the backup: {count}\n\n'
                                   'A safety copy of the current data is saved first in the "backups" folder. '
                                   'Mobile access will stop and everyone will need to log in again.', icon='warning'):
            return
        self.stop_mobile()
        self.close_windows()
        safety = self.store.restore(source, self.backups_folder(), self.actor)
        self.store = Store(self.db_path)
        messagebox.showinfo('Restore complete', f'Backup restored ({count} bookings).\n\nThe previous data was saved as:\n{safety}\n\n'
                            'Log in again. If the backup is from before staff logins existed, you will be asked to create an Admin.')
        self.lock()

    def export(self):
        self.need('reports')
        dest = filedialog.asksaveasfilename(defaultextension='.csv', initialfile='devseva-register.csv')
        if dest:
            self.store.export(dest)
            messagebox.showinfo('Export', 'Booking register saved. AED and INR remain separate.')

    # ------------------------------------------------------------------- staff
    def staff(self):
        self.need('staff')
        win = tk.Toplevel(self.root)
        win.title('Staff logins')
        dialog_keys(win)
        win.geometry('720x460')
        win.transient(self.root)
        frame = ttk.Frame(win, padding=10)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Admin: everything · Supervisor: refunds, cancellations, corrections, mobile access, backups · '
                  'Cashier: bookings and payments · Reception: bookings and devotees only', wraplength=680).pack(anchor='w')
        tree = self.table(frame, ('id', 'name', 'role', 'active'), ('ID', 'Name', 'Role', 'Active'), widths={'id': 50})
        def load():
            self.fill(tree, [(x['id'], (x['id'], x['name'], x['role'], 'Yes' if x['active'] else 'No')) for x in self.store.staff_list()])
        def add():
            def save(v):
                if v['pin'] != v['pin2']:
                    raise ValueError('The two PINs do not match.')
                self.store.add_staff(v['name'], v['role'], v['pin'], self.actor)
                load()
            w = self.form('Add staff login', [('name', 'Name', '', None), ('role', 'Role', 'Reception', list(security.ROLES)),
                                              ('pin', 'PIN (4–12 digits)', '', None), ('pin2', 'Repeat PIN', '', None)], save, parent=win)
            self.mask_pins(w)
        def edit():
            ident = self.selected(tree, 'staff login')
            row = next(x for x in self.store.staff_list() if x['id'] == ident)
            def save(v):
                self.store.update_staff(ident, v['role'], v['active'] == 'Yes', self.actor)
                load()
            self.form(f"Edit {row['name']}", [('role', 'Role', row['role'], list(security.ROLES)),
                                              ('active', 'Can log in', 'Yes' if row['active'] else 'No', ['Yes', 'No'])], save, parent=win)
        def reset():
            ident = self.selected(tree, 'staff login')
            def save(v):
                if v['pin'] != v['pin2']:
                    raise ValueError('The two PINs do not match.')
                self.store.set_pin(ident, v['pin'], self.actor)
                messagebox.showinfo(APP_NAME, 'PIN reset. The login is unlocked.', parent=win)
            w = self.form('Reset PIN', [('pin', 'New PIN', '', None), ('pin2', 'Repeat PIN', '', None)], save, parent=win)
            self.mask_pins(w)
        self.button_row(frame, [('Add staff', add), ('Change role / disable', edit), ('Reset PIN', reset)])
        load()
        return win

    @staticmethod
    def mask_pins(win):
        frame = win.winfo_children()[0]
        labels = [w for w in frame.winfo_children() if w.winfo_class() == 'TLabel']
        entries = [w for w in frame.winfo_children() if w.winfo_class() in ('TEntry', 'TCombobox')]
        for label, entry in zip(labels, entries):
            if 'PIN' in label.cget('text') and entry.winfo_class() == 'TEntry':
                entry.configure(show='•')

    # ------------------------------------------------------------------ mobile
    def stop_mobile(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
            self.server_info = None
            self.mobile_state.config(text='📵 Phone entry off')
            if getattr(self, 'mobile_win', None) is not None and self.mobile_win.winfo_exists():
                self.mobile_win.destroy()

    def mobile(self):
        self.need('mobile')
        if self.server:
            return self.mobile_window()  # already running: show the QR code again (Stop is inside)
        if not messagebox.askyesno('Enable phone entry',
                                   'Connect phones and this laptop to a private, password-protected Wi-Fi or hotspot. '
                                   'Never use public Wi-Fi.\n\nVolunteers scan a QR code with their phone camera, '
                                   'then enter their own name and PIN. Enable phone entry?'):
            return
        addresses = security.local_addresses()
        cert = key = None
        try:
            cert, key = security.ensure_certificate(self.folder / 'tls', addresses)
        except Exception as ex:
            messagebox.showerror('Encryption unavailable',
                                 f'{ex}\n\nPhone entry was not started. DevSeva requires an encrypted HTTPS connection to protect staff PINs and booking details.')
            return
        self.server, self.server_info = start(self.store, 8765, cert, key)
        self.server_info.update(addresses=addresses, cert=cert)
        info = self.server_info
        self.mobile_state.config(text='📱 Phone entry ON · encrypted — click for QR code')
        return self.mobile_window()

    def phone_links(self):
        info = self.server_info
        hosts = info.get('addresses') or ['127.0.0.1']
        return {host: qr.android_access_link(info['scheme'], host, info['port'], info['code']) for host in hosts}

    def mobile_window(self):
        info = self.server_info
        if getattr(self, 'mobile_win', None) is not None and self.mobile_win.winfo_exists():
            self.mobile_win.deiconify()
            self.mobile_win.lift()
            self.mobile_win.focus_force()
            return self.mobile_win
        win = tk.Toplevel(self.root)
        self.mobile_win = win
        win.title('Phone entry — scan to connect')
        win.transient(self.root)
        win.resizable(False, False)
        dialog_keys(win)
        mono = 'Menlo' if sys.platform == 'darwin' else 'Courier'
        frame = ttk.Frame(win, padding=18)
        frame.pack(fill='both', expand=True)
        left = ttk.Frame(frame)
        left.grid(row=0, column=0, sticky='n')
        right = ttk.Frame(frame)
        right.grid(row=0, column=1, sticky='nw', padx=(22, 0))
        links = self.phone_links()
        host = tk.StringVar(value=next(iter(links)))
        qr_label = ttk.Label(left)
        qr_label.pack()
        link_label = ttk.Label(left, font=(mono, 13, 'bold'))
        link_label.pack(pady=(8, 0))
        chooser = ttk.Frame(left)
        if len(links) > 1:
            chooser.pack(pady=(6, 0))
            ttk.Label(chooser, text='Laptop address:').pack(side='left')
            tip(ttk.Combobox(chooser, textvariable=host, values=list(links), state='readonly', width=16),
                'This laptop has more than one network address. Choose the one on the same Wi-Fi as the phones.').pack(side='left', padx=4)

        def draw(*_):
            win.qr_image = qr.photo(tk, win, links[host.get()], pixels=320)
            qr_label.config(image=win.qr_image)
            link_label.config(text=f"{info['scheme']}://{host.get()}:{info['port']}")
        host.trace_add('write', draw)
        draw()

        ttk.Label(right, text='Scan with the phone camera', font=('', 20, 'bold')).pack(anchor='w')
        steps = ['Join this laptop\'s Wi-Fi / hotspot, then point the camera at the code and tap the link.',
                 'First time only: the phone says the connection is not private — tap Advanced / Show details → Proceed / visit website.',
                 'Enter your own name and PIN. The access code is filled in by the QR code.',
                 'Optional: add DevSeva to the home screen (Share → Add to Home Screen on iPhone, ⋮ → Add to Home screen on Android).']
        for n, step in enumerate(steps, 1):
            ttk.Label(right, text=f'{n}.  {step}', wraplength=420, justify='left').pack(anchor='w', pady=3)
        ttk.Label(right, text='Access code (for typing by hand):', foreground='#555').pack(anchor='w', pady=(14, 0))
        ttk.Label(right, text=info['code'], font=(mono, 24, 'bold')).pack(anchor='w')
        detail = ('Encrypted with this laptop\'s own certificate. Its SHA-256 fingerprint starts with '
                  + security.fingerprint(info['cert'])[:23] + '.')
        ttk.Label(right, text=detail, wraplength=420, foreground='#555').pack(anchor='w', pady=(10, 0))
        ttk.Label(right, text='The code changes every time phone entry is started, so old QR photos and printouts stop working. '
                  'Allow incoming connections if the Mac firewall asks, and keep the laptop awake.',
                  wraplength=420, foreground='#555').pack(anchor='w', pady=(6, 0))
        buttons = ttk.Frame(right)
        buttons.pack(anchor='w', pady=(16, 0))

        def print_sheet():
            self.open_html(qr_sheet_html(links[host.get()], info, self.store), 'devseva-qr-')

        def copy_link():
            self.root.clipboard_clear()
            self.root.clipboard_append(links[host.get()])
            copied.config(text='Link copied — paste it into WhatsApp to send it to a volunteer.')

        def stop():
            if messagebox.askyesno('Stop phone entry', 'Stop phone entry? Every phone is logged out and this QR code stops working.', parent=win):
                self.stop_mobile()
                win.destroy()
        for title, command, help_text in (
                ('Print QR sheet', print_sheet, 'Open a printable page with this QR code for the counter table.'),
                ('Copy link', copy_link, 'Copy the phone link (it includes the access code).'),
                ('Stop phone entry', stop, 'Log out every phone and turn phone entry off.'),
                ('Close', win.destroy, 'Hide this window; phone entry keeps running (Esc).')):
            tip(ttk.Button(buttons, text=title, command=lambda c=command: self.safe(c, win)), help_text).pack(side='left', padx=(0, 6))
        copied = ttk.Label(right, text='', foreground='#1b6b34')
        copied.pack(anchor='w', pady=(6, 0))
        win.update_idletasks()
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - win.winfo_reqwidth()) // 2)
        y = self.root.winfo_rooty() + 40
        win.geometry(f'+{x}+{y}')
        win.lift()
        win.focus_force()  # so Esc works straight away
        return win

    def close(self):
        self.stop_mobile()
        try:
            self.store.auto_backup(self.backups_folder(), keep=AUTO_BACKUPS_KEPT)
        except Exception as ex:
            if not messagebox.askyesno(APP_NAME, f'The automatic backup failed: {ex}\n\nQuit anyway?'):
                return
        for path in self.previews:
            try:
                os.remove(path)
            except OSError:
                pass
        self.root.destroy()


def self_test():
    """Quick check used by the build script and for support: no window, no real data touched."""
    import shutil
    checks = []
    folder = Path(tempfile.mkdtemp(prefix='devseva-selftest-'))
    try:
        store = Store(folder / 'test.sqlite3')
        store.add_staff('Self Test', 'Admin', '4821')
        checks.append(('database and PIN login', store.login('Self Test', '4821')['role'] == 'Admin'))
        event = store.event(dict(name='Test', day=today(), place='Here', currency='INR'))
        seva = store.seva(dict(event_id=event, name='Pooja', price='10', kind='Seva'))
        bid = store.book(dict(request_key='t', event_id=event, devotee='Test', items=[dict(seva_id=seva, quantity=1)]), 'Self test')
        checks.append(('booking and receipt', 'Pooja' in receipt(store.detail(bid))))
        checks.append(('phone page file', Path(__import__('mobile').page_path()).exists()))
        checks.append(('developer module', callable(developer.Guard(folder).verify)))
        if getattr(sys, 'frozen', False):
            checks.append(('developer key inside the app', developer.has_key()))
        store.save_settings({'org_name': 'Self Test Temple'}, 'Self test')
        checks.append(('organisation on receipt', 'Self Test Temple' in receipt(store.detail(bid))))
        checks.append(('factory reset', store.factory_reset('Self test') > 0 and not Store(folder / 'test.sqlite3').has_staff()))
        try:
            security.ensure_certificate(folder / 'tls', ['127.0.0.1'])
            checks.append(('encryption certificate', True))
        except Exception as ex:
            checks.append((f'encryption certificate ({ex})', False))
        checks.append(('Tk version ' + str(tk.TkVersion), tk.TkVersion >= 8.6))
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    for name, ok in checks:
        print(('OK    ' if ok else 'FAIL  ') + name)
    return 0 if all(ok for _, ok in checks) else 1


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        sys.exit(self_test())
    root = tk.Tk()
    App(root)
    root.mainloop()
