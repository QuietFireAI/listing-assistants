# Changelog

All notable changes to the **ListingAssistants Archetype** (`ListingAssistants.com` / QuietFireAI) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased] - audit fixes (branch `audit-fixes-2026-10-11`)

### Fixed
- Client drawers: path traversal, cross-client filing, identity overwrite; real traversal tests.
- HITL: decisions must be signed `hitl.decision.authority` envelopes bound to the client; the CLI no longer reports fake success.
- Update-pack verifier: takes a public key; unlisted files, unsafe paths and downgrades refused; no environment bypass; `tools/sign_manifest.py` added.
- Signer config restored to an unratified template; draft configs no longer loaded (07, 08, console).
- JEV adapter: one shared lead rubric with Agent 02; missing confidence holds; external calls need `allow_external=True`.
- Hermes seam: no fabricated thoughts or drafts; missing `<think>` trips the taint gate; no pillar stand-ins.
- SQLite store: exact decimal money, append-only ledgers, consent history, re-opt-in needs human confirmation, WAL.
- Checkpoints: no exam without a model; fabricated 100% scores removed.
- EOD report: integrity lines computed or "not computed".
- Agent 11 reply routing; lead.reply handlers for 04 and 12.
- Handoff rule enforced on every spoke send (`handoff.failed`).
- Daily clock and console reports go through the hub (`clock.tick` route).
- MCP server no longer signs for the host outside `--demo-signing`; medical-billing code removed.
- `tools/inspect_client_drawer.py` reports real hash results instead of a fixed "VERIFIED" line.
- Documentation rewritten to match the code; deleted disclosures restored; `docs/WHY_JEV_OVER_LLM.md`, `docs/LEARNING_LOOP_AND_DRIFT_ARCHITECTURE.md`, `docs/WEBSITE_PROJECT_HANDOFF.md` and `docs/SECURITY_AUDIT_REPORT.md` removed from the repository.

- Operator scenes (`scenes/`) and a test that runs them; fourteen real-traffic breaks they exposed fixed (see RELEASE_NOTES.md).
- Swarm state saved and restored through the SQLite store, vouched for by the audit chain; one swarm builder for console, clock and MCP server.
- Held threads (duplicate person, owner-less reply, social drafts) through the HITL protocol; console `decide`, `release`, `onboard`.
- Owner decisions: Agent 03 sequences on the clock, Agent 13 neighborhood path removed, Agent 19 comps, Agent 20 template drafts held for approval, Agent 20 off `behavioral.signal`, P13 on the clock.
- Unrecognized signed settings and uncovered client replies held instead of dropped; once-only escalations.
- Repository is the single source; JOB_DESCRIPTIONS generated here; TelsonBase references removed; `SESSION_HANDOFF_6.md` removed.
- Modules wired (2026-10-12): client drawers (04, 05, 07, 08, 14, 15 file; HITL holds recorded), plain-language log and chain-built EOD ledger, JEV adapter in Agent 02 (signed `decision_engine` opt-in for live calls; low-confidence holds), model drafting for Agent 04 behind a signed switch and an examined checkpoint (`restore_point.py --exam` against a served model; console `--model-url`/`--model-name`).
- Owner J decisions (2026-10-12): P18-P21 on the daily clock; disclosure-deadline warning (08); market-update paths removed from 03/11 and their routes; pillars pinned to commits; console text pager (`console.py pager`); 23 DECISIONS.md tuples added, 2 retired.
- Fixed: case-insensitive removal of flagged phrases in 04 (a capitalized phrase looped 20 times); a re-sent signed setting already in effect no longer pages as unrecognized; README P01 diagram renders on GitHub.

### Corrections to the 1.0.0 entry below
Several 1.0.0 items did not match the code at the time: "MCP tool contract (`tools/call_jev_decision`)" (no such tool), "Dual-key" verifier (single key, and the CLI could not take one), "Immediate real-time alert dispatch via SMS, webhook, or push" for HITL (an optional callback only), "Standardized all 21 agent skills" (no agent SKILL.md changed), the WAL claim (no PRAGMA), and "561 / 561" (the suite at the `archetype-v1.0.0` tag runs 577 tests, all passing; checked 2026-10-11). The entry is kept as written for history.

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
