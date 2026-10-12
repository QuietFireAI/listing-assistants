# ListingAssistants - Operator Guide

Setup, configuration, storage, offline updates, and the optional modules.
Every command and code block in this guide was run against this repository
on 2026-10-11. For every numeric parameter, see
[TUNING_MANUAL.md](TUNING_MANUAL.md).

> **Fiduciary notice.** Price, terms, and every movement of money stay with the
> licensed broker and the client. ListingAssistants coordinates the work around
> those decisions. Its default build contains no payment, transfer, or wire
> capability, and any disclosure of a client's position to the other side waits
> for the broker's signed release. Details: [FINANCIAL_CAPABILITY.md](FINANCIAL_CAPABILITY.md).

---

## 1. How the system is built

- **Hub.** `dispatcher/hub.py` (Agent 00) receives every message, checks it
  against the closed track (`identity/routes.json`), verifies signatures on
  authority intents, persists it to the hash-chained audit log, delivers it,
  and only then acknowledges it.
- **Core parity.** Fifteen files in `dispatcher/` are vendored from
  dispatcher-agents and must stay byte-identical. The list is in
  `tools/sync_core.py`; `python tools/sync_core.py --core <checkout> --check`
  reports any drift, and CI runs it.
- **Agents.** `dispatcher/listing_spokes*.py` holds the 20 agents. They are
  deterministic Python rule engines and make no model calls. Each holds its
  hub through `HandoffGuard` (`dispatcher/handoff_guard.py`), which turns a
  rejected or undeliverable handoff into `handoff.failed` plus a
  clarification request.
- **One builder.** `dispatcher/swarm.py` builds the hub, the 20 agents, the
  HITL manager and the state store. The console and the daily clock both use
  it.
- **State.** At the end of every console session and clock run the swarm's
  state is saved to a local SQLite file (`console-state/swarm-state.sqlite`
  by default) and its SHA-256 is appended to the audit log as `state.saved`.
  At start-up the newest save is restored only if the audit chain verifies
  and its last `state.saved` names that save and hash; otherwise the start
  is refused and neither file is touched. Run one process at a time against
  the same files.

## 2. Install and verify

```bash
git clone https://github.com/QuietFireAI/listing-assistants.git
cd listing-assistants
pip install -r requirements.txt
python -m pytest tests_listing/          # expect: 961 passed
python tools/console.py init             # your signing key, mode 0600, stays on this machine
python tools/console.py onboard          # your name and login, asked once
python tools/console.py verify           # audit chain check
```

The six pillar packages are pinned to exact commits in `requirements.txt`.
To move one forward, change its hash, run the suite, and commit both.

## 3. Ratify your configuration

Files in `config/` ship as drafts. A file counts as ratified when its
`_status` contains `RATIFIED` followed by a date (YYYY-MM-DD) in the same
`|`-separated clause, e.g. `"RATIFIED 2026-10-15 J. Broker"`. "UNRATIFIED"
and "NOT RATIFIED" do not count.

| File | Ships as | Read by |
|---|---|---|
| `description_cut_priority.json` | ratified | Agent 04 |
| `message_templates.json` | ratified | reference content; no code reads it yet |
| `cadence_settings.json` | draft | Agent 08 |
| `transaction_milestones.json` | draft | Agent 07 |
| `milestone_map.json` | draft | reference content; no code reads it yet |
| `vendor_panel.json` | unratified template | the swarm builder, for Agent 09's roster |
| `authority_signers.json` | unratified template | signer registry |

Agents 07 and 08 and the swarm builder load their config files only when
ratified, and append a `config.load` entry to the audit log saying which
file they loaded or skipped and why. `vendor_panel.json` lists vendors as
`vendor_id -> {kind, license_expiry, insurance_expiry, regulated}`; an entry
with a missing field or a placeholder is skipped and named. Point the
console at another folder with `--config-dir` (the operator scenes use
`scenes/config/`).

Business rules that change at runtime arrive as signed `config.update`
messages, for example through a console session. Each is validated whole;
a bad one changes nothing and is held for you with the problems named, and
a setting the agent does not recognize is held too.

