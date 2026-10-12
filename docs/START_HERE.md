# START HERE — The 60-Second Version

<!-- diagram:team-start - drawn in tools/doc_diagrams.py; edit it there, not here -->
```mermaid
flowchart TB
    B(["You - the broker<br/>sign, decide, release"])
    H{{"00 Dispatcher hub<br/>carries and logs every message"}}
    B -- "signed listings, settings, releases, decisions" --> H
    H -- "questions, holds, alerts, reports" --> B
    subgraph LEADS["Leads"]
        A01["01 Lead Capture"]
        A02["02 Lead Qualification"]
        A03["03 Lead Nurture"]
        A19["19 Prospecting"]
    end
    subgraph LISTING["Listing"]
        A04["04 Listing Description"]
        A05["05 MLS and Listing"]
        A10["10 Market Data"]
        A12["12 Marketing Campaign"]
    end
    subgraph BUYERS["Buyers and showings"]
        A06["06 Showing Scheduler"]
        A13["13 Buyer Search and Match"]
    end
    subgraph DEAL["Transaction"]
        A07["07 Transaction Coordinator"]
        A08["08 Document Collection"]
        A09["09 Vendor Coordination"]
    end
    subgraph RECORDS["Clients and records"]
        A11["11 Client Communication"]
        A14["14 CRM and Pipeline"]
        A15["15 Financial Tracking"]
        A16["16 After-Close and Referral"]
    end
    subgraph OVERSIGHT["Oversight"]
        A17["17 Compliance and Fair Housing"]
        A18["18 Calendar and Tasks"]
        A20["20 Social Media Monitoring"]
    end
    H <--> LEADS
    H <--> LISTING
    H <--> BUYERS
    H <--> DEAL
    H <--> RECORDS
    H <--> OVERSIGHT
    X[/"Outside world<br/>clients, vendors, platforms"/]
    H <-- "in: inquiries, replies, deliveries<br/>out to your client: sent, with consent on record<br/>out to vendors and the public: held for your release" --> X
    classDef you fill:#f2cc60,stroke:#9a6700,color:#1f2328
    classDef hub fill:#1f6feb,stroke:#1f6feb,color:#ffffff
    classDef out fill:#d0d7de,stroke:#57606a,color:#1f2328
    class B you
    class H hub
    class X out
```

*No agent talks to another directly: every arrow goes through the hub, and only on lanes listed in `identity/routes.json`. Each agent's own picture is in its folder (for example [05-mls-listing-management](../05-mls-listing-management/README.md)).*
<!-- /diagram:team-start -->

**What this is.** Twenty specialized agents, coordinated by one dispatcher hub, that run the coordination
layer of a residential listing business — lead intake, listing
go-to-market, transaction deadlines, document chasing, showing
logistics, client updates, follow-up, and the books — under one
dispatcher, on one auditable track. You keep every decision that makes
you a fiduciary: prices, offers, negotiations, legal calls, and every
word that goes out under your name past a hold.

**Name.** ListingAssistants ([ListingAssistants.com](https://ListingAssistants.com)),
formerly `listing-agents`. The agents are deterministic rule engines: the
same input always produces the same, testable result.

**What makes it different, in one sentence.** Nothing here trusts a
claim: listings are live-*verified* not push-logged, milestones need
their artifact on file, every client-facing word passes a Fair Housing
screen, every authority action needs your cryptographic signature, and
when something can't complete it stops with a named reason on your
queue instead of failing quietly.

**What you need.** A machine that can run Python, your MLS/CRM/email
adapter credentials when you're ready to connect them, and about ten
minutes:

```bash
git clone https://github.com/QuietFireAI/listing-assistants.git
cd listing-assistants
pip install -r requirements.txt
python -m pytest tests_listing/     # watch all 24 playbooks prove themselves (988 passed)
```

That last command isn't a formality — it executes every playbook,
end to end, against the same hub that runs in production, and it's the
same check our CI runs on every change.

**What day one looks like.** You configure what only you can: your
lead-scoring rubric (the thresholds are yours, signed, versioned),
your approved vendor roster with credential dates, your compliance
ruleset, your nurture sequences, your message templates, your cadences.
Then a daily scheduler
invokes the clock layer (`tools/run_sweeps.py` — one cron line), and
the swarm starts doing what the docs describe. Until your external
adapters are connected, outbound actions (MLS writes, client sends,
ad publishes) queue visibly rather than pretending — the system tells
you what's dark.

**Test it yourself on camera.** `docs/OPERATOR_TESTING_MANUAL.md` walks
ten ready-made scenes (`scenes/`), each with the exact output to expect;
the suite runs the same ten files on every build.

**Where to read next, in order:**
1. `docs/AGENT_USER_MANUAL.md` — your day with ListingAssistants, as a broker
2. `docs/OPERATOR_TUNING_GUIDE.md` — setup, storage, offline updates, and the optional modules
3. `docs/WHAT_SUCCESS_MEANS.md` — what each playbook delivers and what it takes off your plate
4. `docs/PLAY-BY-PLAY.md` — the step-by-step narration of what actually moves between agents
5. `docs/JOB_DESCRIPTIONS.md` — every agent's role and rules
6. `docs/PLAYBOOKS.md` — all 24 playbooks: triggers, agents, gates
7. `docs/TUNING_MANUAL.md` — every number you can turn, and its default

**The four guarantees, which every document above keeps repeating
because they're the product:** completion is verified, never claimed;
the audit trail sits under every deliverable; your judgment is
protected by structure, not politeness; and failures get names and
queues, never silence.
