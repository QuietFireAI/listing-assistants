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

- **Closed track.** Only the 51 (sender, intent, receiver) routes in
  `identity/routes.json` are legal. Anything else is rejected and logged;
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
  and the message goes to the human clarification queue.
- **Predeliberated decisions.** 227 decision tuples (each agent's
  `DECISIONS.md`) say what an agent does at each known crossing. A situation
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

Each playbook has one end-to-end test that drives it from its real trigger
through the hub (`tests_listing/test_playbooks_e2e.py`,
`tests_listing/test_playbooks_e2e_all.py`). Triggers, agents and human gates
are in [docs/PLAYBOOKS.md](docs/PLAYBOOKS.md).

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
    A17->>A04: content.verdict (approved; flagged halts the path)
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

## Optional modules

These modules ship with tests and can be used from your own code. The
twenty agents do not call them yet; wiring each one in is a deliberate
step for a deployment.

| Module | What it does | Wired to the swarm |
|---|---|---|
| `dispatcher/client_drawer.py` | One directory per client; safe path segments only; artifacts filed under the acting client's context; SHA-256 per file with `verify_hashes()` | No. Files are stored unencrypted. |
| `dispatcher/hitl_protocol.py` | Pauses an operation and resumes it only on a signed `hitl.decision.authority` from the broker, bound to that client | No |
| `tools/verify_update_pack.py`, `tools/sign_manifest.py` | Signs and verifies offline update packs: Ed25519 signature, every file hashed, unlisted files and downgrades refused | Operator tools |
| `dispatcher/persistence_sqlite.py` | Local store: exact decimal money, append-only ledgers, consent history, WAL mode | No. Keep it on a local disk. |
| `dispatcher/decision_adapter.py` | JEV decision adapter: local rubric engine (same rules as Agent 02), optional injected MCP client, optional live API only with `allow_external=True`; low or missing confidence becomes a hold | No |
| `dispatcher/hermes_seam.py` | Seam for a locally served Hermes-family model: separates `<think>` reasoning, feeds it to the taint gate, raises an error when no model is configured | No |
| `dispatcher/model_checkpoint_manager.py`, `tools/restore_point.py` | Manifest of model adapter checkpoints with a keyword-screened regression exam and rollback of the active pointer | No; no weights ship |
| `dispatcher/readable_logger.py`, `tools/show_logs.py` | Plain-language event log and end-of-day report; verifies the audit chain when you pass it | Tools only |
| `tools/dashboard.py` | Client funnel view built from drawer manifests (`--html` writes a page) | Reads drawers |

## Current limits

- **State lives in one process.** Spoke state, the hub's duplicate check and
  outbound holds are held in memory. The audit log survives a restart; live
  state does not rehydrate from it yet. `tools/run_sweeps.py` run standalone
  builds an empty swarm, so the daily clock belongs inside the long-running
  process that holds the agents.
- **External adapters queue until connected.** MLS writes, client sends and
  ad publishes stay visibly queued until you wire your providers
  (`docs/TUNING_MANUAL.md`). The SMS notifier is a real Twilio client with
  placeholder credentials and fails with a 401 until you supply real ones.
- **Signer identities are yours to ratify.** `config/authority_signers.json`
  ships as an unratified template and refuses to arm.
- **Pin the pillars for production.** They install from branch tips; pin each
  to a commit hash.
- **Three declared routes have no sender in code:** 20 → 03
  `behavioral.signal`, and 11 → 04/12 `lead.reply` (04 and 12 have no reply
  handler; Agent 11 sends those replies to the human instead).

## Install and verify

Python 3.10 or newer (3.12 recommended) and `git`.

```bash
git clone https://github.com/QuietFireAI/listing-assistants.git
cd listing-assistants
pip install -r requirements.txt
python -m pytest tests_listing/        # expect: __TESTCOUNT__ passed
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
python tools/console.py init             # create your signing key, then: session / verify
python tools/run_sweeps.py --audit-log logs/sweep-audit.jsonl   # the daily clock (see limits)
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
8. [docs/OPERATOR_TUNING_GUIDE.md](docs/OPERATOR_TUNING_GUIDE.md) - setup, storage, updates, optional modules
9. [docs/OPERATOR_TESTING_MANUAL.md](docs/OPERATOR_TESTING_MANUAL.md) - a filmable operator test script
10. [docs/FINANCIAL_CAPABILITY.md](docs/FINANCIAL_CAPABILITY.md) - the financial locks and the security reviewer's risk list

## Layout

- `dispatcher/` - vendored dispatcher-agents core (the 15 files listed in
  `tools/sync_core.py`, kept identical by `--check` in CI), the 20
  `listing_spokes*.py` agents, `handoff_guard.py`, `lead_rubric.py`,
  `config_status.py`, and the optional modules above.
- `identity/routes.json` - the closed track.
- `00-dispatcher/` ... `20-social-media-monitoring/` - each agent's ratified
  SKILL.md and DECISIONS.md.
- `config/` - business content the code cannot guess (templates, cadences,
  milestones, vendor panel, authority signers). Drafts until you ratify them.
- `tests_listing/` - the full suite. Run it from a fresh clone before
  trusting any "done" claim, including this README's.

## Provenance

The ratified source for every agent's SKILL.md and DECISIONS.md, and for the
routes, is
[listing-agents-blueprint](https://github.com/QuietFireAI/listing-agents-blueprint).
This repository is the working build against that blueprint; edits to one
belong in the other.

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
