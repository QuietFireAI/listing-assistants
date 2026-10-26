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
| `signer` | its own closed network | the operator's key, the authenticator secret, the security keys | signs one message at a time after your code or key, on its own page |
| `signer-door` | the signer's network + this computer | nothing | passes your browser to the signer's page; 127.0.0.1:8767 only |
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

## The signer: your key in a room of its own

The operator's key lives only in the `signer` container (owner decision
2026-10-26). The dispatcher holds the public key: it can check a signature,
never make one. The signer is on a network of its own (`signing`) that the
dispatcher is not on; the dispatcher cannot reach it at all. What leaves
the signer: the public key and the signed list of installed files (the
`signer-out` volume, which the dispatcher mounts read-only), and each
signature you make.

Every signature needs a second factor:

- **Authenticator code** (V1 default): the six-digit code from an app such
  as Google Authenticator, Authy or 1Password. Each code works once; five
  wrong codes lock the signer for 15 minutes.
- **Security key** (WebAuthn / FIDO2, e.g. a YubiKey): add one on the
  signer's page at http://localhost:8767/keys (adding a key needs the
  code). Register two (keyring and safe) and turn on the key's PIN.

How a signature travels, with no line between dispatcher and signer:

1. You press a button on the Desk that needs your signature (Send, Do not
   send, a decision on a paused item, Release hold).
2. The Desk hands the prepared message to your browser, which opens the
   signer's page (http://localhost:8767) in a window of its own.
3. The signer shows what you are about to sign, built from the message
   itself, and asks for your code or your key.
4. It signs exactly that message, writes it on its own record
   (`signer-log.jsonl`: every signature, every wrong code, every lock,
   every key added) and hands the signature back to the Desk window.
5. The Desk checks the signature against your public key and carries on.

Settings files and scripts (setup, a playbook run) are signed in a batch
with one code:

    docker compose -f docker/compose.yml run --rm -v <folder>:/s dispatcher \
        python tools/console.py prepare /s/script.jsonl --out /s/unsigned.jsonl
    docker compose -f docker/compose.yml run --rm -it -v <folder>:/s signer \
        python -m dispatcher.signer_service sign-batch --dir /signer --in /s/unsigned.jsonl --out /s/signed.jsonl
    docker compose -f docker/compose.yml run --rm -v <folder>:/s dispatcher \
        python tools/console.py session /s/script.jsonl --signed /s/signed.jsonl

Lines that answer a held message (release, decline, decide) name a message
that exists only when the script runs; those are signed on the Desk.

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
    docker compose -f docker/compose.yml run --rm -it signer python -m dispatcher.signer_service init \
        --dir /signer --out /out --account you@example.com      # add the authenticator it shows
    docker compose -f docker/compose.yml run --rm dispatcher python tools/console.py init --from-signer /signer-out
    docker compose -f docker/compose.yml run --rm dispatcher python tools/console.py onboard
    docker compose -f docker/compose.yml run --rm -it alert-door \
        python -m dispatcher.alert_door setup /door-config/pager.json
    docker compose -f docker/compose.yml up -d

Then open http://127.0.0.1:8765 on the same computer. The signer's page is
http://localhost:8767 (add your security keys at /keys).

After an update (a new image), the signer signs the new list of files and
the dispatcher records it:

    docker compose -f docker/compose.yml run --rm -it signer python -m dispatcher.signer_service attest --dir /signer --out /out
    docker compose -f docker/compose.yml run --rm dispatcher python tools/console.py attest --from-signer /signer-out

## How it is checked

- `tests_isolation/test_portal.py`: each agent in its own process; a rogue
  program on one agent's line tries impersonation, a route off the track,
  an unknown kind of message, off-menu asks and a forged record line, each
  refused and stopping the agent; crashes and timeouts; restart after
  review; the alert door; the Desk's restart button; two playbooks with
  records matching the one-process run line for line.
- `tests_isolation/test_signer.py`: authenticator codes (the RFC 6238
  test values, one use per code, the lock after five wrong codes), the
  signer refusing anything but your authority messages, the dispatcher
  side holding the public key only and rejecting a changed message, the
  signer's page (other origins and hosts refused), a session refused line
  by line without its signatures, and in Chromium: a held message released
  on the Desk and signed on the signer's page with the authenticator code,
  and again with a security key (Chrome's virtual authenticator), after
  which playbook P01 runs to its end.
- `tests_isolation/test_containers.py`: the same in real containers
  (CI job `linux-containers`, `LA_DOCKER_TESTS=1`): playbook P01, an agent
  container with no network, no capabilities and a read-only disk, the
  dispatcher with no internet, the Desk through its door only, a rogue
  agent container stopped with the alert going to the alert door, the key
  only in the signer's volume, and the signer unreachable from the
  dispatcher (P01 runs to the booking that waits for your signed release).
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
- The signer protects the key from the agents, from the dispatcher and
  from an AI assistant: none of them has a line to it, and every signature
  needs your code or your key. It does not stop you from signing something
  you did not read; the signer's page shows you what you sign.
- The Hermes door (the MCP server, `docs/MOUNTING.md`) is not wired into
  the containers yet.
