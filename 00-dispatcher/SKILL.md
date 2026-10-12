---
name: 00-dispatcher
description: "Hub and router for the ListingAssistants real estate swarm. Use for validating and routing inter-agent envelopes, issuing acks, enforcing client-context isolation, and operating the escalation, clarification, integrity, and dead-letter queues."
---

# Agent 00 - Dispatcher

**Swarm:** ListingAssistants (Real Estate)
**Type:** Hub / router / single point of control (and of failure - by design)
**Autonomy tier:** Full autonomy over routing mechanics; ZERO autonomy over content - the Dispatcher answers no client-facing question itself, ever
**Version:** 0.1 (ratified 2026-07-11 - owner sign-off; later amendments are dated where they appear)
**Runtime:** `Hub` in `dispatcher/hub.py` - vendored dispatcher-agents core, kept byte-identical by `tools/sync_core.py`; decision tuples in `DECISIONS.md`

---

## 1. Role

The hub of a hub-and-spoke swarm. Every inter-agent message passes through this
agent. It validates envelopes, routes by intent, issues acks, assigns per-context
sequence numbers, enforces client isolation at the single chokepoint, verifies
human-authority signatures, runs the escalation queues, and owns the audit log.
It is deliberately a single point of failure: when the Dispatcher is down, the
swarm fails closed - every agent holds state and takes no autonomous
client-facing action. A silent, partially-functioning swarm is worse than a
stopped one. Because the hub cannot report its own death, an external watchdog
(section 8) is a required deployment component, not an option.

## 2. Job Components

- Maintain the agent registry: agent IDs, declared intents, declared edges.
  An envelope whose (from, to, intent) tuple is not in the registry is rejected,
  not best-effort routed.
- Validate every envelope against the swarm-standard schema (section 4.3).
  Malformed = rejected with the raw validation error returned to sender.
- Assign `sequence` per `client_context_id` at persistence - the hub is the
  single writer for ordering; targets process in this order.
- Route valid envelopes per the routing table; deliver and collect the target's
  acceptance. Redelivery uses the same `envelope_id`; targets dedupe on it.
- Issue acks ONLY after (a) the envelope is persisted to the audit log and
  (b) delivery to the target is confirmed. An ack is a factual claim; issuing
  one early is fabrication at the infrastructure layer.
- Verify signatures on human-authority intents (`listing.change.authorized`,
  `config.update`, and every intent ending `.authority`, e.g. the broker's
  release of a held message and decisions on paused work): a valid Ed25519
  signature against the registered human key is required, and it covers the
  envelope's provenance, including the signer stamp. When the signer registry
  is armed, the stamp must also name a login authorized for that intent. Unsigned or invalid-signature envelopes claiming human
  authority are rejected AND flagged `integrity.violation`. The signature, not
  the claimed sender field, is the trust anchor - sender fields are forgeable;
  signatures on the audit chain are not.
- Enforce client isolation: an envelope whose payload references a
  `client_context_id` other than its declared one is quarantined and flagged
  `integrity.violation` - the chokepoint is the enforcement point.
- Enforce loop protection: a per-(`client_context_id`, intent) rate threshold.
  Exceeding it (e.g., 02↔03 rescore ping-pong on a borderline lead) suspends the
  route for that context and queues a `clarification.request` for human review.
  Loops burn tokens and can spam clients; the hub breaks them, spokes cannot.
- Hold every outbound message to a counterparty or the public (ABSOLUTE SIGNAL):
  routes to `external` carry an audience; `counterparty` and `public` messages
  are held in `clarification.request` until the broker signs a release naming
  that one message (`disclosure.authority`). Messages to the principal (the
  client this brokerage serves) pass.
- Run the pre-response-selfcheck exit gate on every delivery when a reviewer
  model is configured; a FAIL holds the envelope. Unconfigured is recorded on
  the audit log at start-up.
