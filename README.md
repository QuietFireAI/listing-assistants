# ListingAssistants (formerly listing-agents)

**The Governed 21-Agent Residential Real Estate Swarm on a Closed Track**  
*Every message routed by one hub, every route pre-approved, every action recorded on a tamper-evident, hash-chained audit log.*  
*(Official Production Domain: [ListingAssistants.com](https://ListingAssistants.com) — Brand notice: distinct from listingagent.com)*

[![Test Suite](https://img.shields.io/badge/pytest-558%20passed-brightgreen.svg)](tests_listing/)
[![Closed Track](https://img.shields.io/badge/routes-51%20closed%20lanes-blue.svg)](identity/routes.json)
[![Playbooks](https://img.shields.io/badge/playbooks-24%20ratified-blueviolet.svg)](playbooks/)
[![Decisions](https://img.shields.io/badge/tuples-227%20deterministic-orange.svg)](docs/SWARM_COACHES_PLAYBOOK.md)
[![Audit](https://img.shields.io/badge/chain-SHA--256%20%2B%20Ed25519-success.svg)](dispatcher/core.py)

---

## What is ListingAssistants?

**ListingAssistants** is a production-grade, multi-agent AI operating chassis specifically engineered for residential real estate brokerages, top-producing listing agents, and high-volume transaction teams. 

Unlike conventional, unconstrained LLM chat wrappers that hallucinate prices, leak client confidential data, or improvise legal terms, **ListingAssistants** operates on an **invariable railroad chassis**:
* **21 Specialized Spoke Agents (00–20):** Dedicated single-responsibility agents covering every phase of the listing lifecycle (lead capture, qualification, MLS ingestion, photography curation, showing logistics, transaction management, Fair Housing compliance, CRM updates, and financial reconciliation).
* **Closed Routing Track (51 Verified Lanes):** The LLM never decides who to speak to. Every envelope is routed through a central dispatcher hub strictly governed by [`identity/routes.json`](identity/routes.json). Unapproved routing attempts are immediately rejected and logged.
* **Deterministic Decision Tuples (227 Tuples):** All ambiguous, sensitive, or statutory edge cases are pre-deliberated. If a situation matches a tuple, the rule executes deterministically without model improvisation.
* **Cryptographic Authority & Money Gates:** High-risk actions (listing price authorizations, listing status changes, and wire-related instructions) require an **Ed25519 cryptographic signature**. Unsigned or invalid requests are dropped fail-closed.
* **6 QuietFire Forensic Detection Pillars:** Continuously inspects agent thought traces and outputs for adversarial divergence, prompt injection, and goal drift.

---

## Key Capabilities & Hardened Additions

### 1. JEV AI Decision Platform Integration
Integrates with the high-efficiency **JEV AI Decision Platform** (`dispatcher/decision_adapter.py`) via the Model Context Protocol (MCP) tool contract. Includes an in-process, zero-network pure Python fallback engine (`JevPythonDecisionEngine`) that evaluates multi-attribute lead rubrics and showing calendar conflicts with zero HTTP REST overhead.

### 2. Nous Hermes Cognitive Seam & Thought Extraction
Leverages **Nous Hermes** (`dispatcher/hermes_seam.py`) to extract `<think>...</think>` tokens directly in-stream. This bypasses frontier provider thought-inspection bans and feeds authentic internal deliberation directly into the QuietFire detection pillars. Includes the `BrokerContextIngestor` to onboard Hermes like a junior college graduate undergoing in-house brokerage training (SOPs, Fair Housing hard lines, and NAR 2024 settlement rules).

### 3. Local Appliance SQLite Persistence Layer
Equipped with `dispatcher/persistence_sqlite.py`, providing zero-daemon ACID transactional persistence tailored for local NVMe storage or repurposed Drobo NAS RAID partitions. Persists CRM interaction histories (Agent 14), client drawer registers, and financial commission ledgers (Agent 15) across reboots and power cycles.

### 4. Air-Gapped Apricorn Update Pack Verifier
Offline hardware appliances deployed in the field receive updates via encrypted Apricorn USB flash drives verified by `tools/verify_update_pack.py`. Enforces SHA-256 payload integrity and Ed25519 digital signatures, with a `--dev-bypass` option for cloud VM testing.

### 5. "One Client, One Drawer" Privacy Vaults
Eliminates confidential client data leakage and cross-contamination via strict filesystem and database isolation (`dispatcher/client_drawer.py`). Every client receives an isolated vault (`drawers/<client_id>/`). Attempts to access files across drawer boundaries raise `ComminglingBreachError` fail-closed. Verified via `tools/inspect_client_drawer.py`.

### 6. Human-in-the-Loop (HITL) Resumption Protocol & Real-Time Alerts
Provides a complete pause-and-resume lifecycle (`dispatcher/hitl_protocol.py`) when agents hit human authorization gates. Serializes task state to `WaitState`, fires immediate real-time notifications via SMS (Twilio), webhook, or push, deterministically resumes the exact halted spoke upon human directive, and recaps open decisions in Agent 18's 08:00 AM morning dossier. Managed via `tools/manage_hitl_queue.py`.


---

## The 21 Spoke Agents

| Agent ID | Name | Core Responsibilities | Absolute Invariant |
| :--- | :--- | :--- | :--- |
| **00** | Human Principal | Licensed Broker / Team Lead | Owns all fiduciary pricing, legal lines, and final sign-offs. |
| **01** | Lead Capture | Inbound ingestion across web, email, SMS | Never promises service without jurisdiction verification. |
| **02** | Lead Qualification | Applies signed lead-scoring rubric via JEV AI | Never authors rubrics; exact boundary scores drop to lower tier. |
| **03** | Lead Nurture | Cadenced buyer/seller follow-up | Respects legal quiet hours; honors immediate opt-outs. |
| **04** | Listing Description | Drafts property MLS remarks via Hermes | Zero subjective steering words; physical property facts only. |
| **05** | Listing Onboarding | Onboarding package & draft MLS records | Go-live requires verified active status, not an assumed push log. |
| **06** | Showing Scheduler | Showing calendar logistics & buffer management | Access codes never transmitted; double-bookings strictly arbitrated. |
| **07** | Transaction Coordinator | Escrow timeline & contractual deadlines | Wire fraud lines absolute; inspection repair negotiations human-only. |
| **08** | Document Collection | Files disclosure forms & transaction artifacts | Sensitive docs from unexpected senders quarantined immediately. |
| **09** | Vendor Coordinator | Dispatches photographers, stagers, inspectors | Vendor contact details shielded; unvetted vendors rejected. |
| **10** | Market Data | Comp packages & neighborhood statistics | Pure statistics only; opinions and appraisal substitutions refused. |
| **11** | Client Communication | Central client-facing communication voice | Angry clients trigger immediate outbound hold & human queue review. |
| **12** | Marketing & Media | Prepares brochures, flyers, ad copy | Assets held until Fair Housing clearance & Clear Cooperation proof. |
| **13** | Buyer Matching | Matches active listings to pre-qualified buyers | Never fabricates property amenities or pricing concessions. |
| **14** | CRM & Pipeline | Authoritative system of record for interaction logs | Zero-loss persistence of client consent and communication history. |
| **15** | Financial & Commission | Commission calculations & escrow tracking | Reconciliation tolerance is $0.00; wire transfers never handled. |
| **16** | Referral & Post-Close | Post-closing relationship & review management | Annual milestone checks; immediate opt-out compliance. |
| **17** | Compliance & Fair Housing | Statutory Fair Housing & MLS rules review | Flagged phrases hard-stop publication; near-misses audited. |
| **18** | Calendar & Tasks | Human agent daily briefings & wait-state tracking | Contractual deadlines outrank soft meetings; recurring tasks debounced. |
| **19** | Prospecting & Farm | Geo-farm analysis & outreach planning | DNC / TCPA compliance strictly enforced before any touch. |
| **20** | Social Media Monitor | Brand sentiment tracking & review monitoring | Public complaints trigger immediate P14 outbound hold & human handoff. |

---

## Installation & Verification

### 1. Requirements
* Python 3.10+ (Python 3.12 recommended)
* `git`

### 2. Setup
```bash
git clone https://github.com/QuietFireAI/listing-agents.git
cd listing-agents
pip install -r requirements.txt
```

### 3. Verification Suite
Run the 558-test verification matrix:
```bash
python -m pytest tests_listing/
```
*Guaranteed: 558 passed, 0 failures, 0 warnings.*

Run the live MCP stdio roundtrip test:
```bash
python tools/mcp_roundtrip.py
```

Run the Six-Act end-to-end swarm lifecycle demonstration:
```bash
python tools/run_demo.py
```

---

## Documentation Roadmap

* **For Prospective Real Estate Agents:**
  * [`docs/AGENT_USER_MANUAL.md`](docs/AGENT_USER_MANUAL.md) — How ListingAssistants powers your daily workflow while safeguarding your license.
* **For System Owners & Architects:**
  * [`docs/OPERATOR_TUNING_GUIDE.md`](docs/OPERATOR_TUNING_GUIDE.md) — How to fine-tune Hermes, adapt JEV AI rubrics, configure Drobo NAS storage, and deploy updates.
  * [`docs/JEV_DECISION_PLATFORM.md`](docs/JEV_DECISION_PLATFORM.md) — JEV AI decision protocol and Python fallback engine details.
  * [`docs/TUNING_MANUAL.md`](docs/TUNING_MANUAL.md) — Complete register of configurable operational thresholds.
* **Operational Playbooks & Coaches Guide:**
  * [`docs/SWARM_COACHES_PLAYBOOK.md`](docs/SWARM_COACHES_PLAYBOOK.md) — Plain-English guide to all 24 playbooks and 227 decision tuples.
  * [`docs/PLAYBOOKS.md`](docs/PLAYBOOKS.md) — Technical triggers, inputs, and human-in-the-loop gates for Playbooks P01 through P24.

---

## Licensing & Brand Notice

* **Brand Notice:** **ListingAssistants** is being rebranded at [ListingAssistants.com](https://ListingAssistants.com). It is entirely separate, distinct, and independent from *listingagent.com*.
* **License:** Dual-licensed under the **QuietFire Identity License** over an **AGPL-3.0** floor. Evaluation, development, and internal testing are open. Commercial deployment requires an authorized commercial license from QuietFireAI.
