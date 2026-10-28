# TUPLE_MAP.md - the tuples sorted by what they protect

<!-- written by tools/gen_tuple_map.py from synth/tuples/TUPLE_MAP.json, the tuple specs and identity/playbooks.json; edit those, not this page -->

**ACCEPTED 2026-10-21 by Jeff Phillips as placed (every tuple read and placed by hand by Claude; the owner's corrections are made here).**

A tuple is one rule for one hard case: the situation, what the agent does, and what it must never do. There are 273 (268 in force, 5 retired). Each is sorted below by what it protects (category) and how bad a failure would be (tier).

Columns: **status** is RUNS (it runs through the console and is checked), NOT REACHABLE (nothing in the product can produce the situation yet), NOT BUILT (the agent does not do it yet) or RETIRED. **Playbooks** are the playbooks whose agents include the tuple's agent, so where the rule can fire; it is not a record of a run firing it.

## Categories

- **Legal line** - things the system must never do on its own (price or legal opinion, fair housing, commission wording, trust and escrow, wire instructions, compliance gates); it hands them to you word for word
- **Consent and contact** - who may be contacted, how, when and how often, and who may see a client's information
- **Truth of the record** - missing, stale, unverified or contradicting facts; unknown stays unknown, nothing is made up
- **Your authority** - only what you signed changes things: signatures, identity, property access, money approvals, forgery
- **Choices that are yours** - two of something or an unclear case; the system holds and asks, it never picks the likely one
- **Time and reliability** - deadlines, overdue escalations, the clock, outages, capacity; when something breaks it stops loudly
- **People moments** - an angry, upset or vulnerable person, a public complaint; a person answers, not a template

## Tiers

- **Tier 1**: a failure could cost a license, money or a lawsuit
- **Tier 2**: a failure could hurt a client relationship or your reputation
- **Tier 3**: a failure slows the work

## Counts (tuples in force)

| Category | Tier 1 | Tier 2 | Tier 3 | Total | Runs | Not reachable | Not built |
|---|---|---|---|---|---|---|---|
| Legal line | 51 | 12 | 0 | 63 | 60 | 2 | 1 |
| Consent and contact | 18 | 10 | 1 | 29 | 28 | 1 | 0 |
| Truth of the record | 5 | 52 | 16 | 73 | 64 | 6 | 3 |
| Your authority | 17 | 7 | 1 | 25 | 25 | 0 | 0 |
| Choices that are yours | 4 | 18 | 12 | 34 | 28 | 5 | 1 |
| Time and reliability | 9 | 17 | 6 | 32 | 30 | 2 | 0 |
| People moments | 1 | 8 | 3 | 12 | 11 | 1 | 0 |
| **All** | 105 | 124 | 39 | 268 | 246 | 17 | 5 |

## Legal line

Things the system must never do on its own (price or legal opinion, fair housing, commission wording, trust and escrow, wire instructions, compliance gates); it hands them to you word for word.

### Tier 1 (51)

| Tuple | Rule | Status | Playbooks |
|---|---|---|---|
| 03-16 | compliance flags a sequence, keep it paused and send nothing; tell the broker with 17's findings and wait for a corrected signed sequence | RUNS | P11, P12, P21 |
| 04-03 | human-supplied copy appears to violate fair housing, flag to 17 and the human; never silently rewrite | RUNS | P01, P02, P04 |
| 04-05 | superlatives requested ('best block in town'), decline in copy; characterization is a steering vector | RUNS | P01, P02, P04 |
| 04-07 | seller requests language naming schools-quality or neighborhood demographics, refuse; fair-housing gate; 17 verdict required regardless | RUNS | P01, P02, P04 |
| 04-08 | photo shows an item revealing protected-class information, flag to human before any use | RUNS | P01, P02, P04 |
| 04-10 | 17 returns content.verdict requiring changes, apply exactly; no negotiation with the compliance agent | RUNS | P01, P02, P04 |
| 04-14 | compliance flags a phrase inside model remarks, remove exactly the sentence carrying it and resubmit | NOT REACHABLE | P01, P02, P04 |
| 05-09 | comp-offer field present anywhere, leave blank per 8/17/24 rules; flag any request to fill it | RUNS | P01, P02, P03, P05, P18, P20, P23 |
| 05-11 | withdrawal requested while under contract, halt; 17 + human; status math on a live contract is never autonomous | RUNS | P01, P02, P03, P05, P18, P20, P23 |
| 07-05 | wire topic appears anywhere, full stop; escalation.legal_line flagged out-of-band; no partial handling | RUNS | P03, P08, P09 |
| 07-06 | inspection report received, log + distribute per contract parties; repair NEGOTIATION content is human-only, full stop | RUNS | P03, P08, P09 |
| 07-07 | appraisal below contract price, log the fact, all options are human; never draft gap strategies | RUNS | P03, P08, P09 |
| 07-09 | title exception surfaces, log verbatim to human; never characterize severity | RUNS | P03, P08, P09 |
| 08-09 | document contains visible wire instructions, quarantine + legal-line escalation; do not forward, do not store in general records | RUNS | P03, P08, P09 |
| 08-11 | retention window question, hold everything; disposal is owner-authorized only | RUNS | P03, P08, P09 |
| 09-03 | vendor proposes a rate change mid-job, halt + human; RESPA-adjacent territory | RUNS | P01, P09, P19, P20 |
| 10-03 | anyone asks for the opinion ('the number you'd go with'), refuse - data only; escalate if pressed | RUNS | P02, P06, P12, P15, P16, P18, P20, P21, P22, P23, P24 |
| 10-05 | license limits the recipient, deliver to the human only + note the limit | NOT REACHABLE | P02, P06, P12, P15, P16, P18, P20, P21, P22, P23, P24 |
| 10-10 | request smells like appraisal substitution, data package with the not-an-appraisal note; 17 informed | RUNS | P02, P06, P12, P15, P16, P18, P20, P21, P22, P23, P24 |
| 11-01 | client reply mixes routine + advice questions, answer neither; split and route both | RUNS | P01, P02, P03, P04, P05, P06, P07, P08, P09, P11, P13, P14, P18, P22, P23, P24 |
| 11-05 | 'what would you do?' from a client, escalation.legal_line with the question verbatim | RUNS | P01, P02, P03, P04, P05, P06, P07, P08, P09, P11, P13, P14, P18, P22, P23, P24 |
| 11-06 | client asks a pricing/strategy question in any channel, Legal Line; template acknowledgment + human handoff | RUNS | P01, P02, P03, P04, P05, P06, P07, P08, P09, P11, P13, P14, P18, P22, P23, P24 |
| 12-01 | approved asset needs platform truncation, truncation is an edit; back through 17 | RUNS | P01, P02, P03, P04, P05, P10, P12 |
| 12-04 | CCP status unclear for a listing, no publish; the gate is hard | RUNS | P01, P02, P03, P04, P05, P10, P12 |
| 12-07 | fair-housing verdict pending, nothing publishes; verdict is a gate not a race | RUNS | P01, P02, P03, P04, P05, P10, P12 |
| 12-08 | campaign targets a geography, farm rules apply; demographic targeting parameters are refused outright | RUNS | P01, P02, P03, P04, P05, P10, P12 |
| 12-11 | compliance flags campaign copy, publish nothing; tell the broker with 17's findings and wait for corrected signed copy | RUNS | P01, P02, P03, P04, P05, P10, P12 |
| 13-02 | a criterion correlates with a protected class, refuse the criterion + escalation.legal_line + verbatim log | RUNS | P01, P06, P07, P22, P24 |
| 13-04 | 'is this a good price?', escalation.legal_line | RUNS | P01, P06, P07, P22, P24 |
| 13-07 | match found on a colleague's listing, disclosure rules to human before showing motion | RUNS | P01, P06, P07, P22, P24 |
| 13-08 | buyer asks what seller would accept, refuse + Legal Line; other-party information is never shared | RUNS | P01, P06, P07, P22, P24 |
| 13-11 | compliance does not approve buyer criteria, do not use them for matching; tell the broker which criteria and why | RUNS | P01, P06, P07, P22, P24 |
| 14-05 | record deletion request, human; retention rules are jurisdiction, not judgment | RUNS | P01, P02, P03, P04, P05, P06, P07, P10, P11, P13, P14, P16, P17, P18, P19, P20, P21, P22, P23, P24 |
| 14-10 | retention/deletion request received, freeze + owner; deletion is never a spoke decision | RUNS | P01, P02, P03, P04, P05, P06, P07, P10, P11, P13, P14, P16, P17, P18, P19, P20, P21, P22, P23, P24 |
| 15-01 | recorded figure differs from contract language, escalate with the clause verbatim | RUNS | P09, P10, P16, P17, P23 |
| 15-05 | any commission-language question, escalation.legal_line | RUNS | P09, P10, P16, P17, P23 |
| 15-09 | disbursement instruction arrives by email, wire-adjacent, full stop legal line; voice-verified human process only | RUNS | P09, P10, P16, P17, P23 |
| 16-05 | referral gift or incentive idea, escalation.legal_line; license law + RESPA territory | RUNS | P10, P13 |
| 16-08 | referral reward mention requested, 17 gate first; inducement rules vary by state | RUNS | P10, P13 |
| 16-10 | compliance verdict on a past client's referral-reward mention, send it to the broker with the client's own words; the broker answers the client | RUNS | P10, P13 |
| 17-01 | ruleset is silent on the construction, flag as uncovered; never approve by omission | RUNS | P01, P02, P04, P06, P12, P14, P18, P21, P22, P24 |
| 17-04 | federal-compliant but stricter local rule applies, the stricter rule wins + flag | RUNS | P01, P02, P04, P06, P12, P14, P18, P21, P22, P24 |
| 17-05 | asked to pre-approve a template class, refuse; verdicts are per-item | RUNS | P01, P02, P04, P06, P12, P14, P18, P21, P22, P24 |
| 17-06 | content contains steering language however soft, changes required with the exact phrase cited; never approve with a note | RUNS | P01, P02, P04, P06, P12, P14, P18, P21, P22, P24 |
| 17-07 | advertising missing brokerage identification, block until corrected; no exceptions for format constraints | RUNS | P01, P02, P04, P06, P12, P14, P18, P21, P22, P24 |
| 17-09 | state-specific rule uncertainty, block + human counsel flag; training-level knowledge never clears a legal gate | RUNS | P01, P02, P04, P06, P12, P14, P18, P21, P22, P24 |
| 19-06 | expired listing surfaced, human + compliance gate before ANY contact; prior-brokerage rules bind | RUNS | P12, P16, P24 |
| 19-07 | FSBO surfaced, same gate; solicitation rules differ by channel and state | RUNS | P12, P16, P24 |
| 19-10 | neighbor data requested for farm outreach, aggregate level only; individual household inferences refused | RUNS | P12, P16, P24 |
| SW-02 | a playbook step conflicts with an agent's legal line, halt playbook; integrity.violation - spec defect, never a judgment call | RUNS | all |
| SW-08 | uncertainty about whether a legal line is crossed, treat as crossed; escalate | RUNS | all |

### Tier 2 (12)

| Tuple | Rule | Status | Playbooks |
|---|---|---|---|
| 01-13 | inquiry is about a property this brokerage does not list, log + human; never redirect to another brokerage unprompted | RUNS | P04, P05, P11, P12 |
| 03-11 | contact asks a substantive question from inside a drip, out of sequence, route to 11 for a gated human-reviewed reply | RUNS | P11, P12, P21 |
| 04-15 | compliance flags a phrase this agent cannot find in its draft, hold for the broker; never resubmit the same draft | RUNS | P01, P02, P04 |
| 10-06 | scrape source changes its terms or blocks access, stop that source, log raw error; never route around a block | NOT BUILT | P02, P06, P12, P15, P16, P18, P20, P21, P22, P23, P24 |
| 12-02 | platform rejects an ad, log the raw rejection + human; never tweak targeting to pass a filter | RUNS | P01, P02, P03, P04, P05, P10, P12 |
| 13-05 | match volume overload, rank strictly by stated-criteria fit; inferred preferences do not exist here | RUNS | P01, P06, P07, P22, P24 |
| 16-03 | past client signals new business, lead.captured to 02; never negotiate | RUNS | P10, P13 |
| 17-02 | flagged content resubmitted unchanged, flag the repeat + human | RUNS | P01, P02, P04, P06, P12, P14, P18, P21, P22, P24 |
| 17-03 | SLA pressure on a verdict, verdict quality wins; alert the SLA breach instead | RUNS | P01, P02, P04, P06, P12, P14, P18, P21, P22, P24 |
| 17-08 | request to review its own prior verdict, re-review fresh; never rubber-stamp its own history | RUNS | P01, P02, P04, P06, P12, P14, P18, P21, P22, P24 |
| 17-10 | pattern of near-miss language from one agent, report the pattern to owner; single verdicts miss drift | RUNS | P01, P02, P04, P06, P12, P14, P18, P21, P22, P24 |
| 19-02 | a discovery source's rule-compliance is unclear, exclude the source + flag | RUNS | P12, P16, P24 |


## Consent and contact

Who may be contacted, how, when and how often, and who may see a client's information.

### Tier 1 (18)

| Tuple | Rule | Status | Playbooks |
|---|---|---|---|
| 01-02 | prospect refuses consent, capture the lead, mark no-consent; downstream messaging stays off | RUNS | P04, P05, P11, P12 |
| 01-07 | caller refuses consent recording, capture contact only, mark no-consent; NO nurture entry, human informed | RUNS | P04, P05, P11, P12 |
| 01-08 | lead arrives on the DNC list, log source and suppress outreach; human notified; the list wins over the opportunity | RUNS | P04, P05, P11, P12 |
| 01-11 | minor or apparent minor inquiring, capture nothing beyond the fact of contact; human immediately | RUNS | P04, P05, P11, P12 |
| 01-15 | lead asks to not be contacted again mid-capture, suppression immediately, confirmation once, records updated everywhere via 14 | RUNS | P04, P05, P11, P12 |
| 03-02 | ambiguous opt-out ('stop sending so many'), treat as frequency complaint: reduce + confirm; an explicit 'stop' is a full opt-out | RUNS | P11, P12, P21 |
| 03-06 | contact replies STOP or equivalent, suppression across ALL channels immediately; confirmation only if channel rules allow | RUNS | P11, P12, P21 |
| 03-07 | sequence step lands on a legal holiday or outside contact hours, shift to next legal window; never send anyway | RUNS | P11, P12, P21 |
| 08-10 | party emails a document to the wrong context, do not file; return-path to human; cross-context filing is a confidentiality breach | RUNS | P03, P08, P09 |
| 11-07 | message would go out after legal contact hours, queue for the next window; urgency claim requires human override | RUNS | P01, P02, P03, P04, P05, P06, P07, P08, P09, P11, P13, P14, P18, P22, P23, P24 |
| 11-12 | client has no consent on record at 14 on any channel, send nothing; log each blocked message to 14 and tell the broker once for that client | RUNS | P01, P02, P03, P04, P05, P06, P07, P08, P09, P11, P13, P14, P18, P22, P23, P24 |
| 11-13 | client opted out on every channel, send nothing and log it; the one opt-out confirmation still goes | RUNS | P01, P02, P03, P04, P05, P06, P07, P08, P09, P11, P13, P14, P18, P22, P23, P24 |
| 14-04 | consent flags conflict across channels, honor the most restrictive per channel, exactly | RUNS | P01, P02, P03, P04, P05, P06, P07, P10, P11, P13, P14, P16, P17, P18, P19, P20, P21, P22, P23, P24 |
| 14-09 | context requested by an agent without a routed intent, refuse; need-to-know is structural | RUNS | P01, P02, P03, P04, P05, P06, P07, P10, P11, P13, P14, P16, P17, P18, P19, P20, P21, P22, P23, P24 |
| 14-14 | broker signs a client's consent record, set each channel as signed; a channel the client opted out of stays "no" unless the record says the client reconfirmed; a malformed record is rejected whole | RUNS | P01, P02, P03, P04, P05, P06, P07, P10, P11, P13, P14, P16, P17, P18, P19, P20, P21, P22, P23, P24 |
| 16-02 | opt-out arrives mid-cycle, halt all touches for that contact same-day | RUNS | P10, P13 |
| 19-08 | prospect appears on DNC, suppress, log; the miss goes in the books as suppressed-by-rule | RUNS | P12, P16, P24 |
| 20-02 | mention may involve a client, identity unconfirmed, route without confirming identity anywhere, including the clarification itself | RUNS | P11, P14 |

### Tier 2 (10)

| Tuple | Rule | Status | Playbooks |
|---|---|---|---|
| 03-01 | lead replies mid-sequence, pause the sequence; route the reply; never auto-continue over a reply | RUNS | P11, P12, P21 |
| 03-05 | engagement spike detected, rescore via 02; never convert a signal into direct outreach yourself | RUNS | P11, P12, P21 |
| 03-08 | engagement spike mid-sequence, pause sequence + lead.rescored to 02; never keep dripping on a hot signal | RUNS | P11, P12, P21 |
| 03-15 | lead opted out or its sequence is paused, no re-score | RUNS | P11, P12, P21 |
| 06-05 | same-day showing request on occupied property, minimum-notice rules still apply; occupancy is never squeezed | RUNS | P01, P04, P07, P18, P19, P22 |
| 06-07 | showing request inside occupied-home notice window, offer first legal slot; never ask seller to waive notice unprompted | RUNS | P01, P04, P07, P18, P19, P22 |
| 11-04 | urgent deadline alert lands inside quiet hours, send only if human config marks that alert class exempt; otherwise wake the human, not the client | NOT REACHABLE | P01, P02, P03, P04, P05, P06, P07, P08, P09, P11, P13, P14, P18, P22, P23, P24 |
| 11-11 | client requests contact-channel change, honor immediately, record via 14, confirm once | RUNS | P01, P02, P03, P04, P05, P06, P07, P08, P09, P11, P13, P14, P18, P22, P23, P24 |
| 16-04 | greeting requested for someone not on the supplied list, refuse; the list is the authority | RUNS | P10, P13 |
| 16-09 | contact bounced/disconnected, mark stale, no skip-tracing; re-permission is a human choice | RUNS | P10, P13 |

### Tier 3 (1)

| Tuple | Rule | Status | Playbooks |
|---|---|---|---|
| 06-10 | feedback request unanswered after two asks, stop; nagging showing agents burns the network | RUNS | P01, P04, P07, P18, P19, P22 |


## Truth of the record

Missing, stale, unverified or contradicting facts; unknown stays unknown, nothing is made up.

### Tier 1 (5)

| Tuple | Rule | Status | Playbooks |
|---|---|---|---|
| 07-02 | party claims an extension with no amendment on file, track the original; record the claim as stated_by_party; alert human | RUNS | P03, P08, P09 |
| 07-03 | received artifact contradicts the tracked deadline, halt that milestone; human with both items | RUNS | P03, P08, P09 |
| 07-10 | closing date moves verbally, track original until amendment signed; claim recorded stated_by_party | RUNS | P03, P08, P09 |
| 14-07 | record edit would erase history, append-correct instead; the log is written in ink | RUNS | P01, P02, P03, P04, P05, P06, P07, P10, P11, P13, P14, P16, P17, P18, P19, P20, P21, P22, P23, P24 |
| 15-06 | commission math depends on an unsigned amendment, compute on signed docs only; projection labeled as such | RUNS | P09, P10, P16, P17, P23 |

### Tier 2 (52)

| Tuple | Rule | Status | Playbooks |
|---|---|---|---|
| 00-08 | spoke acks but its trace is absent, result tainted at ingestion; integrity queue; the ack stands, the CONTENT is quarantined | NOT REACHABLE | all |
| 01-01 | multiple inbound simultaneously, order: live call > text > web form; capture all, drop none | RUNS | P04, P05, P11, P12 |
| 01-05 | possible duplicate identity unconfirmed, record.request first; still unconfirmed = new context + flag, never merge | RUNS | P04, P05, P11, P12 |
| 01-10 | lead claims prior relationship with the agent, capture claim as stated_by_party; human confirms before any history is assumed | RUNS | P04, P05, P11, P12 |
| 01-14 | voicemail transcription confidence low, mark unknown; never tier on a garbled transcript | RUNS | P04, P05, P11, P12 |
| 02-02 | rubric version missing or unreadable, halt scoring; clarification - never score from memory of the rubric | RUNS | P04, P11, P13, P21 |
| 02-07 | financing letter present but expired, treat as no financing verification; stated_by_party at best | RUNS | P04, P11, P13, P21 |
| 02-10 | lead's stated budget conflicts with pre-approval doc, doc wins for scoring; conflict logged verbatim | RUNS | P04, P11, P13, P21 |
| 02-12 | all rubric inputs unknown, tier is UNKNOWN not COLD; unknown is not a low score, it is absent data | RUNS | P04, P11, P13, P21 |
| 02-15 | decision engine returns a tier this agent does not recognize, treat it as below the floor and hold | NOT REACHABLE | P04, P11, P13, P21 |
| 04-01 | photos contradict the data sheet, halt the asset; clarification with both artifacts attached | RUNS | P01, P02, P04 |
| 04-02 | a feature cannot be verified, omit it; never hedge with 'may include' | RUNS | P01, P02, P04 |
| 04-06 | square footage differs between tax record and seller claim, publish the verifiable source, note the discrepancy to human; never average | RUNS | P01, P02, P04 |
| 04-09 | feature cannot be verified (roof age, HVAC year), include only as per-seller with attribution or omit; no bare claims | RUNS | P01, P02, P04 |
| 04-13 | model draft has no reasoning, exceeds the MLS limit, or contains a number not in the data, do not use it; draft by rules and record why | NOT REACHABLE | P01, P02, P04 |
| 05-01 | supplied data has no valid MLS field, clarification; never approximate into the wrong field | RUNS | P01, P02, P03, P05, P18, P20, P23 |
| 05-02 | syndicated portal shows different data than MLS, correct the source record, then re-verify every portal | NOT BUILT | P01, P02, P03, P05, P18, P20, P23 |
| 05-04 | portal still stale after the verification window, log + notify human; never mark complete | NOT BUILT | P01, P02, P03, P05, P18, P20, P23 |
| 05-07 | MLS rejects an entry on a rule, log raw rejection, human; never adjust data to pass validation | NOT BUILT | P01, P02, P03, P05, P18, P20, P23 |
| 05-10 | listing data and marketing asset disagree, MLS record is truth; asset.release corrected version; discrepancy logged | RUNS | P01, P02, P03, P05, P18, P20, P23 |
| 06-11 | request for a property under contract, confirm show-ability status via 05 first; never assume active | RUNS | P01, P04, P07, P18, P19, P22 |
| 08-01 | received doc is the wrong type ('close enough'), request the correct type explicitly; never file a substitute | RUNS | P03, P08, P09 |
| 08-06 | document arrives unsigned where signature expected, status incomplete; never file as done | RUNS | P03, P08, P09 |
| 08-13 | a disclosure deadline is not a readable date, ask the human; never guess the date | RUNS | P03, P08, P09 |
| 09-04 | deliverable arrives partial, report partial truthfully; never mark collected | RUNS | P01, P09, P19, P20 |
| 09-08 | completion claimed without proof artifact, status stays open; deliverable.release requires the proof | RUNS | P01, P09, P19, P20 |
| 10-01 | comps come back thin, report the thinness; never widen parameters silently | RUNS | P02, P06, P12, P15, P16, P18, P20, P21, P22, P23, P24 |
| 10-02 | sources conflict on a datum, present both with provenance; never average | RUNS | P02, P06, P12, P15, P16, P18, P20, P21, P22, P23, P24 |
| 10-04 | staleness threshold reached, regenerate; never reship | RUNS | P02, P06, P12, P15, P16, P18, P20, P21, P22, P23, P24 |
| 10-07 | datum lacks a timestamp or source, it does not enter any package; provenance or absence | RUNS | P02, P06, P12, P15, P16, P18, P20, P21, P22, P23, P24 |
| 10-08 | comp set thinner than rubric minimum, deliver with the thinness NAMED; a thin comp set that says so beats a padded one | RUNS | P02, P06, P12, P15, P16, P18, P20, P21, P22, P23, P24 |
| 10-09 | two sources disagree on a sold price, report both with sources; never pick silently | RUNS | P02, P06, P12, P15, P16, P18, P20, P21, P22, P23, P24 |
| 10-11 | historic data requested beyond retention, absent is the answer; never reconstruct from model memory | RUNS | P02, P06, P12, P15, P16, P18, P20, P21, P22, P23, P24 |
| 11-08 | template variable unresolved, message does not send; a blank filled by guess is a fabrication to a client | RUNS | P01, P02, P03, P04, P05, P06, P07, P08, P09, P11, P13, P14, P18, P22, P23, P24 |
| 11-09 | client references a conversation not on the log, acknowledge + ask for particulars; never pretend recall | RUNS | P01, P02, P03, P04, P05, P06, P07, P08, P09, P11, P13, P14, P18, P22, P23, P24 |
| 12-06 | asset references specifics not in listing.data, pull; marketing never outruns the MLS record | NOT REACHABLE | P01, P02, P03, P04, P05, P10, P12 |
| 12-09 | published asset found factually stale, correct or retract within the same day; log the delta | RUNS | P01, P02, P03, P04, P05, P10, P12 |
| 13-09 | saved-search returns a property with data anomalies, flag before presenting; never present suspect data as inventory | RUNS | P01, P06, P07, P22, P24 |
| 13-10 | buyer pre-approval expires mid-search, notify + mark; matches continue flagged unverified-financing | RUNS | P01, P06, P07, P22, P24 |
| 14-01 | two agents logged conflicting facts for one event, keep both + flag; the record system never merges truth | RUNS | P01, P02, P03, P04, P05, P06, P07, P10, P11, P13, P14, P16, P17, P18, P19, P20, P21, P22, P23, P24 |
| 14-02 | merge candidate with unconfirmed identity, no merge | RUNS | P01, P02, P03, P04, P05, P06, P07, P10, P11, P13, P14, P16, P17, P18, P19, P20, P21, P22, P23, P24 |
| 14-03 | report requested over a known logging gap, state the gap; never smooth | NOT REACHABLE | P01, P02, P03, P04, P05, P06, P07, P10, P11, P13, P14, P16, P17, P18, P19, P20, P21, P22, P23, P24 |
| 14-06 | merge candidates detected, propose merge with evidence; never auto-merge client contexts | RUNS | P01, P02, P03, P04, P05, P06, P07, P10, P11, P13, P14, P16, P17, P18, P19, P20, P21, P22, P23, P24 |
| 14-08 | external system import conflicts with log-derived state, log wins; import differences flagged | NOT REACHABLE | P01, P02, P03, P04, P05, P06, P07, P10, P11, P13, P14, P16, P17, P18, P19, P20, P21, P22, P23, P24 |
| 15-04 | a month of data is missing, label it missing; never interpolate | RUNS | P09, P10, P16, P17, P23 |
| 15-07 | expense without receipt artifact, recorded as unverified; never promoted to verified by time | RUNS | P09, P10, P16, P17, P23 |
| 15-08 | pipeline value requested including UNKNOWN-tier leads, exclude them, note the exclusion; unknowns are not value | RUNS | P09, P10, P16, P17, P23 |
| 15-10 | forecast requested past data horizon, decline the horizon, deliver what data supports | RUNS | P09, P10, P16, P17, P23 |
| 18-02 | a briefing item's source envelope is missing, state the gap in the briefing | RUNS | P01, P03, P07, P08, P09, P15, P16, P17, P19, P20 |
| 19-01 | representation status unclear, mark unknown with source; the human decides posture | RUNS | P12, P16, P24 |
| 19-09 | ranking rationale weaker than threshold, present unranked with data; a confident-looking rank without basis is fabrication | RUNS | P12, P16, P24 |
| SW-05 | required data is stale beyond threshold, regenerate; never present stale as current | RUNS | all |

### Tier 3 (16)

| Tuple | Rule | Status | Playbooks |
|---|---|---|---|
| 01-04 | volunteered info beyond schema fields, record verbatim in notes payload; never interpret it into fields | RUNS | P04, P05, P11, P12 |
| 01-09 | same person inquires on two properties, one context per person, both interests recorded inside it; never two contexts | RUNS | P04, P05, P11, P12 |
| 01-12 | lead supplies obviously false contact data, record verbatim with a validity flag; never 'correct' it by guess | RUNS | P04, P05, P11, P12 |
| 02-04 | stated urgency conflicts with financing signals, weight verifiable financing over stated urgency; log the conflict | RUNS | P04, P11, P13, P21 |
| 02-16 | lead goes to nurture, send its scoring inputs with it so Lead Nurture can re-score it on the cadence | RUNS | P04, P11, P13, P21 |
| 03-12 | a nurtured lead's re-score interval has passed, ask 02 to re-score with the stated timeline counted down by the days elapsed; never invent any other input | RUNS | P11, P12, P21 |
| 03-13 | a re-score did not return the lead to nurture, it left WARM; take it out of the re-score pool and log it to 14 | RUNS | P11, P12, P21 |
| 03-14 | a re-score keeps the lead WARM on the same sequence, the sequence continues; never restart it from day 0 | RUNS | P11, P12, P21 |
| 04-04 | space forces cuts, cut adjectives before facts; source attributions are never cut | RUNS | P01, P02, P04 |
| 04-11 | remarks exceed MLS field limits, cut by priority list from the identity config; never silently truncate mid-claim | RUNS | P01, P02, P04 |
| 08-02 | document unreadable, request re-send; log the raw error | RUNS | P03, P08, P09 |
| 12-03 | engagement numbers conflict between sources, report both, named | RUNS | P01, P02, P03, P04, P05, P10, P12 |
| 15-03 | ROI attribution claimed by two sources, report both claims | RUNS | P09, P10, P16, P17, P23 |
| 16-07 | past client asks a new-transaction question, new context opened, routed as new lead; old context stays closed | RUNS | P10, P13 |
| 19-04 | an expired listing relists with another broker, update the record; the opportunity is closed | RUNS | P12, P16, P24 |
| 20-05 | question arrives via DM vs public, both route to 01; channel recorded in provenance | RUNS | P11, P14 |


## Your authority

Only what you signed changes things: signatures, identity, property access, money approvals, forgery.

### Tier 1 (17)

| Tuple | Rule | Status | Playbooks |
|---|---|---|---|
| 00-02 | signature invalid on authority intent, reject + integrity.violation; notify human out-of-band | RUNS | all |
| 00-07 | an envelope arrives with sequence pre-filled, reject; sequence is hub-stamped at persist, a pre-filled sequence is a forgery signal | RUNS | all |
| 00-09 | authority intent with valid signature but illegal tuple, reject on tuple; a good signature never overrides the closed track | RUNS | all |
| 02-09 | rubric update arrives unsigned, keep scoring on the last signed version; alert human; never adopt unsigned config | RUNS | P04, P11, P13, P21 |
| 02-14 | lead data would go to the live decision engine, only with a key set AND the broker's signed decision_engine.allow_external; a key alone sends nothing | RUNS | P04, P11, P13, P21 |
| 05-05 | status change requested without its required artifact, refuse; artifact first | RUNS | P01, P02, P03, P05, P18, P20, P23 |
| 05-06 | status change requested without signed listing.change.authorized, refuse; verbal or email instruction is not authority | RUNS | P01, P02, P03, P05, P18, P20, P23 |
| 06-02 | requester identity cannot be verified, cancel the access-bearing appointment; no exceptions | RUNS | P01, P04, P07, P18, P19, P22 |
| 06-03 | 'just let them in' request, refuse + escalation.legal_line; access is the line | RUNS | P01, P04, P07, P18, P19, P22 |
| 06-06 | access code or lockbox combo requested in a message, never transmit; access instructions route through the custody protocol only | RUNS | P01, P04, P07, P18, P19, P22 |
| 08-04 | sensitive doc from an unexpected sender, quarantine; verify sender before filing | RUNS | P03, P08, P09 |
| 09-07 | vendor requests property access codes, custody protocol only; codes never ride vendor messages | RUNS | P01, P09, P19, P20 |
| 09-09 | invoice differs from quote, log both, human; never approve variances | RUNS | P01, P09, P19, P20 |
| 14-11 | broker-signed access grant, record party, window end and custody reference only; reject any other field and any value that looks like the secret itself | RUNS | P01, P02, P03, P04, P05, P06, P07, P10, P11, P13, P14, P16, P17, P18, P19, P20, P21, P22, P23, P24 |
| 18-04 | an agent asks to move a protected deadline block, refuse; human confirmation only | RUNS | P01, P03, P07, P08, P09, P15, P16, P17, P19, P20 |
| 19-05 | bulk-outreach instruction arrives unsigned, require signed config; chat is not authority | RUNS | P12, P16, P24 |
| SW-11 | visibility limited but the path seems clear, proceed only within stopping distance: reversible increments; irreversible or client-visible actions wait for full verified authority | RUNS | all |

### Tier 2 (7)

| Tuple | Rule | Status | Playbooks |
|---|---|---|---|
| 04-12 | broker signed drafting mode "model", draft remarks with the model only while the active checkpoint passed the broker exam on the served model; otherwise draft by rules and tell the broker why | RUNS | P01, P02, P04 |
| 06-12 | broker's signed seller-report weekday arrives, count each listed property's showings and feedback for the week and hold the report for the broker; continue sends it through 11, cancel skips; once per week per listing | RUNS | P01, P04, P07, P18, P19, P22 |
| 09-02 | credential expires mid-engagement, flag before any next scheduling | RUNS | P01, P09, P19, P20 |
| 09-06 | vendor not on the approved list, refuse to schedule; propose addition to human; urgency does not create approval | RUNS | P01, P09, P19, P20 |
| 09-11 | work scope grows on-site per vendor, stop work order message per template; scope changes are human-approved | RUNS | P01, P09, P19, P20 |
| 09-12 | a delivery arrives for a booking that never reached the vendor (still held for release, or declined), hold the delivery for the human; continue accepts it, cancel refuses it | RUNS | P01, P09, P19, P20 |
| SW-04 | signed human instruction conflicts with a playbook, signed human wins; deviation logged in the after-action report | RUNS | all |

### Tier 3 (1)

| Tuple | Rule | Status | Playbooks |
|---|---|---|---|
| 06-13 | seller-report setting is malformed, reject it whole; nothing changes | RUNS | P01, P04, P07, P18, P19, P22 |


## Choices that are yours

Two of something or an unclear case; the system holds and asks, it never picks the likely one.

### Tier 1 (4)

| Tuple | Rule | Status | Playbooks |
|---|---|---|---|
| 05-08 | price in the authorized change conflicts with the agreement amendment on file, halt; both documents to human | RUNS | P01, P02, P03, P05, P18, P20, P23 |
| 07-12 | possession terms ambiguous in contract, clarification with the exact clause quoted; never interpolate intent | RUNS | P03, P08, P09 |
| 18-03 | human instruction conflicts with a contractual deadline, surface both; act on neither until directed | RUNS | P01, P03, P07, P08, P09, P15, P16, P17, P19, P20 |
| 18-06 | two deadline sources disagree, track both, alert the conflict; never pick the friendlier date | RUNS | P01, P03, P07, P08, P09, P15, P16, P17, P19, P20 |

### Tier 2 (18)

| Tuple | Rule | Status | Playbooks |
|---|---|---|---|
| 00-01 | route valid but ambiguous, hold in clarification queue; never route on 'most likely' | RUNS | all |
| 00-03 | two signed config.update conflict, apply neither; human | NOT BUILT | all |
| 00-15 | same client_context appears in two live playbooks with conflicting next actions, hold both; human sequences them | RUNS | all |
| 02-06 | supplied rubric conflicts with a predeliberated tuple, the tuple wins; apply the tuple, record the conflict verbatim in the tier record, flag for human review; never silently pick either side - a surfaced conflict is a spec finding, a silent pick is drift | RUNS | P04, P11, P13, P21 |
| 02-08 | lead is an agent shopping for a client, flag agent-to-agent; different track, human decides engagement | RUNS | P04, P11, P13, P21 |
| 02-11 | re-score request on a context with an open escalation, hold; the human's read outranks the rubric mid-escalation | RUNS | P04, P11, P13, P21 |
| 02-13 | decision engine result is below the confidence floor, hold the lead for the broker; continue = score with the signed rubric and act on that tier, cancel = archive; never act on an uncertain tier | RUNS | P04, P11, P13, P21 |
| 05-03 | two authorized changes conflict, execute neither; human | NOT REACHABLE | P01, P02, P03, P05, P18, P20, P23 |
| 07-01 | deadline calculable two ways, clarification with both calculations shown | RUNS | P03, P08, P09 |
| 08-03 | two versions of one document conflict, keep both + flag; never pick | RUNS | P03, P08, P09 |
| 08-07 | two versions of the same document differ, keep both, flag conflict; never discard the older unilaterally | RUNS | P03, P08, P09 |
| 11-03 | two agents report conflicting statuses, send nothing; clarification | NOT REACHABLE | P01, P02, P03, P04, P05, P06, P07, P08, P09, P11, P13, P14, P18, P22, P23, P24 |
| 12-05 | trending-topic tie-in idea, human approval first; reputational surface | RUNS | P01, P02, P03, P04, P05, P10, P12 |
| 13-01 | client feedback contradicts stated criteria, ask the client via 11; never rewrite the profile silently | RUNS | P01, P06, P07, P22, P24 |
| 13-06 | buyer criteria conflict internally (budget vs area), present the conflict with data; never silently relax a criterion | RUNS | P01, P06, P07, P22, P24 |
| 18-01 | event conflict the priority rules cannot resolve, human; never silently move either | RUNS | P01, P03, P07, P08, P09, P15, P16, P17, P19, P20 |
| SW-09 | no suitable tuple exists for the task at hand, STOP; clarification.request to the human and wait - a missing tuple is a design omission to fix, never a license to improvise | RUNS | all |
| SW-13 | task requires a path outside declared edges, refuse; clarification.request - an undeclared path is ambiguity, not opportunity | RUNS | all |

### Tier 3 (12)

| Tuple | Rule | Status | Playbooks |
|---|---|---|---|
| 00-05 | two playbooks match a situation, deploy neither; clarification with both named | NOT REACHABLE | all |
| 02-01 | score lands on a tier boundary, assign the lower tier + flag for human | RUNS | P04, P11, P13, P21 |
| 02-05 | a lead's tier oscillates a third time, human review; oscillation is a signal, not noise | RUNS | P04, P11, P13, P21 |
| 03-04 | two sequences eligible for one lead, run neither until the human picks; never stack sequences | RUNS | P11, P12, P21 |
| 03-10 | two sequences would target one context, one sequence per context, newest signed instruction wins; overlap logged | RUNS | P11, P12, P21 |
| 09-05 | two agents request the same vendor slot, deadline-driven request wins; ties go to human | NOT REACHABLE | P01, P09, P19, P20 |
| 13-03 | listing is incomplete on a hard criterion, hold and ask the client; delivering flagged-unknown requires their standing preference | RUNS | P01, P06, P07, P22, P24 |
| 15-02 | expense fits two categories with different tax flags, flag both; the accountant decides | RUNS | P09, P10, P16, P17, P23 |
| 18-05 | overloaded day, propose a priority order; the human confirms it | RUNS | P01, P03, P07, P08, P09, P15, P16, P17, P19, P20 |
| 19-03 | opportunity matches an existing client context, flag the relationship; no outreach implication | RUNS | P12, P16, P24 |
| SW-01 | two playbooks match one trigger, run neither; clarification.request naming both | NOT REACHABLE | all |
| SW-14 | an unlisted crossing is reached, ambiguity protocol; propose the missing tuple in the after-action report for human ratification | RUNS | all |


## Time and reliability

Deadlines, overdue escalations, the clock, outages, capacity; when something breaks it stops loudly.

### Tier 1 (9)

| Tuple | Rule | Status | Playbooks |
|---|---|---|---|
| 00-04 | audit log unwritable or queue overflow, stop accepting envelopes entirely; fail closed, loudly | RUNS | all |
| 00-10 | escalation queue item unacknowledged past SLA, re-alert once then page the owner channel; never silently expire an escalation | RUNS | all |
| 00-13 | audit write fails, full stop everything; no persist = no ack = no work; run on a log or do not run | RUNS | all |
| 00-14 | clock skew detected between components, hold time-triggered playbooks; deadlines computed on a bad clock are fabricated deadlines | RUNS | all |
| 07-04 | multiple deadlines land the same day, alert each individually; never summarize into one alert | RUNS | P03, P08, P09 |
| 07-08 | financing contingency date passes with no removal on file, alert human same hour; contingency math is never assumed waived | RUNS | P03, P08, P09 |
| 07-11 | earnest money receipt not confirmed by deadline, escalate; money milestones never get benefit of the doubt | RUNS | P03, P08, P09 |
| 08-08 | disclosure deadline approaching with document absent, alert 07 + human; absence is the alert, never soften | RUNS | P03, P08, P09 |
| 18-09 | timezone ambiguity on any party, confirm before scheduling; assumptions here cost closings | NOT REACHABLE | P01, P03, P07, P08, P09, P15, P16, P17, P19, P20 |

### Tier 2 (17)

| Tuple | Rule | Status | Playbooks |
|---|---|---|---|
| 00-11 | identity reload requested mid-run, refuse until open runs complete or owner forces; a track change under live traffic derails | RUNS | all |
| 00-12 | clarification queue exceeds owner-set depth, halt new playbook starts; a swarm that cannot get answers must not take on more | RUNS | all |
| 00-17 | a text page to the broker fails, record the failure on the chain; the on-screen page stands and nothing else waits on the text | RUNS | all |
| 01-16 | record.response never returns, retry once then hold the lead in pending with a handoff.failed; never tier undeduped | RUNS | P04, P05, P11, P12 |
| 05-12 | listing marked vacant by the broker, order a property condition check through 09 every interval until occupied or the listing ends; a check counts only with proof | RUNS | P01, P02, P03, P05, P18, P20, P23 |
| 06-01 | calendar double-booking, protected deadline blocks win; otherwise first-confirmed wins and alternatives are offered | RUNS | P01, P04, P07, P18, P19, P22 |
| 08-05 | chase attempts exhausted, escalate; silence is never converted into 'received' | RUNS | P03, P08, P09 |
| 08-12 | a pending disclosure's deadline is three days or less away, warn the legal line once; never repeat it daily | RUNS | P03, P08, P09 |
| 09-01 | vendor cancels late, notify 07/06 immediately + offer roster alternatives; regulated roles are never auto-rebooked without human | RUNS | P01, P09, P19, P20 |
| 09-10 | vendor no-show on a deadline-critical job, escalate + offer next approved vendor to human; never self-substitute | RUNS | P01, P09, P19, P20 |
| 14-12 | an access window has ended and the broker has not closed it, flag it once; never daily | RUNS | P01, P02, P03, P04, P05, P06, P07, P10, P11, P13, P14, P16, P17, P18, P19, P20, P21, P22, P23, P24 |
| 14-13 | filing a client record into the client's drawer fails, record the refusal and hold it for the broker; the CRM entry stands | RUNS | P01, P02, P03, P04, P05, P06, P07, P10, P11, P13, P14, P16, P17, P18, P19, P20, P21, P22, P23, P24 |
| 18-07 | owner calendar shows conflict with a contractual deadline, deadline outranks; propose the move on the soft item | RUNS | P01, P03, P07, P08, P09, P15, P16, P17, P19, P20 |
| 18-08 | recurring task silently failing (no completion events), surface the pattern; a quiet calendar is a suspect calendar | NOT REACHABLE | P01, P03, P07, P08, P09, P15, P16, P17, P19, P20 |
| SW-03 | workload exceeds capacity, priority order: escalations > active-transaction deadlines > client-facing requests > internal/marketing > discovery; ties go to the older item | RUNS | all |
| SW-06 | one parallel step fails mid-phase, complete independent siblings; hold dependents; flag - never abandon the phase silently | RUNS | all |
| SW-07 | identical envelope arrives twice, process once; envelope_id is the idempotency key | RUNS | all |

### Tier 3 (6)

| Tuple | Rule | Status | Playbooks |
|---|---|---|---|
| 00-06 | two playbooks claim the same spoke segment, class decides; equal class = holder keeps, FIFO behind; every siding event logged | RUNS | all |
| 00-16 | an audit entry cannot be written to the plain-language view, the chain entry stands; count the failure and report it at the end of the session | RUNS | all |
| 05-13 | vacant listing ends or is marked occupied, stop the watch and log it to 14 | RUNS | P01, P02, P03, P05, P18, P20, P23 |
| 06-09 | overlapping showings requested, sequence with buffer; never double-book and hope | RUNS | P01, P04, P07, P18, P19, P22 |
| SW-10 | context fade suspected or long run, re-read MANNERS.md and own SKILL.md before the next action | RUNS | all |
| SW-12 | two runs contend for the same agent, higher priority class proceeds; the lower takes the siding - held live on route, resumes when the segment clears; contention never aborts a run | RUNS | all |


## People moments

An angry, upset or vulnerable person, a public complaint; a person answers, not a template.

### Tier 1 (1)

| Tuple | Rule | Status | Playbooks |
|---|---|---|---|
| 20-03 | negative thread going viral, escalation.complaint at priority; no drafts | RUNS | P11, P14 |

### Tier 2 (8)

| Tuple | Rule | Status | Playbooks |
|---|---|---|---|
| 01-03 | caller demands a human now, escalate immediately; capture what is already given | RUNS | P04, P05, P11, P12 |
| 01-06 | abusive contact, stay professional, close capture politely, log verbatim, escalation.complaint | RUNS | P04, P05, P11, P12 |
| 02-03 | lead demands a human, hot path regardless of score | RUNS | P04, P11, P13, P21 |
| 11-10 | negative-tone reply received, route P14 complaint intake; never freestyle de-escalation | RUNS | P01, P02, P03, P04, P05, P06, P07, P08, P09, P11, P13, P14, P18, P22, P23, P24 |
| 11-14 | client is angry, straight to the human: escalation.complaint with the words verbatim, logged to 14, outbound held; nothing is sent to the client - the response is human | RUNS | P01, P02, P03, P04, P05, P06, P07, P08, P09, P11, P13, P14, P18, P22, P23, P24 |
| 16-01 | adverse life event on the contact's record, hold the touch; human decides | RUNS | P10, P13 |
| 16-06 | anniversary touch would land during a known distress event (death, divorce on file), suppress; human decides | RUNS | P10, P13 |
| 20-01 | sentiment is genuinely mixed, classify at complaint priority; protective default | RUNS | P11, P14 |

### Tier 3 (3)

| Tuple | Rule | Status | Playbooks |
|---|---|---|---|
| 06-04 | no-show, log + send feedback request; no reproach messaging | RUNS | P01, P04, P07, P18, P19, P22 |
| 06-08 | agent no-shows twice, flag pattern to human before third confirmation | NOT REACHABLE | P01, P04, P07, P18, P19, P22 |
| 20-04 | praise post detected, log only; no auto-engagement | RUNS | P11, P14 |

## Retired

| Tuple | Rule |
|---|---|
| 03-03 | sequence content contains expired market data, regenerate before send, or skip the touch) - RETIRED 2026-10-12 (owner decision J5: Lead Nurture no longer requests or sends market data |
| 03-09 | nurture content references a listing that changed status, pull the step; stale property claims are fabrications) - RETIRED 2026-10-12 (owner decision J5: Lead Nurture no longer requests or sends market data |
| 11-02 | client is angry, acknowledge + escalation.complaint; no defensiveness, no promises) - RETIRED 2026-10-12 (owner decision): angry clients go straight to the human; no acknowledgement is sent (replacement tuple below |
| 12-10 | budget change requested verbally, current signed budget stands until config.update) - RETIRED 2026-10-28 (owner decision D-A17: no ad carries a cost and nothing is bought, so a budget guarded nothing; a budget setting is now refused |
| 20-06 | EXPANSION DEFERRED BY OWNER - social phase is later; existing tuples stand; lead.signal handoff rules in P11 remain the only active surface, |