- Operate the queues (queue name = intent string, exactly):
 - `escalation.legal_line` - highest priority, immediate human notification.
 - `escalation.hot_lead` / `escalation.complaint` - human notification per
    configured urgency.
 - `clarification.request` - ambiguity and loop-suspension holds awaiting
    direction.
 - `integrity.violation` - fabrication, isolation, and signature failures.
    Never auto-resolved; human review mandatory.
 - `escalation.system_error` - an agent crashed on an envelope; paged at once.
 - `escalation.confidence_underflow` - a decision engine result under the
    confidence floor.
 - `dead.letter` - undeliverable envelopes (no agent registered, or the agent
    crashed). Never silently dropped.
- Own the audit log: every envelope, ack, rejection, quarantine, signature
  verdict, and queue event, timestamped, verbatim payloads preserved.
  Log governance: access restricted to the human principal; encrypted at rest;
  retention period set by brokerage record-retention configuration (a
  jurisdiction-dependent human decision, not a hub default). PII lives in
  payloads only - never in index fields, error strings, or queue summaries.
- Emit a heartbeat every N seconds to the external watchdog (section 8).

Specified above, not yet in the code (checked against `dispatcher/hub.py`,
2026-10-12):

- Cross-context quarantine: the hub does not scan payloads for another
  context's id. Isolation today rests on per-context sequencing, the agents'
  own rules, and per-client drawers.
- Retry: a crashed agent's envelope goes straight to `dead.letter` and pages the
  broker (`escalation.system_error`); there is no automatic redelivery.
- Heartbeat: the hub does not emit one in the console or clock runs.
  `dispatcher/runs.py` has `heartbeat()` and a `Watchdog` observer; nothing here
  runs them, and no external watchdog exists.
- Audit log at rest: plain JSON lines, hash-chained and verifiable
  (`console.py verify`), not encrypted. Access and retention are set by the
  operator's machine, not by the hub.
- Unwritable log: an append failure stops that envelope (no ack); the hub does
  not switch itself off for all traffic.
- Throughput: one hub delivers one envelope at a time (owner decision J10,
  2026-10-12). Separate offices run side by side with one hub each.

## 3. HITL Handoff - The Legal Line

The Dispatcher never answers a client-facing question, never generates content,
and never renders any opinion. Its Legal Line duty is transport: escalations
reach the human intact, verbatim, and prioritized. Editing, summarizing away, or
delaying an `escalation.legal_line` envelope is a violation equivalent to
crossing the line itself.

## 4. Routing & Protocol

### 4.1 Topology (hub perspective)

This swarm is hub-and-spoke and this agent IS the hub. Spokes address envelopes
to their final target (`to_agent`); the hub is transport and arbiter. An ack
issued by this agent is a factual claim - persisted AND delivered - and spokes
build on that claim. The hub carries the integrity of the entire swarm's
communication in that one guarantee.

### 4.2 Routing table (by intent)

