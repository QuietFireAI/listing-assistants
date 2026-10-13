"""Hand-drawn diagrams for the docs, kept here so tools/gen_diagrams.py can
place them and tests_listing/test_docs_diagrams.py can check they are in
place. Each one draws something the page already says in words, and each
names the code or test it was checked against (2026-10-12).

Edit a picture here, then run: python tools/gen_diagrams.py
"""

YOU = "classDef you fill:#f2cc60,stroke:#9a6700,color:#1f2328"
STOP = "classDef stop fill:#ffd8d3,stroke:#cf222e,color:#1f2328"
OK = "classDef ok fill:#dafbe1,stroke:#1a7f37,color:#1f2328"
HUBC = "classDef hub fill:#1f6feb,stroke:#1f6feb,color:#ffffff"
OUTC = "classDef out fill:#d0d7de,stroke:#57606a,color:#1f2328"

# Agent 00 is the hub: it has no lanes of its own, every message passes
# through it. Its picture is the order of checks in Hub.send()
# (dispatcher/hub.py, steps 0-7), in plain words.
HUB_FLOW = """```mermaid
flowchart TD
    M["A message arrives at the hub"] --> D{"Seen this exact<br/>message before?"}
    D -- yes --> DUP["Not delivered twice"]
    D -- no --> L{"Same topic going<br/>round in a loop?"}
    L -- yes --> SUS["Paused - you are asked"]
    L -- no --> S{"Properly formed?"}
    S -- no --> R1["Refused"]
    S -- yes --> A{"Needs your signature?"}
    A -- "yes, and it is missing or wrong" --> R2["Refused and reported to you"]
    A -- "no, or signed" --> T{"On the closed track?"}
    T -- "wrong sender or receiver" --> R3["Refused"]
    T -- "a kind of message no lane knows" --> H1["Held - you are asked"]
    T -- yes --> O{"Leaving the swarm for<br/>someone other than your client?"}
    O -- yes --> H2["Held until you sign the release"]
    O -- no --> P["Written to the tamper-evident log"]
    H2 -. "you sign" .-> P
    P --> C{"Final self-check<br/>(when installed) passes?"}
    C -- no --> H3["Held - you are asked"]
    C -- yes --> DL{"Delivered?"}
    DL -- no --> DEAD["Recorded as undeliverable -<br/>the sending agent tells you"]
    DL -- yes --> ACK["Only now: confirmed done"]
    classDef you fill:#f2cc60,stroke:#9a6700,color:#1f2328
    classDef stop fill:#ffd8d3,stroke:#cf222e,color:#1f2328
    classDef ok fill:#dafbe1,stroke:#1a7f37,color:#1f2328
    class SUS,H1,H2,H3 you
    class R1,R2,R3,DUP,DEAD stop
    class ACK ok
```"""

# The six areas as the README and the broker's manual list them. Drawn
# narrow on purpose (2026-10-13, owner: "can it be easier to read?"): one
# row of twenty agents made GitHub shrink the picture until no word was
# readable. Each group is one card listing its agents; the six cards sit in
# two rows of three (the ~~~ links are invisible and only set the rows); one
# two-way arrow joins the hub to the team: no agent talks to another
# directly, every message goes through the hub.
TEAM = f"""```mermaid
flowchart TB
    B(["You - the broker<br/>sign, decide, release"])
    H{{{{"00 Dispatcher hub<br/>carries and logs every message"}}}}
    X[/"Outside world<br/>clients, vendors, platforms"/]
    B -- "signed listings, settings,<br/>releases, decisions" --> H
    H -- "questions, holds,<br/>alerts, reports" --> B
    H <-- "in: inquiries, replies, deliveries<br/>out to your client: with consent on record<br/>out to vendors and the public: held for your release" --> X
    subgraph TEAMBOX["Your twenty agents - each one talks only through the hub"]
        direction TB
        LEADS["<b>Leads</b><br/>01 Lead Capture<br/>02 Lead Qualification<br/>03 Lead Nurture<br/>19 Prospecting"]
        LISTING["<b>Listing</b><br/>04 Listing Description<br/>05 MLS and Listing<br/>10 Market Data<br/>12 Marketing Campaign"]
        BUYERS["<b>Buyers and showings</b><br/>06 Showing Scheduler<br/>13 Buyer Search and Match"]
        DEAL["<b>Transaction</b><br/>07 Transaction Coordinator<br/>08 Document Collection<br/>09 Vendor Coordination"]
        RECORDS["<b>Clients and records</b><br/>11 Client Communication<br/>14 CRM and Pipeline<br/>15 Financial Tracking<br/>16 After-Close and Referral"]
        OVERSIGHT["<b>Oversight</b><br/>17 Compliance and Fair Housing<br/>18 Calendar and Tasks<br/>20 Social Media Monitoring"]
        LEADS ~~~ DEAL
        LISTING ~~~ RECORDS
        BUYERS ~~~ OVERSIGHT
    end
    H <--> TEAMBOX
    classDef grp fill:#ffffff,stroke:#8c959f,color:#1f2328,text-align:left
    {YOU}
    {HUBC}
    {OUTC}
    class B you
    class H hub
    class X out
    class LEADS,LISTING,BUYERS,DEAL,RECORDS,OVERSIGHT grp
```"""

