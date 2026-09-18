# DevSeva / ದೇವಸೇವೆ — offline temple desk, version 0.8

© 2026 Raviraj Shetty. All rights reserved. Proprietary software — see NOTICE.txt.

DevSeva is an offline desktop app for temples, ashrams and religious event committees. It manages daily poojas, special sevas, festival bookings, devotee records, cashier collection and reports. It runs on one laptop with a local SQLite database. Phones can optionally enter bookings over a private Wi-Fi network served by that laptop. No internet, hosting account or cloud database is used during operation.

## Development source and releases

This folder is the authoritative, version-controlled source. The adjacent `DevSeva.app` is the distributable macOS application; do not edit Python files inside it directly.

1. Make changes here and run `python3 -m unittest discover -s tests -p 'test*.py' -v` from this folder.
2. Check which source files differ from the app: `python3 tools/sync_bundle.py`.
3. After review and passing tests, update the local app: `python3 tools/sync_bundle.py --apply`.
4. Use **Build Standalone DevSeva.command** only after the app is synchronised. It now builds from this source folder while preserving the private developer passphrase kept in the app bundle.

`developer.key`, databases, backups, archives and generated apps are excluded from Git. Never commit a customer's data or developer passphrase.

This is a working prototype (formerly "Seva Desk"). The DevSeva.app launcher uses the Python 3.10+ and Tk already installed on the Mac. **Build Standalone DevSeva.command** makes a version that doesn't need Python (see below).

## What's new in 0.8 — branding, event banner, developer reset, copyright

**Brand and event on screen**
- The DevSeva logo and name sit at the top left, with the temple / organisation name underneath.
- A maroon **event banner** shows the chosen event in large type, with its Kannada name, weekday and date, venue and a countdown ("in 39 days", "Tomorrow", "TODAY", "ON NOW · day 2 of 3"). **Change event** on the banner also switches the counter tab.
- The banner also shows whether phone entry is on; click it to open the QR code.
- The window title shows the event, e.g. "Sri Satyanarayana Pooja (2026-10-25) — DevSeva".
- Phones show the same event card at the top, with the temple name in the header.

**Temple / organisation details**
- Set the temple name (English and Kannada) and place in **Masters → Temple / organisation details…** (Admin).
- First-time setup now asks for the temple name too.
- The name appears on the login screen, at the top, on every receipt and in About.

