# ListingAssistants Identity Module - Real Estate (v0.1, ratified 2026-07-10)

Side-loaded vertical identity for the dispatcher-agents hub (the core files
vendored in `dispatcher/`, listed in `tools/sync_core.py`). This module
declares WHAT is orchestrated; the core
defines HOW orchestration works. Swap this module to redeploy the same
dispatcher into another vertical (e.g., insurance/claims).

## Practice identity
A residential real estate listing practice's non-licensed operations layer:
intake, nurture, listing production, MLS operations, scheduling, transaction
coordination, documents, vendors, market data, client communication,
marketing, buyer matching, records, financial tracking, post-close
relationships, compliance review, calendar, prospecting discovery, social
listening. The licensed human agent performs all fiduciary, legal, pricing,
negotiation, and representation acts.

## Declared resources (attested at boot per core)
- Agent roster: skill folders 00-20 (each folder's SKILL.md; docs/JOB_DESCRIPTIONS.md lists them all); specs are authoritative - 
  read them, never restate from memory.
- Playbook library: docs/PLAYBOOKS.md, P01-P24 (triggers, agents, gates);
  each has an end-to-end test in tests_listing/.
- Routing table: identity/routes.json (the closed track).
- Registered human key(s): deployment configuration.

## Vertical escalation queues
`escalation.legal_line` (immediate - fiduciary/legal/pricing/negotiation),
`escalation.hot_lead` (per configured urgency), `escalation.complaint`
(per configured urgency). Threads an agent cannot continue on its own hold
through the HITL protocol until the broker signs continue or cancel.

## Authority intents requiring signature (per core directive 5)
`listing.change.authorized`, `config.update`, and every `*.authority`
intent: `disclosure.authority` (releasing a held outbound message) and
`hitl.decision.authority` (continue or cancel on a held thread).

## Playbook priority classes (per core JIT doctrine - ratified 2026-07-10, owner sign-off)
- Class 2 (JIT freight - clocks at risk): P02 (signed price execution), P03
  (status flip + marketing halt windows), P05 (halt legs are compliance
  clocks), P08 (offer response deadlines), P09 (contract-to-close), P14
  (complaint containment steps; notification rides Class 1 queues).
- Class 3 (scheduled service): P01, P04, P06, P07, P10 (close/post-close
  transitions), P11 (front door; hot-lead escalations ride Class 1), P15
  (appointment-anchored).
- Class 4 (junk trains - take the siding): P12, P13.

## Vertical hard lines the sequences must never route around
- Fiduciary pricing advice, contract negotiation, legal opinions,
  representation, signing: human only, every playbook, every step.
- Wire/funds instructions: never transmitted, confirmed, or modified by any
  spoke (07/08/11 carry the line; the sequence enforces it).
- Fair housing: no content publishes without a compliance verdict
  (`content.verdict: approved` in the provenance chain); no steering in
  matching, marketing, or data presentation.
- Clear Cooperation: no public listing marketing before MLS entry
  confirmation or a documented exempt status with signed seller disclosure.
- Written buyer agreements before touring (showing requests carry the
  agreement-on-file flag).
- Consent/opt-out flags (authoritative in 14) gate every outbound touch. In the
  code (2026-10-12) Agent 11 asks 14 before every client send and sends nothing
  to a client opted out on every channel; client messages carry no channel, so a
  single-channel opt-out does not block them.

## Status: v0.1 ratified 2026-07-10 (owner sign-off) - runtime-tested via the dispatcher-agents suite; no licensed legal review yet.