TEAM_CAPTION = ("*No agent talks to another directly: every arrow goes through the "
                "hub, and only on lanes listed in `identity/routes.json`. Each "
                "agent's own picture is in its folder (for example "
                "[05-mls-listing-management](../05-mls-listing-management/README.md)).*")

# Where each playbook sits; groups as docs/PLAY-BY-PLAY.md orders them.
PLAYBOOK_MAP = f"""```mermaid
flowchart TB
    subgraph SELL["The listing"]
        direction LR
        P15["P15 CMA and listing<br/>appointment prep"] --> P01["P01 New listing<br/>onboarding"]
        P01 --> ACTIVE(("Listing<br/>active"))
        ACTIVE --> P02["P02 Price<br/>adjustment"]
        ACTIVE --> P04["P04 Open house"]
        ACTIVE --> P18["P18 Seller<br/>weekly report"]
        P23["P23 Price review<br/>evidence"] --> P02
        ACTIVE --> P08["P08 Offer to<br/>acceptance"]
        ACTIVE --> P05["P05 Expired or<br/>withdrawn"]
        P08 --> P03["P03 Under-contract<br/>transition"]
        P03 --> P09["P09 Contract<br/>to close"]
        P09 --> P10["P10 Close and<br/>handoff"]
    end
    subgraph BUY["The buyer"]
        direction LR
        P06["P06 New buyer<br/>onboarding"] --> P07["P07 Tour day"]
        P07 --> P22["P22 Feedback and<br/>match refresh"]
        P22 --> P07
    end
    subgraph LEAD["Leads"]
        direction LR
        P11["P11 Speed<br/>to lead"] --> P21["P21 Lead<br/>re-score"]
        P12["P12 Farm<br/>campaign"]
        P24["P24 Prospecting<br/>outreach"]
        P13["P13 Referral and<br/>anniversary"]
    end
    subgraph OPS["Every day"]
        direction LR
        P16["P16 Morning<br/>operations"]
        P17["P17 End-of-day<br/>books"]
        P19["P19 Property<br/>access custody"]
        P20["P20 Vacant<br/>property watch"]
        P14["P14 Complaint<br/>response"]
    end
    P11 -- "a buyer signs an agreement" --> P06
    P22 -. "an offer" .-> P08
    P10 --> P13
    P13 -- "a referral becomes a lead" --> P11
```"""

PLAYBOOK_MAP_CAPTION = ("*Arrows show what usually leads to what; any playbook can "
                        "also start on its own trigger (listed in "
                        "[PLAYBOOKS.md](PLAYBOOKS.md)). The \"Every day\" group "
                        "runs alongside all of it.*")