| Agent | Payload key | What it sets |
|---|---|---|
| 01 | `brokerage_scope` | the listings you hold (replaces the list) |
| 01 | `dnc_add` | numbers or emails added to do-not-contact (adds only) |
| 02 | `rubric`, `resolve_hot_lead` | the scoring rubric; closes a hot-lead wait |
| 02 | `decision_engine` | `{"allow_external": true\|false, "confidence_floor": 0..1}`: lets lead data go to live JEV (needs `JEV_API_KEY` too); the floor under which a lead holds for you |
| 04 | `drafting` | `{"mode": "rules"}` (default) or `{"mode": "model"}`: model-written remarks, used only when section 10's conditions hold |
| 03 | `nurture_sequences` | each sequence's touches: `{"touches": [{"day": 0, "text": "..."}]}` |
| 05 | `occupancy`, `watch_interval_days` | `"vacant"` starts the P20 property-check watch (every 7 days unless you set the interval); `"occupied"` stops it. A listing package with `"occupancy": "vacant"` does the same |
| 06 | `confirm_protected_bump` | confirms a held showing bump |
| 06 | `seller_reports` | P18: `{"weekday": "monday", "listings": {"L8": "<seller context>"}}` - which day, and which seller gets each listing's report |
| 07 | `timeline_init` | a transaction's milestone dates |
| 08 | `expected_senders` | who should send each sensitive document: `{"closing_settlement_statement": ["title@..."]}` |
| 11 | `resolve_complaint_hold`, `resolve_advice_response` | releases a complaint hold; closes an advice wait |
| 13 | `buyer_criteria` | a buyer's stated criteria |
| 14 | `buyer_agreement_on_file`, `requester_identity_verified` | your record that the agreement is signed / identity checked |
| 14 | `client_dates` | P13 dates for a client: `{"purchase_anniversary": "07-18"}` (MM-DD every year, YYYY-MM-DD once) |
| 14 | `access_grant`, `access_closed` | P19: `{"party": "...", "window_end": "YYYY-MM-DD", "custody_ref": "..."}` - never the code or key; `{"party": "..."}` when it is back or changed |
| 16 | `client_list_entry` | puts a closed client on the after-close program |
| 17 | `ruleset` | the fair-housing ruleset |
| 19 | `zip_codes`, `approved_sources`, `dnc_entries` | prospecting scope |
| 20 | `monitored_channels`, `reply_templates` | channels watched; your reply templates (question, praise) |

**Signer registry.** `config/authority_signers.json` names which human
logins may sign which authority intents, bound to an identity provider with
MFA. Arming it needs an identity provider that stamps each signed envelope
with the login, MFA and session; none is connected in this build, so leave
the template unratified. The hub records `signer.unarmed` and checks the
cryptographic signature only. `console.py onboard` records your login and
stamps it on your signed console actions; that stamp is information, not
the identity-provider binding.

## 4. The daily clock

Time-based checks (contract deadlines, document chases, vendor no-shows,
SLA timers, the morning briefing) run when something calls
`run_daily_sweeps(hub, spokes, today)` from `dispatcher/sweep_runner.py`.
It reaches each agent with a `clock.tick` envelope through the hub, so
every tick is persisted, acknowledged and on the audit log like any other
message; nothing calls an agent directly. The checks per agent are listed
in `dispatcher/clock.py`. Since 2026-10-12 they include P18 (06, weekly
seller report on your signed weekday), P19 (14, access windows ended and
not closed), P20 (05, property checks on vacant listings), P21 (03, WARM
leads re-scored every 7 days) and Agent 08's disclosure warning (three days
before a pending seller disclosure is due). Call it once a day inside the process that holds
the swarm.

`tools/run_sweeps.py` is the scheduler's caller. By default it uses the
console's audit log and saved state, runs every agent's daily checks
through the hub, saves the state and exits nonzero if a check errored:

```bash
python tools/run_sweeps.py                      # cron: 0 7 * * *
python tools/run_sweeps.py --today 2026-10-21   # replay a day
```

If the saved state does not match the audit log it runs nothing and exits 2.

## 5. Client drawers (`dispatcher/client_drawer.py`)

One directory per client. Client ids, file names and categories are
checked: ids and names must be single safe path segments, categories come
from a fixed set, and a path that resolves outside the drawer (including
through a symlink) is refused. An artifact is filed only under the client
context the acting agent is working on; a mismatch raises
`ComminglingBreachError`. Each file's SHA-256 is recorded in the drawer
manifest, and `verify_hashes()` re-checks them on demand.

```python
from dispatcher.client_drawer import ClientDrawerManager

drawers = ClientDrawerManager("/srv/listingassistants/drawers")
drawer = drawers.provision_drawer("ctx-oak-100", "Bob Seller", "100 Oak Lane")
drawers.record_agent_artifact("ctx-oak-100", "04", "artifacts", "remarks_v1.md",
                              "Three bedrooms, two baths.",
                              acting_client_context_id="ctx-oak-100")
print(drawer.verify_hashes())
```

Files are stored unencrypted. Put the drawer root on an encrypted volume if
you need encryption at rest.