**Developer tools (for the developer only)**
- Open with **⌘+Shift+D** (Ctrl+Shift+D on Windows), or click the version text at the bottom of the window **5 times**. This also works on the login screen.
- The first time, you create a **developer passphrase** (at least 10 characters). It is stored only as a salted hash in `developer.key` inside DevSeva.app, **not** in the temple's database, so restores and resets never remove it. It can only be changed with the current passphrase. After 5 wrong tries the tools lock for 15 minutes.
- **Factory reset:** saves a final backup (you choose where), can also delete the automatic backups and the phone certificate, and asks you to type RESET. It then erases all bookings, devotees, events, sevas, staff, settings and the audit log, and DevSeva opens at first-time setup, ready for a new temple.
- **Reset a customer Admin PIN** (the temple's data stays) and **change the developer passphrase**.
- **Set the passphrase before you share or sell any copy.** The standalone builder refuses to build until it is set, and every copy you build carries your lock.

**Copyright**
- © 2026 Raviraj Shetty appears in the status bar, the login screen, About DevSeva, receipts, the phone page, the QR sheet and the source files.
- NOTICE.txt holds the licence terms and the third-party notice (qrcodegen, MIT).
- To show a company name instead, change `COPYRIGHT_HOLDER` in core.py.

**Fixes**
- **Add every member** stays greyed out until a register family is chosen with Find…. For a new devotee, "Add seva line" is enough.

## What's new in 0.7.1 — phone access by QR code

**Mobile access** now opens a window with a large **QR code**. Volunteers join the counter Wi-Fi and scan the code with the phone camera. On the first visit they tap past the "not private" warning. They then enter only their **name and PIN**: the access code comes from the QR code, and the phone remembers the name for next time. **Type the code instead** is still available on the phone for anyone without a camera.

**Safety:**

- The access code travels in the link's `#` part, which browsers never send over the network, and it is removed from the address bar straight away.
- A PIN is still required.
- The code changes every time phone entry starts, so old photos and printouts stop working. A phone with an outdated code is asked to type the current one.

**On the laptop:**

- **Laptop address:** choose which address the QR code uses if the laptop is on more than one network.
- **Print QR sheet:** an A4 page for the counter table, with bilingual steps, the address and the typed code.
- **Copy link:** copy the link, for example to send it to a volunteer on WhatsApp.
- **Stop phone entry** turns phone entry off.
- **Close / Esc** hides the window while phone entry keeps running; **Mobile access** shows the same QR code again.
- Dialogs no longer open as full-screen tabs on macOS.

The QR codes are made offline by the bundled QR Code generator library by Project Nayuki (MIT licence, `qrcodegen.py`). Tests scan every generated code back with a real QR reader.

## What's new in 0.7 — importing bookings and the event-day counter

This release is for festivals where bookings are collected in advance, such as the Sri Satyanarayana Pooja on 25 October 2026.

### Import bookings (Supervisor or Admin)

Open **Import bookings** from the top bar and choose the event. Bookings can come from four kinds of source:

- **Excel or CSV file:** `.xlsx` files (for example a Google Form response sheet downloaded as Excel) and `.csv` files are read directly. DevSeva guesses which column holds the booking number, name, Kannada name, phone, email, total amount, pooja or sponsorship, quantity, payment status, payment method, gotra, rashi, nakshatra and notes. You can change any guess from the drop-down lists. Old `.xls` and Numbers files must first be saved as `.xlsx` or CSV.
- **WhatsApp messages or an exported chat:** paste the messages, or open the chat's `.txt` export.
- **PDF receipts:** in Preview, select the text, copy it and paste it in.
- **Photos of paper forms:** in Photos or Preview, select the text in the picture, copy it and paste it in. You can also add a paper form by hand with **Add a paper form by hand…**.

DevSeva picks out names, phone numbers, emails, booking numbers, amounts, payment words (paid, transferred, GPay, will pay at venue…) and the sevas mentioned.

**How each row's sevas and slips are worked out.** Each row is matched to the event's sevas. "Satyanarayana Pooja" matches *Pooja Booking*, and "Pooja x2, Flowers" becomes two pooja slips plus a Flowers sponsorship. When there is only one pooja, the number of slips comes from the quantity column or the amount (AED 150 ÷ 50 = 3 slips). Whatever is left of the total goes to the sponsorship. Rows that don't name a seva use the default you choose.

**Nothing is saved until you check the preview.** Each row is colour-coded:

| Colour | Status | Meaning |
|---|---|---|
| Green | Ready | Will be imported. |
| Yellow | Check | Something needs a human decision: no name, an amount that isn't a whole number of poojas, an unclear payment status, a sponsorship with no amount, or any row read from pasted text. Double-click to open and correct it, or tick it after checking. Rows with a real problem cannot be ticked until they are fixed. |
| Blue | Update | Already imported as unpaid, but the new list says paid, so it will be marked paid. |
| Grey | Duplicate / Skip | Already in DevSeva, or repeated in the same file, so it is never imported twice. |

**Before and after importing:**

- A safety backup is saved before importing.
- Rows marked paid are recorded as *Paid before event (imported by …)* with their payment method, so they are never mixed into a counter's cash.
- Each booking keeps its **booking number and email**, which are searchable and printed on the slips.
- Tick **Also add new devotees to the Devotee register** to add them to the register as well.

**Re-importing is safe.** Import the updated sheet whenever new bookings arrive. Bookings already imported are recognised by booking number, or by name, phone and amount when a row has no booking number. They are skipped, or marked paid if the new list says so. A "Sl No" serial column is not treated as a booking number.

`samples/DevSeva-booking-import-template.xlsx` is a ready-made sheet that the committee can fill in or copy into a Google Form.

### Event-day counter (first tab)

The counter opens on the next upcoming festival.

1. Type part of the devotee's **name, phone, email or booking number**. Press Return to select the first match. The right-hand panel shows the sevas, the total, and whether the booking is paid.
2. Use one of the four buttons:
   - **Collect cash + print slips:** after "Yes, money is in hand", the booking is marked PAID and the slips open for printing.
   - **Collect cash only**.
   - **Print slips only:** use this for bookings paid in advance.
   - **Paid by UPI / card / bank…**
3. After printing, confirm that the slips came out. A later print is marked REPRINT.

Also on the counter:

- **Colours:** yellow bookings are unpaid and green bookings are paid.
- **Filters:** **Show Unpaid / Paid** narrows the list, and the counter shows how many unpaid bookings remain.
- **Your own total:** *Collected today by <you>* shows what you have taken, split by payment method, ready for the cash handover.
- **Reception can collect cash.** Reception logins can now mark bookings paid, for event-day counters. Refunds, cancellations and corrections still need a Supervisor or Admin.
- **Cash handover report:** the Reports tab has a **CASH HANDOVER** section totalling each person's collections by method, with refunds subtracted. Prepaid imports appear on their own line.

### Devotee register and keyboard improvements

**No duplicate devotees.**

- A mobile number can belong to only one family. 050 600 1015, +971 50 600 1015 and 971-50-6001015 count as the same number.
- If you try to add a family whose number is already registered, DevSeva offers to open that family and add the person as a member instead.
- Walk-in bookings ticked **Save to register**, and imported bookings, also reuse the registered family rather than creating a second one.
- Families created twice by an older version are flagged with a warning in the Devotees tab. **Merge duplicates…** (Supervisor or Admin) combines them into the one you choose: members, bookings and missing details are moved across, and a person entered twice becomes one member. Printed slips are not changed, and a backup is saved first.

**Email ID** is now a field for each family, shown in the Devotees list and filled into bookings.

**Type to search Rashi and Nakshatra.** Start typing and matching entries appear. For example, `kar` finds Karkataka, `ash` finds Ashwini and Ashlesha, and `pubba` finds Purva Phalguni. Common alternative spellings and English sign names also work. ↑/↓ move through the list and Enter picks. The same applies to Relation and to every form that asks for rashi or nakshatra, on phones too. The sign previously listed as "Karka" is now **Karkataka / ಕರ್ಕಾಟಕ**; saved devotees are updated, and printed slips keep their wording.

**Find a devotee by typing.** In **New booking**, type part of a name, phone or gotra in the *Devotee register* box and press Enter or **Find…**. If only one family matches, it is filled in at once. Otherwise the search window opens with your text already entered: use ↓ to move into the list and Enter to choose. Find also uses the name typed in *Devotee name* if the register box is empty. **Clear** removes the family and the details it filled in.

**Keyboard shortcuts:**

- **Enter** saves a form and **Esc** closes it (in a booking with lines, Esc first asks before closing).
- In a type-to-search list, Enter picks the suggestion and does not save the form.
- Search boxes: Enter selects the first result and Esc clears the box.
- ⌘+N opens a new booking, ⌘+F jumps to search, ⌘+L logs out and ⌘+Enter saves a booking. On Windows, use Ctrl instead of ⌘.
- Double-click or Enter on a list row opens it.

**Tooltips** appear on the main buttons, search boxes and type-to-search fields.

**Log out.** The **Log out / ಲಾಗ್ ಔಟ್** button ends your session and returns to the login screen. Log-ins and log-outs are recorded in the audit log, and idle screens still log out after 15 minutes.

**Search accuracy.** A booking number such as "SSP-001" no longer matches phone numbers that happen to contain "001". Phone matching applies when you type mostly digits.

### iPhone and Android

The phone page adapts to the device automatically:

- **iPhone:** iOS system font, rounded cards and a translucent header.
- **Android:** Material-style pill buttons, header shadow and a highlighted bottom tab.

Both have a bottom tab bar (**Counter** / **New booking**), a Log out button in the header, and space for the notch and home bar. Success messages fade after five seconds; tap any message to close it.

**Home-screen app icon.** The laptop serves an app icon (a lit diya) and an app manifest, so DevSeva can be added to the home screen:

- **iPhone:** in Safari, tap Share → **Add to Home Screen**.
- **Android:** in Chrome, tap ⋮ → **Add to Home screen** or **Install app**.

The login screen shows these steps for the phone in use. After that DevSeva opens full screen, like an app. It still needs the laptop's Mobile access to be running, and the one-time certificate warning may appear again after the laptop's address changes.

Phones also get the type-to-search Rashi and Nakshatra, "next" and "go" keys on the login keyboard, and a search keyboard for finding bookings.

This is a web app served by the laptop, so there is no App Store or Play Store install and nothing to update on the phones. A store app would need developer accounts, Apple review and a separate build for each platform.

### Phones on event day

After logging in, phones open in **Counter** mode:

- **Search** by name, phone, email or booking number, or tap **Show all unpaid**.
- **Mark paid:** tap **Money received — mark PAID** and choose Cash, UPI, Card or Bank transfer.
- **Print:** tap **Send slips to laptop printer**. The laptop's **Print requests from phones (n)** button lists these requests; open one, print it and confirm.
- **New bookings:** walk-in bookings are still made in **New booking** mode.

Phone numbers stay masked on phones and emails are not shown there.

## What's new in 0.6

**Staff logins with PINs.** The first time 0.6 opens, it asks you to create the Administrator login. After that, everyone logs in with their own name and a 4–12 digit PIN. Obvious PINs such as 1111 or 1234 are refused. PINs are stored only as salted PBKDF2 hashes, never in readable form. Five wrong PINs lock that login for 5 minutes, and an Admin can reset a PIN, which also unlocks the login.

The screen locks after 15 idle minutes, and the **Lock** button locks it immediately. Locking closes any open booking windows, so save first. Phone entry keeps running while the laptop is locked. **Change my PIN** is available to everyone. Every action is recorded under the person who did it, for example "Cashier: Lakshmi" or "Reception: Desk 1 (phone)".

What each role can do:

| Action | Reception | Cashier | Supervisor | Admin |
|---|---|---|---|---|
| Bookings, devotee register, printing | ✓ | ✓ | ✓ | ✓ |
| Receive payments, view reports and exports | | ✓ | ✓ | ✓ |
| Change fixed prices, cancel, refund, correct, link bookings, phone access, backups | | | ✓ | ✓ |
| Masters, staff logins, restore | | | | ✓ |

**Refunds (Supervisor or Admin).** Select a paid booking and choose **Refund…**, then enter the amount, the method and a reason (required).

- A **partial refund** keeps the sevas booked.
- A **full refund** marks the booking REFUNDED, removes its sevas from the priest sheet and frees their per-day slots.

Receipts list each refund and the net amount paid. Reports show refunds on the date they were given, by method, and a **net collection** figure. Refunds cannot exceed the amount paid.

**Corrections (Supervisor or Admin).** Every correction needs a reason and is written to the audit log with the old and new values.

- **Correct payment method…** fixes a payment recorded under the wrong method, for example Cash that was actually UPI.
- **Correct details / date…** fixes the devotee's name, Kannada name, phone, gotra, rashi, nakshatra or notes. It can also fix any slip's name and details, or move a daily-pooja booking to another allowed date. The per-day limit is checked when you move a booking.
- Amounts and sevas never change in place: refund and book again instead.
- Once **Confirm printed** has been used, any later print of that booking is marked **REPRINT / ನಕಲು ಪ್ರತಿ**.

**Gotra per family member.** Each member can have their own gotra, for example a married daughter. It prints on that person's slip and appears on the priest sheet. Searching for a gotra finds the family.

**Linking older bookings.** **Booking history** now lists older, unlinked bookings that match the family, either by a member's exact name or by phone number. Check each suggestion before you **Link** it. From the Bookings tab, **Link to devotee family…** links any booking and **Unlink family** undoes it.

**Encrypted phone connection (HTTPS).** **Mobile access** creates this laptop's own security certificate using the openssl tool built into macOS. The certificate is reused until the laptop's network address changes. Phones connect to `https://<laptop address>:8765`.

- **Certificate warning.** The first time, each phone warns that the connection is not private. Tap *Advanced / Show details → Proceed*.
- **Checking the laptop.** The laptop window shows the start of the certificate's SHA-256 fingerprint, so you can confirm the phone reached the right laptop.
- **No unencrypted fallback.** If a certificate cannot be made, DevSeva does not start phone entry. This prevents staff PINs and booking details from ever travelling over plain HTTP.
- **Logging in.** The two shared access keys are gone. A phone now needs the **access code** shown on the laptop plus the staff member's **own name and PIN**. Each phone login lasts up to 12 hours or until you stop phone entry. Twenty wrong access codes block that phone until phone entry restarts.
- **Masked numbers.** Phones see register phone numbers masked (•••• 4567). Leave the phone field blank and the full number from the register is used.
- **Payments.** Only Cashier, Supervisor and Admin logins see the phone payment section.

**Restore inside the app (Admin).** **Restore backup** checks the file first: it must be undamaged and be a DevSeva or Seva Desk database. It then saves a safety copy of the current data in the `backups` folder, restores the backup and upgrades it if it's older. Everyone must log in again afterwards. If the backup is from before staff logins existed, you'll be asked to create an Admin.

**Automatic backups.** Each time you quit, a backup is saved to `backups` in the data folder. The last 10 are kept. Keep copying backups to a USB drive as well.

**Faster with many bookings.** The Bookings tab loads 300 bookings at a time, with **Show more** for older ones. Search runs inside the database and also matches the names on individual slips. The screen refreshes only when something has changed, for example a phone booking. DevSeva no longer leaves Python cache files inside the app.

**Self-test.** Running `DevSeva --selftest` (or `python3 app.py --selftest`) checks the database, PIN login, receipts, the phone page, certificate creation and Tk, without opening a window.

## Standalone app (no Python needed)

Keep **Build Standalone DevSeva.command** next to DevSeva.app and double-click it once, with internet on. First set the developer passphrase (Developer tools, see 0.8); the builder stops if it is missing. It works as follows:

1. It downloads PyInstaller into a private build folder (`~/Library/Caches/DevSevaBuild`) and tests the source.
2. It builds DevSeva.app and tests the built app.
3. It signs the app and saves it with a ZIP in a new **DevSeva Standalone** folder.

Without an Apple Developer account the app has an ad-hoc signature, so macOS asks for *Open Anyway* once on each Mac. If you later get a Developer ID, set `DEVSEVA_SIGN_ID` and `DEVSEVA_NOTARY_PROFILE` (see the comments at the top of the script) and run it again to sign and notarise.

The build runs on the processor type of the Mac that built it, either Apple Silicon (arm64) or Intel (x86_64). Build on each type if you need both. It uses the same data folder as the launcher version.

## Version 0.5 features

**Rebrand.** The app is now called DevSeva. It still uses your existing database at `~/Library/Application Support/SevaDeskPrototype/seva-desk.sqlite3`, so every earlier booking stays in place. The folder name was deliberately left unchanged.

**Devotee register (Devotees tab).** Each family is saved with a phone number, gotra, address and notes. Each family member is saved with their English and Kannada name, relation, rashi and nakshatra. You can search by name, any member's name, gotra or phone digits. A possible duplicate phone number is flagged when you add a family. **Booking history** shows every booking linked to a family, and **New booking for family** opens a booking with the details filled in. Bookings made before 0.5 are not linked to any family automatically.

**A slip for each person.** In a booking, every seva line has a **Slip for** choice, either the main devotee or any family member. That person's name, Kannada name, rashi and nakshatra print on their own slip. **Add every member** adds one slip per active family member. The cashier summary shows who each line is for. Slips keep the details as they were when booked, so later register edits don't change printed history.

**Walk-in devotees.** Walk-ins can still be booked without the register. Tick **Save this new devotee to the register** to add them as a new family during the same save. A retry never creates the family twice.

**Daily poojas and special sevas.** In Masters, an event or calendar is one of two types. **Once** is a festival or event on one date; its bookings are for that date. **Daily** is a regular temple pooja calendar with a start date, an optional end date and the days it runs (for example "All" or "Mon, Fri"); bookings choose a pooja date within those rules. Any seva can have a **per-day limit** (0 means no limit). The limit is checked safely even when several phones book at once, and cancelled bookings free their slot. Remaining slots are shown while booking.

**Postponed festivals.** If you change a Once event's date, its active bookings move to the new date and the change is written to the audit log. Receipts show the new pooja date, while the stored event snapshot keeps the original details.

**Archive.** Events and sevas can be archived. They disappear from new bookings on the laptop and phones but stay in history and reports. **Restore** brings them back.

**Pooja schedule tab.** The priest's day sheet lists every non-cancelled slip for a date, grouped by seva, with name, Kannada name, gotra, rashi, nakshatra and payment state. You can move day by day and filter by event. **Print priest sheet** opens a printable A4 page.

**Reports tab.** Choose a date range (with Today, This week, This month and This year shortcuts) and an optional event filter. The report shows:

- cash collected by the date payment was received, split by payment method, by seva and by day;
- bookings entered in the period, cancellations and in-kind slips;
- the unpaid balance;
- sevas scheduled in the period by pooja date.

**Print report** opens a printable page. **Export slip-level CSV** writes one row per slip. AED and INR are never converted or added together.

**Bookings tab.** You can search by name, booking number or phone digits, and double-click a booking to preview it. The list now shows the pooja date and slip count, and the footer shows today's collections and the unpaid balance for all dates.

**Phones.** The phone page offers the same devotee search, per-member slips, "every member" button, pooja date picker, remaining slots, gotra and save-to-register option. Archived events are hidden. When a booking is rejected (for example because a seva is full), the phone says nothing was saved and lets you correct the booking. Only connection or server failures keep the "Retry same booking" lock, so a booking is never duplicated.

## Daily use

0. **Log in** with your name and PIN. The first time, create the Admin login, then add volunteers under **Staff logins**.
1. **Masters:** add your festival (Type: Once) or temple calendar (Type: Daily), then its sevas, sponsorships and in-kind categories.
2. **Devotees:** add regular devotee families and their members.
3. **New booking:** choose the event, then the pooja date if it's a Daily calendar. Use **Find…** to pick a family, or type a walk-in devotee. Add seva lines, choosing who each slip is for, then **Save and preview slips** and print from the browser. Click **Confirm printed** only after the paper has actually printed.
4. **Cashier:** select the booking, then **Receive payment**. Payment is never recorded automatically when slips print.
5. **Pooja schedule:** print the priest sheet for the day.
6. **Reports:** review collections at the end of the day, then use **Backup database**.

Unpaid bookings can be cancelled with a reason. A Supervisor or Admin handles paid bookings with **Refund…** and the **Correct…** buttons, which are described above.

## Phones and hotspot

Keep the laptop and phones on the same private, password-protected Wi-Fi or hotspot.

1. Add each volunteer under **Staff logins**.
2. A Supervisor or Admin clicks **Mobile access**.
3. On each phone, open the `https://…:8765` address shown, accept the one-time certificate warning, and log in with the access code, your name and your PIN.

Phones can search the devotee register, which shows names and gotra, with phone numbers masked. Stop mobile access when finished: every phone is logged out, and the access code changes next time. Never use public Wi-Fi or set up port forwarding. Allow incoming connections if the macOS firewall asks.

## Data and backup

The database is `SevaDeskPrototype/seva-desk.sqlite3` in `~/Library/Application Support` (Windows: Local AppData). Use **Backup database** after each session and copy the file to a secure external drive. The backup includes the devotee register, glossary and audit log.

To restore:

1. Quit all copies of the app.
2. Keep a copy of the whole data folder.
3. Move the database and its `-wal`/`-shm` files aside.
4. Copy the backup into the folder, named `seva-desk.sqlite3`.
5. Open the app and check the register.

Version 0.5 upgrades the database automatically and additively: it adds new tables and columns, and existing bookings keep their amounts, status and receipt details. Once upgraded, the database should be opened only with 0.5 or later. The old 0.4 app will not show the new information and has not been tested against an upgraded database.

Automatic backups are saved in the `backups` folder inside the data folder, and **Restore backup** does the restore steps above for you. The database and backups themselves are not encrypted, so protect the Mac with its own login password and FileVault. The phone connection's certificate is stored in the `tls` folder. Receipt, schedule and report previews are temporary files that are deleted when the app closes normally.

## Kannada

Event and seva names use an offline glossary that translates by meaning, and corrections you save are remembered. Devotee names get an editable phonetic suggestion. Always have the Kannada spelling checked with the devotee, and have a fluent reader review public wording.

## Verification

Run `python3 -m unittest test_core test_kannada test_v05 test_v06 test_v07 test_v08` from the Resources folder (69 tests). The 0.8 tests (`test_v08`) cover organisation settings on receipts, factory reset (data gone, backup intact, fresh setup works), the developer key (strength rules, no re-keying without the current passphrase, lockout, surviving a data reset) and the banner countdown. The 0.7 tests (`test_v07`) cover the importer, duplicate blocking and merging:

- **Readers:** Excel reading (shared and inline strings, hidden sheets, numeric phone cells), CSV encodings and delimiters, and column guessing.
- **Text extraction:** WhatsApp (iPhone and Android formats), PDF text and one-line lists, plus payment and method words.
- **Planning and importing:** seva matching with sponsorships, the review statuses, safe re-import with payment updates, rows without booking numbers, and a clean failure when a seva is archived.
- **Event day:** counter search by name, email and booking number, phone print requests and reprints, the cash handover that keeps prepaid imports separate, the phone counter over HTTPS, and importing into the real 25 October event from the v0.4 backup.

The earlier tests cover:

- **Earlier behaviour:** receipts, retries and parallel entry, prices, payments, cancellations, in-kind entries, backups, the Kannada glossary, daily-pooja rules, per-day limits, per-person slips, the register, schedules and reports.
- **Staff logins:** PIN hashing and lockout, role permissions and the last-Admin rule.
- **Refunds and corrections:** partial and full refunds (including freed slots and net reports), payment-method and detail corrections with rescheduling, and reprint marking.
- **Register and bookings:** per-member gotra, link suggestions, paged search and change detection.
- **Backups:** refusing bad files, restoring (including a real v0.4 backup that still has its unsaved `-wal` journal file) and pruning automatic backups.
- **Phone connection:** HTTPS login, masked numbers, role limits, logout and blocking of wrong access codes.

In a Linux test environment, the whole desktop flow was also run end to end, the phone page was tested in Chromium over HTTPS, and the standalone build was checked with its self-test. Native macOS behaviour, iPhone/Android certificate prompts, Kannada rendering, physical printers and the Mac standalone build still need testing on your devices.

## Still to do before commercial release

- **Printing:** automatic thermal printing with a tested printer.
- **Data encryption:** an encrypted database file.
- **Distribution:** Windows installer, notarisation (needs an Apple Developer account) and offline licensing.
