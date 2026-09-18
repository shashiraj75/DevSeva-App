"""Run with Python 3.10+ on Windows or macOS: python app.py"""
import datetime as dt
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import uuid
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from core import Store, receipt
from mobile import start
from kannada import bind_suggestion, translate_label, RASHIS, NAKSHATRAS


def data_folder():
    if sys.platform == 'win32':
        base = Path(os.environ.get('LOCALAPPDATA', str(Path.home())))
    elif sys.platform == 'darwin':
        base = Path.home() / 'Library' / 'Application Support'
    else:
        base = Path.home() / '.local' / 'share'
    folder = base / 'SevaDeskPrototype'
    folder.mkdir(parents=True, exist_ok=True)
    return folder


class App:
    def __init__(self, root):
        self.root = root
        self.folder = data_folder()
        self.store = Store(self.folder / 'seva-desk.sqlite3')
        self.server = None
        self.previews = []
        root.title('Seva Desk / ಸೇವಾ ಕೇಂದ್ರ — offline prototype')
        root.geometry('1120x740')
        root.minsize(900, 600)
        style = ttk.Style()
        style.configure('TButton', padding=7)
        ttk.Label(root, text='Seva Desk / ಸೇವಾ ಕೇಂದ್ರ', font=('',22,'bold')).pack(anchor='w',padx=18,pady=(15,3))
        ttk.Label(root, text='Offline event registration • Separate seva slips • Cashier collection').pack(anchor='w',padx=18)
        bar = ttk.Frame(root); bar.pack(fill='x',padx=15,pady=10)
        for title,command in [('New booking / ನೋಂದಣಿ',self.booking),('Mobile access',self.mobile),('Backup database',self.backup),('Export register CSV',self.export)]:
            ttk.Button(bar,text=title,command=lambda c=command:self.safe(c)).pack(side='left',padx=3)
        self.width = tk.StringVar(value='80')
        ttk.Label(bar,text='Paper mm:').pack(side='left',padx=8)
        ttk.Combobox(bar,textvariable=self.width,values=['58','80'],width=4,state='readonly').pack(side='left')
        tabs=ttk.Notebook(root);tabs.pack(fill='both',expand=True,padx=15,pady=5)
        self.books=ttk.Frame(tabs); self.setup=ttk.Frame(tabs)
        tabs.add(self.books,text='Bookings and cashier / ನೋಂದಣಿ');tabs.add(self.setup,text='Event and seva masters / ವಿವರಗಳು')
        self.tree=self.table(self.books,('id','event','devotee','currency','amount','status','print'),('Booking','Event','Devotee','Currency','Total','Payment','Print queue'))
        buttons=ttk.Frame(self.books);buttons.pack(fill='x',pady=8)
        for title,command in [('Preview / print slips',self.preview),('Confirm printed',self.printed),('Receive payment',self.pay),('Cancel unpaid booking',self.void),('Refresh',self.refresh)]:
            ttk.Button(buttons,text=title,command=lambda c=command:self.safe(c)).pack(side='left',padx=3)
        self.summary=ttk.Label(self.books,text='');self.summary.pack(anchor='w',pady=8)
        self.events=self.table(self.setup,('id','name','day','place','currency'),('ID','Event','Date','Place','Currency'),height=5)
        eb=ttk.Frame(self.setup);eb.pack(fill='x')
        ttk.Button(eb,text='Add event',command=lambda:self.edit_event()).pack(side='left')
        ttk.Button(eb,text='Edit selected event',command=lambda:self.safe(lambda:self.edit_event(self.selected(self.events)))).pack(side='left')
        self.sevas=self.table(self.setup,('id','event','name','kind','price'),('ID','Event ID','Seva','Type','Default amount'),height=6)
        sb=ttk.Frame(self.setup);sb.pack(fill='x')
        ttk.Button(sb,text='Add seva / sponsorship',command=lambda:self.safe(self.edit_seva)).pack(side='left')
        ttk.Button(sb,text='Edit selected seva',command=lambda:self.safe(lambda:self.edit_seva(self.selected(self.sevas)))).pack(side='left')
        ttk.Label(self.setup,text='Create an event, then its sevas. Existing receipts keep their original details and rates.').pack(anchor='w',pady=10)
        ttk.Label(root,text='Prototype: print preview requires the system print dialog. Keep the laptop awake during mobile entry.').pack(anchor='w',padx=15,pady=8)
        root.protocol('WM_DELETE_WINDOW',self.close)
        self.refresh();self.poll()

    def safe(self, command):
        try:return command()
        except Exception as ex:messagebox.showerror('Seva Desk',str(ex),parent=self.root)

    def table(self,parent,columns,labels,height=12):
        frame=ttk.Frame(parent);frame.pack(fill='both',expand=True,pady=5)
        tree=ttk.Treeview(frame,columns=columns,show='headings',height=height,selectmode='browse')
        for column,label in zip(columns,labels):tree.heading(column,text=label);tree.column(column,width=120,minwidth=50)
        scroll=ttk.Scrollbar(frame,orient='vertical',command=tree.yview);tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');tree.pack(fill='both',expand=True)
        return tree

    def selected(self,tree=None):
        chosen=(tree or self.tree).selection()
        if not chosen:raise ValueError('Select a row first.')
        return int(chosen[0])

    def refresh(self):
        keep={t:t.selection() for t in (self.tree,self.events,self.sevas)}
        for t in (self.tree,self.events,self.sevas):t.delete(*t.get_children())
        pending={x['booking_id'] for x in self.store.queue()}
        totals={}
        for b in self.store.bookings():
            e=json.loads(b['snapshot']);cur=e['currency']
            self.tree.insert('', 'end',iid=str(b['id']),values=(b['id'],e['name'],b['devotee'],cur,f"{b['total']/100:.2f}",b['status'],'Pending' if b['id'] in pending else 'Confirmed'))
            totals.setdefault(cur,{'PAID':0,'UNPAID':0})
            if b['status'] in totals[cur]:totals[cur][b['status']]+=b['total']
        self.summary.config(text='   |   '.join(f"{c}: collected {v['PAID']/100:.2f} · unpaid {v['UNPAID']/100:.2f}" for c,v in totals.items()) or 'No bookings yet. Create event and seva masters to begin.')
        cat=self.store.catalog()
        for e in cat['events']:self.events.insert('','end',iid=str(e['id']),values=(e['id'],e['name'],e['day'],e['place'],e['currency']))
        for s in cat['sevas']:self.sevas.insert('','end',iid=str(s['id']),values=(s['id'],s['event_id'],s['name'],s['kind'],f"{s['price']/100:.2f}"))
        for tree,selection in keep.items():
            if selection and tree.exists(selection[0]):tree.selection_set(selection[0])

    def poll(self):
        self.safe(self.refresh)
        self.root.after(4000,self.poll)

    def form(self,title,fields,on_save):
        win=tk.Toplevel(self.root);win.title(title);win.transient(self.root)
        frame=ttk.Frame(win,padding=18);frame.pack(fill='both',expand=True)
        vars={}
        for i,(key,label,value,choices) in enumerate(fields):
            ttk.Label(frame,text=label).grid(row=i,column=0,sticky='w',padx=4,pady=7)
            var=tk.StringVar(value=str(value));vars[key]=var
            if choices:widget=ttk.Combobox(frame,textvariable=var,values=choices,state='readonly',width=40)
            else:widget=ttk.Entry(frame,textvariable=var,width=43)
            widget.grid(row=i,column=1,sticky='ew',padx=4,pady=7)
        if 'name' in vars and 'kannada' in vars:
            saved=self.store.label_dictionary()
            convert=lambda text:translate_label(text,saved)
            reset=bind_suggestion(vars['name'],vars['kannada'],convert)
            ttk.Button(frame,text='Use Kannada glossary',command=reset).grid(row=len(fields)+1,column=1,sticky='e')
            hint=ttk.Label(frame,text='',wraplength=460)
            hint.grid(row=len(fields)+2,column=0,columnspan=2,pady=8)
            def explain(*_):
                wording=convert(vars['name'].get())
                hint.config(text=('Offline glossary available. Review the Kannada wording. Corrections are remembered when saved.' if wording else 'No glossary match. Enter the Kannada wording once; it will be remembered. No phonetic guess is used for categories.'))
            vars['name'].trace_add('write',explain);explain()
        def save():
            try:on_save({k:v.get() for k,v in vars.items()});win.destroy();self.refresh()
            except Exception as ex:messagebox.showerror(title,str(ex),parent=win)
        ttk.Button(frame,text='Save / ಉಳಿಸಿ',command=save).grid(row=len(fields),column=1,sticky='e',pady=12)
        return win

    def edit_event(self,ident=None):
        e=next((x for x in self.store.catalog()['events'] if x['id']==ident),{})
        fields=[('name','Event name',e.get('name',''),None),('kannada','Kannada name / ಕನ್ನಡ ಹೆಸರು',e.get('kannada',''),None),('day','Pooja date YYYY-MM-DD',e.get('day',dt.date.today().isoformat()),None),('place','Place / ಸ್ಥಳ',e.get('place',''),None),('currency','Currency',e.get('currency','AED'),['AED','INR'])]
        self.form('Event master',fields,lambda v:self.store.event(v,ident))

    def edit_seva(self,ident=None):
        cat=self.store.catalog()
        if not cat['events']:raise ValueError('Create an event first.')
        options={f"{e['id']} · {e['name']}":e['id'] for e in cat['events']}
        s=next((x for x in cat['sevas'] if x['id']==ident),{})
        selected=next((k for k,v in options.items() if v==s.get('event_id')),next(iter(options)))
        fields=[('event_id','Event',selected,list(options)),('name','Seva / contribution name',s.get('name',''),None),('kannada','Kannada name',s.get('kannada',''),None),('kind','Type',s.get('kind','Seva'),['Seva','Sponsorship','In-kind']),('price','Default cash amount',f"{s.get('price',0)/100:.2f}",None)]
        def save(v):v['event_id']=options[v['event_id']];self.store.seva(v,ident)
        self.form('Seva master',fields,save)

    def booking(self):
        cat=self.store.catalog()
        if not cat['sevas']:raise ValueError('Create event and seva masters first.')
        win=tk.Toplevel(self.root);win.title('New booking / ಸೇವಾ ನೋಂದಣಿ');win.geometry('760x820')
        frame=ttk.Frame(win,padding=16);frame.pack(fill='both',expand=True)
        evs={f"{e['id']} · {e['name']} ({e['currency']})":e['id'] for e in cat['events']}
        vars={}
        labels=[('event_id','Event',list(evs)),('devotee','Devotee (English)',None),('devotee_kn','Kannada name (editable)',None),('phone','Phone (optional)',None),('rashi','Rashi / ರಾಶಿ (optional)',['']+RASHIS),('nakshatra','Nakshatra / ನಕ್ಷತ್ರ (optional)',['']+NAKSHATRAS),('note','Notes / in-kind details',None)]
        for i,(key,label,choices) in enumerate(labels):
            ttk.Label(frame,text=label).grid(row=i,column=0,sticky='w',pady=5)
            vars[key]=tk.StringVar(value=choices[0] if choices else '')
            widget=ttk.Combobox(frame,textvariable=vars[key],values=choices,state='readonly',width=43) if choices else ttk.Entry(frame,textvariable=vars[key],width=46)
            widget.grid(row=i,column=1,sticky='ew',pady=5)
        reset_kn=bind_suggestion(vars['devotee'],vars['devotee_kn'])
        ttk.Button(frame,text='Regenerate Kannada',command=reset_kn).grid(row=14,column=0,pady=8)
        ttk.Label(frame,text='Review Kannada before saving.').grid(row=14,column=1)
        sel=tk.StringVar(); qty=tk.StringVar(value='1'); amount=tk.StringVar()
        ttk.Label(frame,text='Seva').grid(row=7,column=0,sticky='w')
        combo=ttk.Combobox(frame,textvariable=sel,state='readonly',width=43);combo.grid(row=7,column=1,pady=6)
        ttk.Label(frame,text='Quantity (one slip per seva)').grid(row=8,column=0,sticky='w');ttk.Entry(frame,textvariable=qty).grid(row=8,column=1,sticky='ew',pady=5)
        ttk.Label(frame,text='Amount each (admin editable)').grid(row=9,column=0,sticky='w');ttk.Entry(frame,textvariable=amount).grid(row=9,column=1,sticky='ew',pady=5)
        lines=[];choices={};cart=tk.Listbox(frame,height=7);cart.grid(row=11,column=0,columnspan=2,sticky='ew',pady=8)
        total=ttk.Label(frame,text='');total.grid(row=12,column=0,columnspan=2)
        def price(*_):
            if sel.get() in choices:amount.set(f"{choices[sel.get()]['price']/100:.2f}")
        def event_changed(*_):
            lines.clear();cart.delete(0,'end');total.config(text='')
            choices.clear();choices.update({f"{s['id']} · {s['name']} / {s['kannada']}":s for s in cat['sevas'] if s['event_id']==evs[vars['event_id'].get()]})
            combo.config(values=list(choices));sel.set(next(iter(choices),''));price()
        vars['event_id'].trace_add('write',event_changed);combo.bind('<<ComboboxSelected>>',price);event_changed()
        def add():
            from core import money
            s=choices.get(sel.get())
            if not s:raise ValueError('Choose a seva.')
            q=int(qty.get());p=money(amount.get())
            if q<1 or sum(x['quantity'] for x in lines)+q>100:raise ValueError('Use 1–100 total slips.')
            if s['kind']=='In-kind' and p:raise ValueError('In-kind contributions must have zero cash amount.')
            lines.append({'seva_id':s['id'],'quantity':q,'amount':f'{p/100:.2f}'})
            cart.insert('end',f"{q} × {s['name']} = {p*q/100:.2f}")
            total.config(text=f"Total: {sum(money(x['amount'])*x['quantity'] for x in lines)/100:.2f}")
        ttk.Button(frame,text='Add seva',command=lambda:self.safe(add)).grid(row=10,column=1,sticky='e')
        def clear():lines.clear();cart.delete(0,'end');total.config(text='')
        ttk.Button(frame,text='Clear selected sevas',command=clear).grid(row=13,column=0,pady=8)
        key=str(uuid.uuid4())
        def save():
            data={k:v.get() for k,v in vars.items()};data['event_id']=evs[data['event_id']];data['items']=lines;data['request_key']=key
            bid=self.store.book(data,'Laptop administrator',True);win.destroy();self.refresh();self.tree.selection_set(str(bid));self.preview()
        ttk.Button(frame,text='Save and preview slips',command=lambda:self.safe(save)).grid(row=13,column=1,pady=8)

    def preview(self):
        b=self.store.detail(self.selected())
        handle,path=tempfile.mkstemp(prefix='seva-receipt-',suffix='.html')
        with os.fdopen(handle,'w',encoding='utf-8') as f:f.write(receipt(b,int(self.width.get())))
        self.previews.append(path);webbrowser.open(Path(path).as_uri())

    def printed(self):
        bid=self.selected()
        if messagebox.askyesno('Confirm printing','Have all seva slips and the cashier summary physically printed?'):
            self.store.printed(bid);self.refresh()

    def pay(self):
        b=self.store.detail(self.selected())
        if b['status']!='UNPAID':raise ValueError('Select an unpaid booking.')
        def save(v):
            if messagebox.askyesno('Confirm payment',f"Have you received {b['event']['currency']} {b['total']/100:.2f} from {b['devotee']}?"):
                self.store.pay(b['id'],'Laptop administrator',v['method'])
        self.form('Receive payment',[('method','Payment method','Cash',['Cash','Bank transfer','Card','UPI'])],save)

    def void(self):
        bid=self.selected();reason=simpledialog.askstring('Cancel unpaid booking','Reason (record stays in the audit log):')
        if reason:self.store.void(bid,reason);self.refresh()

    def backup(self):
        dest=filedialog.asksaveasfilename(defaultextension='.sqlite3',initialfile=f'seva-backup-{dt.date.today()}.sqlite3')
        if dest:
            if Path(dest).resolve()==(self.folder/'seva-desk.sqlite3').resolve():raise ValueError('Choose a different backup file.')
            self.store.backup(dest);messagebox.showinfo('Backup','Database backup saved.')

    def export(self):
        dest=filedialog.asksaveasfilename(defaultextension='.csv',initialfile='seva-register.csv')
        if dest:self.store.export(dest);messagebox.showinfo('Export','Booking register saved. AED and INR remain separate.')

    def mobile(self):
        if self.server:
            if messagebox.askyesno('Mobile access','Stop mobile access and revoke both access keys?'):
                self.server.shutdown();self.server.server_close();self.server=None
            return
        if not messagebox.askyesno('Enable local mobile entry','Connect phones and laptop to a private, password-protected Wi-Fi or hotspot. This prototype uses unencrypted local HTTP. Do not use public/shared Wi-Fi. Enable access?'):return
        self.server,tokens=start(self.store)
        addresses=set()
        try:addresses.update(socket.gethostbyname_ex(socket.gethostname())[2])
        except OSError:pass
        win=tk.Toplevel(self.root);win.title('Mobile connection details')
        text=tk.Text(win,width=78,height=20,wrap='word');text.pack(padx=15,pady=15)
        urls='\n'.join(f'http://{ip}:8765' for ip in sorted(addresses) if not ip.startswith('127.'))
        text.insert('end','Open on phones connected to the same private network:\n'+(urls or 'http://<laptop Wi-Fi IPv4 address>:8765')+'\n\nIf an address does not work, use the laptop Wi-Fi IPv4 shown in network settings. Allow local/private network access through the firewall.\n\n')
        for key,role in tokens.items():text.insert('end',f'{role} access key:\n{key}\n\n')
        text.insert('end','Reception: register bookings. Cashier: register and receive payments.\nKeep this window open to copy the keys. Restarting mobile access changes the keys.\nThe laptop receives print jobs; open them under Bookings.\n')
        text.configure(state='disabled')

    def close(self):
        if self.server:self.server.shutdown();self.server.server_close()
        for path in self.previews:
            try:os.remove(path)
            except OSError:pass
        self.root.destroy()


if __name__=='__main__':
    root=tk.Tk();App(root);root.mainloop()