**In the running swarm** (`dispatcher/drawer_filing.py`) the console's
drawers live in `console-state/drawers/`, one per client context, provisioned
the first time anything is filed for that client:

| Agent | Category | What it files |
|---|---|---|
| 05 | `artifacts/` | the signed listing package; also fills the drawer's address and seller name when the package has them |
| 04 | `artifacts/` | the description as released after Agent 17 approved it |
| 07 | `timeline/` | the transaction timeline as loaded |
| 08 | `documents/` | every document filed clean, as received |
| 14 | `interactions/` | every CRM entry, one file each |
| 15 | `financials/` | every expense entry |
| HITL | `timeline/` | each hold (`<wait_id>_pause.json`) and its resolution |

Every filing is on the audit chain as `drawer.filed` with the file's
SHA-256. A refusal (an id that is not a safe path segment, a disk error) is
recorded as `drawer.refused` and held for you. A later name or address that
differs from the one on file is not written; it is recorded as
`drawer.identity_conflict` and held for you.

```bash
python tools/inspect_client_drawer.py --list          # every drawer
python tools/inspect_client_drawer.py S7              # one drawer, hashes re-checked
python tools/dashboard.py --html                      # funnel page read from the drawers
```

## 6. Local SQLite store (`dispatcher/persistence_sqlite.py`)

```python
from decimal import Decimal
from dispatcher.persistence_sqlite import ApplianceStorage

with ApplianceStorage("/srv/listingassistants/appliance.db") as db:   # local disk
    db.record_financial_entry("ctx-oak-100", "commission_calculated",
                              amount=Decimal("15000.00"), commission_rate="0.03")
    db.update_client_consent("ctx-oak-100", {"sms": "yes"}, source="intake form 2026-10-11")
    print(db.get_financial_history("ctx-oak-100")[0]["amount"])      # Decimal('15000.00')
```

- Money is stored as exact decimal text and returned as `Decimal`. A Python
  `float` is refused, because its rounding error is already in the value.
- `crm_interactions`, `financial_ledger`, `client_drawer_files` and the
  consent and identity history tables are append-only (database triggers).
  Corrections are new rows.
- Consent keeps every event; `get_client_consent()` returns the latest
  effective value per channel, `get_consent_history()` returns all of them.
  An opt-in on a channel that is opted out is stored as
  `pending_confirmation` and stays out of effect until
  `confirm_consent(ctx, channel, confirmed_by)` records a human's
  confirmation (`get_pending_consent()` lists them). Agent 14 applies the
  same rule to its in-memory consent.
- Registering an existing drawer with a different name or address raises
  `DrawerIdentityConflict` unless you pass `update_identity=True`, which
  keeps the old identity in history.
- File databases run in WAL mode. Keep `db_path` on a local disk: SQLite
  locking is not reliable over network shares, NAS shares included.

The swarm writes its state snapshots to this store (`state_snapshots`,
append-only, schema version 3; a version-2 file is upgraded in place). The
CRM, consent, ledger and drawer tables are not written by the agents: Agents
14 and 15 keep those records in their own state, which the snapshot saves,
and file a copy of each into the client's drawer (section 5).

## 7. Offline updates

For an appliance without internet access, updates travel as a signed pack
(on an encrypted USB drive, for example).

On the staging workstation, once:

```bash
python tools/sign_manifest.py --keygen authority     # authority.key (0600, keep private) + authority.pub
```

For each update:

```bash
# put the files under my_update/payload/, paths mirroring the install tree
python tools/sign_manifest.py my_update --private-key authority.key --version 1.2.0
```

On the appliance (which holds only `authority.pub`):

```bash
python tools/verify_update_pack.py /media/drive/my_update --pubkey authority.pub --installed-version 1.1.0
```

Copy `payload/` into place only on exit code 0. The verifier checks the
Ed25519 signature over the manifest, the SHA-256 of every listed file, that
no unlisted file is present, that no manifest path escapes `payload/`, and,
with `--installed-version`, that the pack is strictly newer. `--dev-bypass`
skips only the signature check, exits 3, and prints NOT VERIFIED. Afterwards,
run the test suite and `python tools/console.py verify`.

## 8. Human decisions on paused work (`dispatcher/hitl_protocol.py`)

`HITLManager` pauses an operation, notifies Agent 18 (and an optional
real-time notifier), and records the pause in the client's drawer when a
drawer manager is attached. It resumes only on a `hitl.decision.authority`
envelope from `human`, signed with a key the hub verifies, for the same
client context. MODIFY-type decisions may change only fields that were in
the paused payload. A used decision cannot be replayed.

