# Financial Capability — Status, Controls, and Absolute Fiduciary Guardrails

> ### ⚠️ CRITICAL FIDUCIARY NOTICE (FRONT AND CENTER)
> **DISPATCHER AGENTS AND LISTING AGENTS ARE FUNDAMENTALLY INCAPABLE OF PERFORMING FINANCIAL TRANSACTIONS. IT IS NOT WIRED.**
> 
> * **Zero Financial Execution Wiring:** There is no payment SDK, no automated wire gateway, and no banking transfer execution path anywhere in this software. The wiring does not exist.
> * **Sole Human Fiduciary Responsibility:** Under state real estate licensing law and the REALTOR® Code of Ethics, fiduciary responsibility belongs 100% to the licensed broker-in-charge. Fiduciary duty cannot be delegated to an AI agent.
> * **NEVER During Training Under Any Circumstances:** Under no circumstances—whether during broker onboarding, model training, prompt personalization, or local fine-tuning—is an agent ever permitted to handle financial authority. The user must maintain full fiduciary control. A user must NEVER attempt to delegate financial actions to an agent during training. Only after an agent has been formally deployed into production motion and has demonstrated repeated, verified proficiency in its assigned administrative tasks can an authorized human even release a held *text disclosure*—and even then, financial *execution* remains completely unwired.

This is the document a held message points you to. If a ListingAssistants agent stopped
and told you it could not send financial, pricing, or position-bearing content, it linked
here. Nothing broke. The system did exactly what it was engineered to do.

This document is written for the licensed broker-in-charge and for that
brokerage's legal, risk management, or compliance reviewer. It states what the system
cannot do, why, and where the boundaries are.

---

## The Core Rule: Financial Execution Is Not Wired

A ListingAssistants agent **cannot execute a financial transaction, cannot quote or negotiate a listing price, and cannot reveal a client's financial position without explicit, authenticated human authorization**.

The default software appliance ships with financial execution capabilities completely absent:
* There is no Stripe, Plaid, ACH, Fedwire, or banking API integration.
* There is no dormant code path waiting to move money.
* Turning on financial movement is not a toggle or setting—it is fundamentally unwired at the architectural level to protect the brokerage from liability.

---

## The Four Non-Negotiable Financial Firewalls

Real estate transactions involve the transfer of substantial personal wealth, legal contingency deadlines, and high-stakes fiduciary liabilities. The platform enforces four non-negotiable financial firewalls:

### 1. Fiduciary Pricing Firewall (Zero Autonomous Valuation)
* **Rule:** No agent within the swarm will ever set, invent, suggest, discount, or negotiate property prices, offer amounts, counteroffers, or concession figures.
* **Mechanism:** Valuation belongs exclusively to the licensed human broker (Agent 00). Inquiries regarding bottom-line prices, acceptable offer floors, or property valuation are immediately halted, logged to `escalation.legal_line`, and routed to the human broker.

### 2. Wire Fraud Zero-Tolerance Shield
* **Rule:** Wire fraud is the #1 cyber threat in residential real estate. ListingAssistants strictly forbids transmitting bank routing numbers, account details, or wire instructions over email, SMS, or chat.
* **Mechanism:** Any inbound or outbound communication mentioning wire instructions, wiring changes, or routing numbers triggers an immediate conversation lock and alerts the broker. Clients are instructed that wire verification must occur strictly via authenticated voice contact or encrypted title closing portals.

### 3. Strict Pre-Approval Document Precedence (JEV AI)
* **Rule:** Self-reported buyer budgets never override verified documentation.
* **Mechanism:** When scoring buyer qualification (Agent 02), the JEV AI decision coprocessor strictly anchors purchasing power to the verified pre-approval letter amount filed in the client drawer. Stated claims of higher budgets are logged verbatim as discrepancies but ignored for financial scoring.

### 4. Earnest Money Deposit (EMD) & Closing Ledger Tracking
* **Rule:** Earnest money deposits, contingency releases, and commission splits must reconcile to $0.00 against verified escrow receipts.
* **Mechanism:** Handled by Agent 07 (Transaction Coordinator) and Agent 15 (Commission & Finance). Figures pass into the ledger verbatim from title company escrow receipts and final settlement statements—never re-typed, estimated, or approximated.

