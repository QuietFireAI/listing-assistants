# ListingAssistants - Broker's Manual

This manual is for the licensed broker or agent the swarm works for. It
covers what the agents do for you each day, where your decisions come in,
and how to read what the system tells you. Every behavior described here has
a test in `tests_listing/`; where a feature is not wired yet, this manual
says so.

> **Fiduciary notice.** Price, terms, and every movement of money stay with the
> licensed broker and the client. ListingAssistants coordinates the work around
> those decisions. Its default build contains no payment, transfer, or wire
> capability, and any disclosure of a client's position to the other side waits
> for the broker's signed release. Details: [FINANCIAL_CAPABILITY.md](FINANCIAL_CAPABILITY.md).

---

## 1. Your operations team

Twenty agents each own one job, and one dispatcher hub carries every message
between them. No agent talks to another directly, and no agent can use a
route that is not on the closed track in `identity/routes.json`.

| Area | Agents |
|---|---|
| Leads | 01 Lead Capture, 02 Lead Qualification, 03 Lead Nurture, 19 Prospecting |
| Listing | 04 Listing Description, 05 MLS & Listing Management, 10 Market Data, 12 Marketing Campaign |
| Buyers & showings | 06 Showing Scheduler, 13 Buyer Search & Match |
| Transaction | 07 Transaction Coordinator, 08 Document Collection, 09 Vendor Coordination |
| Clients & records | 11 Client Communication, 14 CRM & Pipeline, 15 Financial Tracking, 16 After-Close & Referral |
| Oversight | 17 Compliance & Fair Housing, 18 Calendar & Task Management, 20 Social Media Monitoring |

The agents are rule engines, not chat models. Each one follows its ratified
SKILL.md and its decision tuples (`DECISIONS.md`): a list of the crossings it
can meet and what it does at each. When something comes up that no tuple
covers, the agent stops and puts it in front of you with the facts.

One role per agent: [JOB_DESCRIPTIONS.md](JOB_DESCRIPTIONS.md).

## 2. What stays yours

You decide:

- **Price.** The list price arrives on your signed listing authorization. No
  agent creates or changes it. A client question about price, offers or
  strategy goes to your legal-line queue with the client's own words; the
  client receives only a short acknowledgment.
- **Anything about wiring money.** A client message that mentions wire
  instructions, wiring details, a wire transfer or a routing number goes to
  your legal-line queue before anything else happens. The agents send no wire
  or account details on any channel.
- **Fair housing calls.** Agent 17 screens listing copy and outbound content
  against your ratified ruleset. A flagged draft stops the marketing path;
  Agent 17 never rewrites the copy. You or your copywriter fix it.
