# The Broker Desk - Testing Guide

> **Words used here.** Tuple, playbook, swarm, hold, release and the other technical words are explained in plain language in [GLOSSARY.md](GLOSSARY.md).

Fourteen tests, in order, each with what to do and exactly what you should see.
Together they cover the desk end to end: the showcase (what the client video
records), your own live desk, test scripts, Send and Don't send, the lock,
restarts, a tablet, and Windows. Allow about 45 minutes.

The user's manual explains every part of the page:
[BROKER_DESK_MANUAL.md](BROKER_DESK_MANUAL.md). Record your results in the
table at the end; anything that does not match its **Expect** line is a
finding.

Commands are shown for Linux and macOS; on Windows write `tools\desk.py` and
use PowerShell ([QUICKSTART_WINDOWS.md](../QUICKSTART_WINDOWS.md)).

---

## T1 - The build is sound

```bash
git clone https://github.com/QuietFireAI/listing-assistants.git
cd listing-assistants
pip install -r requirements.txt
python -m pytest tests_listing/ -q
```

**Expect:** `1034 passed, 1 skipped` on Linux or macOS (the skipped test runs
only on Windows); `1035 passed` on Windows, after 5 to 8 minutes.

## T2 - The showcase plays through

```bash
python tools/desk.py --showcase --fresh
```

Open http://127.0.0.1:8765.

**Expect:** the badge reads **SHOWCASE · synthetic data**; a yellow bar at the
top reads "SCENE 1 · THE SIGNATURE MATTERS" (the bar's top line is always in
capitals); **Next** is blue.

Press **Next** repeatedly (or tick **play on its own**). Five times the bar
turns red and reads "Your move: ...", the matching card in **Needs you** is
outlined in red, and **Next** is greyed out until you answer:

| # | Scene | The bar says | You press | Expect after |
|---|---|---|---|---|
| 1 | 3 | press Cancel on the paused thread for S3-hot-again | **Cancel** | The card leaves; the lead "Pat Hot ... S3-hot-again" reads "Closed by your decision" |
| 2 | 4 | press Send on the held vendor booking for S4 | **Send**, then **Tap again to sign and send** | Listing S4: Booked turns green |
| 3 | 4 | press Send on the held marketing for S4 | **Send** twice, as above | S4: Marketed green, "Now: Marketing out"; the recap reads "1 of 1 sent on your signature" |
| 4 | 5 | press Send on the held vendor booking for S5 | **Send** twice | S5: Booked green |
| 5 | 6 | press Send on the held vendor booking for S6 | **Send** twice | S6: Booked green |

**Expect at the end:** the bar reads "SHOWCASE COMPLETE" over "All ten scenes
played. Check the record to finish." The recap under it reads **14 waiting
for you**, "3 to send or not · 11 to handle · **2 hot leads to call**", and
its four buttons read **✓ Record intact**, **4 of 4 sent on your
signature**, **Today: 16 client messages · 3 leads · 3 bookings**, **1 of 6
connected**. Needs you counts **14**.

Tap **1 of 6 connected**. **Expect:** **Proof and connections** opens lower
on the page: four tiles (**✓ Intact**, **4 of 4**, **3** held, **16** client
messages) and the six connection chips, with only **Vendor roster: loaded**
in green.

![The showcase at its first marketing hold](images/desk-manual/02-your-move.png)

## T3 - Don't send (showcase)

Still on the finished showcase. On the first held card (Book a vendor, S1),
tap **Don't send**, type `wrong photographer`, tap **Sign: don't send**.

**Expect:** a note at the bottom "Signed: not sent - Book a vendor"; the card
leaves; the recap reads **13 waiting for you** and "2 to send or not"; its
**4 of 4 sent on your signature** does not change (nothing went out); in
Proof and connections the held tile reads **2** with "· 1 you signed not to
send"; the **What just
happened** line near the bottom reads "· latest: You signed Don't send: books
the vendor (wrong photographer)".