HOLD_AND_RELEASE = f"""```mermaid
sequenceDiagram
    autonumber
    participant A as An agent (09 Vendors, 12 Marketing)
    participant H as Hub
    actor B as You (broker)
    participant X as Vendor or public
    A->>H: message for a vendor or the public
    H->>H: who is on the far end? not your client
    H-->>B: held - in your clarification queue, with why it stopped
    Note over H,X: nothing has left
    B->>H: console "release" - signs one disclosure.authority for that message
    H->>H: checks your signature (and login + MFA, once a signer registry is armed)
    H->>X: sends that one message, once - written to the audit log
    B->>H: the same release again
    H-->>B: refused - a release is used up
```"""

HOLD_CAPTION = ("*Checked against `Hub.release_disclosure` in `dispatcher/hub.py` "
                "and `tests/test_absolute_signal.py` in dispatcher-agents. A message "
                "to your own client (Agent 11) is not held.*")

AUDIENCE = f"""```mermaid
flowchart LR
    M["An outbound message"] --> W{{"Who is on<br/>the far end?"}}
    W -- "your client (principal)" --> S["Sent"]
    W -- "the other side (counterparty):<br/>a vendor, a buyer's agent" --> H1["Held for your<br/>signed release"]
    W -- "the public:<br/>an ad, a feed" --> H2["Held for your<br/>signed release"]
    W -- "not labelled" --> H3["Held - the default<br/>is the guarded one"]
    {YOU}
    {OK}
    class H1,H2,H3 you
    class S ok
```"""

AUDIENCE_CAPTION = ("*In this repository: `client.message.send` is principal, "
                    "`vendor.schedule` counterparty, `campaign.publish` public "
                    "(`identity/routes.json`). The gate reads the label, not the words.*")

TWO_LOCKS = f"""```mermaid
flowchart LR
    A["An action that<br/>moves money"] --> L1{{"Lock 1 - the build:<br/>is the capability installed?"}}
    L1 -- "no (the default build)" --> N1["Nothing to unlock"]
    L1 -- "yes - a different, signed build,<br/>installed on purpose by a person" --> L2{{"Lock 2 - the key:<br/>your signed authorization<br/>for this action, now?"}}
    L2 -- no --> N2["Nothing moves"]
    L2 -- yes --> Y["Runs once,<br/>on the audit log"]
    {STOP}
    {OK}
    class N1,N2 stop
    class Y ok
```"""

TWO_LOCKS_CAPTION = ("*The default build stops at Lock 1: it contains no payment, "
                     "transfer or wire code.*")

QUEUES = f"""```mermaid
flowchart LR
    AG["Any agent"] --> H{{{{"Hub"}}}}
    H --> Q1["escalation.legal_line<br/>price, strategy, legal, wire"]
    H --> Q2["escalation.hot_lead"]
    H --> Q3["escalation.complaint"]
    H --> Q4["clarification.request<br/>a missing fact, a hold, a failed handoff"]
    H --> Q5["integrity.violation<br/>unsigned or tampered"]
    H --> Q6["dead.letter"]
    H --> Q7["decision_required<br/>a paused thread"]
    Q1 & Q2 & Q3 & Q4 & Q5 & Q6 & Q7 --> C["Your console"]
    C -. "optional text: queue and client id,<br/>never the client's words" .-> P(["Your phone"])
    {YOU}
    {HUBC}
    class C,P you
    class H hub
```"""

DAY = f"""```mermaid
flowchart LR
    subgraph MORNING["Morning"]
        CLK["Daily clock<br/>deadlines, chases, no-shows, timers"] --> BR["18 morning briefing<br/>what waits on whom"]
    end
    subgraph DAYTIME["During the day"]
        L["New listing - P01"]
        LD["New lead - P11"]
        UC["Under contract - P09"]
    end
    subgraph EVENING["End of day"]
        BK["15 books the day<br/>off by any amount? it comes to you"]
    end
    MORNING --> DAYTIME --> EVENING
    BR -. "you read it first" .-> Y(["You"])
    DAYTIME -. "holds and questions" .-> Y
    BK -. "anything that is not $0.00" .-> Y
    {YOU}
    class Y you
```"""

