# Agents in their own containers (agent isolation V1)

> **Words used here.** Tuple, playbook, swarm, hold, release and the other technical words are explained in plain language in [GLOSSARY.md](GLOSSARY.md).

Owner decisions of 2026-10-26 (the decisions record is in the project as
`claude/AGENT_ISOLATION_DECISIONS_2026-10-26.md`). Every agent runs alone
and reaches nothing except the dispatcher, and only on a route that is on
`identity/routes.json`.

## What runs where

| Container | Network | What it holds | What it can do |
|---|---|---|---|
| `dispatcher` | closed (no internet) | the record, the state, the drawers, the routes, every agent's line | routes messages, prepares, keeps the record, runs the Desk |
| `desk-door` | closed + this computer | nothing | passes your browser to the Desk; published on 127.0.0.1:8765 only |
| `alert-door` | internet | the Twilio details | sends one kind of text: system id, error code, queue |
| `agent-01` ... `agent-20` | none at all | its own working memory | answers the dispatcher on its one line |

Every container runs as an unprivileged user, read-only, with no Linux
capabilities and no way to gain more (`no-new-privileges`). Each agent sees
one folder: the one holding its own line.

## The portal (how an agent talks)

One private socket per agent and a fixed menu (`dispatcher/portal.py`):
send, trace, escalate, log note, outbound state, on record, hold for you,
phase gate, and narrow items only some agents may use: file a record into
a client's drawer (agents 04, 05, 07, 08, 14, 15; the drawers stay with the
dispatcher), the decision engine (Agent 02) and model drafting (Agent 04).
Anything else is refused. A log note may only be one of the kinds agents
write (`AGENT_NOTE_KINDS` in `dispatcher/portal_dispatcher.py`); an agent
cannot write a line the dispatcher owns, such as `state.saved`. The dispatcher knows the
agent by its line, so whatever an agent writes in a "from" field, it is
treated as itself. Values travel as JSON with explicit type tags, never
pickle.

## When an agent breaks a rule

A route not on `identity/routes.json`, speaking as another agent, asking
for something off its menu, or writing a kind of line on the record that
only the dispatcher writes: refused, recorded as `portal.violation`, the
agent's line cut, and a text sent through the alert door:

    ListingAssistants LA-1A2B3C: portal.violation V05-9F3A2C. Agent 05 is stopped until you clear it.

`LA-...` is this system's id; `V05-...` is the start of the record entry to
look up. Messages for a stopped agent wait for you (dead letter, on the
Desk). A crash or no answer in 120 seconds stops the agent the same way
(`C05-...`), without restarting it on its own.

A stopped agent stays stopped when the dispatcher restarts: the record
says so (a `portal.agent_stopped` with no `portal.agent_cleared` after it),
and the dispatcher does not connect it. On the Desk the item has a button,
**Reviewed: restart agent NN**. It starts the agent on a new line and gives
it back the state it last reported (`portal.agent_cleared`,
`portal.agent_restarted`, with your login).

## Running it

    docker compose -f docker/compose.yml build
    # behind a proxy with its own certificate, build with it (kept out of the image):
    # docker build -f docker/Dockerfile -t listingassistants:local --secret id=ca,src=<file> .
    docker compose -f docker/compose.yml run --rm dispatcher python tools/console.py init
    docker compose -f docker/compose.yml run --rm dispatcher python tools/console.py onboard
    docker compose -f docker/compose.yml run --rm -it alert-door \
        python -m dispatcher.alert_door setup /door-config/pager.json
    docker compose -f docker/compose.yml up -d

Then open http://127.0.0.1:8765 on the same computer.

## How it is checked

- `tests_isolation/test_portal.py`: each agent in its own process; a rogue
  program on one agent's line tries impersonation, a route off the track,
  an unknown kind of message, off-menu asks and a forged record line, each
  refused and stopping the agent; crashes and timeouts; restart after
  review; the alert door; the Desk's restart button; two playbooks with
  records matching the one-process run line for line.
- `tests_isolation/test_containers.py`: the same in real containers
  (CI job `linux-containers`, `LA_DOCKER_TESTS=1`): playbook P01, an agent
  container with no network, no capabilities and a read-only disk, the
  dispatcher with no internet, the Desk through its door only, and a rogue
  agent container stopped with the alert going to the alert door.
- Every tuple and playbook run both ways (`LISTINGASSISTANTS_PORTAL=process
  python synth/tuples/run_tuples.py`): on 2026-10-26, 246 of 247 records
  identical line for line; the one difference is fault-harness tuple 01-16,
  where the one-process run cannot save its state because the harness
  plants a function in an agent (the run behind the portal saves it).

Running the agents as separate processes without Docker:
`LISTINGASSISTANTS_PORTAL=process python tools/console.py session ...`
(Linux and macOS; the portal uses Unix sockets).

## What this does not do

- It controls who an agent can talk to, not whether what it says is
  right. A wrong date on an allowed route is caught by the tuples, the
  playbooks and the review agent, not by containers.
- Containers share the machine's kernel. Non-root, read-only, no
  capabilities and no-new-privileges make an escape much harder, not
  impossible.
- The signing key still sits with the dispatcher in this step; the
  signer container with two-factor is the next step.
- The Hermes door (the MCP server, `docs/MOUNTING.md`) is not wired into
  the containers yet.
