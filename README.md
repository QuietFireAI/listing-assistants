# ListingAssistants

**Twenty agents that run the coordination work of a residential listing
business, on a closed track: one dispatcher hub routes every message, every
route is pre-approved, and every action lands on a hash-chained audit log.**

ListingAssistants (formerly `listing-agents`,
[ListingAssistants.com](https://ListingAssistants.com)) is the residential
real estate identity for [dispatcher-agents](https://github.com/QuietFireAI/dispatcher-agents).
The dispatcher supplies the governance chassis; this repository supplies the
real estate domain: the agents, their routes, their decision tuples, and 24
playbooks.

> **Fiduciary notice.** Price, terms, and every movement of money stay with the
> licensed broker and the client. ListingAssistants coordinates the work around
> those decisions. Its default build contains no payment, transfer, or wire
> capability, and any disclosure of a client's position to the other side waits
> for the broker's signed release. Details: [docs/FINANCIAL_CAPABILITY.md](docs/FINANCIAL_CAPABILITY.md).

---

## What it does

Twenty spoke agents cover the listing lifecycle end to end:

| Area | Agents |
|---|---|
| Leads | 01 Lead Capture, 02 Lead Qualification, 03 Lead Nurture, 19 Prospecting |
| Listing | 04 Listing Description, 05 MLS & Listing Management, 10 Market Data, 12 Marketing Campaign |
| Buyers & showings | 06 Showing Scheduler, 13 Buyer Search & Match |
| Transaction | 07 Transaction Coordinator, 08 Document Collection, 09 Vendor Coordination |
| Clients & records | 11 Client Communication, 14 CRM & Pipeline, 15 Financial Tracking, 16 After-Close & Referral |
| Oversight | 17 Compliance & Fair Housing, 18 Calendar & Task Management, 20 Social Media Monitoring |

Agent 00 is the dispatcher: the hub process that validates, routes and logs
every message. The broker is the principal the swarm serves and the only
holder of signing authority.

Every agent is a deterministic Python rule engine
(`dispatcher/listing_spokes*.py`). The same input produces the same result,
which is what lets every rule carry a test. The agents call no language
model.

## How it stays accountable

- **Closed track.** Only the 52 routes in `identity/routes.json` (146
  sender-intent-receiver lanes) are legal, and every message to or from an
  agent travels on one of them, including the daily clock (`clock.tick`). Anything else is rejected and logged;
  a well-formed message on an unknown route is held for a human.
- **Hash-chained audit log.** Every entry links to the previous one by
  SHA-256 from a genesis anchor. `verify_chain()` names the first line that
  was edited, deleted or reordered.
- **Signed authority.** Listing changes, configuration updates, disclosure
  releases and human decisions on paused work require a cryptographic
  signature (Ed25519 for production). An unsigned or tampered authority
  message is rejected and flagged as an integrity violation. The signer
  registry (which human login signed) arms once you ratify
  `config/authority_signers.json`; until then the hub records on the audit
  log that it is checking signatures only.
- **Outbound holds.** A message leaving for a counterparty or the public
  (a vendor, a buyer's agent, an ad network) holds for the broker's signed
  release, whatever its wording. Messages to the client the identity serves
  pass.
- **Every handoff is checked.** When the hub rejects or dead-letters a
  message an agent sent, the agent records `handoff.failed` on the audit log
  and the message goes to the human clarification queue. A signed
  configuration an agent does not recognize is held for you too, never
  acknowledged in silence.
- **Held threads wait for you.** When an agent cannot finish on its own (the
  same person arriving under a new lead, a client reply that names no agent,
  a social reply draft), the whole thread holds through the HITL protocol
  until you sign continue or cancel.
- **State survives a restart.** The swarm's state is saved to a local SQLite
  file after each session or clock run and restored at start-up only when
  the hash-chained audit log vouches for that exact save.
- **Predeliberated decisions.** 250 decision tuples (each agent's
  `DECISIONS.md`; 2 of them marked retired) say what an agent does at each
  known crossing. A situation
  no tuple covers stops and goes to the human.
- **Drafts stay drafts.** Configuration files ship as proposed drafts.
  Agents 07 and 08 load their config files only when the file's status
  records a ratification date; otherwise they keep their ratified defaults
  and log which file they skipped.
- **Pillars declare themselves.** The six QuietFire pillar packages
  (open-mind, agent-open-mind, before-turn, pre-response-selfcheck,
  sleep-marks, splitvantage) install from `requirements.txt`. A pillar that
  is not installed is declared UNARMED on the audit log.

## The 24 playbooks

Each playbook has an end-to-end test through the hub
(`tests_listing/test_playbooks_e2e.py`, `tests_listing/test_playbooks_e2e_all.py`).
Triggers, agents and human gates are in [docs/PLAYBOOKS.md](docs/PLAYBOOKS.md).
Since 2026-10-12 the daily clock also starts **P18** (weekly seller report,
on the weekday you sign), **P19** (access windows you record, flagged when
they end unclosed), **P20** (a property check every 7 days on listings you
mark vacant) and **P21** (WARM leads re-scored every 7 days). P13 (date
triggers) runs from the clock since 2026-10-11, and P17 (end-of-day books) runs when you ask for it
(`{"do": "show", "what": "eod"}`).

| | Playbook | | Playbook |
|---|---|---|---|
| P01 | New Listing Onboarding | P13 | Referral/Anniversary Cycle |
| P02 | Price Adjustment | P14 | Complaint Response |
| P03 | Under-Contract Transition | P15 | CMA / Listing-Appointment Prep |
| P04 | Open House Cycle | P16 | Morning Operations |
| P05 | Expired/Withdrawn Wind-down | P17 | End-of-Day Books |
| P06 | New Buyer Onboarding | P18 | Seller Weekly Report |
| P07 | Tour Day Coordination | P19 | Property Access Custody |
| P08 | Offer-to-Acceptance | P20 | Vacant Property Watch |
| P09 | Contract-to-Close | P21 | Lead Re-Score Cycle |
| P10 | Close + Post-Close Handoff | P22 | Buyer Feedback & Match Refresh |
| P11 | Speed-to-Lead | P23 | Price-Review Evidence Assembly |
| P12 | Geographic Farm Campaign | P24 | Prospecting Outreach |

### P01, message by message

This is the route a new listing takes in its end-to-end test
(`test_p01_new_listing_onboarding_all_three_phases`). Every arrow passes
through the hub.

```mermaid
sequenceDiagram
    autonumber
    actor Broker as Broker (human)
    participant A05 as 05 MLS & Listing
    participant A09 as 09 Vendors
    participant A04 as 04 Description
    participant A17 as 17 Compliance
    participant A12 as 12 Marketing
    participant Out as External

    Broker->>A17: config.update (signed fair-housing ruleset)
    Broker->>A05: listing.change.authorized (signed package, price set by broker)
    A05->>A09: vendor.request (photography)
    A09->>Out: vendor.schedule (held until released)
    Out->>A09: vendor.event (photos delivered)
    A09->>A05: deliverable.release
    A05->>A04: listing.data
    A04->>A17: content.review (draft remarks)
    A17->>A04: content.verdict (approved, or flagged and the path stops)
    A04->>A05: asset.release
    A04->>A12: asset.release
    A05->>A12: status.update (go-live verified, not assumed)
    A12->>Out: campaign.publish (held for the broker's signed release)
```

Along the way the agents log each step to the CRM (14), report what they are
waiting on to the calendar agent (18), and Agent 11 sends the client status
updates. A flagged verdict from 17 stops the marketing path; that case has
its own test (`test_p01_compliance_flag_halts_marketing_path`).

## What you keep

The broker decides price, offers, negotiation, legal questions, and every
word that goes past a hold. Agent 11 routes client questions about price or
strategy, and any client message about wire instructions, to the legal-line
queue with the client's own words. What each playbook takes off your plate:
[docs/WHAT_SUCCESS_MEANS.md](docs/WHAT_SUCCESS_MEANS.md).

## Modules wired into the swarm

Everything below is built by `dispatcher/swarm.py`, so the console, the daily
clock and the MCP server run the same wiring.

| Module | What it does in the running swarm |
|---|---|
| `dispatcher/hitl_protocol.py`, `dispatcher/human_holds.py` | Holds a thread and resumes it only on your signed `hitl.decision.authority` (continue or cancel), bound to that client |
| `dispatcher/persistence_sqlite.py`, `dispatcher/state_snapshot.py` | Saves and restores the swarm's state (append-only `state_snapshots` table, JSON, fingerprint on the audit chain) |
| `dispatcher/handoff_guard.py` | Checks every agent send and every signed configuration an agent receives |
| `dispatcher/readable_audit.py`, `dispatcher/readable_logger.py`, `tools/show_logs.py` | Every audit-chain entry is also written in plain language to `console-state/readable/stream.log` and to the client's drawer; `show eod` writes the end-of-day ledger from the chain and verifies it |
| `dispatcher/client_drawer.py`, `dispatcher/drawer_filing.py`, `tools/inspect_client_drawer.py`, `tools/dashboard.py` | One drawer per client under `console-state/drawers/`. Agents 04, 05, 07, 08, 14 and 15 file the client's listing package, approved description, timeline, documents, CRM entries and expenses there; every filing is on the chain with its SHA-256; HITL holds are recorded there. Files are **not encrypted** |
| `dispatcher/decision_adapter.py` | Agent 02 scores every lead through the JEV adapter. Its local engine is 02's own rubric, so tiers are unchanged; live JEV runs only when a key is set **and** you sign `{"decision_engine": {"allow_external": true}}` to 02. A result under the confidence floor holds the lead for your continue/cancel |
| `dispatcher/model_drafting.py`, `dispatcher/hermes_seam.py`, `dispatcher/model_checkpoint_manager.py`, `tools/restore_point.py` | Optional model-written listing remarks for Agent 04. Off by default. Used only when you sign `{"drafting": {"mode": "model"}}` to 04, the console runs with `--model-url` and `--model-name` (a model on this machine), and the active checkpoint passed the broker exam on that model (`restore_point.py --exam`). Model remarks are checked for reasoning, length and added numbers, and go through Agent 17 like every draft |

Operator tools, not part of the message path:

| Module | What it does |
|---|---|
| `tools/verify_update_pack.py`, `tools/sign_manifest.py` | Signs and verifies offline update packs: Ed25519 signature, every file hashed, unlisted files and downgrades refused |
| `dispatcher/provider_gateway.py` | Records which external providers you intend to connect (masked); makes no network calls |

## Current limits

- **External adapters queue until connected.** MLS writes, client sends and
  ad publishes stay visibly queued until you wire your providers
  (`docs/TUNING_MANUAL.md`). Text-message pages are off until you run
  `python tools/console.py pager` with your Twilio details; a page carries
  the queue name and client context id only.
- **Signer identities need an identity provider.** `config/authority_signers.json`
  binds signers to an identity-provider login with MFA. No identity provider
  is connected, so the hub verifies the key's signature and records on the
  audit log that the login binding is off. `console.py onboard` records who
  you are and stamps your login on your signed console actions.
- **One process at a time.** Run one console session or one clock run at a
  time against the same state file; the hub's lock serializes work inside a
  process, not across processes.
- **Pillars are pinned.** The six pillar packages install from exact commits
  in `requirements.txt` (the ones this suite passed against). pip-audit
  cannot check git installs; moving a pillar forward means changing its hash
  and re-running the suite.

## Install and verify

Python 3.10 or newer (3.12 recommended) and `git`.

```bash
git clone https://github.com/QuietFireAI/listing-assistants.git
cd listing-assistants
pip install -r requirements.txt
python -m pytest tests_listing/        # expect: 939 passed
```

The suite includes the 24 playbook end-to-end tests, a full-swarm test for
every route that has a sender, and mutation-hardening tests. CI runs it from
a clean clone, checks that the vendored core files match dispatcher-agents
byte for byte, and checks that the swarm still routes with no pillars
installed. Windows setup: [QUICKSTART_WINDOWS.md](QUICKSTART_WINDOWS.md).

## Run it

```bash
python tools/run_demo.py                 # one listing, six acts, on the real hub
python tools/mcp_roundtrip.py            # live stdio round trip of the MCP server
python tools/console.py init             # create your signing key
python tools/console.py onboard          # who you are, asked once
python tools/console.py session scenes/scene01_signature.jsonl --config-dir scenes/config
python tools/console.py verify           # walk the audit chain
python tools/run_sweeps.py               # the daily clock, on the console's log and saved state
python tools/dashboard.py --html         # client funnel page from drawer manifests
python tools/show_logs.py --eod          # end-of-day report
python tools/manage_hitl_queue.py --list # pending human decisions recorded in drawers
python tools/verify_update_pack.py --guide   # offline update procedure
```

Mounting on Hermes, OpenClaw or Claude Desktop as an MCP server:
[docs/MOUNTING.md](docs/MOUNTING.md).

## Reading order

1. [docs/START_HERE.md](docs/START_HERE.md) - the 60-second version
2. [docs/WHAT_SUCCESS_MEANS.md](docs/WHAT_SUCCESS_MEANS.md) - what each playbook delivers
3. [docs/PLAY-BY-PLAY.md](docs/PLAY-BY-PLAY.md) - what moves between agents, step by step
4. [docs/JOB_DESCRIPTIONS.md](docs/JOB_DESCRIPTIONS.md) - every agent's role and rules
5. [docs/PLAYBOOKS.md](docs/PLAYBOOKS.md) - all 24 playbooks: triggers, agents, gates
6. [docs/TUNING_MANUAL.md](docs/TUNING_MANUAL.md) - every number you can turn
7. [docs/AGENT_USER_MANUAL.md](docs/AGENT_USER_MANUAL.md) - a broker's day with the system
8. [docs/OPERATOR_TUNING_GUIDE.md](docs/OPERATOR_TUNING_GUIDE.md) - setup, storage, updates, drawers, the decision engine and model drafting
9. [docs/OPERATOR_TESTING_MANUAL.md](docs/OPERATOR_TESTING_MANUAL.md) - ten filmable operator scenes (`scenes/`), each checked by the suite
10. [docs/FINANCIAL_CAPABILITY.md](docs/FINANCIAL_CAPABILITY.md) - the financial locks and the security reviewer's risk list

## Layout

- `dispatcher/` - vendored dispatcher-agents core (the 15 files listed in
  `tools/sync_core.py`, kept identical by `--check` in CI), the 20
  `listing_spokes*.py` agents, `handoff_guard.py`, `lead_rubric.py`,
  `config_status.py`, and the modules above.
- `identity/routes.json` - the closed track.
- `00-dispatcher/` ... `20-social-media-monitoring/` - each agent's ratified
  SKILL.md and DECISIONS.md.
- `config/` - business content the code cannot guess (templates, cadences,
  milestones, vendor panel, authority signers). Drafts until you ratify them.
- `scenes/` - the ten operator scenes and their synthetic vendor roster.
- `tests_listing/` - the full suite. Run it from a fresh clone before
  trusting any "done" claim, including this README's.

## Provenance

This repository is the single source for ListingAssistants (owner decision
2026-10-11): every agent's SKILL.md and DECISIONS.md, the closed track, the
configuration templates, and the generated docs (`tools/gen_job_descriptions.py`
rebuilds docs/JOB_DESCRIPTIONS.md; a test fails when it drifts). The
dispatcher core in `dispatcher/` is vendored from
[dispatcher-agents](https://github.com/QuietFireAI/dispatcher-agents) and
must stay byte-identical (`tools/sync_core.py --check`, run in CI).

## License

Dual-licensed under the **QuietFire Identity License** (see `LICENSE`) over
an **AGPL-3.0** floor (see `LICENSE-AGPL`). Evaluation, development, and
internal testing - including cloning, running the suite, and any demo - are
free. **Production and commercial use require a paid license from
QuietFireAI or full AGPL-3.0 compliance.** Building derivative identities
for third parties requires a commercial license. The open chassis this runs
on (dispatcher-agents) is Apache-2.0 and separate.

*License text is a placeholder pending counsel review.*

ListingAssistants is independent of, and unaffiliated with, listingagent.com.
