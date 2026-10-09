# Changelog

All notable changes to the **ListingAssistants Archetype** (`ListingAssistants.com` / QuietFireAI) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] - 2026-10-09 - Archetype Release (`archetype-v1.0.0`)

### Added
- **21-Agent Governed Swarm:**
  - 21 discrete spokes (Agent 00 through Agent 20) with strict single-responsibility boundaries.
  - Closed routing topology with 51 legal lanes enforced by Hub (`identity/routes.json`).
  - 227 deterministic decision tuples preventing hallucinated or unapproved agent behavior (`DECISIONS.md`).
  - Cryptographic Ed25519 signer registry for high-stakes operational intents.
  - 6 QuietFire forensic detection pillars for real-time monitoring of in-stream cognitive drift.
- **JEV AI Decision Platform Integration:**
  - Standardized Model Context Protocol (MCP) tool contract (`tools/call_jev_decision`).
  - Pure-Python deterministic decision fallback engine (`dispatcher/decision_adapter.py`) running sub-2ms without external dependencies.
  - Verified document precedence and multi-attribute lead qualification for Agent 02 and showing arbitration for Agent 06.
  - Comprehensive architectural whitepaper: `docs/WHY_JEV_OVER_LLM.md`.
- **Nous Hermes Cognitive Seam & Broker Training:**
  - Runtime `<think>...</think>` cognitive token interception feeding forensic pillars.
  - "New College Graduate" broker context ingestion engine (`BrokerContextIngestor`) for local brokerage rules, Fair Housing, and wire fraud defense.
  - Local GPU LoRA training dataset exporter for offline fine-tuning on consumer hardware.
- **Appliance SQLite Persistence Layer (Drobo NAS RAID Ready):**
  - Zero-daemon ACID transactional database with Write-Ahead Logging (WAL) mode (`dispatcher/persistence_sqlite.py`).
  - Schemas for CRM interaction histories (Agent 14), TCPA consent logging, and financial commission ledgering (Agent 15).
- **Air-Gapped Apricorn Encrypted Hardware Update Verifier:**
  - Dual-key Ed25519 digital signature and SHA-256 integrity verifier (`tools/verify_update_pack.py`) for off-grid hardware appliances.
- **"One Client, One Drawer" Privacy Vault:**
  - Isolated client directory storage (`drawers/<client_id>/`) with segregated categories (`artifacts`, `documents`, `interactions`, `financials`, `timeline`, `audit`).
  - Fail-closed `ComminglingBreachError` defense against cross-client data contamination.
  - Inspection CLI tool (`tools/inspect_client_drawer.py`).
- **Human-in-the-Loop (HITL) Resumption Protocol & Real-Time Alerts:**
  - Serialized `WaitState` lifecycle capturing pause states, reason codes, and approval metadata (`dispatcher/hitl_protocol.py`).
  - Immediate real-time alert dispatch via SMS (Twilio), webhook, or push.
  - Morning 08:00 AM unresolved decision roll-up dossier via Agent 18.
  - Standardized decision codes: `APPROVE`, `APPROVE_WITH_OVERRIDE`, `REJECT`, `HOLD`, `CLOSE_SYSTEM`.
  - Forensic diagnostic snapshot generator (`tools/snapshot_drawer.py`).
- **Non-Technical Client Funnel & Drawer Portal:**
  - CLI visualization and rich responsive HTML dashboard (`tools/dashboard.py` -> `dashboard.html`).
  - Real-time client status, address, pipeline stage, drawer path, and pending action tracking without stubs.
- **Human-Readable Real-Time & EOD Logging:**
  - Real-time formatted stream logging (`logs/stream.log`).
  - Per-client drawer activity log (`drawers/<client_id>/audit/activity.log`).
  - End-of-Day operations summary dossier (`logs/daily/eod_ledger_YYYY-MM-DD.md`) and log viewing CLI (`tools/show_logs.py`).
- **Production Standard GitHub Documentation:**
  - `SECURITY.md`: Vulnerability disclosure policy and cryptographic signing guidelines.
  - `CONTRIBUTING.md`: Development, verification, and code styling rules.
  - `CODE_OF_CONDUCT.md`: Professional standard of conduct.
  - `RELEASE_NOTES.md`: Comprehensive v1.0.0 release notes.

### Changed
- Refactored `ClientDrawer` directory model to include dedicated `audit/` category for immutable human-readable logs.
- Standardized all 21 agent skills (`00-dispatcher` through `20-social-media-monitoring`) with uniform frontmatter and structural parity.
- Synchronized `OPERATOR_TESTING_GUIDE.md` and `docs/AGENT_USER_MANUAL.md` with complete documentation for all 6 strategic additions and JEV integration.

### Verified
- 561 / 561 pytest tests passing 100% green.
- Verified MCP stdio protocol roundtrip via `tools/mcp_roundtrip.py`.
- Verified end-to-end 6-act swarm execution via `tools/run_demo.py`.
