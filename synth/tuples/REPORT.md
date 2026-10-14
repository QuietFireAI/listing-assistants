# Tuple runs

Written by `python synth/tuples/run_tuples.py`. Each tuple ran in its own fresh
state through `tools/console.py session`, after `synth/tuples/setup.jsonl`.

| Result | Tuples |
|---|---|
| PASS | 224 |
| VARIANCE | 2 |
| NOT REACHABLE | 22 |
| NOT BUILT | 20 |
| RETIRED | 4 |

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
| 03-01 | 03 | intake | PASS | (lead replies mid-sequence, pause the sequence; route the reply; never auto-continue over a reply) | A WARM lead in nurture gets touch 1 on day 0; it replies on day 1; on day 7 the second touch must not go out. |
| 03-02 | 03 | intake | PASS | (ambiguous opt-out ('stop sending so many'), treat as frequency complaint: reduce + confirm; an explicit 'stop' is a full opt-out) |  |
| 03-03 | 03 | none | RETIRED | (sequence content contains expired market data, regenerate before send, or skip the touch) - RETIRED 2026-10-12 (owner decision J5): Lead Nurture no longer requests or sends market data | Retired 2026-10-12 (owner decision J5): Lead Nurture no longer requests or sends market data. |
| 03-04 | 03 | stand-in | PASS | (two sequences eligible for one lead, run neither until the human picks; never stack sequences) | Stand-in: Agent 02 only ever assigns default_drip, so a second eligible sequence does not arise from intake; the runner sends it as Agent 02. |
| 03-05 | 03 | intake | PASS | (engagement spike detected, rescore via 02; never convert a signal into direct outreach yourself) | An engagement spike of 80 on a nurtured lead. The tuple: re-score through 02, never outreach. The last check expects the re-score to land on a real tier (the lead's stored inputs), not UNKNOWN. |
| 03-06 | 03 | intake | PASS | (contact replies STOP or equivalent, suppression across ALL channels immediately; confirmation only if channel rules allow) |  |
| 03-07 | 03 | intake | PASS | (sequence step lands on a legal holiday or outside contact hours, shift to next legal window; never send anyway) | Contact hours only: the daily clock flags no legal holidays (no holiday calendar exists, DECISIONS.md code status). |
| 03-08 | 03 | intake | PASS | (engagement spike mid-sequence, pause sequence + lead.rescored to 02; never keep dripping on a hot signal) |  |
| 03-09 | 03 | none | RETIRED | (nurture content references a listing that changed status, pull the step; stale property claims are fabrications) - RETIRED 2026-10-12 (owner decision J5): Lead Nurture no longer requests or sends market data | Retired 2026-10-12 (owner decision J5): Lead Nurture no longer requests or sends market data. |
| 03-10 | 03 | stand-in | PASS | (two sequences would target one context, one sequence per context, newest signed instruction wins; overlap logged) | Stand-in: a signed reassignment to a different sequence does not arise from intake (Agent 02 only assigns default_drip). |
| 03-11 | 03 | intake | PASS | (contact asks a substantive question from inside a drip, out of sequence, route to 11 for a gated human-reviewed reply) |  |
| 03-12 | 03 | intake | PASS | (a nurtured lead's re-score interval has passed, ask 02 to re-score with the stated timeline counted down by the days elapsed; never invent any other input) |  |
| 03-13 | 03 | intake | PASS | (a re-score did not return the lead to nurture, it left WARM; take it out of the re-score pool and log it to 14) | Timeline 35 days scores WARM (60); seven days later it is 28 and the re-score is HOT (100); the next cadence takes it out of the pool. |
| 03-14 | 03 | intake | PASS | (a re-score keeps the lead WARM on the same sequence, the sequence continues; never restart it from day 0) |  |
| 03-15 | 03 | intake | PASS | (lead opted out or its sequence is paused, no re-score) |  |
| 03-16 | 03 | intake | PASS | (compliance flags a sequence, keep it paused and send nothing; tell the broker with 17's findings and wait for a corrected signed sequence) |  |
| 04-01 | 04 | intake | PASS | (photos contradict the data sheet, halt the asset; clarification with both artifacts attached) |  |
| 04-02 | 04 | intake | PASS | (a feature cannot be verified, omit it; never hedge with 'may include') | An HVAC year with no source: no fact is drafted for it (the omission note rides in the draft's notes). |
| 04-03 | 04 | intake | VARIANCE | (human-supplied copy appears to violate fair housing, flag to 17 and the human; never silently rewrite) | expected {"kind": "envelope.persisted", "intent": "content.review", "ctx": "T1", "contains": "Close to great schools"} (found 0) / The tuple: flag to 17 and the human. Agent 04 escalates to the human but never sends the human-supplied copy to 17 (the draft is built from the data fields only, so the copy is neither reviewed nor used). Owner decision: how human-supplied copy is used and reviewed. |
| 04-04 | 04 | intake | PASS | (space forces cuts, cut adjectives before facts; source attributions are never cut) |  |
| 04-05 | 04 | intake | PASS | (superlatives requested ('best block in town'), decline in copy; characterization is a steering vector) |  |
| 04-06 | 04 | intake | PASS | (square footage differs between tax record and seller claim, publish the verifiable source, note the discrepancy to human; never average) |  |
| 04-07 | 04 | intake | PASS | (seller requests language naming schools-quality or neighborhood demographics, refuse; fair-housing gate; 17 verdict required regardless) |  |
| 04-08 | 04 | intake | PASS | (photo shows an item revealing protected-class information, flag to human before any use) |  |
| 04-09 | 04 | intake | PASS | (feature cannot be verified (roof age, HVAC year), include only as per-seller with attribution or omit; no bare claims) |  |
| 04-10 | 04 | intake | PASS | (17 returns content.verdict requiring changes, apply exactly; no negotiation with the compliance agent) |  |
| 04-11 | 04 | intake | PASS | (remarks exceed MLS field limits, cut by priority list from the identity config; never silently truncate mid-claim) | Whole entries are cut from the end of the adjective class; the first stays whole. |
| 04-12 | 04 | intake | PASS | (broker signed drafting mode "model", draft remarks with the model only while the active checkpoint passed the broker exam on the served model; otherwise draft by rules and tell the broker why) |  |
| 04-13 | 04 | none | NOT REACHABLE | (model draft has no reasoning, exceeds the MLS limit, or contains a number not in the data, do not use it; draft by rules and record why) | Needs a served model and an examined checkpoint; this runner has none. Covered by tests_listing/test_wiring_2026_10_12.py::test_model_drafts_that_fail_the_checks_are_not_used. |
| 04-14 | 04 | none | NOT REACHABLE | (compliance flags a phrase inside model remarks, remove exactly the sentence carrying it and resubmit) | Needs model remarks in the draft; this runner has no served model. Covered by tests_listing/test_wiring_2026_10_12.py::test_compliance_flag_removes_exactly_the_flagged_sentence_from_model_remarks. |
| 04-15 | 04 | intake | PASS | (compliance flags a phrase this agent cannot find in its draft, hold for the broker; never resubmit the same draft) | Compliance reads the whole draft as one text, so a phrase split over two features is flagged but is in no single fact. |
| 05-01 | 05 | intake | PASS | (supplied data has no valid MLS field, clarification; never approximate into the wrong field) |  |
| 05-02 | 05 | none | NOT BUILT | (syndicated portal shows different data than MLS, correct the source record, then re-verify every portal) | Needs a portal connection this build does not have (05-mls-listing-management/DECISIONS.md code status). |
| 05-03 | 05 | none | NOT REACHABLE | (two authorized changes conflict, execute neither; human) | A conflict needs two different signers; the console and the desk sign with the one broker key, and the signer registry (which would name the login) is not armed. |
| 05-04 | 05 | none | NOT BUILT | (portal still stale after the verification window, log + notify human; never mark complete) | Needs a portal connection (DECISIONS.md code status). |
| 05-05 | 05 | intake | PASS | (status change requested without its required artifact, refuse; artifact first) |  |
| 05-06 | 05 | intake | PASS | (status change requested without signed listing.change.authorized, refuse; verbal or email instruction is not authority) |  |
| 05-07 | 05 | none | NOT BUILT | (MLS rejects an entry on a rule, log raw rejection, human; never adjust data to pass validation) | Needs an MLS connection (DECISIONS.md code status). |
| 05-08 | 05 | intake | PASS | (price in the authorized change conflicts with the agreement amendment on file, halt; both documents to human) |  |
| 05-09 | 05 | intake | PASS | (comp-offer field present anywhere, leave blank per 8/17/24 rules; flag any request to fill it) |  |
| 05-10 | 05 | intake | PASS | (listing data and marketing asset disagree, MLS record is truth; asset.release corrected version; discrepancy logged) | The MLS record says 2000 sq ft; the description is built from the 1800 sq ft tax record. |
| 05-11 | 05 | intake | PASS | (withdrawal requested while under contract, halt; 17 + human; status math on a live contract is never autonomous) |  |
| 05-12 | 05 | intake | PASS | (listing marked vacant by the broker, order a property condition check through 09 every interval until occupied or the listing ends; a check counts only with proof) | Checks on day 1 and day 8 (interval 7); not on day 3. |
| 05-13 | 05 | intake | PASS | (vacant listing ends or is marked occupied, stop the watch and log it to 14) |  |
| 06-01 | 06 | intake | PASS | (calendar double-booking, protected deadline blocks win; otherwise first-confirmed wins and alternatives are offered) | Not protected: the first confirmed wins; the second goes to the broker (no alternative time is computed, DECISIONS.md code status). The protected-deadline half (a HOT lead's claim offers the broker a bump) is played in scenes/scene08_showing_bump.jsonl. |
| 06-02 | 06 | intake | PASS | (requester identity cannot be verified, cancel the access-bearing appointment; no exceptions) |  |
| 06-03 | 06 | intake | PASS | ('just let them in' request, refuse + escalation.legal_line; access is the line) | A client's message asking to let someone in. |
| 06-04 | 06 | intake | PASS | (no-show, log + send feedback request; no reproach messaging) |  |
| 06-05 | 06 | intake | PASS | (same-day showing request on occupied property, minimum-notice rules still apply; occupancy is never squeezed) | The listing record says occupied; the client wrote at 10:00 for 15:00 the same day (5 hours); the minimum is 24 hours (TUNING_MANUAL). Wired 2026-10-14 (owner decision: showings read the listing record). |
| 06-06 | 06 | intake | PASS | (access code or lockbox combo requested in a message, never transmit; access instructions route through the custody protocol only) | A client's message asking for the lockbox combination. |
| 06-07 | 06 | intake | PASS | (showing request inside occupied-home notice window, offer first legal slot; never ask seller to waive notice unprompted) | Occupancy is not on this listing's record, so it is treated as occupied. 20 hours' notice against 24: the client is offered the first legal slot and nobody is asked to waive notice. Wired 2026-10-14. |
| 06-08 | 06 | none | NOT REACHABLE | (agent no-shows twice, flag pattern to human before third confirmation) | The pattern counts no-shows by showing_agent_id with is_agent_no_show true; a client's no-show report (via Agent 11) carries neither, and Agent 18's calendar-detected no-show sets is_agent_no_show false. No entry names a showing agent. |
| 06-09 | 06 | intake | PASS | (overlapping showings requested, sequence with buffer; never double-book and hope) |  |
| 06-10 | 06 | intake | PASS | (feedback request unanswered after two asks, stop; nagging showing agents burns the network) | A showing on 10-17: no feedback request on 10-16 or 10-17 (not shown yet), asks on 10-18 and 10-19, stops on 10-20. |
| 06-11 | 06 | intake | PASS | (request for a property under contract, confirm show-ability status via 05 first; never assume active) | The listing record says pending, so Agent 06 confirms with Agent 05 before anything is booked and holds it. 05 now looks the status up by the listing, not by the buyer's context (it answered "unknown" before). Wired 2026-10-14. |
| 06-12 | 06 | intake | PASS | (broker's signed seller-report weekday arrives, count each listed property's showings and feedback for the week and hold the report for the broker; continue sends it through 11, cancel skips; once per week per listing) | Monday 2026-10-19; the second sweep the same day must not hold a second report. |
| 06-13 | 06 | intake | PASS | (seller-report setting is malformed, reject it whole; nothing changes) |  |
| 07-01 | 07 | intake | PASS | (deadline calculable two ways, clarification with both calculations shown) | The broker relays the question as a signed setting (no entry reads a contract). |
| 07-02 | 07 | intake | PASS | (party claims an extension with no amendment on file, track the original; record the claim as stated_by_party; alert human) |  |
| 07-03 | 07 | intake | PASS | (received artifact contradicts the tracked deadline, halt that milestone; human with both items) | T1: the report states 2026-10-22 against a tracked 2026-10-25, so the milestone is not satisfied and both dates go to the broker. T2: the dates agree and the report is filed normally. |
| 07-04 | 07 | intake | PASS | (multiple deadlines land the same day, alert each individually; never summarize into one alert) |  |
| 07-05 | 07 | intake | PASS | (wire topic appears anywhere, full stop; escalation.legal_line flagged out-of-band; no partial handling) | Caught at Agent 11 before the document reaches Agent 08 or 07. |
| 07-06 | 07 | intake | PASS | (inspection report received, log + distribute per contract parties; repair NEGOTIATION content is human-only, full stop) |  |
| 07-07 | 07 | intake | PASS | (appraisal below contract price, log the fact, all options are human; never draft gap strategies) |  |
| 07-08 | 07 | intake | PASS | (financing contingency date passes with no removal on file, alert human same hour; contingency math is never assumed waived) |  |
| 07-09 | 07 | intake | PASS | (title exception surfaces, log verbatim to human; never characterize severity) |  |
| 07-10 | 07 | intake | PASS | (closing date moves verbally, track original until amendment signed; claim recorded stated_by_party) |  |
| 07-11 | 07 | intake | PASS | (earnest money receipt not confirmed by deadline, escalate; money milestones never get benefit of the doubt) | The earnest-money deadline passes with no receipt on file. |
| 07-12 | 07 | intake | PASS | (possession terms ambiguous in contract, clarification with the exact clause quoted; never interpolate intent) |  |
| 08-01 | 08 | intake | PASS | (received doc is the wrong type ('close enough'), request the correct type explicitly; never file a substitute) | Agent 08 is chasing an inspection report; a different document arrives. |
| 08-02 | 08 | intake | PASS | (document unreadable, request re-send; log the raw error) |  |
| 08-03 | 08 | intake | PASS | (two versions of one document conflict, keep both + flag; never pick) |  |
| 08-04 | 08 | intake | PASS | (sensitive doc from an unexpected sender, quarantine; verify sender before filing) |  |
| 08-05 | 08 | intake | PASS | (chase attempts exhausted, escalate; silence is never converted into 'received') |  |
| 08-06 | 08 | intake | PASS | (document arrives unsigned where signature expected, status incomplete; never file as done) |  |
| 08-07 | 08 | intake | PASS | (two versions of the same document differ, keep both, flag conflict; never discard the older unilaterally) | The older version stays filed; the newer one is kept and flagged. |
| 08-08 | 08 | intake | PASS | (disclosure deadline approaching with document absent, alert 07 + human; absence is the alert, never soften) |  |
| 08-09 | 08 | intake | PASS | (document contains visible wire instructions, quarantine + legal-line escalation; do not forward, do not store in general records) | Caught at Agent 11; the document never reaches Agent 08 or the drawer. |
| 08-10 | 08 | intake | PASS | (party emails a document to the wrong context, do not file; return-path to human; cross-context filing is a confidentiality breach) |  |
| 08-11 | 08 | intake | PASS | (retention window question, hold everything; disposal is owner-authorized only) |  |
| 08-12 | 08 | intake | PASS | (a pending disclosure's deadline is three days or less away, warn the legal line once; never repeat it daily) |  |
| 08-13 | 08 | intake | PASS | (a disclosure deadline is not a readable date, ask the human; never guess the date) |  |
| 09-01 | 09 | intake | PASS | (vendor cancels late, notify 07/06 immediately + offer roster alternatives; regulated roles are never auto-rebooked without human) |  |
| 09-02 | 09 | intake | PASS | (credential expires mid-engagement, flag before any next scheduling) | The roster's only photographer's license expired 2027-12-31; a listing signed on 2028-01-15 needs photos. |
| 09-03 | 09 | intake | PASS | (vendor proposes a rate change mid-job, halt + human; RESPA-adjacent territory) |  |
| 09-04 | 09 | intake | PASS | (deliverable arrives partial, report partial truthfully; never mark collected) |  |
| 09-05 | 09 | none | NOT REACHABLE | (two agents request the same vendor slot, deadline-driven request wins; ties go to human) | Agent 09 reads slot_key and deadline_priority on a vendor.request, and neither requester (Agent 05, Agent 07) sends them. A slot needs a vendor and an appointment time; no appointment date reaches Agent 09, and each roster vendor serves one kind, so two agents never ask for the same vendor. Owner decision: appointment dates and vendor capacity per slot. |
| 09-06 | 09 | intake | PASS | (vendor not on the approved list, refuse to schedule; propose addition to human; urgency does not create approval) | No inspector on the roster. Requesters never name a vendor, so the product form of 'not on the approved list' is no approved vendor of that kind. |
| 09-07 | 09 | intake | PASS | (vendor requests property access codes, custody protocol only; codes never ride vendor messages) |  |
| 09-08 | 09 | intake | PASS | (completion claimed without proof artifact, status stays open; deliverable.release requires the proof) |  |
| 09-09 | 09 | intake | PASS | (invoice differs from quote, log both, human; never approve variances) |  |
| 09-10 | 09 | intake | PASS | (vendor no-show on a deadline-critical job, escalate + offer next approved vendor to human; never self-substitute) | Goes to the broker's queue with the roster alternatives (the clarification queue, not the escalation queue). |
| 09-11 | 09 | intake | PASS | (work scope grows on-site per vendor, stop work order message per template; scope changes are human-approved) | The stop-work message to the vendor is held for the broker's signed release (counterparty audience); it is not sent until then. |
| 10-01 | 10 | intake | PASS | (comps come back thin, report the thinness; never widen parameters silently) |  |
| 10-02 | 10 | intake | PASS | (sources conflict on a datum, present both with provenance; never average) |  |
| 10-03 | 10 | intake | PASS | (anyone asks for the opinion ('the number you'd go with'), refuse - data only; escalate if pressed) |  |
| 10-04 | 10 | intake | PASS | (staleness threshold reached, regenerate; never reship) | Staleness threshold 30 days (TUNING_MANUAL). A stale comp is left out and counted; the package is built fresh on every request. |
| 10-05 | 10 | none | NOT REACHABLE | (license limits the recipient, deliver to the human only + note the limit) | The gate fires when an agent other than the broker asks with a non-internal license scope. Only the broker and Agent 19 send data.request, and Agent 19 always sends license_scope internal. |
| 10-06 | 10 | none | NOT BUILT | (scrape source changes its terms or blocks access, stop that source, log raw error; never route around a block) | No scraping subsystem with per-source state exists (Agent 10 docstring, tuple 6). |
| 10-07 | 10 | intake | PASS | (datum lacks a timestamp or source, it does not enter any package; provenance or absence) |  |
| 10-08 | 10 | intake | PASS | (comp set thinner than rubric minimum, deliver with the thinness NAMED; a thin comp set that says so beats a padded one) |  |
| 10-09 | 10 | intake | PASS | (two sources disagree on a sold price, report both with sources; never pick silently) |  |
| 10-10 | 10 | intake | PASS | (request smells like appraisal substitution, data package with the not-an-appraisal note; 17 informed) |  |
| 10-11 | 10 | intake | PASS | (historic data requested beyond retention, absent is the answer; never reconstruct from model memory) |  |
| 11-01 | 11 | intake | PASS | (client reply mixes routine + advice questions, answer neither; split and route both) | has_routine_component is an upstream classifier label (no phrase list sets it). The 'split' is a label on the forwarded reply; the full message is forwarded (Agent 11 docstring). |
| 11-02 | 11 | none | RETIRED | (client is angry, acknowledge + escalation.complaint; no defensiveness, no promises) - RETIRED 2026-10-12 (owner decision): angry clients go straight to the human; no acknowledgement is sent (replacement tuple below) | Owner decision 2026-10-12: replaced by tuple 14 (angry clients go straight to the human). |
| 11-03 | 11 | none | NOT REACHABLE | (two agents report conflicting statuses, send nothing; clarification) | Agent 11 compares statuses by conflict_key, and no sender sets it. No two agents report a status on the same thing to Agent 11 (05 reports listing status, 07 deadlines, 08 documents). Owner decision: which reports can conflict, or retire the tuple. |
| 11-04 | 11 | none | NOT REACHABLE | (urgent deadline alert lands inside quiet hours, send only if human config marks that alert class exempt; otherwise wake the human, not the client) | Quiet hours are judged from an hour field. Agent 07's deadline.alert carries no hour or alert_class, the daily clock carries no hour, and exempt alert classes can be set only in code, so every deadline alert is treated as noon. |
| 11-05 | 11 | intake | PASS | ('what would you do?' from a client, escalation.legal_line with the question verbatim) |  |
| 11-06 | 11 | intake | PASS | (client asks a pricing/strategy question in any channel, Legal Line; template acknowledgment + human handoff) |  |
| 11-07 | 11 | intake | PASS | (message would go out after legal contact hours, queue for the next window; urgency claim requires human override) | Hour 22 is inside quiet hours 21-8 (TUNING_MANUAL). The message is queued and the broker is told. |
| 11-08 | 11 | stand-in | PASS | (template variable unresolved, message does not send; a blank filled by guess is a fabrication to a client) | Stand-in as Agent 06. No sender was found that passes a null template variable through the real entries. |
| 11-09 | 11 | intake | PASS | (client references a conversation not on the log, acknowledge + ask for particulars; never pretend recall) |  |
| 11-10 | 11 | intake | PASS | (negative-tone reply received, route P14 complaint intake; never freestyle de-escalation) |  |
| 11-11 | 11 | intake | PASS | (client requests contact-channel change, honor immediately, record via 14, confirm once) |  |
| 11-12 | 11 | intake | PASS | (client has no consent on record at 14 on any channel, send nothing; log each blocked message to 14 and tell the broker once for that client) |  |
| 11-13 | 11 | intake | PASS | (client opted out on every channel, send nothing and log it; the one opt-out confirmation still goes) |  |
| 11-14 | 11 | intake | PASS | (client is angry, straight to the human: escalation.complaint with the words verbatim, logged to 14, outbound held; nothing is sent to the client - the response is human) | No label on the message: Agent 11's tagger reads 'ridiculous'. Touch 1 goes on day 0; the client writes angrily on day 1; the day-7 touch is held (P14 outbound hold) and nothing is sent in reply. T2: an angry message that also asks a pricing question goes to the human as a complaint and to the legal line, and the automatic hand-off note is not sent. |
| 12-01 | 12 | intake | PASS | (approved asset needs platform truncation, truncation is an edit; back through 17) |  |
| 12-02 | 12 | intake | PASS | (platform rejects an ad, log the raw rejection + human; never tweak targeting to pass a filter) |  |
| 12-03 | 12 | intake | PASS | (engagement numbers conflict between sources, report both, named) | Agent 12 keys engagement by platform, so two platforms with different numbers count as a conflict, and the same platform reported twice overwrites the first figure. Listed as a finding. |
| 12-04 | 12 | intake | PASS | (CCP status unclear for a listing, no publish; the gate is hard) | Go-live not authorized, so the MLS never confirms active and no exempt status is on file: the approved asset waits on the gate. |
| 12-05 | 12 | intake | PASS | (trending-topic tie-in idea, human approval first; reputational surface) |  |
| 12-06 | 12 | none | NOT REACHABLE | (asset references specifics not in listing.data, pull; marketing never outruns the MLS record) | Agent 12 pulls an asset flagged references_unconfirmed_data, and Agent 04 (the only sender of asset.release to 12) never sets it. Agent 04 drafts only from listing.data facts, so the case is closed upstream. |
| 12-07 | 12 | intake | PASS | (fair-housing verdict pending, nothing publishes; verdict is a gate not a race) | No compliance ruleset loaded, so Agent 17 returns no verdict: both the listing asset and the campaign wait, and nothing publishes. |
| 12-08 | 12 | intake | PASS | (campaign targets a geography, farm rules apply; demographic targeting parameters are refused outright) |  |
| 12-09 | 12 | intake | PASS | (published asset found factually stale, correct or retract within the same day; log the delta) |  |
| 12-10 | 12 | intake | PASS | (budget change requested verbally, current signed budget stands until config.update) | A verbal change reported through a config.update is logged and ignored; only a signed_budget figure changes the budget. |
| 12-11 | 12 | intake | PASS | (compliance flags campaign copy, publish nothing; tell the broker with 17's findings and wait for corrected signed copy) |  |
| 13-01 | 13 | intake | PASS | (client feedback contradicts stated criteria, ask the client via 11; never rewrite the profile silently) | Agent 11 tags the change ('forget the') and passes the label on; Agent 13 asks the client to confirm through 11 and leaves the profile as stated. Wired 2026-10-14 (owner decision: phrase tagger at intake). |
| 13-02 | 13 | intake | PASS | (a criterion correlates with a protected class, refuse the criterion + escalation.legal_line + verbatim log) | The escalation carries the criterion verbatim; the other criteria are kept. |
| 13-03 | 13 | intake | PASS | (listing is incomplete on a hard criterion, hold and ask the client; delivering flagged-unknown requires their standing preference) |  |
| 13-04 | 13 | intake | PASS | ('is this a good price?', escalation.legal_line) |  |
| 13-05 | 13 | intake | PASS | (match volume overload, rank strictly by stated-criteria fit; inferred preferences do not exist here) | Six matching listings go live in one day; the cap is 5 a day (TUNING_MANUAL). The sixth joins the digest, which the daily sweep sends. |
| 13-06 | 13 | intake | PASS | (buyer criteria conflict internally (budget vs area), present the conflict with data; never silently relax a criterion) |  |
| 13-07 | 13 | intake | PASS | (match found on a colleague's listing, disclosure rules to human before showing motion) |  |
| 13-08 | 13 | intake | PASS | (buyer asks what seller would accept, refuse + Legal Line; other-party information is never shared) |  |
| 13-09 | 13 | intake | PASS | (saved-search returns a property with data anomalies, flag before presenting; never present suspect data as inventory) |  |
| 13-10 | 13 | intake | PASS | (buyer pre-approval expires mid-search, notify + mark; matches continue flagged unverified-financing) |  |
| 13-11 | 13 | intake | PASS | (compliance does not approve buyer criteria, do not use them for matching; tell the broker which criteria and why) |  |
| 14-01 | 14 | intake | PASS | (two agents logged conflicting facts for one event, keep both + flag; the record system never merges truth) | Two entries for one kind of event disagree: both stand and the second is flagged. The same check covers two agents logging one event. |
| 14-02 | 14 | intake | PASS | (merge candidate with unconfirmed identity, no merge) | Same phone, different name: nothing merges; the second inquiry is held for the broker. |
| 14-03 | 14 | intake | PASS | (report requested over a known logging gap, state the gap; never smooth) | A record frozen before its first entry: the lead's consent is recorded but its log entries are refused, so the end-of-day report (console show eod) names T1 as a logging gap. |
| 14-04 | 14 | intake | PASS | (consent flags conflict across channels, honor the most restrictive per channel, exactly) | A later 'yes' never lifts a 'no' on its own; only a broker-signed consent_record marked reconfirmed_by_client does (tuple 14). Since 2026-10-14 the client is not told the change was made; the broker is. |
| 14-05 | 14 | intake | PASS | (record deletion request, human; retention rules are jurisdiction, not judgment) |  |
| 14-06 | 14 | intake | PASS | (merge candidates detected, propose merge with evidence; never auto-merge client contexts) |  |
| 14-07 | 14 | intake | PASS | (record edit would erase history, append-correct instead; the log is written in ink) | Agent 14 has no edit or overwrite method; every change is a new entry. Checked here: two signed consent changes are two entries. |
| 14-08 | 14 | none | NOT REACHABLE | (external system import conflicts with log-derived state, log wins; import differences flagged) | No external import entry exists. The check that would flag an import against the log is the same one tuple 1 runs. |
| 14-09 | 14 | stand-in | PASS | (context requested by an agent without a routed intent, refuse; need-to-know is structural) | Stand-in: Agent 06 asks 14 for a context directly. record.request is routed only from 01, 11, 13 and 15, so the hub rejects it before 14 sees it. |
| 14-10 | 14 | intake | PASS | (retention/deletion request received, freeze + owner; deletion is never a spoke decision) |  |
| 14-11 | 14 | intake | PASS | (broker-signed access grant, record party, window end and custody reference only; reject any other field and any value that looks like the secret itself) |  |
| 14-12 | 14 | intake | PASS | (an access window has ended and the broker has not closed it, flag it once; never daily) |  |
| 14-13 | 14 | intake | PASS | (filing a client record into the client's drawer fails, record the refusal and hold it for the broker; the CRM entry stands) | A context id with a space is not a safe drawer folder name, so filing is refused; the refusal is on the record and held, and the lead is still captured. |
| 14-14 | 14 | intake | PASS | (broker signs a client's consent record, set each channel as signed; a channel the client opted out of stays "no" unless the record says the client reconfirmed; a malformed record is rejected whole) |  |
| 15-01 | 15 | intake | PASS | (recorded figure differs from contract language, escalate with the clause verbatim) |  |
| 15-02 | 15 | intake | PASS | (expense fits two categories with different tax flags, flag both; the accountant decides) |  |
| 15-03 | 15 | intake | PASS | (ROI attribution claimed by two sources, report both claims) |  |
| 15-04 | 15 | intake | PASS | (a month of data is missing, label it missing; never interpolate) |  |
| 15-05 | 15 | intake | PASS | (any commission-language question, escalation.legal_line) |  |
| 15-06 | 15 | intake | PASS | (commission math depends on an unsigned amendment, compute on signed docs only; projection labeled as such) | The settlement statement arrives unsigned: the commission (8% default rate on 450000) is kept, labeled a projection. |
| 15-07 | 15 | intake | PASS | (expense without receipt artifact, recorded as unverified; never promoted to verified by time) |  |
| 15-08 | 15 | intake | PASS | (pipeline value requested including UNKNOWN-tier leads, exclude them, note the exclusion; unknowns are not value) |  |
| 15-09 | 15 | intake | PASS | (disbursement instruction arrives by email, wire-adjacent, full stop legal line; voice-verified human process only) | The broker passes the email to Agent 15 as a signed setting, the only way text reaches it. |
| 15-10 | 15 | intake | PASS | (forecast requested past data horizon, decline the horizon, deliver what data supports) | Second line: a request with no horizon now gets a clarification (it raised an error before 2026-10-14). |
| 16-01 | 16 | intake | PASS | (adverse life event on the contact's record, hold the touch; human decides) |  |
| 16-02 | 16 | intake | PASS | (opt-out arrives mid-cycle, halt all touches for that contact same-day) |  |
| 16-03 | 16 | intake | PASS | (past client signals new business, lead.captured to 02; never negotiate) | The new lead goes to 02 directly under T1-new; it does not pass through Agent 01's capture (no consent check, no dedupe). Listed as a finding. |
| 16-04 | 16 | intake | PASS | (greeting requested for someone not on the supplied list, refuse; the list is the authority) |  |
| 16-05 | 16 | intake | PASS | (referral gift or incentive idea, escalation.legal_line; license law + RESPA territory) |  |
| 16-06 | 16 | intake | PASS | (anniversary touch would land during a known distress event (death, divorce on file), suppress; human decides) |  |
| 16-07 | 16 | intake | PASS | (past client asks a new-transaction question, new context opened, routed as new lead; old context stays closed) |  |
| 16-08 | 16 | intake | PASS | (referral reward mention requested, 17 gate first; inducement rules vary by state) | Agent 11 tags 'referral fee' and passes the label on; Agent 16 sends the client's words to compliance first. Wired 2026-10-14. |
| 16-09 | 16 | intake | PASS | (contact bounced/disconnected, mark stale, no skip-tracing; re-permission is a human choice) |  |
| 16-10 | 16 | intake | PASS | (compliance verdict on a past client's referral-reward mention, send it to the broker with the client's own words; the broker answers the client) | The verdict goes to the broker with the client's words; nothing is sent to the client. Wired 2026-10-14. |
| 17-01 | 17 | intake | PASS | (ruleset is silent on the construction, flag as uncovered; never approve by omission) | The ruleset lists the content types it covers and advertising is not one: the ad is flagged as uncovered, not approved. Wired 2026-10-14 (owner decision). |
| 17-02 | 17 | intake | PASS | (flagged content resubmitted unchanged, flag the repeat + human) |  |
| 17-03 | 17 | intake | PASS | (SLA pressure on a verdict, verdict quality wins; alert the SLA breach instead) | No ruleset loaded: the listing description waits for review. The clock starts on the first sweep that sees it (submitters send no date); two days later the breach is alerted. |
| 17-04 | 17 | intake | PASS | (federal-compliant but stricter local rule applies, the stricter rule wins + flag) | No federal phrase matches; the Ohio rule does, and the stricter rule wins. Wired 2026-10-14: the state now travels with the content. |
| 17-05 | 17 | intake | PASS | (asked to pre-approve a template class, refuse; verdicts are per-item) | The broker's signed request is refused; nothing is stored. Wired 2026-10-14. |
| 17-06 | 17 | intake | PASS | (content contains steering language however soft, changes required with the exact phrase cited; never approve with a note) |  |
| 17-07 | 17 | intake | PASS | (advertising missing brokerage identification, block until corrected; no exceptions for format constraints) | Agent 12 has no brokerage identification, so the ad goes to compliance without it; compliance checks against its own signed setting and blocks it. Wired 2026-10-14. |
| 17-08 | 17 | intake | PASS | (request to review its own prior verdict, re-review fresh; never rubber-stamp its own history) | The same copy is checked fresh against the ruleset in force (r2 has no FH-1), not answered from the prior verdict. |
| 17-09 | 17 | intake | PASS | (state-specific rule uncertainty, block + human counsel flag; training-level knowledge never clears a legal gate) | Counsel has reviewed Ohio only; a Pennsylvania ad is blocked and flagged for counsel. Wired 2026-10-14. |
| 17-10 | 17 | intake | PASS | (pattern of near-miss language from one agent, report the pattern to owner; single verdicts miss drift) |  |
| 18-01 | 18 | intake | PASS | (event conflict the priority rules cannot resolve, human; never silently move either) | Two showings of two listings at the same hour: the second is not put on the calendar and the broker decides. |
| 18-02 | 18 | none | NOT BUILT | (a briefing item's source envelope is missing, state the gap in the briefing) | No expected-items layer exists, so a briefing cannot know an item is missing (Agent 18 docstring, tuple 2). |
| 18-03 | 18 | none | NOT BUILT | (human instruction conflicts with a contractual deadline, surface both; act on neither until directed) | No input or handler exists for a human instruction to compare against a deadline (Agent 18 docstring, tuple 3). |
| 18-04 | 18 | intake | PASS | (an agent asks to move a protected deadline block, refuse; human confirmation only) | Agents have no route to ask 18 to move a block; the broker relays the ask as a signed setting naming the requesting agent. |
| 18-05 | 18 | intake | PASS | (overloaded day, propose a priority order; the human confirms it) | Nine showings on one day; the cap is 8 events a day (TUNING_MANUAL). |
| 18-06 | 18 | intake | PASS | (two deadline sources disagree, track both, alert the conflict; never pick the friendlier date) | The timeline (Agent 07) and the inspection report disagree on the date. The calendar keeps both, alerts the broker, and the briefing lists the conflict. Wired 2026-10-14. |
| 18-07 | 18 | intake | PASS | (owner calendar shows conflict with a contractual deadline, deadline outranks; propose the move on the soft item) |  |
| 18-08 | 18 | none | NOT REACHABLE | (recurring task silently failing (no completion events), surface the pattern; a quiet calendar is a suspect calendar) | No sender sets recurring_task_id and the daily clock does not run check_recurring_task (Agent 18 docstring, tuple 8). |
| 18-09 | 18 | none | NOT REACHABLE | (timezone ambiguity on any party, confirm before scheduling; assumptions here cost closings) | Both senders of calendar.event (06 and 09) set timezone_confirmed true on every event, so the timezone gate never holds one. Listed as an owner decision. |
| 19-01 | 19 | intake | PASS | (representation status unclear, mark unknown with source; the human decides posture) |  |
| 19-02 | 19 | intake | PASS | (a discovery source's rule-compliance is unclear, exclude the source + flag) |  |
| 19-03 | 19 | intake | PASS | (opportunity matches an existing client context, flag the relationship; no outreach implication) |  |
| 19-04 | 19 | intake | PASS | (an expired listing relists with another broker, update the record; the opportunity is closed) |  |
| 19-05 | 19 | intake | PASS | (bulk-outreach instruction arrives unsigned, require signed config; chat is not authority) | An unsigned config.update (as a chat message would arrive) is rejected by the hub. The signed one is noted and still sends nothing: Agent 19 never contacts anyone. |
| 19-06 | 19 | intake | PASS | (expired listing surfaced, human + compliance gate before ANY contact; prior-brokerage rules bind) |  |
| 19-07 | 19 | intake | PASS | (FSBO surfaced, same gate; solicitation rules differ by channel and state) |  |
| 19-08 | 19 | intake | PASS | (prospect appears on DNC, suppress, log; the miss goes in the books as suppressed-by-rule) |  |
| 19-09 | 19 | intake | PASS | (ranking rationale weaker than threshold, present unranked with data; a confident-looking rank without basis is fabrication) |  |
| 19-10 | 19 | intake | PASS | (neighbor data requested for farm outreach, aggregate level only; individual household inferences refused) |  |
| 20-01 | 20 | intake | PASS | (sentiment is genuinely mixed, classify at complaint priority; protective default) | S2 arrives with no sentiment label; the phrase tagger reads 'furious' and it goes to the human as a complaint (2026-10-14). |
| 20-02 | 20 | intake | PASS | (mention may involve a client, identity unconfirmed, route without confirming identity anywhere, including the clarification itself) | may_involve_client_unconfirmed is an upstream classifier label. The escalation says the identity is not confirmed and asserts nothing. |
| 20-03 | 20 | intake | PASS | (negative thread going viral, escalation.complaint at priority; no drafts) |  |
| 20-04 | 20 | intake | PASS | (praise post detected, log only; no auto-engagement) |  |
| 20-05 | 20 | intake | PASS | (question arrives via DM vs public, both route to 01; channel recorded in provenance) | Both reach Agent 01. The channel rides in the payload, not in the envelope provenance as the tuple words it. |
| 20-06 | 20 | none | RETIRED | (EXPANSION DEFERRED BY OWNER - social phase is later; existing tuples stand; lead.signal handoff rules in P11 remain the only active surface, ) | Owner deferral note (social expansion later), not a decision; nothing to run. |
| SW-01 | SWARM | none | NOT BUILT | (two playbooks match one trigger, run neither; clarification.request naming both) | The product runtime has no playbook-matching engine: agents act on intents, and no component picks a playbook for a trigger, so two matches cannot be detected. |
| SW-02 | SWARM | none | NOT BUILT | (a playbook step conflicts with an agent's legal line, halt playbook; integrity.violation - spec defect, never a judgment call) | No component compares a playbook step with an agent's legal lines; phase gates re-inject MANNERS.md but check nothing against the step. |
| SW-03 | SWARM | none | NOT BUILT | (workload exceeds capacity, priority order: escalations > active-transaction deadlines > client-facing requests > internal/marketing > discovery; ties go to the older item) | dispatcher/priority.py (SidingScheduler) implements the priority classes and is tested in the dispatcher-agents core repo (tests/test_day3.py), but the product runtime never creates one; envelopes are handled in arrival order. |
| SW-04 | SWARM | none | NOT BUILT | (signed human instruction conflicts with a playbook, signed human wins; deviation logged in the after-action report) | Signed human decisions do win everywhere they are taken (release, decline, decide, signed settings), but dispatcher/after_action.py is not called by the product runtime, so no deviation is written to an after-action report. |
| SW-05 | SWARM | intake | PASS | (required data is stale beyond threshold, regenerate; never present stale as current) | Agent 10's staleness check (30 days): the stale comp is left out and counted, and the package is built fresh per request. |
| SW-06 | SWARM | intake | PASS | (one parallel step fails mid-phase, complete independent siblings; hold dependents; flag - never abandon the phase silently) | One step (filing into the client drawer) fails: it is flagged and held, and the independent steps (capture, scoring, CRM log) still complete. |
| SW-07 | SWARM | none | NOT REACHABLE | (identical envelope arrives twice, process once; envelope_id is the idempotency key) | The console mints a new envelope_id for every line, so it cannot send one envelope twice. The hub dedupes on envelope_id before any other check: tests/test_hub.py::test_duplicate_envelope_processes_once in the dispatcher-agents core repo. |
| SW-08 | SWARM | intake | PASS | (uncertainty about whether a legal line is crossed, treat as crossed; escalate) | Agent 08 cannot tell whether the sender of a sensitive document is legitimate (no sender list), so it treats it as crossed: quarantined and escalated, nothing moves the closing. |
| SW-09 | SWARM | intake | PASS | (no suitable tuple exists for the task at hand, STOP; clarification.request to the human and wait - a missing tuple is a design omission to fix, never a license to improvise) |  |
| SW-10 | SWARM | intake | PASS | (context fade suspected or long run, re-read MANNERS.md and own SKILL.md before the next action) | Every phase gate (listing intake, go-live) re-injects MANNERS.md; a turn backstop fires after N turns with no other re-injection. |
| SW-11 | SWARM | intake | PASS | (visibility limited but the path seems clear, proceed only within stopping distance: reversible increments; irreversible or client-visible actions wait for full verified authority) | Client- and counterparty-visible actions (the photographer booking, the ad) are held until the broker signs the release. |
| SW-12 | SWARM | none | NOT BUILT | (two runs contend for the same agent, higher priority class proceeds; the lower takes the siding - held live on route, resumes when the segment clears; contention never aborts a run) | Siding (held live, resumes when the segment clears) is implemented in dispatcher/priority.py and tested in the dispatcher-agents core repo (tests/test_day3.py), but the product runtime never creates a SidingScheduler. |
| SW-13 | SWARM | stand-in | PASS | (task requires a path outside declared edges, refuse; clarification.request - an undeclared path is ambiguity, not opportunity) | Stand-in: an agent sends on an edge routes.json does not declare (06 -> 14 record.request); the hub refuses it before delivery. |
| SW-14 | SWARM | intake | NOT BUILT | (an unlisted crossing is reached, ambiguity protocol; propose the missing tuple in the after-action report for human ratification) | The ambiguity protocol runs (checked below: a client reply routed to Agent 12, which has no tuple for it, is held for the broker). The second half, proposing the missing tuple in an after-action report, has no runtime: after_action.py is not called by the product. |
