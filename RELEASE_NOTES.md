# Release Notes - ListingAssistants (next release, untagged)

Branch `audit-fixes-2026-10-11`, built on `33a835c`. The tag is the owner's
step. Every item below has a test in `tests_listing/`; the full change list,
with before/after and evidence, is in the audit-fix autopsy report.

## What this release is

ListingAssistants: twenty deterministic agents for the coordination work of a
residential listing business, on a closed track. One dispatcher hub routes
every message to and from an agent, each route is pre-approved in
`identity/routes.json`, authority actions need a verified signature, and every
message lands on a hash-chained audit log. 24 playbooks, each with an
end-to-end test.

## Changes in this release

- **Windows install in one line, and the playbook show (2026-10-21, owner
  decisions).** `install.ps1`: paste one PowerShell line; no admin, a
  private Python 3.12, everything in `%LOCALAPPDATA%\ListingAssistants`,
  your records kept on reinstall, desktop shortcuts for your Desk and for
  the playbook show. CI runs the installer on a Windows machine from each
  commit. `python tools\desk.py --playbooks` plays all 24 playbooks on the
  desk, each in a fresh office, stopping at your moves, with each run's
  after-action report. The desk's new **Outbox** lists what would have gone
  out, marked not sent (no outside connections yet); the recap now says
  "released on your signature", not "sent".