```python
from dispatcher.core import Envelope, Routes, AuditLog
from dispatcher.hub import Hub
from dispatcher.hitl_protocol import HITLManager, DECISION_INTENT
from dispatcher.signatures import Ed25519Signer, Ed25519Verifier

broker_key = Ed25519Signer()                     # in production: the broker's own key
hub = Hub(Routes("identity/routes.json"), AuditLog("/srv/listingassistants/audit.jsonl"),
          signature_verifier=Ed25519Verifier(broker_key.public_key_bytes()).verifier())
hitl = HITLManager(hub=hub)

ws = hitl.pause_operation("ctx-oak-100", "07", "milestone.advance",
                          "Buyer requested a $5,000 repair credit.",
                          {"requested_credit": 5000}, "APPROVE_REPAIR_CONCESSION")

decision = Envelope(from_agent="human", to_agent="hitl", intent=DECISION_INTENT,
                    client_context_id="ctx-oak-100",
                    payload={"wait_id": ws.wait_id, "decision": "MODIFY",
                             "updated_fields": {"requested_credit": 3000}},
                    provenance={"source": "human", "captured_at": "runtime"})
broker_key.sign(decision)
print(hitl.resume_operation(decision)["status"])   # decision_recorded_no_handler until you register one
```

Register a handler per agent with `register_resumption_handler(agent_id, fn)`
to have the decision acted on; without one the decision is recorded and the
result says so.

In the swarm the manager is `hub.hitl`, and three agents hold through it
(`dispatcher/human_holds.py`): Agent 01 (the same phone or email under a new
lead), Agent 11 (a client reply that names no agent, or an agent with no
reply handler) and Agent 20 (a social reply draft cleared by 17). Each
takes continue (`APPROVE`, or `APPROVE_WITH_OVERRIDE` with `route_to` for
Agent 11) or cancel (`REJECT_AND_ABORT`); the console's `decide` action
builds and signs that envelope. Open holds are part of the saved state.
Agent 02 also holds through it when a lead's score confidence is under the
floor (section 9). Every hold is recorded in the client's drawer;
`python tools/manage_hitl_queue.py --list` lists the open ones, and the
console's `show waits` lists them from the live swarm.

## 9. JEV decision adapter (`dispatcher/decision_adapter.py`)

```python
from dispatcher.decision_adapter import JevDecisionAdapter

rubric = {"budget_threshold": 500_000, "budget_weight": 40,
          "timeline_days_threshold": 30, "timeline_weight": 40,
          "financing_weight": 20, "hot_threshold": 70, "warm_threshold": 40}
adapter = JevDecisionAdapter()                  # local engine; no data leaves the machine
res = adapter.evaluate_lead("ctx-lead-7", {"budget": 650_000, "timeline_days": 15,
                                           "financing_progress": "preapproved"}, rubric)
print(res["status"], res["tier"], res["score"], res["confidence"])
```

- **Local (default).** Scores with `dispatcher/lead_rubric.py`, the same
  function Agent 02 uses. A rubric missing any of its seven keys is a hold,
  never filled with defaults.
- **Injected MCP client.** `JevDecisionAdapter(mcp_client=...)`; you run the
  server.
- **Live HTTPS.** Needs `JEV_API_KEY` and `allow_external=True`. Lead data
  leaves the machine in this mode. The endpoint must be `https://`; a
  failed call falls back to the local engine.

Every mode returns a hold (`status: held_confidence_underflow`) when the
confidence is below the floor (0.45 by default) or missing.

**In the running swarm** Agent 02 scores every lead through this adapter
(`hub.decision_adapter`), and each decision is on the audit chain as
`decision.lead` with the engine, tier, score and confidence. With no JEV
connection that engine is the local one, so tiers are what 02 always
produced. To send lead data to live JEV, set `JEV_API_KEY` **and** sign
`{"decision_engine": {"allow_external": true}}` to Agent 02; a key alone
sends nothing. A lead whose result falls under the floor holds for you:
continue scores it with your signed rubric and acts on that tier, cancel
archives it with nothing sent. Agent 06 does not use the adapter's showing
resolver; its own rules decide showings.

## 10. Hermes seam (`dispatcher/hermes_seam.py`)

For a locally served Hermes-family model with an OpenAI-style client.

```python
from dispatcher.hermes_seam import HermesCognitiveSeam, HermesUnavailableError

seam = HermesCognitiveSeam(hub=None, client=None)    # pass an OpenAI-style client to use a model
try:
    seam.draft_and_trace("04", "env-1", "Draft remarks for 100 Oak Lane")
except HermesUnavailableError as e:
    print("no model:", e)
seam.ingestor.ingest_document("office_sign_rules", "Yard signs go up Saturday after 8 AM.")
print(seam.ingestor.export_reference_records("/srv/listingassistants/reference.jsonl"))
```