SIGNING = f"""```mermaid
flowchart TB
    K["console.py init<br/>your key, made once, stays on your machine"] --> O["console.py onboard<br/>your name and login"]
    O --> S["console.py session your-file<br/>each action signed with your key"]
    S --> A1["authorize / config<br/>listings and settings"]
    S --> A2["release<br/>one held outbound message"]
    S --> A3["decide continue or cancel<br/>one paused thread"]
    A1 & A2 & A3 --> H{{{{"Hub checks the signature"}}}}
    H -- valid --> G["Done, on the audit log"]
    H -- "missing or wrong" --> R["Refused and logged<br/>as an integrity violation"]
    V["console.py verify"] -. "walks the whole log,<br/>names the first broken line" .-> G
    {OK}
    {STOP}
    {HUBC}
    class G ok
    class R stop
    class H hub
```"""

RUNNING_ORDER = """```mermaid
flowchart LR
    S0["0 Setup<br/>key, name, config"] --> S1["1 Signature"] --> S2["2 Configure"] --> S3["3 Speed to lead"]
    S3 --> S4["4 New listing"] --> S5["5 Compliance"] --> S6["6 Photos vs data"]
    S6 --> S7["7 Contract to close"] --> S8["8 Showing bump"] --> S9["9 Complaint"]
    S9 --> S10["10 Books"] --> V["verify<br/>the whole log"]
```"""

RUNNING_ORDER_CAPTION = ("*One console session per scene, in this order, in the same "
                         "folder: each scene builds on the state the last one saved.*")

BUILT = f"""```mermaid
flowchart TB
    subgraph CORE["dispatcher-agents core - vendored, byte-identical (tools/sync_core.py --check)"]
        HUB["hub.py - checks, logs, delivers"]
        LOG[("hash-chained audit log")]
        HUB --> LOG
    end
    subgraph IDENTITY["This repository"]
        R["identity/routes.json<br/>the closed track"]
        SP["listing_spokes*.py<br/>20 rule-engine agents"]
        HG["handoff_guard.py<br/>a failed handoff comes to you"]
        SW["swarm.py<br/>one builder"]
    end
    R --> HUB
    SW --> HUB
    SW --> SP
    SP --> HG --> HUB
    ST[("swarm-state.sqlite<br/>restored only if the log vouches for it")]
    SW <--> ST
    C["console.py"] --> SW
    CL["run_sweeps.py - daily clock"] --> SW
    {HUBC}
    class HUB hub
```"""

CONFIG_FLOW = f"""```mermaid
flowchart LR
    T["config file ships<br/>as a draft"] --> E["you edit it to<br/>your business"]
    E --> RAT["_status: RATIFIED<br/>with a date and your name"]
    RAT --> LD["loaded - config.load<br/>on the audit log"]
    T -. "still a draft" .-> SK["skipped and named<br/>on the audit log"]
    SET["a signed setting<br/>(console config)"] --> AG{{"key the agent<br/>knows?"}}
    AG -- yes --> AP["applied"]
    AG -- no --> HO["held for you,<br/>nothing changes"]
    {OK}
    {YOU}
    class LD,AP ok
    class SK,HO you
```"""

HITL = f"""```mermaid
sequenceDiagram
    participant A as Agent 01, 02, 11 or 20
    participant M as HITL manager (hub.hitl)
    participant D as Client drawer
    actor B as You (broker)
    A->>M: pause this thread, with the facts
    M->>D: record the hold
    M-->>B: decision_required - shows in "show waits"
    B->>M: console "decide" - signed continue or cancel
    M->>M: signature checked, same client, not used before
    M->>A: carry on as decided
```"""

MCP = f"""```mermaid
flowchart LR
    HOST["Host app<br/>Hermes, OpenClaw, Claude Desktop"] -- "four tools only" --> T["identity.describe<br/>identity.submit<br/>identity.authority<br/>identity.audit"]
    T --> S["identity_mcp server<br/>refuses to start unless the track,<br/>the signature check and the log are intact"]
    S --> H{{{{"Hub"}}}}
    H --> AG["the 20 agents"]
    S -. "signs for the host only<br/>with --demo-signing" .-> H
    {HUBC}
    class H hub
```"""