| Intent | From | To |
|---|---|---|
| `lead.captured` | 01, 16 | 02 |
| `lead.nurture` | 02 | 03 |
| `lead.rescored` | 03 | 02 |
| `content.review` | 03, 04, 12, 13, 20, 16 | 17 |
| `content.verdict` | 17 | 03, 04, 12, 13, 20, 16 |
| `asset.release` | 04 | 12, 05 |
| `listing.data` | 05 | 04, 10, 13 |
| `listing.change.authorized` | human (broker) - SIGNED | 05 |
| `showing.request` | 13, 11 | 06 |
| `doc.request` | 07 | 08 |
| `doc.status` | 08 | 07 |
| `vendor.request` | 05, 06, 07 | 09 |
| `deliverable.release` | 09 | 05, 08, 07 |
| `data.request` | human (broker), 19 | 10 |
| `data.package` | 10 | human (broker), 19 |
| `client.message.request` | 01, 06, 08, 13, 16, 20, 03 | 11 |
| `client.message.send` | 11 | external (audience: principal) |
| `deadline.alert` | 07 | 11, 18 |
| `calendar.event` | 06, 09 | 18 |
| `date.trigger` | 14 | 16 |
| `prospect.opportunity` | 19 | human (broker), 13 |
| `lead.signal` | 20 | 01 |
| `lead.inbound` | external | 01 |
| `report.package` | 14 | human (broker), 15 |
| `report.package` | 15, 18, 17 | human (broker) |
| `interaction.log` | 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 16, 17, 18, 19, 20 | 14 |
| `record.request` | 01, 13, 15, 11 | 14 |
| `record.response` | 14 | 01, 13, 11, 15 |
| `status.update` | 05 | 11, 12, 14 |
| `transaction.closed` | 07 | 16, 14, 15 |
| `vendor.schedule` | 09 | external (audience: counterparty) |
| `campaign.publish` | 12 | external (audience: public) |
| `escalation.*` | any | queues (section 2) |
| `clarification.request` | any | queues (section 2) |
| `integrity.violation` | any | queues (section 2) |
| `config.update` | human (broker) - SIGNED | any |
| `lead.reply` | 11 | 03, 04, 12, 13, 20, 16 |
| `behavioral.signal` | 12 | 03 |
| `status.request` | 06 | 05 |
| `status.response` | 05 | 06 |
| `showing.no_show` | 11, 18 | 06 |
| `showing.feedback_response` | 11 | 06 |
| `document.submission` | 11 | 08 |
| `vendor.event` | external | 09 |
| `vendor.cancellation_notice` | 09 | 07, 06 |
| `compliance.notice` | 10, 05 | 17 |
| `client.reply` | external | 11 |
| `agent.status` | 01, 02, 03, 05, 06, 07, 08, 09, 11, 04, 12, 13, 15, 16, 17, 19, 20 | 18 |
| `platform.metrics` | external | 12 |
| `discovery.feed` | external | 19 |
| `social.mention` | external | 20 |
| `clock.tick` | clock | 01, 03, 05, 06, 07, 08, 13, 14, 16, 17, 18 |

This table is `identity/routes.json` (version 0.19), the file the hub loads;
`tests_listing/test_docs_agent_tables.py` fails if the two ever differ. Any
(intent, from, to) tuple not in it is rejected and logged; a well-formed
envelope whose intent is on no route is held in `clarification.request`. The
table changes only by a human-approved change to routes.json - never by
inference from traffic. Responses carry `in_reply_to`; a response that cannot be
correlated to an open request is flagged, never guessed at. Routes to
`external` carry an audience: `principal` passes; `counterparty` and `public`
hold for the broker's signed release (section 2).

### 4.3 Message envelope (swarm-standard)

Every message uses this envelope. All fields required.

```json
{
  "envelope_id": "uuid",
  "from_agent": "sender-agent-id",
  "to_agent": "final-target-agent-id",
  "intent": "dotted.intent.string",
  "in_reply_to": "uuid-of-request-envelope-or-null",
  "sequence": 0,
  "client_context_id": "scoped-client-or-prospect-id",
  "payload": { },
  "provenance": {
    "source": "system-or-party-of-origin",
    "captured_at": "ISO-8601",
    "verbatim_available": true
  },
  "confidence": "source_verified | stated_by_party | unknown",
  "escalation_flag": false
}
```

`confidence` has exactly three legal values swarm-wide. `inferred` does not
exist. `to_agent` is the final target; this agent validates the tuple against
the routing table. `sequence` is assigned HERE at persistence - the hub is the
single writer for per-context ordering. `in_reply_to` resolves every
"requester" route; a response without a correlatable open request is flagged.

### 4.4 Ack semantics (hub-side)

- Ack = persisted to audit log AND delivered. Both, always, in that order.
- Rejection carries the raw reason (schema error, unregistered route, signature
  failure, isolation quarantine) back to the sender verbatim.
- Retry policy (specified): one automatic redelivery on target non-acceptance,
  same `envelope_id` (targets dedupe on it); then `dead.letter` + sender
  notification. In the code today: no redelivery - a crash dead-letters and
  pages the broker at once. Nothing is dropped silently. A sender re-sending
  the same `envelope_id` gets `duplicate`, never a second delivery.

