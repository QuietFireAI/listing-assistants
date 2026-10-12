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

- **The Broker Desk.** `python tools/desk.py` shows the broker everything
  waiting on them, with Send, Continue/Cancel and Done buttons that sign
  with the broker's key, plus listing progress, hot-lead clocks, the
  agents' status and a proof strip. `--showcase` replays the operator
  scenes for recording (README, "The Broker Desk").
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
python -m pytest tests_listing/        # expect: 994 passed
python tools/run_demo.py
python tools/mcp_roundtrip.py
```
