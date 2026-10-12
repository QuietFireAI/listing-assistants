# OPERATOR_TESTING_MANUAL.md - Test It Like a Customer Would

This is the script for operational testing: you, set up as the broker any
buyer of this product would be, driving the swarm through the console with
no Python, and a camera running. The ten scenes are ready-made files in
`scenes/` with synthetic data; you run each one and compare the screen with
the **Expected** below. A test (`tests_listing/test_operator_scenes.py`) runs
the same ten files on every build and checks every Expected, so what you
film is what the suite checks.

Two ground rules for the recordings. Never cut between action and outcome:
the footage is the unbroken line from "I did this" to "the log shows this."
End every session with `verify` on camera: the chain check and the anchor
are the proof the footage was not staged.

If what you see differs from what is written here, that difference is a
finding: capture it, do not work around it.

## How the console works (read once)

- Each scene is one console session: `python tools/console.py session scenes/<file> --config-dir scenes/config`.
- **State carries between sessions.** At the end of every session the swarm's
  state (every agent's records, held messages, open holds) is saved to
  `console-state/swarm-state.sqlite`, and its fingerprint is written to the
  audit log. The next session restores it only when the audit chain vouches
  for it; otherwise it refuses, changes nothing and tells you why. Run the
  scenes in order, in one folder, and Scene 10's briefing covers all of them.
- **Everything that needs you prints the moment it lands** as
  `{"HUMAN_QUEUE": ...}`: escalations, clarifications, integrity violations,
  held outbound messages, and decisions waiting on you (`decision_required`).
- **Messages leaving for a vendor, a counterparty or the public hold** until
  you release them: `{"do": "release", "ctx": "...", "intent": "..."}` signs one
  release per held message with your key. `{"do": "show", "what": "held"}` lists them.
- **Threads an agent cannot finish on its own hold** until you sign
  `{"do": "decide", "ctx": "...", "decision": "continue"}` or `"cancel"`.
  `{"do": "show", "what": "waits"}` lists them.
- `{"do": "send", ...}` injects a message as if from the named sender. Use
  `external` (the outside world) or `human` where the closed track has a
  route; the hub applies every check either way.
- **Everything is also written in plain language** to
  `console-state/readable/stream.log` (`python tools/show_logs.py` shows the
  last 25 lines), and each client's records are filed in that client's
  drawer under `console-state/drawers/` (`python tools/inspect_client_drawer.py --list`).
  Good B-roll between scenes: the stream scrolling, and one drawer's files
  with their hashes re-checked.

## Scene 0 - One-time setup

```
git clone https://github.com/QuietFireAI/listing-assistants.git
cd listing-assistants
pip install -r requirements.txt
python -m pytest tests_listing/          # expect: 829 passed
python tools/console.py init             # generates YOUR signing key
python tools/console.py onboard          # your name and login, asked once
```

Expected: the test count; `{"initialized": ..., "operator_key": "generated (0600)", ...}`;
then `{"onboarded": {...}, "not_armed": {...}}`. The `not_armed` block says
plainly what is not switched on: the identity-provider signer binding (no
identity provider is connected) and the text pager, which
`python tools/console.py pager` turns on if you want pages on your phone
while filming (optional; every page also prints on screen).

**Ratify the test vendor roster on camera.** Open `scenes/config/vendor_panel.json`.
Its `_status` line says UNRATIFIED. Replace that line's text with
`RATIFIED <today's date YYYY-MM-DD> <your name>` and save. This is the same
rule every configuration file follows: a draft is never loaded. (Run any
scene before you do this and the first line says `"vendor_roster": "unratified"`,
and Scene 4 cannot book a photographer.)

## Scene 1 - The signature matters (`scene01_signature.jsonl`)

Expected: line 1 (an unsigned listing change) - `"status": "reject",
"reason": "unverified signature on authority intent"`, and an
`integrity.violation` page. Line 2 (the same intent, signed by your key) -
`"status": "ack"`. **The opening shot of any demo: the unsigned command
bounces, yours lands.**

## Scene 2 - Configure your business (`scene02_configure.jsonl`)

Sends a signed scoring rubric to 02 and a fair-housing ruleset to 17, then a
broken ruleset (a phrase with no rule id).

Expected: three `ack`s (the hub delivered all three), and a
`clarification.request` page: `"malformed compliance ruleset rejected"`
naming the problem and version `r2`. The earlier ruleset stays active - Scene 5
uses it.

## Scene 3 - Speed to lead, and the same person twice (`scene03_speed_to_lead.jsonl`)

Line 1 tells Agent 01 which listings are yours (signed). Then a hot web lead
asking about L1.

Expected:
- An `escalation.hot_lead` page for `S3-hot` with `"sla_s": 300`, and nothing
  sent to the lead.
- The briefing (line 3) shows `hot_lead_human_response` waiting for `S3-hot`,
  since today.
- The same person arrives again under a new context (same phone, written
  differently). Expected: **no second hot-lead page**; a `decision_required`
  page instead - possible duplicate person, held. `show waits` lists it.
- Line 6 cancels it: `"handler_result": "cancelled"`. Nothing was merged or
  scored. (Sign `continue` instead and it is scored as a separate person and
  pages you.)
- A lead that refuses all contact is captured with its consent recorded, and
  no message ever goes to it.

## Scene 4 - New listing, end to end (`scene04_new_listing.jsonl`)

One signed listing authorization with go-live, then the outside world answers.

Expected:
- The photography booking holds for you (`HUMAN_QUEUE` with
  `"absolute_signal"`); `show held` lists it; line 4 releases it.
- A photo delivery with `"proof_artifact_present": false` releases
  **nothing**: line 6 shows only the booking in `external`. The claim is not
  the artifact.
- The real delivery: 04 drafts, 17 approves, the assets go to 05 and 12, the
  listing goes active (11, 12, 14 told), and the campaign holds for you.
- After line 9's release, `external` shows the booking, the seller's
  "active" notice and the campaign.

## Scene 5 - Compliance catches your planted phrase (`scene05_compliance.jsonl`)

A listing whose features include the phrase from your Scene 2 ruleset.

Expected (on the audit log): `content.verdict: flagged` citing the phrase
and rule FH-1; 04 removes exactly that phrase and resubmits; the second
verdict is `approved`; no released asset contains the phrase.

## Scene 6 - Photos versus data sheet (`scene06_photo_contradiction.jsonl`)

The data sheet claims an in-ground pool the photos do not show.

Expected: a `clarification.request` page, `"photos contradict data sheet"`,
naming `in-ground pool`; no draft reaches 17.

## Scene 7 - Under contract to close (`scene07_contract_to_close.jsonl`)

The executed contract arrives by email (through 11), the signed status flip
to pending, the signed timeline, then the clock.

Expected:
- 07 asks 08 for the inspection report and the financing-contingency removal
  by their real document names, and asks 09 for an inspector. There is no
  inspector on your roster, so 09 holds that for you.
- Sweep on 2026-10-21: the inspection and financing-contingency deadlines
  alert as overdue, **once**; the financing contingency also goes to the legal
  line; the vendor hold-up escalates once.
- Line 8 names the title company as the expected sender of the settlement
  statement (signed). Line 9: it arrives by email; 07 closes the transaction
  to 14, 15 and 16 with the sale price and close date.
- Sweep on 2026-12-02: `{"agent": "16", "sweep": "post_close_milestones", "result": "sent:30"}` -
  the 30-day check-in, from the clock, with nobody asking.

## Scene 8 - Showing bump needs hotness AND you (`scene08_showing_bump.jsonl`)

Three buyers want the same house Saturday morning. You record each buyer's
signed representation agreement first (Agent 14).

Expected:
- Buyer A is booked at 10:00.
- Buyer B claims a deadline but is not a hot lead: plain conflict
  sequencing, reason naming the tier gate, **no bump offered**.
- Buyer C is a hot lead (scored by 02 from a real web lead) with the same
  claim: the bump **holds for you**; A's showing stands.
- Line 9, your signed confirmation: A gets a `showing_bumped_notice`, C gets a
  confirmation.

## Scene 9 - Complaint containment (`scene09_complaint.jsonl`)

A viral complaint on a monitored channel.

Expected: an `escalation.complaint` page with the verbatim text and
`"priority": "viral"`; a scheduled touch to that client **holds**
(`external` stays empty for S9); your signed release of the hold; the next
touch goes out.

## Scene 10 - The books don't lie (`scene10_books.jsonl`)

Expected: the briefing lists every wait left open across Scenes 1-9
(for example 02's hot lead from Scene 3 and 08's missing inspection report
from Scene 7), because the state carried between sessions. The end-of-day
report's `logging_gaps` is `[]`, and its `readable_ledger` names the ledger
file with `"chain_ok": true`. Then the anchor.

Off the console, three checks of what the scenes left behind:

```
python tools/show_logs.py --eod                  # the day's ledger, built from the chain
python tools/inspect_client_drawer.py S7         # Scene 7's client: package, timeline,
                                                 # contract, settlement statement, CRM entries;
                                                 # ends "[OK] ... match their recorded SHA-256"
python tools/dashboard.py --html                 # S7 shows CLOSED, S4/S5 MARKETING READY
```

Close the recording with:

```
python tools/console.py verify
```

`{"chain": {"ok": true, ...}}`. Then, off camera, copy
`console-state/console-audit.jsonl`, change one word on any line of the copy,
and run `python tools/console.py verify --audit-log <copy>` ON camera:
expected `"ok": false` with `break_at` naming that line, and exit code 1.
That is the closing shot: the record defends itself.

## Optional Scene 11 - model-written remarks (needs a local model)

Not part of the ten scenes and not run by the suite against a real model
(the suite uses a stand-in model over real HTTP). Run it only if a model is
served on this machine, for example by Ollama at `http://localhost:11434/v1`.

1. `python tools/restore_point.py --exam my-model-1 --model-url http://localhost:11434/v1 --model-name <model>`.
   Expected: four graded answers and `[PASSED]` or `[FAILED]`. Only a pass
   activates the checkpoint. A model that fails stays off; that is the
   correct outcome, not a bug.
2. A session with `--model-url ... --model-name <model>`: its first line shows
   `"model_drafting": {"ok": true, "checkpoint": "my-model-1"}`. Sign
   `{"do": "config", "to": "04", "ctx": "setup", "payload": {"drafting": {"mode": "model"}}}`,
   then run Scene 4 or 5's listing. Expected: the `content.review` to 17
   carries `remarks` and `"remarks_source": "model:my-model-1"`; if the model
   added a number or skipped its reasoning, the draft says
   `"remarks_source": "rules"` and you are told why.

## Resolving what is left open

- A hot lead: `{"do": "config", "to": "02", "ctx": "<any>", "payload": {"resolve_hot_lead": "<ctx>"}}`.
- A complaint hold: `{"do": "config", "to": "11", "ctx": "<ctx>", "payload": {"resolve_complaint_hold": "<ctx>"}}`.
- A held thread: `decide` continue or cancel, as above.
- A held outbound message: `release`.

## Starting over

The console never replaces your log silently. To start clean, move the
`console-state/` folder aside yourself and run `init` and `onboard` again.

## Filing what you find

Anything that deviates from an Expected: file it with the scene file, the
line number, the actual JSON output and the anchor from that session. That
tuple is a complete, replayable bug report. No deviations across all ten
scenes, on camera, with the chain verified at the end, is the operational
sign-off this manual exists to produce.
