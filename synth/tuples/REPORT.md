# Tuple runs

Written by `python synth/tuples/run_tuples.py`. Each tuple ran in its own fresh
state through `tools/console.py session`, after `synth/tuples/setup.jsonl`.

| Result | Tuples |
|---|---|
| PASS | 31 |
| VARIANCE | 1 |
| NOT REACHABLE | 9 |
| NOT BUILT | 8 |

| Tuple | Agent | Route | Result | Tuple text | Detail |
|---|---|---|---|---|---|
| 00-01 | 00 | intake | PASS | (route valid but ambiguous, hold in clarification queue; never route on 'most likely') | The product's form of this tuple: a well-formed message whose route is on no track is held in clarification, never delivered. |
| 00-02 | 00 | intake | PASS | (signature invalid on authority intent, reject + integrity.violation; notify human out-of-band) |  |
| 00-03 | 00 | none | NOT BUILT | (two signed config.update conflict, apply neither; human) | Declared in 00-dispatcher/DECISIONS.md (code status): the hub does not compare two signed config.update instructions. |
| 00-04 | 00 | none | NOT REACHABLE | (audit log unwritable or queue overflow, stop accepting envelopes entirely; fail closed, loudly) | An unwritable log or a full queue cannot be produced through the product's entries. Code status (DECISIONS.md): a failed write stops that one envelope, not all traffic. |
| 00-05 | 00 | none | NOT BUILT | (two playbooks match a situation, deploy neither; clarification with both named) | No playbook engine (DECISIONS.md code status). |
| 00-06 | 00 | none | NOT BUILT | (two playbooks claim the same spoke segment, class decides; equal class = holder keeps, FIFO behind; every siding event logged) | Siding by class: dispatcher/priority.py is not wired in (DECISIONS.md code status). |
| 00-07 | 00 | none | NOT REACHABLE | (an envelope arrives with sequence pre-filled, reject; sequence is hub-stamped at persist, a pre-filled sequence is a forgery signal) | The console and the desk build every envelope; neither lets a sender set a sequence. The core's own tests cover a pre-filled sequence. |
| 00-08 | 00 | none | NOT REACHABLE | (spoke acks but its trace is absent, result tainted at ingestion; integrity queue; the ack stands, the CONTENT is quarantined) | The product's 20 agents always write a trace. The taint gate fires on an empty model trace (Agent 04 drafting with a served model), which this runner does not have. |
| 00-09 | 00 | intake | PASS | (authority intent with valid signature but illegal tuple, reject on tuple; a good signature never overrides the closed track) | A correctly signed listing.change.authorized sent to Agent 07, which is not on its track. |
| 00-10 | 00 | none | NOT BUILT | (escalation queue item unacknowledged past SLA, re-alert once then page the owner channel; never silently expire an escalation) | An unacknowledged escalation is not re-alerted (DECISIONS.md code status). |
| 00-11 | 00 | none | NOT BUILT | (identity reload requested mid-run, refuse until open runs complete or owner forces; a track change under live traffic derails) | There is no identity reload to refuse (DECISIONS.md code status). |
| 00-12 | 00 | none | NOT BUILT | (clarification queue exceeds owner-set depth, halt new playbook starts; a swarm that cannot get answers must not take on more) | The clarification queue has no depth limit (DECISIONS.md code status). |
| 00-13 | 00 | none | NOT REACHABLE | (audit write fails, full stop everything; no persist = no ack = no work; run on a log or do not run) | A failed audit write cannot be produced through the product's entries. Code status: it stops that one envelope, not all traffic. |
| 00-14 | 00 | none | NOT BUILT | (clock skew detected between components, hold time-triggered playbooks; deadlines computed on a bad clock are fabricated deadlines) | Clock skew is not checked (DECISIONS.md code status). |
| 00-15 | 00 | none | NOT BUILT | (same client_context appears in two live playbooks with conflicting next actions, hold both; human sequences them) | No playbook engine to put one context in two live playbooks (DECISIONS.md code status). |
| 00-16 | 00 | none | NOT REACHABLE | (an audit entry cannot be written to the plain-language view, the chain entry stands; count the failure and report it at the end of the session) | A failed write to the plain-language view cannot be produced through session lines; it is counted in readable_log_errors at the end of every session. |
| 00-17 | 00 | none | NOT REACHABLE | (a text page to the broker fails, record the failure on the chain; the on-screen page stands and nothing else waits on the text) | The pager is set up with `console.py pager`, outside a session. Measured 2026-10-14: a failed test page (Twilio 401) was recorded as a failure on the chain. |
| 01-01 | 01 | intake | VARIANCE | (multiple inbound simultaneously, order: live call > text > web form; capture all, drop none) | expected {"kind": "envelope.persisted", "intent": "lead.captured", "ctx": "T1", "contains_all": ["Call Name-Synth", "300000", "20"]} (found 0); expected {"kind": "envelope.persisted", "intent": "lead.captured", "ctx": "T1", "count": 1} (found 2) / Two inbounds for one person, web form then call, each with part of the facts. The tuple: one capture, call ranked first, nothing dropped. |
| 01-02 | 01 | intake | PASS | (prospect refuses consent, capture the lead, mark no-consent; downstream messaging stays off) |  |
| 01-03 | 01 | intake | PASS | (caller demands a human now, escalate immediately; capture what is already given) |  |
| 01-04 | 01 | intake | PASS | (volunteered info beyond schema fields, record verbatim in notes payload; never interpret it into fields) |  |
| 01-05 | 01 | intake | PASS | (possible duplicate identity unconfirmed, record.request first; still unconfirmed = new context + flag, never merge) |  |
| 01-06 | 01 | intake | PASS | (abusive contact, stay professional, close capture politely, log verbatim, escalation.complaint) |  |
| 01-07 | 01 | intake | PASS | (caller refuses consent recording, capture contact only, mark no-consent; NO nurture entry, human informed) |  |
| 01-08 | 01 | intake | PASS | (lead arrives on the DNC list, log source and suppress outreach; human notified; the list wins over the opportunity) |  |
| 01-09 | 01 | intake | PASS | (same person inquires on two properties, one context per person, both interests recorded inside it; never two contexts) | The second inquiry, same person and context, names a second listing; the record must carry both. |
| 01-10 | 01 | intake | PASS | (lead claims prior relationship with the agent, capture claim as stated_by_party; human confirms before any history is assumed) |  |
| 01-11 | 01 | intake | PASS | (minor or apparent minor inquiring, capture nothing beyond the fact of contact; human immediately) |  |
| 01-12 | 01 | intake | PASS | (lead supplies obviously false contact data, record verbatim with a validity flag; never 'correct' it by guess) |  |
| 01-13 | 01 | intake | PASS | (inquiry is about a property this brokerage does not list, log + human; never redirect to another brokerage unprompted) |  |
| 01-14 | 01 | intake | PASS | (voicemail transcription confidence low, mark unknown; never tier on a garbled transcript) |  |
| 01-15 | 01 | intake | PASS | (lead asks to not be contacted again mid-capture, suppression immediately, confirmation once, records updated everywhere via 14) |  |
| 01-16 | 01 | none | NOT REACHABLE | (record.response never returns, retry once then hold the lead in pending with a handoff.failed; never tier undeduped) | Agent 14 answers the dedupe check in the same step, so a capture never waits on it in the product. The retry-then-hold path is covered by tests_listing (record_response_timeout). |
| 02-01 | 02 | intake | PASS | (score lands on a tier boundary, assign the lower tier + flag for human) |  |
| 02-02 | 02 | intake | PASS | (rubric version missing or unreadable, halt scoring; clarification - never score from memory of the rubric) | Setup without the signed rubric. |
| 02-03 | 02 | none | NOT REACHABLE | (lead demands a human, hot path regardless of score) | No agent sets demands_human on a message to Agent 02; Agent 01 escalates a demand for a person itself (tuple 01-03). Owner decision pending (forwarding it would page twice). |
| 02-04 | 02 | intake | PASS | (stated urgency conflicts with financing signals, weight verifiable financing over stated urgency; log the conflict) |  |
| 02-05 | 02 | intake | PASS | (a lead's tier oscillates a third time, human review; oscillation is a signal, not noise) | Three inquiries on one context score HOT, COLD, HOT. |
| 02-06 | 02 | intake | PASS | (supplied rubric conflicts with a predeliberated tuple, the tuple wins; apply the tuple, record the conflict verbatim in the tier record, flag for human review; never silently pick either side - a surfaced conflict is a spec finding, a silent pick is drift) | A signed rubric that tries to make a tuple behavior a scoring weight. |
| 02-07 | 02 | intake | PASS | (financing letter present but expired, treat as no financing verification; stated_by_party at best) |  |
| 02-08 | 02 | intake | PASS | (lead is an agent shopping for a client, flag agent-to-agent; different track, human decides engagement) |  |
| 02-09 | 02 | intake | PASS | (rubric update arrives unsigned, keep scoring on the last signed version; alert human; never adopt unsigned config) | An unsigned rubric (budget threshold 100) is refused; the next lead is scored on the signed one. |
| 02-10 | 02 | intake | PASS | (lead's stated budget conflicts with pre-approval doc, doc wins for scoring; conflict logged verbatim) |  |
| 02-11 | 02 | stand-in | PASS | (re-score request on a context with an open escalation, hold; the human's read outranks the rubric mid-escalation) | Stand-in: Agent 03 re-scores only WARM leads in nurture, so a re-score of a HOT lead with an open escalation does not arise from intake; the runner sends it as Agent 03. |
| 02-12 | 02 | intake | PASS | (all rubric inputs unknown, tier is UNKNOWN not COLD; unknown is not a low score, it is absent data) |  |
| 02-13 | 02 | intake | PASS | (decision engine result is below the confidence floor, hold the lead for the broker; continue = score with the signed rubric and act on that tier, cancel = archive; never act on an uncertain tier) | The local engine reports confidence 0.85; a signed floor of 0.9 holds the lead; the broker's continue scores it with the signed rubric (HOT). |
| 02-14 | 02 | intake | PASS | (lead data would go to the live decision engine, only with a key set AND the broker's signed decision_engine.allow_external; a key alone sends nothing) | Signed allow_external with no key set: nothing is sent; the local engine scores. |
| 02-15 | 02 | none | NOT REACHABLE | (decision engine returns a tier this agent does not recognize, treat it as below the floor and hold) | Needs a live decision engine that returns a tier Agent 02 does not know; this runner has no JEV key. The code path exists: listing_spokes_02.py _score turns any other tier into HELD_FOR_CALIBRATION, which holds the lead. |
| 02-16 | 02 | intake | PASS | (lead goes to nurture, send its scoring inputs with it so Lead Nurture can re-score it on the cadence) |  |