- With a client, `draft_and_trace()` sends the model's `<think>` reasoning
  to the hub's taint gate and offers the run to the learning loop. A reply
  with no `<think>` block sends an empty thought, which the gate flags.
- Without a client, or when the call fails, it raises
  `HermesUnavailableError`; nothing is traced or collected.
- `HermesLearningLoop` keeps runs that pass the taint gate and a variance
  screen; its policy check is a phrase screen, not a compliance review.
  Exports carry a `thought_origin` field so template-made thoughts can be
  filtered out of any training set.
- The learning loop refuses to collect anything when the open-mind or
  agent-open-mind pillar is not installed.

**In the running swarm** Agent 04 can have a locally served model write the
listing remarks (`dispatcher/model_drafting.py`). It does so only when all
three hold:

1. you signed `{"drafting": {"mode": "model"}}` to Agent 04;
2. the console runs with the model, e.g.
   `python tools/console.py session <file> --model-url http://localhost:11434/v1 --model-name <model>`
   (a host other than this machine is refused unless you pass
   `--allow-remote-model`, because the prompt carries listing data);
3. the active checkpoint passed the broker exam on that same model
   (section 11).

A model draft is used only if the model produced its `<think>` reasoning
(sent to the taint gate), the remarks fit the MLS limit, and every number in
them, in digits or words, appears in the listing facts. It does not prove
every word is supported by the data, so the remarks travel with the facts,
go through Agent 17 like every draft, and are labeled `remarks_source:
model:<checkpoint>`. If 17 flags a phrase, 04 removes the sentence that
carries it. When any condition fails, 04 drafts by rules, records
`drafting.model_unavailable` with the reason, and tells you. The learning
loop is not run on live drafts.

## 11. Model checkpoint manifest

```bash
python tools/restore_point.py --exam hermes-2026-10-12 --model-url http://localhost:11434/v1 --model-name <model>
python tools/restore_point.py --list
python tools/restore_point.py --snapshot          # record today's restore point
python tools/restore_point.py --restore baseline  # move the active pointer back (turns model drafting off)
```

The console's manifest is `console-state/checkpoints/checkpoint_manifest.json`
(the one under `checkpoints/` in the repository is the shipped reference).
It records checkpoints and which one is active; it copies and loads no
weights, and no weights ship with this repository. `--exam` asks the served
model the four broker questions (fair housing, wire instructions, price
guarantees, buyer agreements), grades each answer with a keyword screen,
stores every answer for you to read, and activates the checkpoint only if
all four pass. The shipped baseline was never examined, so model drafting
stays off until you run the exam. Agent 04 reads the active entry before
every model draft.

## 12. Logs and reports

```bash
python tools/show_logs.py --tail 50               # plain-language stream
python tools/show_logs.py --client S7             # one client
python tools/show_logs.py --eod                   # today's end-of-day ledger
```

Every entry the swarm writes to the hash-chained audit log
(`console-state/console-audit.jsonl`) is also written in plain language to
`console-state/readable/stream.log`, and to `audit/activity.log` in the
client's drawer. The chain is the record; the readable log leaves out
bookkeeping entries (acknowledgements, hub reflections), and a failure to
write it never touches the chain (the console reports `readable_log_errors`
at the end of each session). The end-of-day ledger is built from the chain
for the date, so it covers every session that day; it verifies the chain
and counts integrity-violation and reject entries; lines it cannot compute
say "not computed". The console's `show eod` writes the same ledger.

## 13. External providers (`dispatcher/provider_gateway.py`)

A registry of provider settings read from `config/integrations.json`
(template: `config/integrations_template.json`), with secret masking for
display. It makes no network calls and no agent reads it; it records which
providers you intend to connect.

## 14. Text-message pages

```bash
python tools/console.py pager          # asks for the Twilio account SID, auth token, from and to numbers
python tools/console.py pager --test   # one test page
python tools/console.py pager --off    # forget the details
```

Run it after `onboard`. The details are saved in `console-state/pager.json`
(readable by your user only). From then on every console session texts you
whenever something lands in a human queue, as well as printing it. A page
says which queue and which client context, never the client's words, and
every page attempt is on the audit chain (`pager.sent` / `pager.failed`)
without the credentials.

## 15. Health checks

```bash
python -m pytest tests_listing/ -q
python tools/console.py verify
python tools/sync_core.py --core /path/to/dispatcher-agents --check
python tools/mcp_roundtrip.py
```