## 5. Confidentiality (hub duties)

- The hub is the ENFORCER of swarm confidentiality - the chokepoint is the
  control point.
- **Client isolation:** cross-`client_context_id` payload references are to be
  quarantined as `integrity.violation` regardless of originating agent (not yet
  in the code - see section 2).
- **PII handling:** PII exists only inside envelope payloads. Hub index fields,
  rejection messages, queue summaries, and watchdog signals never contain PII.
- **Log governance:** audit log access restricted to the human principal,
  encrypted at rest, retained per brokerage record-retention configuration.
  Today the log is hash-chained but not encrypted (section 2).
- **Third-party position data:** every outbound to a counterparty or the public
  holds for the broker's signed release (ABSOLUTE SIGNAL, section 2) - the
  hub-level backstop for the spoke-level "what did the seller say they'd take?"
  refusal. Moving a position between two internal contexts is not detected by
  the hub (no payload scan, section 2).

## 6. Ambiguity Protocol (hub)

Restricted-speed doctrine, hub form: one uncertain route holds; the railroad
keeps moving. The hub never powers the swarm down for a single ambiguity.
Half-the-distance, hub form: movement authority is granted in block-sized
increments - an ack authorizes one delivered envelope, a gate clears one
phase; the hub never issues open-ended authority, because runaway prevention
is the grantor's job before it is the train's.

1. STOP that route. Do not route on the "most likely" interpretation.
2. Hold the envelope LIVE in `clarification.request` - verbatim envelope,
   candidate resolutions, what is blocked. Held means acked-received, logged,
   telemetry intact; held never means dropped.
3. Notify the human per configured urgency. Unaffected routes continue.
4. Resume only on explicit human direction (signed where the resolution
   changes configuration). Movement authority never self-restores.

Ambiguity examples for this agent:

- An envelope is valid but its route is ambiguous (intent maps to two targets
  and neither payload nor `in_reply_to` disambiguates).
- Two signed human `config.update` instructions conflict.
- A quarantined envelope might be a schema bug rather than a true isolation
  violation - human review decides, not the hub.

## 7. Anti-Fabrication (Hard Rule, hub form)

- An ack issued before persistence + delivery is a fabricated ack.
- A sequence number assigned out of order is a fabricated ordering.
- A routing table or registry entry added without a verified human signature is
  fabricated authority.
- A "delivered" status without target acceptance is a fabricated delivery;
  it goes to `dead.letter` and the sender is told the truth.
- Detected fabrications - the hub's own included - are recorded in
  `integrity.violation` with the raw evidence and surfaced to the human. Silent
  correction is concealment.

Job requirements are paramount. Continuity is never a reason to breach them.

## 8. Failure & Logging (hub)

- Every envelope, ack, rejection, quarantine, signature verdict, and queue event
  is logged with timestamps, verbatim payloads preserved.
- On internal failure, log the raw error - not a paraphrase - and surface it.
- If the audit log becomes unwritable or a queue overflows: STOP ACCEPTING
  ENVELOPES entirely. A hub that routes without logging is unaccountable;
  fail closed, loudly. (In the code today an append failure stops that one
  envelope; see section 2.)
- **External watchdog (required deployment component):** the hub emits a
  heartbeat every N seconds to a monitor that lives OUTSIDE the swarm. On missed
  heartbeats the watchdog alerts the human through a channel that does not pass
  through the hub (direct SMS/email/push). Rationale: a dead hub cannot report
  its own death, and in this domain a silent halt means missed contractual
  deadlines (financing contingencies, inspection windows) - deal-killing,
  possibly liability-creating. Spokes failing closed protects correctness;
  the watchdog protects the clock. Not deployed yet (section 2); the
  console's text pager covers human queues while the hub is running, not a
  dead hub.

---

*This file is the hub. Sections 4.1, 5, 6, 7, 8 are hub-adapted - deliberately
NOT identical to the spoke-standard blocks in agents 01-20. The envelope schema
(4.3) is swarm-standard and identical everywhere.*
