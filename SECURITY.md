# Security Policy — ListingAssistants

## 1. Security Architecture & Invariants

**ListingAssistants** is a governed multi-agent operations platform for licensed real estate professionals. The system is designed with fail-closed security guarantees:

* **Closed Routing Track:** Messages only travel along explicitly approved routes defined in `identity/routes.json`. Lateral or unauthorized communication between agents is rejected at the dispatcher hub.
* **Cryptographic Signatures:** High-stakes actions (fiduciary pricing changes, listing status updates, and wire authorizations) require valid Ed25519 digital signatures from registered authority keys.
* **Tamper-Evident Audit Logging:** All state transitions and envelope passes are recorded in an append-only, SHA-256 hash-chained audit log.
* **Client Isolation ("One Client, One Drawer"):** Every client context has a physically and logically isolated directory vault (`drawers/<client_id>/`). Cross-context access raises `ComminglingBreachError` fail-closed.
* **Zero-Tolerance Wire Fraud Shield:** The system will never transmit bank routing numbers, wire instructions, or account details over email, chat, or SMS.

---

## 2. Supported Versions

| Version | Supported | Notes |
| :--- | :--- | :--- |
| `1.x` / `main` | :white_check_mark: | Active production release ([ListingAssistants.com](https://ListingAssistants.com)) |
| `< 1.0` | :x: | Legacy unhardened prototypes |

---

## 3. Reporting a Vulnerability

We treat all security and compliance concerns with utmost urgency. 

If you discover a potential vulnerability, prompt-injection bypass, routing escape, or data leak:
1. **Do NOT** open a public GitHub issue.
2. Email your findings directly to: **security@quietfireai.com** (or platform owner).
3. Include:
   - A description of the vulnerability and attack vector.
   - Exact steps or script to reproduce the behavior.
   - Any observed audit log output or bypass traces.
4. You will receive an acknowledgment within 24 hours.

---

## 4. Responsible Disclosure

We request that you give the project team a reasonable window (typically 30 to 90 days depending on severity) to develop, test, and release a patch before disclosing details publicly.
