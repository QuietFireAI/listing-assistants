# Agent 00 - Predeliberated Decisions (Tuple Layer) v0.1 (ratified 2026-07-11)

PRE-TEXT - ROOT OF THE TUPLE DECISION TREE (owner rule, binding):
before ANY task or decision, consult this layer. If NO suitable tuple covers
the task: STOP. Contact the human via clarification.request and wait. Do not
improvise, do not pick the nearest tuple, do not proceed on judgment - a
missing tuple is a design omission to be fixed, never a license to act. A
PARTIAL OR UNCERTAIN MATCH IS NOT-FOUND: if it takes judgment to decide the
tuple fits, it does not fit - STOP applies. The after-action proposes the
missing tuple so the omission is closed.

Meta pre-decision layer, above playbooks: crossings this agent may reach,
already deliberated. Format: (crossing, answer) - a location with its answer,
stored before the run. Swarm-wide tuples in /SWARM.md apply first; MANNERS.md
constrains everything.

- (route valid but ambiguous, hold in clarification queue; never route on 'most likely')
- (signature invalid on authority intent, reject + integrity.violation; notify human out-of-band)
- (two signed config.update conflict, apply neither; human)
- (audit log unwritable or queue overflow, stop accepting envelopes entirely; fail closed, loudly)
- (two playbooks match a situation, deploy neither; clarification with both named)
- (two playbooks claim the same spoke segment, class decides; equal class = holder keeps, FIFO behind; every siding event logged)
- (an envelope arrives with sequence pre-filled, reject; sequence is hub-stamped at persist, a pre-filled sequence is a forgery signal)
- (spoke acks but its trace is absent, result tainted at ingestion; integrity queue; the ack stands, the CONTENT is quarantined)
- (authority intent with valid signature but illegal tuple, reject on tuple; a good signature never overrides the closed track)
- (escalation queue item unacknowledged past SLA, re-alert once then page the owner channel; never silently expire an escalation)
- (identity reload requested mid-run, refuse until open runs complete or owner forces; a track change under live traffic derails)
- (clarification queue exceeds owner-set depth, halt new playbook starts; a swarm that cannot get answers must not take on more)
- (audit write fails, full stop everything; no persist = no ack = no work; run on a log or do not run)
- (clock skew detected between components, hold time-triggered playbooks; deadlines computed on a bad clock are fabricated deadlines)
- (same client_context appears in two live playbooks with conflicting next actions, hold both; human sequences them)

Added 2026-10-12 (owner sign-off, Jeff: modules wired, J3/J4/J8 decisions):
- (an audit entry cannot be written to the plain-language view, the chain entry stands; count the failure and report it at the end of the session)
- (a text page to the broker fails, record the failure on the chain; the on-screen page stands and nothing else waits on the text)

Code status (checked 2026-10-20): the running hub does not compare two
signed config.update instructions (an agent that receives conflicting
changes holds them - Agent 05 does for listing changes). The rest runs:
a failure that escapes the hub, an unwritable audit log among them, halts
all traffic and alarms (`escalation.system_halt`, 2026-10-15);
`dispatcher/escalation_watch.py` re-alerts an unanswered escalation at 30
minutes and pages the owner at 60, and holds time-triggered checks on a
skewed clock; `dispatcher/identity_reload.py` refuses a reload while work
is open; and the playbook run tracker (`dispatcher/run_tracker.py`,
2026-10-20) holds two playbook matches and conflicting runs on one client
for you, holds new starts past 25 open questions, releases waiting work by
priority class through `dispatcher/priority.py`'s siding, halts a run whose
step the track refuses, and writes an after-action report for every run
(`after_action/` next to the audit log). Each is run as a tuple through the
console (synth/tuples).

(Root rule, restated: no suitable tuple - or an uncertain match - means STOP and ask the human.)
