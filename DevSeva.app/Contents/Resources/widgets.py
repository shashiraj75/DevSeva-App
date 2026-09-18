# DevSeva — © 2026 Raviraj Shetty. All rights reserved.
"""Small Tk helpers for DevSeva: type-to-search fields, tooltips and keyboard handling."""
import sys
import tkinter as tk
from tkinter import ttk
from kannada import rank_choices

MAC = sys.platform == 'darwin'
ACCEL = 'Command' if MAC else 'Control'


class Tooltip:
    """Shows a short help text when the pointer rests on a widget."""
    def __init__(self, widget, text, delay=600):
        self.widget, self.text, self.delay = widget, text, delay
        self.tip = self.job = None
        widget.bind('<Enter>', self.schedule, add='+')
        widget.bind('<Leave>', self.hide, add='+')
        widget.bind('<ButtonPress>', self.hide, add='+')

    def schedule(self, _=None):
        self.cancel()
        self.job = self.widget.after(self.delay, self.show)

    def cancel(self):
        if self.job:
            self.widget.after_cancel(self.job)
            self.job = None

    def show(self):
        if self.tip or not self.widget.winfo_viewable():
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f'+{x}+{y}')
        tk.Label(self.tip, text=self.text, justify='left', wraplength=340, background='#fffbe6', foreground='#222',
                 relief='solid', borderwidth=1, padx=8, pady=5).pack()

    def hide(self, _=None):
        self.cancel()
        if self.tip:
            self.tip.destroy()
            self.tip = None


def tip(widget, text):
    Tooltip(widget, text)
    return widget


class AutoComplete(ttk.Entry):
    """Entry that suggests list items as you type ("kar" → "Karka / ಕರ್ಕ").

    ↑/↓ move through suggestions, Enter or Tab picks one, Esc closes the list.
    Leaving the field with a partial word picks the best match.
    """
    def __init__(self, master, choices, textvariable=None, allow_blank=True, **kw):
        self.var = textvariable or tk.StringVar()
        super().__init__(master, textvariable=self.var, **kw)
        self.choices = [c for c in choices if c]
        self.allow_blank = allow_blank
        self.popup = self.listbox = None
        self.bind('<KeyRelease>', self.on_key)
        self.bind('<Down>', lambda e: self.move(1))
        self.bind('<Up>', lambda e: self.move(-1))
        self.bind('<Return>', self.accept)
        self.bind('<KP_Enter>', self.accept)
        self.bind('<Tab>', self.accept_tab)
        self.bind('<Escape>', self.escape)
        self.bind('<FocusOut>', lambda e: self.after(150, self.focus_left))
        self.bind('<Destroy>', lambda e: self.close(), add='+')

    def matches(self):
        text = self.var.get()
        return self.choices if text in self.choices or not text.strip() else rank_choices(text, self.choices)

    def on_key(self, event):
        if event.keysym in ('Up', 'Down', 'Return', 'KP_Enter', 'Escape', 'Tab', 'Shift_L', 'Shift_R'):
            return
        found = rank_choices(self.var.get(), self.choices) if self.var.get().strip() else []
        self.show(found[:12]) if found and self.var.get() not in self.choices else self.close()

    def show(self, items):
        if not self.winfo_viewable():
            return
        if not self.popup:
            self.popup = tk.Toplevel(self)
            self.popup.wm_overrideredirect(True)
            self.listbox = tk.Listbox(self.popup, height=6, activestyle='dotbox', exportselection=False)
            self.listbox.pack(fill='both', expand=True)
            self.listbox.bind('<ButtonRelease-1>', lambda e: self.choose(self.listbox.get(self.listbox.nearest(e.y))))
        self.listbox.delete(0, 'end')
        for item in items:
            self.listbox.insert('end', item)
        self.listbox.config(height=min(len(items), 8))
        self.listbox.selection_clear(0, 'end')
        self.listbox.selection_set(0)
        x, y = self.winfo_rootx(), self.winfo_rooty() + self.winfo_height()
        self.popup.wm_geometry(f'{max(self.winfo_width(), 260)}x{min(len(items), 8) * 22 + 6}+{x}+{y}')
        self.popup.lift()

    def move(self, step):
        if not self.popup:
            items = self.matches()
            if items:
                self.show(items[:12])
            return 'break'
        size = self.listbox.size()
        current = (self.listbox.curselection() or (0,))[0]
        new = max(0, min(size - 1, current + step))
        self.listbox.selection_clear(0, 'end')
        self.listbox.selection_set(new)
        self.listbox.see(new)
        return 'break'

    def choose(self, value):
        self.var.set(value)
        self.icursor('end')
        self.close()
        self.event_generate('<<Chosen>>')

    def accept(self, _=None):
        if self.popup:
            selected = self.listbox.curselection()
            self.choose(self.listbox.get(selected[0] if selected else 0))
            return 'break'  # Enter picked a suggestion; it must not also submit the form
        self.settle()
        return None

    def accept_tab(self, _=None):
        if self.popup:
            self.accept()
        else:
            self.settle()

    def escape(self, _=None):
        if self.popup:
            self.close()
            return 'break'
        return None

    def settle(self):
        text = self.var.get().strip()
        if text and text not in self.choices:
            found = rank_choices(text, self.choices)
            if found:
                self.var.set(found[0])

    def focus_left(self):
        try:
            focused = self.focus_get()
        except (KeyError, tk.TclError):
            focused = None
        if self.popup and focused is self.listbox:
            return
        self.close()
        if self.winfo_exists():
            self.settle()

    def close(self):
        if self.popup:
            try:
                self.popup.destroy()
            except tk.TclError:
                pass
            self.popup = self.listbox = None


def no_tabs(win):
    """macOS may open new windows as tabs of a full-screen main window; keep dialogs as separate windows."""
    try:
        win.wm_attributes('-tabbingmode', 'disallowed')
    except tk.TclError:
        pass  # older Tk or not macOS


def dialog_keys(win, ok=None, cancel=None):
    """Enter runs `ok`, Esc (and ⌘W / Ctrl+W) runs `cancel` (default: close the window)."""
    cancel = cancel or win.destroy
    no_tabs(win)

    def on_enter(event):
        if isinstance(event.widget, (tk.Text, tk.Listbox)) or getattr(event.widget, 'popup', None):
            return None
        if isinstance(event.widget, (ttk.Button, tk.Button)):
            event.widget.invoke()
            return 'break'
        if ok:
            ok()
            return 'break'
        return None

    win.bind('<Return>', on_enter)
    win.bind('<KP_Enter>', on_enter)

    def on_tab(event, backwards=False):
        # Aqua can leave keyboard traversal disabled at the system level.
        # Drive the dialog's focus order explicitly so Tab behaves the same
        # on every supported platform.  Widgets such as AutoComplete handle
        # Tab at their own binding level first and keep their accept behavior.
        if getattr(event.widget, 'popup', None):
            return None
        command = 'tk_focusPrev' if backwards else 'tk_focusNext'
        try:
            target = win.tk.call(command, event.widget._w)
            if target:
                win.nametowidget(target).focus_set()
                return 'break'
        except (tk.TclError, KeyError):
            pass
        return None

    win.bind('<Tab>', on_tab)
    win.bind('<Shift-Tab>', lambda e: on_tab(e, True))

    def on_escape(_event):
        # Returning "break" prevents the key from leaking into the parent
        # window (which could clear a search field or trigger another action).
        if win.winfo_exists():
            cancel()
        return 'break'

    win.bind('<Escape>', on_escape, add='+')
    win.bind(f'<{ACCEL}-w>', on_escape, add='+')
    return win
