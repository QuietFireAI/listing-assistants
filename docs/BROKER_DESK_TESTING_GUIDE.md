# The Broker Desk - Testing Guide

Twelve tests, in order, each with what to do and exactly what you should see.
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

**Expect:** `1015 passed, 1 skipped` on Linux or macOS (the skipped test runs
only on Windows); `1016 passed` on Windows, after 5 to 8 minutes.

## T2 - The showcase plays through

```bash
python tools/desk.py --showcase --fresh
```

Open http://127.0.0.1:8765.

**Expect:** the badge reads **SHOWCASE · synthetic data**; a yellow bar at the
top reads "Scene 1 · The signature matters"; **Next** is blue.

Press **Next** repeatedly (or tick **play on its own**). Five times the bar
turns red and reads "Your move: ...", the matching card in **Needs you** is
outlined in red, and **Next** is greyed out until you answer:

| # | Scene | The bar says | You press | Expect after |
|---|---|---|---|---|
| 1 | 3 | press Cancel on the paused thread for S3-hot-again | **Cancel** | The card leaves; the lead "Pat Hot ... S3-hot-again" reads "Closed by your decision" |
| 2 | 4 | press Send on the held vendor booking for S4 | **Send**, then **Tap again to sign and send** | Listing S4: Booked turns green |
| 3 | 4 | press Send on the held marketing for S4 | **Send** twice, as above | S4: Marketed green, "Now: Marketing out"; proof tile "1 of 1" |
| 4 | 5 | press Send on the held vendor booking for S5 | **Send** twice | S5: Booked green |
| 5 | 6 | press Send on the held vendor booking for S6 | **Send** twice | S6: Booked green |

**Expect at the end:** the bar reads "Showcase complete - All ten scenes
played"; the proof strip reads **✓ Intact**, **4 of 4**, **3** held, **16**
client messages; Needs you counts **14**.

![The showcase at its first marketing hold](images/desk-manual/02-your-move.png)

## T3 - Don't send (showcase)

Still on the finished showcase. On the first held card (Book a vendor, S1),
tap **Don't send**, type `wrong photographer`, tap **Sign: don't send**.

**Expect:** a note at the bottom "Signed: not sent - Book a vendor"; the card
leaves; the held tile reads **2** with "· 1 you signed not to send"; the
**4 of 4** tile does not change (nothing went out); the first line of **What
just happened** reads "You signed Don't send: books the vendor (wrong
photographer)".

![Don't send with a reason](images/desk-manual/13-dont-send.png)

Then tap **Don't send** on another card and tap **Keep it held**.
**Expect:** the card stays, unchanged.

## T4 - The record checks

Press **Check the record**.
**Expect:** a note "The record is intact".

Stop the showcase with **Ctrl+C**.

## T5 - Your live desk, first run

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
shows **LIVE · your records**, your name and login at the top left, **✓
Intact**, **0 of 0**, "Nothing is waiting for you.", "No listings yet.", all
twenty agents IDLE, and the chip **Vendor roster: unratified**.

![A first live desk](images/desk-manual/15-live-first-run.png)

## T6 - The lock

With the desk from T5 still running, in a second window (same
`LISTINGASSISTANTS_STATE_DIR`):

```bash
python tools/console.py session scenes/scene04_new_listing.jsonl --config-dir scenes/config
```

**Expect:** `{"error": "the Broker Desk is running on .../test-state (pid N) -
stop it, or do this from the desk; ..."}` and nothing changes on the page.

Try a second desk on the same folder: `python tools/desk.py --port 8770`.
**Expect:** `a desk is already running on .../test-state (pid N)`.

Stop the desk (Ctrl+C).

## T7 - A test script into your live desk

The scenes' vendor roster is a draft. Ratify it for this test: open
`scenes/config/vendor_panel.json`, replace the `_status` line's text with
`RATIFIED <today YYYY-MM-DD> <your name>`, save.

```bash
python tools/desk.py --config-dir scenes/config --script scenes/scene04_new_listing.jsonl
```

**Expect:** still **LIVE · your records**; the bar reads "Test script ·
scene04_new_listing.jsonl", step 0 of 11; **Vendor roster: loaded**.

Press **Next** until the bar turns red.
**Expect:** "Your move: press Send on the held vendor booking for S4", step
4 of 11; the Book a vendor card for S4 outlined.

![A test script waiting for you](images/desk-manual/16-test-script.png)

## T8 - Restart in the middle

Without pressing Send, stop the desk (Ctrl+C) and start it again with the
same command as T7.

**Expect:** the bar is back at "Your move: press Send on the held vendor
booking for S4", step 4 of 11 - not step 0. The S4 listing card shows once,
not twice.

Now press **Send** twice, then **Next** until the bar turns red again
("press Send on the held marketing for S4"), and **Send** twice.

**Expect at the end:** "Test script complete - All 11 lines played"; S4's
track green from Signed to Marketed; **2 of 2**; **✓ Intact**. The listing
was signed with *your* key: your login is at the top left.

## T9 - Don't send on your live desk

Stop the desk and start it with the next scene:

```bash
python tools/desk.py --config-dir scenes/config --script scenes/scene05_compliance.jsonl
```

Play it through; press **Send** twice when it asks for the S5 booking. The
script ends with the S5 marketing held. On that card tap **Don't send**, type
`hold for new photos`, tap **Sign: don't send**.

**Expect:** the card leaves; held tile "· 1 you signed not to send"; the
**N of N** tile does not move; S5's Marketed step stays grey; the feed reads
"You signed Don't send: ... (hold for new photos)".

## T10 - The daily clock from the desk

Press **Run today's checks**.
**Expect:** a note "Today's checks ran"; new lines in **What just happened**
(the morning briefing from 18 among them).

## T11 - A tablet

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

## T12 - Windows only

On Windows, in PowerShell: start `python tools\desk.py --showcase --fresh`,
press **Next** a few times, then **Ctrl+Break** (or Ctrl+C).

**Expect:** the desk stops; no `desk.lock` is left in `showcase-state\`;
starting it again (without `--fresh`) works and keeps the cards.

Run `python tools\console.py init` in a new test folder and check the key's
permissions: right-click `operator-key.bin` → Properties → Security.
**Expect:** your account, SYSTEM and Administrators (OWNER RIGHTS may be
listed too) - and no "Users", "Authenticated Users" or "Everyone".

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
| T4 The record checks | | |
| T5 Your live desk, first run | | |
| T6 The lock | | |
| T7 A test script into your live desk | | |
| T8 Restart in the middle | | |
| T9 Don't send on your live desk | | |
| T10 The daily clock from the desk | | |
| T11 A tablet | | |
| T12 Windows only | | |
