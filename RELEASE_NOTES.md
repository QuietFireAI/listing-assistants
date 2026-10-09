# Release Notes — ListingAssistants Archetype v1.0.0
### Tag: `archetype-v1.0.0` (Production Master Chassis)
*(Official Domain: [ListingAssistants.com](https://ListingAssistants.com) &bull; QuietFireAI)*

---

## 1. Executive Summary

We are pleased to announce the formal release of **ListingAssistants Archetype v1.0.0** (`archetype-v1.0.0`). 

This release marks the transition from prototype research into a production-grade, hardened, multi-agent operational chassis designed for residential real estate brokerages, top-producing listing agents, and high-volume transaction teams. It establishes the **Master Archetype** from which nine subsequent industry personalities can be stamped.

All **561 verification tests** pass with 100% green integrity across all unit, mutation hardening, and end-to-end playbook vectors.

---

## 2. What's Included in Archetype v1.0.0

### Core Governance & Chassis
* **21 Specialized Spoke Agents (00–20):** Dedicated single-responsibility agents covering every phase of the real estate listing lifecycle.
* **Closed Routing Track (51 Legal Lanes):** Hub-enforced message transport strictly governed by `identity/routes.json`.
* **227 Deterministic Decision Tuples:** Pre-deliberated operational edge cases preventing stochastic improvisation.
* **Cryptographic Signer Registry:** Ed25519 digital signature enforcement on authority intents (pricing changes, go-live authorizations, wire transfers).
* **6 QuietFire Forensic Detection Pillars:** In-stream thought inspection detecting cognitive drift, prompt injection, and lateral context leakage.

### The 6 Strategic Additions
1. **JEV AI Decision Platform Adapter & Pure-Python Fallback Engine:**
   * MCP stdio tool contract (`tools/call_jev_decision`) + sub-2ms in-process pure Python engine (`dispatcher/decision_adapter.py`).
   * Evaluates multi-attribute lead qualification (Agent 02) and showing schedule conflict arbitration (Agent 06).
   * Enforces verified document precedence and conservative boundary drops.
2. **Nous Hermes Cognitive Seam & Broker Ingestion Engine:**
   * In-stream `<think>...</think>` token extraction feeding QuietFire forensic detection pillars.
   * "New College Graduate" in-house onboarding curriculum (`BrokerContextIngestor`) for NAR 2024 settlement rules, Fair Housing hard lines, and wire defense.
   * Structured JSONL exporter for fast local LoRA fine-tuning on consumer/appliance GPUs.
3. **Appliance SQLite Persistence Layer on Drobo NAS RAID:**
   * Zero-daemon ACID transactional engine with WAL mode (`dispatcher/persistence_sqlite.py`).
   * Persistent schemas for CRM interaction histories (Agent 14), TCPA communication consent, and financial commission ledgers (Agent 15).
4. **Air-Gapped Apricorn Encrypted Flash Drive Update Verifier:**
   * Ed25519 digital signature and SHA-256 payload integrity verifier (`tools/verify_update_pack.py`) for offline hardware appliances.
5. **"One Client, One Drawer" Privacy Vault Architecture:**
   * Isolated client directory trees (`drawers/<client_id>/`) with `raw/`, `working/`, `delivered/`, `timeline/`, and `audit/` subfolders.
   * Fail-closed `ComminglingBreachError` defense preventing cross-client data bleeding.
   * Inspection CLI: `tools/inspect_client_drawer.py`.
6. **Human-in-the-Loop (HITL) Resumption Protocol & Real-Time Alerts:**
   * Serialized `WaitState` lifecycle for gated decisions (`dispatcher/hitl_protocol.py`).
   * Immediate real-time alert dispatch via SMS (Twilio), webhook, or push.
   * Standardized decision actions: `APPROVE`, `APPROVE_WITH_OVERRIDE`, `REJECT`, `HOLD`, `CLOSE_SYSTEM`.
   * Daily 08:00 AM morning dossier roll-up via Agent 18.
   * Forensic diagnostic snapshot tool: `tools/snapshot_drawer.py`.

### Non-Technical Interfaces & Observability
* **Client Funnel & Drawer Portal (`tools/dashboard.py`):**
  * Visual terminal pipeline board and interactive HTML web dashboard (`dashboard.html`).
  * Shows client location, 6-stage funnel progress, active next steps, and pending HITL decisions.
* **Human-Readable Real-Time & EOD Logging (`dispatcher/readable_logger.py`, `tools/show_logs.py`):**
  * Real-time stream logging (`logs/stream.log`).
  * Per-client activity log in their drawer vault (`drawers/<client_id>/audit/activity.log`).
  * Automated End-of-Day (EOD) Operations Ledger (`logs/daily/eod_ledger_YYYY-MM-DD.md`).

---

## 3. Verification & Compliance Matrix

* **Pytest Suite:** 561 passed in 11.18s (`python -m pytest tests_listing/`).
* **MCP Protocol Test:** Verified (`python tools/mcp_roundtrip.py`).
* **Six-Act Swarm Demonstration:** Verified (`python tools/run_demo.py`).
* **Tuning Manual Freshness:** AST-verified (`tests_listing/test_tuning_manual_freshness.py`).
* **License:** Dual-licensed under QuietFire Identity License over an AGPL-3.0 floor.