MCP_CAPTION = ("*The host never routes inside the swarm; it pushes requests at the "
               "front door. There is no release tool: releasing a held message "
               "needs your own signature (see FINANCIAL_CAPABILITY.md).*")

INSTALL = """```mermaid
flowchart LR
    P["Install Python"] --> G["git clone<br/>or ZIP"] --> V["python -m venv venv<br/>activate it"]
    V --> R["pip install -r<br/>requirements.txt"] --> T["python -m pytest<br/>tests_listing/"]
    T --> D["python tools/run_demo.py<br/>the six acts"] --> F["python tools/dashboard.py --html"]
```"""

SECURITY = f"""```mermaid
flowchart TB
    M["Any message"] --> T{{"On the closed track?"}}
    T -- no --> RJ["Refused"]
    T -- yes --> S{{"Needs a signature?"}}
    S -- "yes, missing or tampered" --> IV["Refused, integrity violation"]
    S -- "no, or valid" --> O{{"Leaving for a counterparty<br/>or the public?"}}
    O -- yes --> HL["Held for the broker's signed release"]
    O -- no --> L[("Hash-chained audit log<br/>before delivery")]
    L --> DL["Delivered"]
    W["A client mentions a wire<br/>or routing number"] --> LL["Broker's legal-line queue"]
    {STOP}
    {YOU}
    {OK}
    class RJ,IV stop
    class HL,LL you
    class DL ok
```"""

TESTING_STORY = f"""```mermaid
flowchart LR
    A1["Act 1<br/>signed listing - vendor booking held"] --> A2["Act 2<br/>photos verified, copy reviewed"]
    A2 --> A3["Act 3<br/>steering phrase flagged, never marketed"]
    A3 --> A4["Act 4<br/>campaign held - you sign - published"]
    A4 --> A5["Act 5<br/>price question goes to a human"]
    A5 --> A6["Act 6<br/>the log verifies"]
    {YOU}
    class A4 you
```"""

ROADMAP = f"""```mermaid
flowchart LR
    subgraph DONE["Done"]
        D1["HITL holds"]
        D2["State survives a restart"]
        D3["Client drawers, plain log,<br/>JEV scoring, model drafting"]
        D4["P18-P21 on the daily clock"]
    end
    subgraph LEFT["Left"]
        L1["SQLite CRM, consent and ledger tables"]
        L2["Identity-provider signer binding"]
        L3["Host-signed actions over MCP"]
        L4["Outside providers: MLS, email, SMS"]
    end
    {OK}
    {YOU}
    class D1,D2,D3,D4 ok
    class L1,L2,L3,L4 you
```"""

SUCCESS = f"""```mermaid
flowchart LR
    S1["Signature"] --> S2["Photos, verified"] --> S3["Copy, reviewed"] --> S4["Go-live recorded -<br/>you confirm the MLS"]
    S4 --> S5["Marketing,<br/>released by you"] --> S6["Offer accepted"] --> S7["Deadlines met,<br/>each with its paper"]
    S7 --> S8["Closed"] --> S9["Referral and<br/>anniversary"]
```"""