- **Playbooks signed (2026-10-21).** You signed 22 of the 24 playbooks:
  P01 to P15 and P18 to P24 (each carries its own `ratified` line in
  `identity/playbooks.json`; P06 after it was changed to start at the
  buyer's first criteria). P16 and P17 are not signed yet: they run on real
  mornings and evenings first. The tuple map's placements are accepted.
  With the signing: a nurture touch Agent 11 did not send is reported back
  to Agent 03 and tried again (P11); a **Release hold** button on the Broker
  Desk for a client held after a complaint (P14); the vacant-property check
  is daily and never stacks bookings (P20).

- **Tuple map and a Mark handled button (2026-10-21, owner request).**
  `docs/TUPLE_MAP.md` sorts all 273 tuples by what they protect (seven
  categories) and how bad a failure would be (three tiers), with run status
  and the playbooks each can fire in; the placing is in
  `synth/tuples/TUPLE_MAP.json`, PROPOSED for your review, and a test keeps
  the page current. The Broker Desk lists Agent 19's prospects waiting, with
  a **Mark handled** button that signs the `prospects_handled` setting.

- **Owner playbook walkthrough (2026-10-21).** P01 and P02 signed. Ten
  decisions applied (`docs/walkthrough/PLAYBOOK_WALKTHROUGH_2026-10-21.md`):
  a comparables request starts P23 on a live listing and P15 otherwise;
  buyer matches wait for the signed buyer agreement; stated criteria
  exclude, numbers are minimums; a close with open milestones waits for
  you, naming them; the day-0 nurture touch goes at once inside contact
  hours; the morning briefing carries overnight leads, yesterday's books,
  prospects waiting and market changes; the end-of-day books run on the
  evening clock (`run_sweeps.py --evening`) with Agent 15's figures; each
  prospect reaches you once, with its comps. Farm campaigns outside the
  Clear Cooperation hold: confirmed. Found on the way: Agent 01 forwarded a
  lead before logging its consent, which blocked an immediate touch.

- **One product (owner decisions 2026-10-20).** The dispatcher core is
  part of this repository and no longer copied from dispatcher-agents
  (`dispatcher/CORE_ORIGIN.md`); the pillars are built in
  (`dispatcher/pillar_lib/`, five of them; splitvantage removed) and
  nothing is installed from git. The pillar code is now covered by boot
  attestation.

- **Playbook runs (2026-10-20).** The dispatcher tracks each playbook as
  runs from the table in `identity/playbooks.json` (PROPOSED until you
  ratify it): a message that starts two playbooks, or a run that conflicts
  with one already open for the same client, is held for your choice; with
  25 questions waiting, new runs wait and are released by priority class;
  a step the track refuses halts its run as a defect in the playbook; every
  run ends with an after-action report listing your signed decisions and
  any missing tuple it found. All 24 playbooks run start to end through the
  console (`python synth/tuples/run_tuples.py --set playbooks`). Found and
  fixed on the way: a price change halted every live ad (Agent 12); a farm
  campaign could never publish (Agent 12, rule confirmed 2026-10-21); there
  was no way to schedule an open house (Agent 06, P04 built). Settings:
  `docs/TUNING_MANUAL.md`, "Ratified 2026-10-15".

- **Dispatcher checks (2026-10-15).** A failure that escapes the hub halts
  all traffic and alarms; unanswered escalations are re-alerted at 30
  minutes and the owner paged at 60; a skewed clock holds time-triggered
  checks; an identity reload is refused while work is open; the morning
  briefing names items whose source is missing from the log; your calendar
  instruction past a contractual deadline is held for you. A test harness
  injects the failures no product entry can produce
  (`synth/tuples/fault_harness.py`). Tuples now: 246 pass, 2 variance
  (01-01, 04-03, owner decisions), 15 not reachable, 5 not built, 4 retired.

- **Your decisions of 2026-10-14, wired.** A phrase tagger reads client
  words at intake, and any angry or negative message goes to you as a
  complaint at once, whatever else it asks. Compliance is told each piece of
  content's type and state and checks every ad for your brokerage
  identification, which Agent 12 adds to every ad (set it with a signed
  `brokerage_identification` to Agents 12 and 17; until then approved ads
  are held). Showings read occupancy, status and state from your listing
  record. A signed change to beds, baths, square feet, remarks, address or
  photos is applied and logged. Tuples now: 224 pass, 2 variance, 22 not
  reachable, 20 not built, 4 retired. Details and the new phrase lists and
  settings: `docs/TUNING_MANUAL.md`, "Ratified 2026-10-14".

- **Every tuple run through the product (2026-10-14).** All 272 tuples
  (agents 00 to 20 and `SWARM.md`) have a spec in `synth/tuples/` and were
  run through the console as a broker drives it:
  `python synth/tuples/run_tuples.py` writes `synth/tuples/REPORT.md`.
  213 pass. 2 differ from the tuple and wait on an owner decision (01-01,
  04-03). 33 cannot be reached from the product's entries, 20 have no code
  path, 4 are retired; each says why. Seventeen fixes came out of the runs
  (Agents 03, 04, 05, 06, 07, 09, 10, 11, 12, 14, 15, 17 and 19), listed
  with the open decisions in `docs/TUNING_MANUAL.md`, "Tuple runs
  (2026-10-14)". CI checks every tuple has its spec and reruns the 19
  specs whose code changed. A plumbing pass the same day wired 07-03 (a
  document's own deadline is compared with the timeline) and 18-06 (the
  calendar tracks deadlines by source), and Agent 11 no longer confirms a
  channel change that Agent 14 did not record.

- **Three lead-capture gaps closed (2026-10-14, found by the synthetic
  sample run).**
  - A lead marked as an agent shopping for a client now reaches Agent 02's
    agent-to-agent rule. Before, Agent 01 dropped the flag and the lead
    scored as a consumer.
  - The same phone written with the country code (`+1 216 555 0101`) is
    now matched as the same person as `(216) 555-0101`.
  - The do-not-contact list is now matched whatever the number's format,
    and on the email as well as the phone.

- **The Broker Desk answers only its own page (2026-10-14).** Before, the
  desk on this computer had no check at all. A web page the broker visited
  could reach it by DNS rebinding, read it, and post actions the desk signs
  with the broker's key. Now:
  - The desk on this computer answers only a request addressed to it by
    name (`127.0.0.1`, `localhost` or `[::1]`).
  - An action must come from the desk's own page and must be JSON.
  - The access code of the `--lan` desk is compared in constant time.
- **Your records folder is private (2026-10-14).** On Linux and macOS the
  record, client drawers, readable logs and the state store used to be
  readable by every account on the computer. Only the key and the pager
  settings were private. Now:
  - Every program that writes them creates files readable only by your
    account.
  - The console, the desk and the daily clock tighten a folder an earlier
    version left readable.
  - On Windows, files under your user folder were already private to you;
    that is not measured by the suite.
- **The MCP server's boot check leaves no file behind (2026-10-14).** Each
  start used to leave a `conformance-*.jsonl` file in the temp folder.

- **MANNERS is wired (owner decision 2026-10-14).** MANNERS.md's
  re-injection now fires: at P01's three phase gates, at every signed
  human decision the system accepts (a release, a decline, a HITL
  decision, a price change, a config.update), and every 10 envelopes an
  agent handles with no other trigger. Each goes on the audit log
  (`manners.reinjection`), and Agent 04's drafting prompt carries the
  MANNERS.md text on every call. The post-compaction trigger has no event
  in this product (nothing compacts a context) and is documented as such.
- **Boot attestation.** `console.py init` signs, with your key, the SHA-256
  of every importable file in `dispatcher/` and `tools/` (the code and the
  programs that start the system),
  everything in `identity/`, MANNERS.md, SWARM.md, the playbooks and job
  descriptions, and every agent's SKILL.md and DECISIONS.md, and records
  it on the audit chain. The console, the Broker Desk, the daily clock and
  `repair-record` check it before loading any agent code or writing
  anything, and refuse on any change, on an older attestation put back, or
  on another key's attestation; after reviewing a change,
  `console.py attest` names what changed and signs it (Operator Guide §16).
  An existing install needs `console.py attest --new-key` once (and once
  per log kept elsewhere, with `--audit-log`): taking a log written before
  attestation is recorded on the chain. A replaced key takes a log over only
  with `console.py attest --new-key`, recorded on the chain. The daily
  clock now also checks signatures with your key. This is drift detection with your
  signature, not tamper resistance: someone who can write to the install
  can also change the checker.

- **The Broker Desk.** `python tools/desk.py` shows the broker everything
  waiting on them, with Send, Continue/Cancel and Done buttons that sign
  with the broker's key, plus listing progress, hot-lead clocks, the
  agents' status and a proof strip. `--showcase` replays the operator
  scenes for recording (README, "The Broker Desk").
- **"Don't send."** A held message can now be answered no: a signed
  decline (`Hub.decline_disclosure`, core `50c65a8`) removes that one
  message unsent and puts the decline and your reason on the audit log. The
  decision is inside what is signed, so a decline can never be used as a
  release, nor the other way round. On the desk it is the **Don't send**
  button; in a console session, `{"do": "decline", ...}`.
- **The desk serves several screens at once.** Connections get their own
  threads; every swarm call still runs on one thread, as SQLite requires. A
  stalled connection no longer freezes everyone's page.
- **The desk on Windows is tested.** CI runs the desk's tests on
  `windows-latest`, including the lock's process check and a clean
  Ctrl+Break stop (the desk now handles Ctrl+Break).
- **The pager texts you from the desk and the daily clock.** Turned on with
  `python tools/console.py pager`, it used to text only during console
  sessions while the desk showed it as on. Now the desk and the clock text
  you too, and a broken `pager.json` stops them with the reason.
- **Words used here.** `docs/GLOSSARY.md` explains every software word in
  plain language (tuple, playbook, swarm, closed track, hold, release and
  more); the README opens with the ones that matter most, and every manual
  and agent page points to it.
- **The day's work.** The desk counts what the swarm did each day, from the
  audit record: 14 kinds of work done for you, 4 kinds of protection, 5
  kinds of decision you signed. Every line opens to the entries behind its
  number; any day can be picked and printed. Counts only: emails and texts
  are not split (no channel is connected yet) and no time-saved figure is
  shown (that needs minutes per task that only the broker can set).
- **Broker Desk UI version 1.** The page, the README (with pictures of a busy day and a quiet first morning) and the manual all name it; a test keeps them agreeing.
- **A recap at the top.** One box says where things stand: how much waits
  for you and any hot lead to call, the record's check, how many messages
  went out on your signature, today's headline numbers, how many
  connections are live. Each part opens its detail; the proof tiles and
  connection chips fold below it and open themselves if the record ever
  fails. Listings are one row each with the step names printed once above
  them.
- **A calmer desk.** Needs you is in collapsible sections; a held message
  shows one line until opened, and opens itself when you tap Send, so a
  release is never signed unseen; listings fold their notes; Your team and
  What just happened are one line until opened. The desk remembers what you
  open. Typeface: Manrope (SIL OFL 1.1, bundled; `THIRD_PARTY_NOTICES.md`).
- **The Broker Desk has its own manual and testing guide.**
  `docs/BROKER_DESK_MANUAL.md` explains every part and button of the page
  with real screenshots; `docs/BROKER_DESK_TESTING_GUIDE.md` is fifteen tests,
  each with what you should see. `tests_listing/test_desk_manual.py` fails if
  a button, title, step, flag, picture or link they name stops existing.
- **Test scripts on your own desk.** `python tools/desk.py --script FILE`
  plays a session file into your live desk, signed with your key, stopping at
  your moves (Send, Continue/Cancel, Don't send). Its place is saved, so a
  restarted desk resumes it and applies no line twice; a broken line is
  refused at start with its line number.
- **Windows: the whole suite passes, and CI holds it there.** The first
  Windows runs found text files read without an encoding (Windows reads
  cp1252; 118 places fixed, 33 in core) and secrets "made private" with
  chmod, which does nothing on Windows - the signing keys and pager config
  were readable by other accounts. `dispatcher/private_file.py` now makes
  them private on every system. Windows: 1024 passed; Linux: 1023 passed,
  1 skipped (a Windows-only test).
- **Pictures for non-technical readers.** Every agent folder has a README
  with a diagram of who it hears from and who it talks to (drawn from
  `identity/routes.json`); every playbook in `docs/PLAY-BY-PLAY.md` has a
  numbered diagram of one real test run, holds and your releases included;
  the README, broker's manual, financial-capability page, guides and
  quickstart have diagrams of what they describe. `tools/gen_diagrams.py`
  draws them and `tests_listing/test_docs_diagrams.py` fails if one falls
  out of step with the routes or the playbook runs.
- **All agent traffic through the dispatcher.** The daily clock and the
  console's briefing and EOD reports reach agents as `clock.tick` messages
  through the hub (new route). Every agent send is checked: a rejected or
  undeliverable handoff records `handoff.failed` and goes to the human
  clarification queue.
- **Client replies.** Agent 11 routes replies only to agents that handle
  them (03, 04, 12, 13, 16, 20; 04 and 12 log the reply and hold it for the
  broker). Anything else goes to the broker with the client's words.
- **Lead scoring.** One rubric (`dispatcher/lead_rubric.py`) for Agent 02
  and the JEV adapter. An expired pre-approval letter earns no financing
  points, including a separately stated "preapproved".
- **Configs.** Draft config files are not loaded; each skip is logged.
  `config/authority_signers.json` is an unratified template again.
- **MCP server.** It signs authority actions for a host only in
  `--demo-signing` mode. Leftover medical-billing code removed.
- **Modules, corrected and wired** (all wired by 2026-10-12, see "Modules
  wired" below):
  client drawers (safe paths, client-bound filing, hash verification),
  signed HITL decisions, offline update packs (public-key verification,
  unlisted files and downgrades refused, `tools/sign_manifest.py`), SQLite
  store (exact decimal money, append-only ledgers, consent history with human
  confirmation of re-opt-in), JEV adapter (fail-closed confidence, explicit
  opt-in for external calls), Hermes seam (no fabricated reasoning or
  drafts), checkpoint manifest (no exam without a model), EOD report
  (integrity computed or labeled "not computed").
- **The operator scenes.** Ten ready-to-film scenes (`scenes/`) run session
  by session through the console; `tests_listing/test_operator_scenes.py`
  runs the same files on every build. Running them first found fourteen
  places where real agent-to-agent traffic broke while the unit tests,
  fed hand-written messages, passed. All fixed, among them: the console
  could not release a held message; the vendor roster always loaded empty;
  07 asked for documents by the wrong names, so 08 refused the real ones;
  a new listing matched no buyer; two buyers could be booked into the same
  house at the same time; nothing recorded a buyer agreement, so no client
  showing could book; undated vendor bookings skipped the license and
  insurance checks; the settlement statement's sale price never reached
  15; four waits never cleared.
- **Restart survival.** The swarm's state is saved to the SQLite store
  after each session and clock run and restored only when the audit chain
  vouches for that exact save. The daily clock runs on that state.
- **Held threads.** The same person under a new lead, a client reply that
  names no agent, and an approved social reply draft hold until the broker
  signs continue or cancel (HITL protocol, now wired).
- **Modules wired (2026-10-12).** Client drawers: Agents 04, 05, 07, 08, 14
  and 15 file each client's records, every filing on the audit chain with
  its SHA-256; the dashboard and inspector read them. Plain-language log:
  every chain entry also written in plain words, and the end-of-day ledger
  built from the chain. JEV adapter: Agent 02 scores every lead through it
  (local engine = 02's rubric; live JEV only on the broker's signed opt-in);
  a low-confidence result holds the lead. Model drafting: Agent 04 can use a
  model on this machine for listing remarks, only on the broker's signed
  switch and only while the active checkpoint passed the broker exam on
  that model (`restore_point.py --exam`).
- **Owner's J decisions applied (2026-10-12).** P18-P21 start from the daily
  clock; Agent 08 warns three days before a seller disclosure is due; the
  market-update paths in 03 and 11 are removed (market data goes only to
  the broker and Agent 19); the six pillar packages are pinned to exact
  commits; the console's text pager can be turned on (`console.py pager`).
  23 new decision tuples record these behaviors.
- **Dispatcher core (owner decision J10, 2026-10-12).** Changed in
  dispatcher-agents and synced here: the signature now covers who a message
  says signed it (provenance), so that claim cannot be altered after
  signing; the shared-secret HMAC signing tier is gone (Ed25519 only); the
  hub's JEV start-up line reports a key as present, never as live; the
  unauthenticated text-message command parser is removed. Signatures made
  before this release do not verify after it.
- **Consent and complaints (owner decisions, 2026-10-12).** Agent 11 sends
  nothing to a client without consent on record at Agent 14; a lead's
  consent comes in at capture, and the broker records any other client's
  with a signed `consent_record`. An angry client goes straight to the
  broker, logged, with no automatic reply.
- **Also fixed while wiring.** A capitalized prohibited phrase was flagged
  by 17 but never found by 04, so the draft bounced twenty times until the
  hub suspended the loop; a signed setting re-sent with the same values
  paged the broker as "unrecognized"; the README's P01 diagram did not
  render on GitHub.
- **Owner decisions applied.** Lead Nurture sends broker-written sequences
  from the clock after 17 clears them; Agent 13's neighborhood path removed
  (fair-housing steering risk); Agent 19 gets comps for every opportunity;
  Agent 20 drafts only from the broker's templates; P13 date triggers run
  from the clock.
- **Silence removed.** A signed setting an agent does not recognize, and a
  client reply no rule covers, are held for the broker instead of acked
  and dropped. An exhausted document chase and a vendor hold-up escalate
  once, not daily.
- **Console.** `onboard`, `release`, `decide`, `show held`, `show waits`,
  `--config-dir`, `--state-db`. The MCP server and the daily clock build
  the same swarm.
- **Single source.** This repository is the source of truth (the blueprint
  repository is retired); `docs/JOB_DESCRIPTIONS.md` is generated here and
  checked by a test. TelsonBase references removed from this drop.
- **Docs** rewritten to match the code; deleted risk disclosures restored.

## Known gaps

- No identity provider is connected, so the signer login binding is off.
- Drawer files are not encrypted. The SQLite CRM, consent and ledger
  tables are not written by Agents 14 and 15 (their records live in the
  saved state and the drawers).
- One hub handles one message at a time (about 4 s for eight 0.5 s
  deliveries). Separate offices run side by side with one hub each.
- Model drafting covers Agent 04's listing remarks only and has been tested
  against a stand-in model over HTTP, not against a real served model.

## Corrections to the archetype-v1.0.0 / v1.1.0 notes

Those notes described capabilities the code did not have: encrypted
drawers, state that survives reboots, JEV and Hermes powering agents,
real-time WhatsApp/Signal alerts, a "dual-key" update verifier, a ratified
signer registry, an MCP tool `tools/call_jev_decision`, and "21 spoke
agents". The autopsy report lists each one with what the code actually did.

## Verify

```bash
pip install -r requirements.txt
python -m pytest tests_listing/        # expect: 1315 passed, 1 skipped
python tools/run_demo.py
python tools/mcp_roundtrip.py
```