![Don't send with a reason](images/desk-manual/13-dont-send.png)

Then tap **Don't send** on another card and tap **Keep it held**.
**Expect:** the card stays, unchanged.

## T4 - The day's work (showcase)

Still on the showcase. Find **Today's work** under the connection chips.

**Expect:** its title line reads "· 16 client messages · 3 leads · 3 bookings ·
7 held for you · 4 releases you signed".

Tap the title. **Expect:** three groups. Among the lines: Leads captured
**3**, Hot leads flagged to you **2**, Client messages written and released
**16**, Vendor bookings sent **3**, Messages held for your signature **7**,
Compliance problems caught **1**, Unsigned or tampered messages refused **1**,
Releases you signed (Send) **4**, Don't-sends you signed **1** (from T3),
Continue / Cancel decisions **1**, Transactions closed **1**.

Tap **Client messages written and released**. **Expect:** 16 lines, newest
first, each with a time, a client (S4 ... S9), "11 Client Communication →
outside: sends the client a message" and a short code (the entry's
fingerprint in the audit record).

Tap **Print the day**. **Expect:** the print window shows the header, "Day:"
with today's date, and the day's work with every line opened; nothing else
from the page. Cancel the print.

![The day's work](images/desk-manual/19-day.png)

## T5 - The record checks

Press **Check the record**.
**Expect:** a note "The record is intact".

Stop the showcase with **Ctrl+C**.

## T6 - Your live desk, first run

In a new folder for this test (your real records are untouched):

```bash
export LISTINGASSISTANTS_STATE_DIR=$PWD/test-state     # PowerShell: $env:LISTINGASSISTANTS_STATE_DIR="$PWD\test-state"
python tools/desk.py
```

**Expect:** it refuses: `no key in .../test-state: run python tools/console.py
init and python tools/console.py onboard first`.

```bash
python tools/console.py init
python tools/console.py onboard --name "Your Name" --login you@yourbrokerage.example
python tools/desk.py
```

**Expect:** `init` prints `"operator_key": "generated, private: mode 0o600"`
(Windows: "only your account ... on the Windows permission list"). The page
shows **LIVE · your records**, your name and login at the top left; the
recap reads **Nothing is waiting for you**, "All quiet.", **✓ Record
intact**, **0 of 0 sent on your signature**, **Today: nothing yet**, **0 of 6
connected**; Needs you says "Nothing is waiting for you." and Listings "No
listings yet."; **Your team · 20 idle**; **Today's work · nothing recorded
yet**; and, in Proof and connections, the chip **Vendor roster:
unratified**.

![A first live desk](images/desk-manual/15-live-first-run.png)

## T7 - The lock

With the desk from T6 still running, in a second window (same
`LISTINGASSISTANTS_STATE_DIR`):

```bash
python tools/console.py session scenes/scene04_new_listing.jsonl --config-dir scenes/config
```

**Expect:** `{"error": "the Broker Desk is running on .../test-state (pid N) -
stop it, or do this from the desk; ..."}` and nothing changes on the page.

Try a second desk on the same folder: `python tools/desk.py --port 8770`.
**Expect:** `a desk is already running on .../test-state (pid N)`.

Stop the desk (Ctrl+C).

## T8 - A test script into your live desk

The scenes' vendor roster is a draft. Ratify it for this test: open
`scenes/config/vendor_panel.json`, replace the `_status` line's text with
`RATIFIED <today YYYY-MM-DD> <your name>`, save.

```bash
python tools/desk.py --config-dir scenes/config --script scenes/scene04_new_listing.jsonl
```

**Expect:** still **LIVE · your records**; the bar reads "TEST SCRIPT ·
SCENE04_NEW_LISTING.JSONL", step 0 of 11; **Vendor roster: loaded**.

Press **Next** until the bar turns red.
**Expect:** "Your move: press Send on the held vendor booking for S4", step
4 of 11; the Book a vendor card for S4 outlined.

![A test script waiting for you](images/desk-manual/16-test-script.png)

## T9 - Restart in the middle

Without pressing Send, stop the desk (Ctrl+C) and start it again with the
same command as T8.

**Expect:** the bar is back at "Your move: press Send on the held vendor
booking for S4", step 4 of 11 - not step 0. The S4 listing card shows once,
not twice.

Now press **Send** twice, then **Next** until the bar turns red again
("press Send on the held marketing for S4"), and **Send** twice.

**Expect at the end:** the bar reads "TEST SCRIPT COMPLETE" over "All 11 lines
played. Check the record to finish."; S4's
track green from Signed to Marketed; the recap reads **2 of 2 sent on your
signature** and **✓ Record intact**. The listing
was signed with *your* key: your login is at the top left.

## T10 - Don't send on your live desk

Stop the desk and start it with the next scene:

```bash
python tools/desk.py --config-dir scenes/config --script scenes/scene05_compliance.jsonl
```

Play it through; press **Send** twice when it asks for the S5 booking. The
script ends with the S5 marketing held. On that card tap **Don't send**, type
`hold for new photos`, tap **Sign: don't send**.

**Expect:** the card leaves; the recap's "N of N sent on your signature" does
not move; in Proof and connections the held tile adds "· 1 you signed not to
send"; S5's Marketed step stays grey; the **What
just happened** line reads "· latest: You signed Don't send: ... (hold for
new photos)".

