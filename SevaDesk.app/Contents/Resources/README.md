# Seva Desk — offline desktop prototype 0.4

Built for UAE Satyanarayana Pooja and Yermal Nagabana annual events. This is a runnable source prototype, not a signed, sale-ready installer. It uses a native Python/Tk desktop window and a SQLite database on the laptop. The optional phone screen is served by that laptop over your private local network. No hosting account, cloud database, or internet connection is used during operation.

## What is implemented

- Editable event name, Kannada name, date, place and currency (AED or INR).
- Editable seva names, Kannada names, default prices, sponsorships and in-kind categories.
- Devotee name, optional phone, rashi, nakshatra and notes. Prices prefill from the seva master. The desktop administrator can override amounts; mobile operators can enter variable sponsorship amounts.
- Multiple seva lines and quantities per booking. Five sevas create five devotee slips and one cashier summary. Names/rashi/nakshatra currently apply to the whole booking; use separate bookings for different devotees.
- Slips before collection, with payment status tracked internally and a separate payment confirmation. Cash, bank transfer, card and UPI are manual record labels; this software does not process payments.
- English/Kannada labels, Unicode data entry and receipt templates. Some administrative screens remain English. Have a fluent Kannada speaker review wording before public use.
- In-kind contributions carry zero cash value and a no-cash-due acknowledgement. Describe goods/quantities in notes; fulfillment tracking is not yet implemented.
- Separate reception and cashier access keys for mobile use. Mobile submissions enter a persistent laptop print queue.
- Duplicate request protection, SQLite transactions, payment state checks, audit records, unpaid cancellations, database backup and CSV booking export.
- Historical booking snapshots: master edits cannot change existing booking amounts or receipt names.
- 58 mm / 80 mm HTML receipt preview, printable through the desktop browser and installed printer driver. Browser headers/footers should be disabled. Paper sizing/page breaks must be verified on the actual printer.

## Start on your laptop

You need Python 3.10 or later with Tkinter installed. No third-party Python packages are required. If Python is not installed, install it before using this source version; a future packaged installer will remove this prerequisite.

1. Extract the ZIP into a normal folder.
2. Windows: double-click `Start-Windows.bat` (requires the Python `py` launcher). Alternatively open a terminal in the folder and run `python app.py`.
3. Mac: open Terminal in the extracted folder and run `python3 app.py`. The included `Start-Mac.command` is an optional launcher; macOS may require permission to execute downloaded files. If you see `No module named tkinter`, your Python installation needs Tk support.
4. Open **Event and seva masters**. Add the real event/date/place and currency, then add its sevas and amounts.
5. Example UAE setup: Satyanarayana Pooja, AED 50 (editable); another seva, AED 100; stage sponsorship; flowers/fruits as in-kind. These are examples supplied in the request, not prices preloaded into the database.
6. Example Yermal setup: Nagabana annual day, INR; Tanu, Tambila and Annadana. Enter the actual prices yourself.
7. Choose **New booking**. Add seva lines and quantities; save to open the receipt preview. Print using the browser's print button. Confirm printed only after paper has physically printed.
8. The cashier selects the booking and chooses **Receive payment** after collecting the money. Reopening its preview shows the current PAID status. Preview/reprinting does not create another booking or payment.

Existing unpaid bookings can be cancelled with a reason and re-entered. They cannot currently be edited in place. Paid refunds/corrections are intentionally not implemented in this prototype; do not silently overwrite financial history.

## Phones and hotspot