# name -> (file, anchor line regex, mermaid, caption or None)
BLOCKS = {
    "team-readme": ("README.md", r"^\| Oversight \| 17 Compliance .*\|$", TEAM,
                    TEAM_CAPTION.replace("../", "")),
    "hub-readme": ("README.md", r"^## How it stays accountable$", HUB_FLOW,
                   "*What the hub does with every message, in order "
                   "(`dispatcher/hub.py`). The same picture, with each check "
                   "explained: [00-dispatcher](00-dispatcher/README.md).*"),
    "map-readme": ("README.md", r"^## The 24 playbooks$", PLAYBOOK_MAP,
                   PLAYBOOK_MAP_CAPTION.replace("(PLAYBOOKS.md)", "(docs/PLAYBOOKS.md)")),
    "team-start": ("docs/START_HERE.md", r"^# START HERE .*$", TEAM, TEAM_CAPTION),
    "team-manual": ("docs/AGENT_USER_MANUAL.md", r"^## 1\. Your operations team$", TEAM, TEAM_CAPTION),
    "queues-manual": ("docs/AGENT_USER_MANUAL.md", r"^## 3\. Your queues$", QUEUES, None),
    "day-manual": ("docs/AGENT_USER_MANUAL.md", r"^## 4\. A day with the system$", DAY, None),
    "signing-manual": ("docs/AGENT_USER_MANUAL.md", r"^## 6\. Signing and releasing$", SIGNING, None),
    "hitl-manual": ("docs/AGENT_USER_MANUAL.md", r"^## 5\. When something goes wrong$", HITL,
                    "*A paused thread: the same person under a new lead (01), a low-confidence score (02), a reply nobody owns (11), a social reply draft (20).*"),
    "team-jobs": ("docs/JOB_DESCRIPTIONS.md", r"^## Roster$", TEAM, TEAM_CAPTION),
    "locks-fin": ("docs/FINANCIAL_CAPABILITY.md", r"^## The two locks$", TWO_LOCKS, TWO_LOCKS_CAPTION),
    "audience-fin": ("docs/FINANCIAL_CAPABILITY.md", r"^## What \"held\" means for a disclosure$", AUDIENCE, AUDIENCE_CAPTION),
    "release-fin": ("docs/FINANCIAL_CAPABILITY.md", r"^## How to engage a held message \(the key, in practice\)$", HOLD_AND_RELEASE, HOLD_CAPTION),
    "mcp-mount": ("docs/MOUNTING.md", r"^## The four tools$", MCP, MCP_CAPTION),
    "order-testing": ("docs/OPERATOR_TESTING_MANUAL.md", r"^## Running order$", RUNNING_ORDER, RUNNING_ORDER_CAPTION),
    "built-tuning": ("docs/OPERATOR_TUNING_GUIDE.md", r"^## 1\. How the system is built$", BUILT, None),
    "config-tuning": ("docs/OPERATOR_TUNING_GUIDE.md", r"^## 3\. Ratify your configuration$", CONFIG_FLOW, None),
    "hitl-tuning": ("docs/OPERATOR_TUNING_GUIDE.md", r"^## 8\. Human decisions on paused work .*$", HITL, None),
    "map-playbooks": ("docs/PLAYBOOKS.md", r"^# PLAYBOOKS\.md - .*$", PLAYBOOK_MAP, PLAYBOOK_MAP_CAPTION),
    "map-pbp": ("docs/PLAY-BY-PLAY.md", r"^# PLAY-BY-PLAY\.md .*$", PLAYBOOK_MAP,
                PLAYBOOK_MAP_CAPTION + " *Each playbook below has its own picture: "
                "one recorded test run, numbered in order. The yellow notes are "
                "holds waiting for you.*"),
    "config-tunman": ("docs/TUNING_MANUAL.md", r"^## Config files \(separate from code .*$", CONFIG_FLOW, None),
    "audience-tunman": ("docs/TUNING_MANUAL.md", r"^## ABSOLUTE SIGNAL — disclosure gate \(added 2026-08-01\)$", AUDIENCE, AUDIENCE_CAPTION),
    "success": ("docs/WHAT_SUCCESS_MEANS.md", r"^## The listing, from signature to sold sign$", SUCCESS, None),
    "map-success": ("docs/WHAT_SUCCESS_MEANS.md", r"^## The question this document answers$", PLAYBOOK_MAP, PLAYBOOK_MAP_CAPTION),
    "roadmap": ("docs/ROADMAP.md", r"^# ListingAssistants Roadmap$", ROADMAP, None),
    "story-guide": ("OPERATOR_TESTING_GUIDE.md", r"^## 1\. The 90-second story \(the scripted demo\)$", TESTING_STORY, None),
    "install-quick": ("QUICKSTART_WINDOWS.md", r"^## 2\. Download & Install \(3 Commands\)$", INSTALL, None),
    "security": ("SECURITY.md", r"^## 1\. Security Architecture & Invariants$", SECURITY, None),
}