## T11 - The daily clock from the desk

Press **Run today's checks**.
**Expect:** a note "Today's checks ran". Open **What just happened**: new
lines, the morning briefing from 18 among them ("18 Calendar & Task
Management → you: delivers a report"). In **Today's work**, Daily check runs
goes up by one.

## T12 - A tablet

Stop the desk, then:

```bash
python tools/desk.py --lan
```

**Expect:** it prints a link like `http://<this-computer>:8765/?t=...`.
On a tablet or phone on the same network, open that link with your
computer's network address in place of `<this-computer>`.

**Expect:** the same page, one column, with your cards. Open the address
**without** the `?t=...` part: the page answers `{"error": "access code
required"}`.

![The desk on a tablet](images/desk-manual/14-tablet.png)

## T13 - Windows only

On Windows, in PowerShell: start `python tools\desk.py --showcase --fresh`,
press **Next** a few times, then **Ctrl+Break** (or Ctrl+C).

**Expect:** the desk stops; no `desk.lock` is left in `showcase-state\`;
starting it again (without `--fresh`) works and keeps the cards.

Run `python tools\console.py init` in a new test folder and check the key's
permissions: right-click `operator-key.bin` → Properties → Security.
**Expect:** your account, SYSTEM and Administrators (OWNER RIGHTS may be
listed too) - and no "Users", "Authenticated Users" or "Everyone".

## T14 - What you open stays open

On any desk with items in **Needs you**: tap the title of a closed section
(for example "A question for you") to open it, and close an open one. Wait
five seconds. **Expect:** both stay as you left them through the page's
refreshes. Reload the page. **Expect:** still as you left them.

On a held message, tap **Send** once. **Expect:** "What would go out" opens
by itself, and the button reads "Tap again to sign and send". Wait five
seconds without tapping: the button goes back to **Send**.

---

## When a test does not match

Write down: the test number, the time, what the bar and the card said, and
what you expected. Take a screenshot of the page. Copy the last lines of the
window the desk runs in. Keep the state folder as it is (do not delete or
`--fresh` it): the audit record in it shows exactly what happened.

## Results

| Test | Pass / fail | Notes |
|---|---|---|
| T1 The build is sound | | |
| T2 The showcase plays through | | |
| T3 Don't send (showcase) | | |
| T4 The day's work (showcase) | | |
| T5 The record checks | | |
| T6 Your live desk, first run | | |
| T7 The lock | | |
| T8 A test script into your live desk | | |
| T9 Restart in the middle | | |
| T10 Don't send on your live desk | | |
| T11 The daily clock from the desk | | |
| T12 A tablet | | |
| T13 Windows only | | |
| T14 What you open stays open | | |