- **What reaches the other side.** A message to a counterparty or the public
  (a vendor, a buyer's agent, an ad network) is held until you sign a
  release for that specific message.
- **Representation agreements.** Agent 13 requires a buyer agreement on file
  before it requests a showing; without one, the request comes back to the
  buyer workflow instead of going to the showing scheduler.

## 3. Your queues

Everything that needs a human lands in a named queue. The hub can text you
when something lands (the SMS notifier uses Twilio; it needs your account
credentials before it can send).

| Queue | What lands there |
|---|---|
| `escalation.legal_line` | price, strategy, legal and wire questions; highest priority |
| `escalation.hot_lead` | a lead scored HOT that needs a human inside the speed-to-lead window (5 minutes by default) |
| `escalation.complaint` | an angry or negative client message, verbatim |
| `clarification.request` | anything an agent cannot finish on its own: a missing fact, an unknown route, a held outbound message, a failed handoff |
| `integrity.violation` | an unsigned or tampered authority message; never auto-resolved |
| `dead.letter` | a message no agent could take; the hub raises a system-error escalation when an agent crashed |

## 4. A day with the system

**Morning.** Agent 18 builds the morning briefing: calendar items by day,
what each agent is waiting on, unresolved human decisions, and deadline
conflicts it is tracking. The daily clock (`tools/run_sweeps.py`, or the
sweep call in your long-running process) fires the time-based checks:
contract deadlines, document chases, vendor no-shows, follow-up timers.

**A new listing (P01).** You sign the listing package. Agent 05 requests
photography from Agent 09, which books from your approved vendor roster
(the booking holds for your release because it leaves for a vendor). When
the photos arrive, Agent 04 drafts remarks from the property data only;
Agent 17 reviews them. On approval, Agent 05 confirms the MLS entry is
actually live before Agent 12 may market it, and the campaign itself holds
for your release. Agent 11 keeps the seller informed at each step.

**A buyer lead (P11).** Agent 01 captures the lead with consent on first
touch, Agent 14 checks for an existing record, and Agent 02 scores it with
your rubric. A pre-approval document outranks a different stated budget;
an expired or unverified letter does not count. A HOT lead goes to your hot
lead queue. A score sitting exactly on a tier boundary takes the lower tier
and is flagged for you.

**Under contract (P09).** Agent 07 tracks every contract deadline and
counts a milestone done only when its artifact is on file. Agent 08 chases
missing documents on a set cadence and comes to you after the chase limit.
Agent 07 makes no comment on inspection findings and offers no concessions.

**End of day (P17).** Agent 15 assembles the day's figures with their
sources attached; any amount that does not reconcile to $0.00 comes to you.

## 5. When something goes wrong

- **An upset client (P14).** Agent 11 places that client on an outbound hold,
  so no scheduled touch goes out, sends a neutral acknowledgment, and puts
  the message verbatim in your complaint queue.
- **A template with a missing fact.** If a client message would go out with
  a blank (an unknown closing date, say), Agent 11 does not send it and asks
  you for the fact.
- **Quiet hours.** Client messages that would land between 21:00 and 08:00
  wait for the next window and notify you instead, unless the alert class is
  marked exempt in configuration.
- **Opt-outs.** "Stop" stops every channel at once, and Agent 14 records it.
  When consent flags disagree across channels, the most restrictive one wins.
- **A handoff that fails.** If the hub rejects or cannot deliver a message
  one agent sent another, the sending agent records `handoff.failed` and the
  message lands in your clarification queue.

## 6. Signing and releasing

Your signing key is created once with `python tools/console.py init` and
stays on your machine. Signed actions today:

- **Listing authorization and configuration** (rubric, ruleset, vendor
  roster, templates): through a console session script
  (`python tools/console.py session <file>`; format in the script's help
  text) or the MCP server's `identity.authority` tool.
- **Releasing a held outbound message:** a signed `disclosure.authority`
  naming that message, applied with `Hub.release_disclosure` by the process
  that holds the swarm. The console does not have a release command yet.
- **Checking the record:** `python tools/console.py verify` walks the audit
  chain and reports the first broken line, if any.

## 7. Optional modules

The repository includes modules that are tested on their own and are not
yet wired into the agents: per-client drawers (`dispatcher/client_drawer.py`),
signed pause-and-resume for human decisions (`dispatcher/hitl_protocol.py`),
a local SQLite store, an offline update-pack verifier, an optional JEV
decision adapter, an optional seam for a local Hermes-family model, and a
model checkpoint manifest. The README lists what each one does. Until a
deployment wires one in, your day runs exactly as described above.

## 8. Good habits

1. Read the morning briefing first; it shows what is waiting on whom.
2. Keep your vendor roster's license and insurance dates current; Agent 09
   books only vendors whose credentials are on file and current.
3. Ratify your configuration files (rubric, templates, cadences, signers).
   Drafts are not loaded.
4. Treat a hold as information. It names what stopped and why.
5. Run `python tools/console.py verify` when you want proof the record is
   intact.

---

ListingAssistants is a workflow system for licensed real estate
professionals. It does not practice real estate, give legal advice, or
appraise property. The broker of record keeps responsibility for every
client representation, contract and disclosure.
