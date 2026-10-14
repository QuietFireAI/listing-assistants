# Words used here

ListingAssistants is built by software people for real estate people, and
the documents use some words from the software side. This page explains
each one in plain language, with what it means in this system and where to
see it. Real estate words (MLS, CMA, FSBO, comps, contingency) are used as
you already use them.

The words are grouped by what they are about. Every word has its own link,
so other pages can point straight to it.

**The team:** [agent](#agent) · [swarm](#swarm) · [dispatcher and hub](#dispatcher-and-hub) · [identity](#identity) · [rule engine](#rule-engine) · [principal](#principal)

**How work moves:** [message](#message) · [intent](#intent) · [route and lane](#route-and-lane) · [closed track](#closed-track) · [client context](#client-context) · [hand-off](#hand-off) · [playbook](#playbook) · [trigger](#trigger) · [daily clock](#daily-clock) · [queue](#queue)

**Decisions made ahead of time:** [tuple](#tuple) · [stop and ask](#stop-and-ask) · [SKILL.md and DECISIONS.md](#skillmd-and-decisionsmd) · [MANNERS.md and SWARM.md](#mannersmd-and-swarmmd)

**Your authority:** [signing key](#signing-key) · [signature](#signature) · [signed authority message](#signed-authority-message) · [ratify](#ratify) · [signer registry](#signer-registry) · [hold](#hold) · [release](#release) · [don't send](#dont-send) · [paused thread](#paused-thread) · [HITL](#hitl) · [counterparty](#counterparty) · [disclosure](#disclosure) · [consent on record](#consent-on-record)

**The record:** [audit log](#audit-log) · [hash](#hash) · [hash-chained](#hash-chained) · [check the record](#check-the-record) · [record repair](#record-repair) · [readable log](#readable-log) · [client drawer](#client-drawer) · [saved state](#saved-state) · [integrity violation](#integrity-violation) · [dead letter](#dead-letter) · [confidence label](#confidence-label)

**Connections and optional engines:** [adapter](#adapter) · [JEV decision adapter](#jev-decision-adapter) · [model drafting](#model-drafting) · [MCP server](#mcp-server) · [pillars](#pillars) · [pager](#pager)

**Running and testing it:** [console](#console) · [Broker Desk](#broker-desk) · [showcase and scenes](#showcase-and-scenes) · [synthetic data](#synthetic-data) · [test and suite](#test-and-suite) · [end-to-end test](#end-to-end-test) · [mutation testing](#mutation-testing) · [CI](#ci) · [repository, clone and commit](#repository-clone-and-commit) · [vendored core](#vendored-core)

---

## The team

### Agent

One member of your digital operations team, with one job. There are twenty,
numbered 01 to 20 (01 Lead Capture, 05 MLS & Listing Management, 17
Compliance & Fair Housing, and so on). The documents sometimes call them
*spoke agents* or *spokes*, because they sit around the hub like spokes
around a wheel's hub. Each agent's job and limits are in
[JOB_DESCRIPTIONS.md](JOB_DESCRIPTIONS.md).

### Swarm

The whole team working together: the twenty agents plus the hub. "The swarm
saved its state" means the whole system did.

### Dispatcher and hub

Agent 00, the one piece every message passes through. Agents talk only to
the hub, and the hub delivers to the right agent, to you, or to the outside
world. On the way it checks the message, refuses anything off the closed
track, and writes it to the audit log. Think of a dispatcher in a railroad
tower: the trains only move where the dispatcher lines the switches. Its
checks, in order, are pictured in [00-dispatcher](../00-dispatcher/README.md).

### Identity

The real estate version of a general-purpose system. The hub, the record and
the signature checks come from a separate project,
[dispatcher-agents](https://github.com/QuietFireAI/dispatcher-agents), which
can run other kinds of businesses too. This repository supplies the real
estate part: the agents, their routes, their decisions and the playbooks.
"ListingAssistants is the residential real estate identity" means exactly
that.

### Rule engine

Each agent is a set of written rules in Python, the programming language it
is built in. Rules give the same answer to the same input every time
(*deterministic*), which is why every rule can have a test. The agents call
no AI language model. The one optional exception, model-written listing
remarks, is off unless you turn it on ([model drafting](#model-drafting)).

### Principal

The person the swarm works for: the licensed broker. The broker is the only
one who can sign.

## How work moves

### Message

One piece of work passed from one agent to another through the hub, such as
"here is the listing data" or "please book a photographer". In the code a
message is called an *envelope*: it says who sent it, who it is for, what
kind of message it is (its [intent](#intent)), which client it is about
([client context](#client-context)), the content, where the information came
from, and how sure the sender is of it ([confidence label](#confidence-label)).

### Intent

The kind of message, written as two or three words joined by dots:
`listing.data`, `vendor.request`, `content.review`, `campaign.publish`. The
intent decides which lanes the message may travel on. Plain-language words
for every intent appear in the agent pictures and the Broker Desk.

### Route and lane

A *route* is one kind of message and who may send and receive it: for
example, `lead.captured` may be sent by 01 or 16 and received by 02. Each
sender-intent-receiver combination is one *lane*. All routes are listed in
one file, `identity/routes.json`.

### Closed track

The rule that messages travel only on the routes in `identity/routes.json`.
Like a railroad, a train cannot leave the rails or lay new track: an agent
cannot invent a new kind of message or a new recipient. A message from the
wrong sender or to the wrong receiver is refused and logged. A properly
formed message that no lane knows is held for you to decide.

### Client context

Which client or file a message belongs to, given as a short id (in the
showcase, `S4` is one listing). The hub keeps each client's work separate,
and a text-message page carries the client context id rather than the
client's details.

### Hand-off

Any message one agent passes to another. Every hand-off goes through the
hub. When the hub refuses a hand-off or cannot deliver it, the sending agent
records `handoff.failed` on the audit log and the matter comes to you as a
question.

### Playbook

A standard piece of real estate work from start to finish, and which agents
do which part: P01 New Listing Onboarding, P08 Offer-to-Acceptance, P16
Morning Operations, and 22 more. Each playbook names what starts it, the
agents involved, and the points where it waits for you. Each one has a test
that runs it from end to end. All 24 are in [PLAYBOOKS.md](PLAYBOOKS.md),
and pictured message by message in [PLAY-BY-PLAY.md](PLAY-BY-PLAY.md).

### Trigger

The event that starts a playbook: a signed listing, a new inquiry, a date
on the calendar, a client reply.

### Daily clock

The once-a-day run that wakes every agent to do its scheduled checks:
deadlines coming due, leads to re-score, weekly seller reports, vacant
property checks. It sends each agent a `clock.tick` message, through the
hub like everything else. You start it with `python tools/run_sweeps.py`
(a computer's scheduler can run it every morning) or the Broker Desk's
**Run today's checks**. A *sweep* is one of those checks.

### Queue

A waiting list for something only you can handle. Each queue has a name the
Broker Desk shows: a question for you, a hot lead to call, a legal-line
question, an upset client, a message refused as unsigned or tampered, a
message that could not be delivered. The record says you were notified about
a queue item only when it was put on your screen or a text page to you went
through; when a page fails, it says nobody was reached, and the item waits on
its queue.

## Decisions made ahead of time

### Tuple

One decision made ahead of time, written as a pair: *(the situation, what
to do)*. For example, from Agent 05:
*(status change requested without signed listing.change.authorized, refuse;
verbal or email instruction is not authority)*. The documents call them
*predeliberated* because they were thought through before the system ever
ran. Each agent's tuples are in its `DECISIONS.md`. A tuple marked
*retired* stays in the file for the record and is no longer used.

### Stop and ask

The rule above every tuple: when no tuple fits the situation, or it takes
judgment to decide whether one fits, the agent stops and asks you (a
`clarification.request`, shown on the Broker Desk as "A question for you").
It never picks the nearest rule and carries on.

### SKILL.md and DECISIONS.md

The two rule files in every agent's folder. `SKILL.md` is the agent's job
description: what it does, what it may never do, and when it stops. 
`DECISIONS.md` holds its [tuples](#tuple). The `.md` ending means a plain
text file that GitHub shows as a formatted page.

### MANNERS.md and SWARM.md

Two files that apply to every agent. `MANNERS.md` sets how every agent
behaves in every situation: never do harm, always be truthful, never claim
done without checking, ask when unsure. Its rules are put back in front of
the agents at the three phase gates of a new listing (P01), at each signed
decision of yours the system accepts, and every 10 messages an agent
handles; the system will not start if the file changed since you
signed the install (`console.py attest`). `SWARM.md` holds the decisions that
apply to the whole team and the counts of agents, routes and playbooks.

## Your authority

### Signing key

A private file on your computer (`operator-key.bin`, created by
`python tools/console.py init`) that lets you sign. Only your computer
account can read it. Whoever holds the key can sign as you, so it stays on
your machine and in your backups only.

### Signature

A digital signature: a short code made from a message and your signing key.
Anyone can check that the code matches the message and your key, and any
change to the message after signing breaks the match. This system uses a
standard method called *Ed25519*. Signing on the Broker Desk takes two taps
(**Send**, then **Tap again to sign and send**).

### Signed authority message

A message that only you can authorize, and that the hub refuses unless your
signature checks out: a new listing or a listing change, a change to an
agent's settings, a release, a don't-send, and your continue or cancel on a
paused thread. The signature also covers the name of the person who signed.

### Ratify

To approve a draft so it takes effect. Settings files in `config/` ship as
proposed drafts; you ratify one by writing `RATIFIED`, the date and your
name in its status line. Until then, the agents that read that file keep
their built-in defaults. The agents' own rule files (`SKILL.md`,
`DECISIONS.md`) are already ratified; each `DECISIONS.md` gives the date in
its first line.

### Signer registry

The list of which person's login may sign which kinds of message
(`config/authority_signers.json`). It is meant to work with an *identity
provider* (*IdP*): the service your office logs in with, such as Google
Workspace or Microsoft, with *MFA* (multi-factor authentication: a second
proof, such as a code on your phone). No identity provider is connected in
this build, so today the hub checks the signature itself and notes on the
record that the login check is off.

### Hold

A message stopped at the hub until you decide. Anything leaving the swarm
for someone other than your client (a vendor, a buyer's agent, an ad
network, the public) holds for your signed release, whatever it says. A
message the hub cannot place, or that a final check flags, holds too. On the
Broker Desk, held messages are under **Needs you**.

### Release

Your signed permission for one held message to go out. On the Broker Desk
this is **Send**. One release lets one message out, and the record keeps
both.

### Don't send

Your signed decision that a held message never goes out, with your reason
if you give one. A signed don't-send can never be used as a send.

### Paused thread

A piece of work an agent cannot finish on its own: the same person arriving
as a new lead, a client reply that names no agent, a social reply draft.
The whole thread waits for your signed **Continue** or **Cancel**, and
nothing on that thread moves meanwhile.

### HITL

*Human in the loop*: the points where the system waits for a person. Here
the person is always you. The playbooks list their HITL gates; the
`hitl_protocol.py` module is the part that pauses and resumes threads.

### Counterparty

Someone on the other side of a deal or outside your client relationship:
the buyer's agent, a vendor, a platform. Messages to a counterparty always
hold for your release.

### Disclosure

Sharing a client's position (price thinking, terms, motivation) with
someone outside the relationship. A disclosure waits for your signed
release, every time.

### Consent on record

The client's yes or no to being contacted by text, call or email, recorded
at first contact. The agents that message clients (03, 11, 16) send
nothing to a client who has not said yes to at least one channel.

## The record

### Audit log

The running record of everything the swarm does: every message, every hold,
every signature, every refusal, in order, with the time. Also called the
*audit record*, the *audit chain* or simply *the record*. The Broker Desk's
**Today's work** counts come from it, and each number opens to the entries
behind it.

### Hash

A fingerprint of a piece of data: a fixed-length code computed from the
data, which changes completely if a single character changes. This system
uses the standard *SHA-256* method. The Broker Desk shows the first twelve
characters of an entry's fingerprint as its short code.

### Hash-chained

Each audit log entry includes the fingerprint of the entry before it, back
to a fixed starting point (the *genesis anchor*). Editing, deleting or
reordering any line breaks every link after it, so tampering shows. This is
what *tamper-evident* means here: changes cannot be hidden, and the check
names the first line that was changed.

### Check the record

Recomputing every link in the audit log to confirm nothing was changed
(`verify_chain()` in the code; **Check the record** on the Broker Desk;
`python tools/console.py verify` in the console). The answer is "intact" or
the line where the chain breaks, with the reason: a line that was changed,
deleted or moved, or a line that cannot be read at all. Nothing starts on a
record with an unreadable line - not the desk, a console session or the
daily clock; each one names the first line where the record breaks (which
may be an edited line before the unreadable one) and stops before writing
anything. The same holds while they run: before each write, the record
file's size and time are compared with what this program last wrote, and
if another program damaged, cut back, edited or replaced it in the
meantime, nothing more is written and the problem is named (a line, or
that entries this program wrote are gone). Programs on one record take turns
through a lock file next to it (`console-audit.jsonl.lock`), so two of
them never write at the same moment. An edit made to look untouched (same
size, same time) is not seen at that moment; **Check the record** still
finds it.

### Record repair

What you do when a write to the audit log was cut off part-way, for example
by a crash or a power cut: the last line is incomplete, and the desk,
console and daily clock refuse to start and say so. Stop anything using the
folder, then run `python tools/console.py repair-record`. It moves the
incomplete line to a side file next to the log (its name starts with the
log's name and contains `.torn-`), keeps every complete entry exactly as it
was, and adds an entry saying what it did, so the repair is on the record
too. It repairs only that case: if any earlier line is damaged or the chain
breaks, it refuses and changes nothing. `repair-record --check` only checks.
The repair cannot tell a crash from someone cutting the log back on
purpose; the anchor a console session prints at its end (entries and head
hash) is what shows whether earlier entries are gone.

### Readable log

The same audit log written out in plain sentences, one line per entry, in
`console-state/readable/stream.log` and in each client's drawer.

### Client drawer

One folder per client under `console-state/drawers/`, where agents file
that client's listing package, approved description, timeline, documents,
CRM entries and expenses. Every filing is on the audit log with its
fingerprint. The files are **not encrypted**, so keep the computer and its
backups secure.

### Saved state

Where the swarm keeps its working memory between runs (open listings, leads,
pending holds), in a single database file (*SQLite*, a common file-based
database). At start-up it is used only if the audit log vouches for that
exact save.

### Integrity violation

A message that should carry your signature and does not, or whose signature
does not match. It is refused and goes to the "Refused: unsigned or
tampered" queue.

### Dead letter

A message the hub accepted but could not deliver. It is recorded as
undeliverable, and the agent that sent it tells you.

### Confidence label

Every message says how sure the sender is of its facts, using one of three
labels: `source_verified` (checked against the source), `stated_by_party`
(someone said so) or `unknown`. A lead at first contact is never
`source_verified`.

## Connections and optional engines

### Adapter

The part that connects an agent to an outside service: email or text to
clients, a vendor's booking system, an ad network, the MLS. None are
connected in this build: outgoing work is recorded and waits visibly in a
queue until you connect a provider ([TUNING_MANUAL.md](TUNING_MANUAL.md)).

### JEV decision adapter

An optional outside scoring service (JEV, from TypeSafe AI) that Agent 02
can use to score leads. Without it, Agent 02 scores with its own rules and
the tiers are the same. It is used only when its key is set and you sign
permission to Agent 02. A score below the *confidence floor* (a cut-off you
can set) holds the lead for you. Details:
[JEV_DECISION_PLATFORM.md](JEV_DECISION_PLATFORM.md).

### Model drafting

Optional listing remarks for Agent 04 written by an AI language model
running on your own computer. Off by default. A *checkpoint* or *restore
point* is a saved version of the model setup that can be switched back to;
the *broker exam* is a set of test questions the model must pass on your
machine before its remarks are used. Every draft still goes through Agent 17
like any other. Details: [OPERATOR_TUNING_GUIDE.md](OPERATOR_TUNING_GUIDE.md).

### MCP server

*Model Context Protocol*: a standard way for an AI assistant app to use an
outside tool. ListingAssistants can run as an MCP server, so an assistant
app (Hermes, OpenClaw or Claude Desktop, called the *host*) can hand it
work through four fixed tools while the hub keeps all the routing, signing
and logging. It refuses to start if the closed track, the signature check
or the audit chain is broken. Details: [MOUNTING.md](MOUNTING.md).

### Pillars

Six add-on self-check packages from QuietFire (before-turn, open-mind,
agent-open-mind, pre-response-selfcheck, sleep-marks, splitvantage), each
watching a different point in the hub, such as a last read of outgoing text
before it leaves. A pillar is *armed* when it is installed and has what it
needs to run; one that is not says *UNARMED* on the audit log rather than
staying silent. The swarm routes correctly without them, and the build
checks that too.

### Pager

Optional text-message alerts to your phone when something lands in a queue,
while a console session, the Broker Desk or the daily clock is running,
using your own Twilio account (`python tools/console.py pager`). A page
carries only the queue name and the client context id, never client
details. Each page is on the record as sent or failed; a failed page is also
recorded as "Could not reach you about ..." - the item is still on its queue,
and nothing claims you were told.

## Running and testing it

### Console

The command-line program (`tools/console.py`) for setting up your key,
telling the system who you are, running a *session* (a prepared file of
messages played through the hub), checking the record and more. A
*command line* is the text window (Terminal on a Mac, PowerShell on
Windows) where you type commands such as `python tools/desk.py`.

### Broker Desk

The one-page screen in your web browser that shows what the swarm is doing
and what waits for you, with the Send, Don't send, Continue and Cancel
buttons. It runs on your own computer. Everything on it is explained in
[BROKER_DESK_MANUAL.md](BROKER_DESK_MANUAL.md).

### Showcase and scenes

A *scene* is a short scripted situation (a signature check, a new listing,
a compliance catch, a complaint), stored in `scenes/`. There are ten, each
checked by the test suite and written to be filmed
([OPERATOR_TESTING_MANUAL.md](OPERATOR_TESTING_MANUAL.md)). The *showcase*
plays all ten on the Broker Desk and stops at each point where you would
act (`python tools/desk.py --showcase`).

### Synthetic data

Made-up clients, listings and vendors used for demonstrations and tests, so
no real person's information is involved.

### Test and suite

A *test* is a small program that runs one part of the system and checks the
result is exactly what it should be. The *suite* is all of them together:
running `python -m pytest tests_listing/` runs every test and reports how
many *passed* (correct), *failed* (wrong) or were *skipped* (not meant to
run on this kind of computer).

### End-to-end test

A test that runs a whole playbook through the real hub, from its trigger to
its last step, and checks every message along the way.

### Mutation testing

A test of the tests. A tool makes small deliberate mistakes in the code
(flips a "yes" to a "no", removes a check) and confirms some test catches
each one. A mistake no test catches shows a rule nobody is really checking.

### CI

*Continuous integration*: GitHub runs the whole suite automatically every
time the code changes, on a fresh copy, on both Linux and Windows. In this
project a change counts as finished only when CI passes.

### Repository, clone and commit

A *repository* (*repo*) is the project's folder of files, kept on GitHub
with its full history. To *clone* it is to download a complete copy. A
*commit* is one saved, dated change with a note saying what changed.
A *README* is the page GitHub shows first when you open a folder.

### Vendored core

Sixteen files from the separate dispatcher-agents project, copied into
`dispatcher/` so this repository runs on its own. `CORE_PIN.json` names the
exact dispatcher-agents commit they came from, and CI checks that the copies
match that commit byte for byte, so the copy can never drift. Moving to a
newer core is a deliberate step (`tools/sync_core.py`).
