# ListingAssistants Engineering Roadmap & Backlog

**Current Production Version:** `v1.1.0`  
**Target Milestone:** `v1.1.2` (Production Hardening & Live Boundary Validation)

---

## 1. Version Overview

ListingAssistants treats software development like a disciplined practice—deliberate, learned, and verified. Following the successful ratification of `v1.1.0` (which established live JEV co-processor REST integration, Agent 00 boot audit declarations, and explicit `is_fallback: True` telemetry across all spokes), this roadmap outlines the exact operational steps required for subsequent minor releases.

---

## 2. Release Target: v1.1.2 Work Items

The `v1.1.2` cycle addresses physical production boundaries, credentials, and live execution.

### Item 1: Physical Production Hardening
* **Drobo NAS Storage Partitioning & Permissions:**
  * Validate filesystem mounting procedures on local NAS arrays (8TB RAID storage).
  * Establish automated permission checks ensuring each client drawer (`vaults/{client_id}/`) maintains strict OS-level file isolation (`0700` equivalents on POSIX or explicit NTFS ACLs on Windows).
  * Implement automated disk space warning thresholds (Agent 00 alert when available RAID volume drops below 15%).
* **Apricorn Encrypted Hardware Drive Handshake:**
  * Define explicit hardware serial and hash-chain verification protocols when Apricorn encrypted drives are attached.
  * Require physical security pin / challenge-response attestation before granting local backup write access.
  * Standardize physical custody logs recorded directly to the immutable SHA-256 ledger (`audit_ledger.py`).

### Item 2: Third-Party BYOK (Bring-Your-Own-Key) Credential Validation
* **Cellular A2P 10DLC & Twilio Production Activation:**
  * Transition from sandbox/fallback status (`is_fallback: True`, `fallback_reason: TWILIO_NOT_CONFIGURED`) to live carrier delivery once Twilio business EIN and Campaign Registry approvals complete.
  * Verify SMS and WhatsApp outbound delivery confirmation webhooks.
* **RESO MLS Web API Live Testing:**
  * Implement authentication handshake against live RESO Web API compliant MLS servers (Bridge Interactive, Spark, or local MLS RETS/Web API endpoints).
  * Verify listing syndication status pulls and strict read-only boundary adherence prior to broker sign-off.
* **DocuSign / Digital Signature Escrow Gate:**
  * Validate OAuth2 token refresh workflows for DocuSign / LoneWolf digital signing rooms.
  * Ensure document envelope status updates (`sent`, `delivered`, `signed`) trigger corresponding playbook state transitions without improvising document content.

### Item 3: Operational Ergonomics & Observability
* **Automated Fallback Telemetry Dashboard:**
  * Surface a high-visibility status pill on the operator dashboard (`tools/dashboard.py`) showing real-time coprocessor health:
    * `ARMED_LIVE` (Green)
    * `FALLBACK_LOCAL_RULES` (Amber - with explicit reason)
    * `UNARMED` (Red)
* **Periodic Hash Chain Health Checks:**
  * Implement automated daily verification of the SHA-256 ledger (`audit_ledger.verify_chain()`) to guarantee zero bit rot or tampering across long-running storage volumes.

---

## 3. Guiding Invariant for v1.1.2 and Beyond

> **The Zero-Improvisation Standard:**  
> If an external provider, network link, or hardware volume is unconfigured, unreachable, or untrusted, the system **never fakes success**. It transitions explicitly to verified local fallbacks, tags all outputs with `is_fallback: True`, logs the exact reason to the tamper-evident ledger, and halts at the licensed human broker's gate.