1. Keep the laptop and phones on the same private, password-protected Wi-Fi/router/hotspot. Internet access is unnecessary, but devices must be able to reach each other. Some hotspots isolate clients; test before the event.
2. Click **Mobile access** on the laptop. Allow private-network access in the laptop firewall when required; never set up internet port forwarding.
3. Open the displayed laptop address (port 8765) in the phone browser. If address discovery is wrong, find the laptop Wi-Fi IPv4 address in its network settings.
4. Enter the reception or cashier access key and operator name. Keep the credentials window open to copy the long keys. Pairing QR codes are not implemented yet.
5. Save the booking. The laptop list refreshes about every four seconds. A laptop operator must open the queued booking and print it in this version. A phone does not need its own printer driver.
6. Stop mobile access from the laptop when finished. Restarting changes the keys. If a submission loses connection, keep the phone page open and use Retry same booking; it reuses the request ID. Closing/reloading the page loses unsent form data. Check the laptop register before re-entering uncertain bookings.

Bluetooth networking/printing is not implemented. Wi-Fi/hotspot is the supported prototype transport. One laptop is the database authority; simultaneous independent laptops and sync are not supported.

## Thermal printer decision

No printer has been selected or tested. Do not buy solely on the basis of this prototype. Before purchase, verify Windows and macOS drivers, paper width, cutter support, and correct raster printing of Kannada with the supplier or a sample print. Kannada requires appropriate system fonts and a verified rendering/driver path; many printers' built-in text modes will not handle it correctly.

The planned production path is a laptop print worker with a persistent job queue and a tested printer adapter. The mobile saves a booking, and the laptop worker sends the five individual slips plus one cashier summary to the printer. Printer disconnects, paper-out, ambiguous delivery, reprint markings and duplicate prevention need hardware acceptance tests. Physical printing cannot generally be proven by a successful software send alone.

## Data and backup

Database: `SevaDeskPrototype/seva-desk.sqlite3` under Windows Local AppData, macOS `~/Library/Application Support`, or Linux `~/.local/share`.

Use **Backup database** after sessions and copy the backup to a secure external drive. It uses SQLite's backup mechanism so the copy includes committed data while the app is running. Restore procedure: stop all app instances, retain a copy of the whole original data folder, move the original database and any `-wal`/`-shm` files to that retained folder, then copy the backup into the data folder as `seva-desk.sqlite3`. Start the app and verify the register. Never mix a restored database with old journal files.

The database and backups are not encrypted by this prototype. The laptop OS account is the administrator; individual staff passwords, encrypted local transport and database encryption are not implemented. Mobile keys provide role separation, but operator names are self-entered, not verified staff identities. Use synthetic data for initial testing. The local HTTP service is for a trusted private network only, not public Wi-Fi or internet exposure. Receipt previews create temporary local files that are removed on normal app exit; after a crash, remove leftover `seva-receipt-*.html` files from the OS temporary folder if needed.

CSV reports preserve AED and INR separately; they do not convert or combine currencies. The current dashboard totals span all events, while the exported register carries the event for filtering.

## Verification and limits

Run `python -m unittest -v test_core.py`. Tests cover receipt counts, Unicode/HTML escaping, concurrent registration and retries, historical master snapshots, price permissions, money validation, payment/cancellation state transitions, in-kind entries, backups and mobile role permissions.

The automated tests were run in the development environment. Native Windows/macOS GUI behavior, phone browsers, Kannada font rendering and physical printers still need device testing. This source package is not ready to sell or rely on at a live collection desk yet.

## Before commercial release

1. Validate registration, pre-payment slip and cashier workflow with your sample event and actual staff. Confirm whether different family members need different rashi/nakshatra within one booking, and whether one or two printers are required.
2. Choose and test the printer; implement automatic dispatch, cutter behavior, recoverable failures and explicitly marked reprints.
3. Add individual staff login/PINs, robust pairing, encrypted local transport, supervisor approvals, closed-event controls, refunds/corrections, payment reconciliation and searchable event/seva reports.
4. Add tested backup/restore UI, upgrade migrations and recovery procedures; test power/network failure scenarios and lost phone responses.
5. Build and test separate Windows and Mac installers on those systems. Sign/notarize releases as appropriate; installer distribution should not require customers to install Python.
6. Add an offline license file/activation design and customer-specific configuration. Selling/download/payment pages may be online, while event operations stay offline. Licensing/payment distribution and signed installers are not included here.