---

## Human Key Authorizes Disclosures Only (Never Fund Transfers)

When a human broker signs an authorization key (`disclosure.authority`), **they are authorizing the release of held text communication, NEVER the execution of a financial transfer.**

For example:
* A broker signing off on a counteroffer letter authorizes Agent 11 to transmit that text to the buyer's agent.
* The agent does **not** sign the contract, does **not** transfer earnest money, and does **not** disburse funds.
* Fiduciary execution remains 100% in the hands of the licensed human principal.

---

## What "Held" Means for a Position Disclosure

Execution is one half. **Disclosure is the other, and in daily practice the more critical one.** An agent never reveals to any party outside the principal it serves:

- A seller's price floor, reserve, bottom line, net sheet, or motivation to negotiate
- A buyer's maximum financing qualification, pre-approval ceiling, or urgency
- A circumstance, pending divorce, estate sale pressure, or job relocation that weakens a principal's bargaining position
- What a principal has already privately agreed to, declined, or considered internally

Every outbound communication is classified at the routing switchboard by **who is on the far end**:
* `principal` (the client the identity serves — e.g. the seller)
* `counterparty` (the other side — a buyer's agent, tenant, appraiser, or closing attorney)
* `public` (open feeds — MLS remarks, social media, ad networks)

Messages to the principal pass freely. Messages to a counterparty or the public that touch financial, price, or legal positions **automatically hold for human broker review** (`disclosure.authority`) — every time, regardless of how the message is phrased. The gate keys on the recipient class at the routing layer, so no prompt-injection phrasing can bypass it.

---

## How to Release a Held Disclosure

When a message is held at a financial or disclosure boundary:

1. The held message is assigned a unique `wait_id` and indexed in the client's drawer (`drawers/<client_id>/timeline/<wait_id>_pause.json`).
2. An immediate real-time alert is dispatched to the broker's mobile device (WhatsApp, Signal, or SMS) detailing the reason and exact message context.
3. The broker reviews the context and issues a signed decision (`APPROVE`, `APPROVE_WITH_OVERRIDE`, `MODIFY`, or `HOLD`).
4. The system verifies the broker's cryptographic signature against `config/authority_signers.json` (including multi-factor authentication stamps), commits the event to the SHA-256 audit chain, and releases the single message once.

---

## Physical Hard Drive Vaulting of Financial Artifacts

To prevent financial data leakage, all sensitive client financial artifacts are physically partitioned on the local workstation or Drobo NAS RAID partition:

```
drawers/<client_id>/financials/
├── preapproval_letter_verified.pdf      <-- SHA-256 Fingerprinted
├── proof_of_funds_statement.pdf         <-- Encrypted at rest
├── title_earnest_money_receipt.pdf      <-- Verified escrow deposit receipt
└── commission_net_sheet.json            <-- Reconciled to $0.00
```

* **Physical Isolation:** Financial documents live exclusively inside the client's dedicated folder.
* **`ComminglingBreachError`:** If any agent working on Client A ever attempts to access financial artifacts in Client B's drawer, the actor micro-kernel throws an immediate `ComminglingBreachError`, logs the breach to the audit log, and halts.
* **Zero Cloud Exposure:** Client W-2s, bank statements, and escrow numbers are never uploaded to cloud AI APIs, multi-tenant databases, or public model training sets.

---

## Verifiable System Guarantees

- **Zero Payment SDK:** Grep-verifiable absence of payment gateways or automated transfer code in the default codebase.
- **Signed Authority Required:** All financial-authority routes (`listing.change.authorized`, `commission.split.ratified`) strictly require an authorized human sender with a verified signature.
- **Pre-Persist Audit Chain:** Every financial hold and release is cryptographically hashed with SHA-256 and committed to `logs/audit.jsonl` *before* execution.
- **Deterministic Mathematical Scoring:** Lead budgets and commission allocations are calculated deterministically via JEV AI and pure-Python ledgers, with zero LLM hallucination risk.