No production deployment, customer billing, paid service, email distribution or external account has been created.


## Version 0.2 — offline Kannada suggestions

English event and seva names automatically suggest Kannada in their existing Kannada fields. Devotee registration now has a separate editable Kannada name, shown on every slip and the cashier summary. Both laptop and phone entry offer bilingual rashi/nakshatra choices. No internet API, downloaded model, package installation, or per-use cost is required. Phone suggestions are calculated on your laptop over the local connection.

Common names/pooja terms have built-in spellings; other words use basic phonetic letter rules. This is transliteration, not sentence translation. English spellings are ambiguous, and suggestions can be wrong. Always review the name with the devotee. For unknown words, `aa`, `ee`, and `oo` indicate long vowels. Kannada you type directly is retained. English text remains alongside Kannada.

Manual Kannada edits stop automatic replacement for that field. Use **Regenerate Kannada suggestion** to deliberately replace a correction and resume automatic suggestions. Existing nonempty Kannada master names are treated as manual and are preserved. Old bookings are not backfilled or reprinted with guessed Kannada names. Corrections are stored in each record; they do not yet train a shared name dictionary.

### Update an existing Mac installation

1. In the old app, use **Backup database** and save the backup somewhere safe.
2. Quit Seva Desk fully, including mobile access. Do not run both versions at once.
3. Extract the updated ZIP into a new folder. It includes the new `kannada.py`; do not copy only `app.py`.
4. Open Terminal in the new extracted Seva-Desk folder and run `python3 app.py`.
5. The app uses the same database location and adds one optional Kannada-name column. Existing records and payment amounts are retained. Check your old bookings, then try a sample new booking.
6. Test `Satyanarayana Pooja` in an event/seva name, or `Raviraj Shetty` as a sample devotee. Check the Kannada suggestion, correct it if needed, and open the receipt preview.

The update has automated conversion, correction-preservation, receipt and old-database migration tests. Physical Mac/phone and thermal printer verification still depends on your devices.


## Version 0.3 — receipt wording

Pre-payment seva slips and cashier summaries no longer show UNPAID, the non-payment disclaimer, or Payment: Not received. They retain the seva details and amounts. Cashier payment tracking stays unchanged inside the app. Payment is not automatically recorded when a slip is printed. Confirmed paid receipts still show PAID and their payment method; cancelled records still show VOID.

Use the same Mac update steps above: back up, quit, extract the complete updated package, then run `python3 app.py` from the new folder. No database migration is needed for this wording change.


## Version 0.4 — category translation versus name transliteration

Event and seva/category fields now use an exact-phrase offline English–Kannada glossary. Examples: Consumables → ಬಳಕೆ ಸಾಮಗ್ರಿಗಳು; Pooja materials → ಪೂಜಾ ಸಾಮಗ್ರಿಗಳು; Flowers and fruits → ಹೂವುಗಳು ಮತ್ತು ಹಣ್ಣುಗಳು; Stage setup → ವೇದಿಕೆ ಸಿದ್ಧತೆ.

This supersedes version 0.2's phonetic conversion for these category fields. Unknown English categories produce no Kannada guess. Enter Kannada manually once and save; new/changed Kannada wording is remembered locally for the same English phrase in future master entries. This is a domain glossary with editable preferences, not a general-purpose translation model or a professionally certified translation service. Personal names retain their separate phonetic helper.

Existing saved Kannada and historical slips are preserved. To correct an old Consumables entry: Event and seva masters → select entry → Edit selected seva → Use Kannada glossary → Save. Review the wording before saving. If an old incorrect wording was printed on an existing booking, this update does not change that historical booking snapshot.

The glossary is stored in the same database and included in backups. Corrections affect future suggestions; other already-saved master entries do not update automatically. Original English text is retained.
