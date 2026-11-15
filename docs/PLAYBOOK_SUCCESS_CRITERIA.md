# Playbook success criteria: what is checked, and what is not

Written by `python synth/tuples/run_tuples.py --set playbooks`; do not edit by hand.
Edit `synth/playbooks/specs/PLAYBOOKS.jsonl` and run it again.

Each playbook runs once, from its trigger to its end, in a fresh state, through
`tools/console.py session` with synthetic data. Every line under "Checked by this run" is
a part of that playbook's success statement in [WHAT_SUCCESS_MEANS.md](WHAT_SUCCESS_MEANS.md),
tied to what must be on the audit record afterwards. One run is one path, so a part of the
statement or a human gate that needs a different path is checked by a run of its own: a
tuple session ([synth/tuples/REPORT.md](../synth/tuples/REPORT.md)) that reaches exactly that
case, named under "Checked by another run". The runner runs those too. All of it runs in
the test suite (`tests_listing/test_playbook_runs.py`), so a line that stops holding fails CI.

- **VERIFIED**: every line holds, here and in the runs named, and every part of the success
  statement is checked or needs an outside system that is not connected (named).
- **VERIFIED, WITH PARTS NOT BUILT**: the same, except that the success statement says
  things the product does not do. They are named; they are gaps in the product, not in the checking.
- **PARTLY VERIFIED**: every line holds; parts of the success statement are not shown by any run (named).
- **FAILED**: a line does not hold.

Nothing here was run against a live MLS, a live ad platform or real clients.

| Playbook | Owner's sign-off of the run table | Status | Checked by this run | Checked by another run | Not built | Not shown | Needs an outside system | Gates not reached |
|---|---|---|---|---|---|---|---|---|
| P01 New Listing Onboarding | RATIFIED | VERIFIED | 13 | 4 | 0 | 0 | 1 | 0 |
| P02 Price Adjustment | RATIFIED | VERIFIED | 13 | 2 | 0 | 0 | 1 | 0 |
| P03 Under-Contract Transition | RATIFIED | PARTLY VERIFIED | 12 | 1 | 1 | 1 | 0 | 0 |
| P04 Open House Cycle | RATIFIED | VERIFIED, WITH PARTS NOT BUILT | 11 | 1 | 2 | 0 | 0 | 0 |
| P05 Expired/Withdrawn Wind-down | RATIFIED | VERIFIED, WITH PARTS NOT BUILT | 9 | 2 | 1 | 0 | 1 | 0 |
| P06 New Buyer Onboarding | RATIFIED | VERIFIED, WITH PARTS NOT BUILT | 8 | 0 | 2 | 0 | 0 | 0 |
| P07 Tour Day Coordination | RATIFIED | VERIFIED, WITH PARTS NOT BUILT | 11 | 4 | 1 | 0 | 0 | 0 |
| P08 Offer-to-Acceptance | RATIFIED | VERIFIED, WITH PARTS NOT BUILT | 7 | 1 | 1 | 0 | 0 | 0 |
| P09 Contract-to-Close | RATIFIED | PARTLY VERIFIED | 12 | 6 | 0 | 1 | 0 | 0 |
| P10 Close + Post-Close Handoff | RATIFIED | PARTLY VERIFIED | 8 | 1 | 0 | 1 | 0 | 0 |
| P11 Speed-to-Lead | RATIFIED | PARTLY VERIFIED | 12 | 3 | 0 | 1 | 1 | 0 |
| P12 Geographic Farm Campaign | RATIFIED | VERIFIED, WITH PARTS NOT BUILT | 9 | 2 | 1 | 0 | 1 | 0 |
| P13 Referral/Anniversary Cycle | RATIFIED | PARTLY VERIFIED | 9 | 2 | 0 | 1 | 0 | 0 |
| P14 Complaint Response | RATIFIED | VERIFIED | 10 | 2 | 0 | 0 | 1 | 0 |
| P15 CMA / Listing-Appointment Prep | RATIFIED | PARTLY VERIFIED | 8 | 0 | 0 | 1 | 1 | 0 |
| P16 Morning Operations | PROPOSED | PARTLY VERIFIED | 7 | 1 | 0 | 2 | 1 | 0 |
| P17 End-of-Day Books | PROPOSED | PARTLY VERIFIED | 7 | 0 | 0 | 2 | 0 | 0 |
| P18 Seller Weekly Report | RATIFIED | VERIFIED, WITH PARTS NOT BUILT | 7 | 1 | 1 | 0 | 0 | 0 |
| P19 Property Access Custody | RATIFIED | VERIFIED, WITH PARTS NOT BUILT | 6 | 3 | 1 | 0 | 0 | 0 |
| P20 Vacant Property Watch | RATIFIED | VERIFIED, WITH PARTS NOT BUILT | 8 | 1 | 2 | 0 | 0 | 0 |
| P21 Lead Re-Score Cycle | RATIFIED | VERIFIED | 7 | 3 | 0 | 0 | 0 | 0 |
| P22 Buyer Feedback & Match Refresh | RATIFIED | PARTLY VERIFIED | 7 | 3 | 0 | 1 | 0 | 0 |
| P23 Price-Review Evidence Assembly | RATIFIED | VERIFIED, WITH PARTS NOT BUILT | 7 | 1 | 2 | 0 | 1 | 0 |
| P24 Prospecting Outreach | RATIFIED | VERIFIED, WITH PARTS NOT BUILT | 8 | 3 | 1 | 0 | 1 | 0 |

## P01 New Listing Onboarding

**VERIFIED.**

### Checked by this run

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for L1, containing `"playbook": "P01"` | holds |
| The run ends as completed | playbook.completed for L1, containing `"playbook": "P01"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for L1, containing `"playbook": "P01"` | holds |
| The photographer's booking waits for your release | absolute_signal.hold containing `vendor.schedule` | holds |
| and goes out only after it | absolute_signal.released containing `vendor.schedule` | holds |
| Photos move on only with their proof artifact | a deliverable.release message for L1, containing `sha256-photo-L1` | holds |
| The listing description is reviewed for fair housing before it is released for use | a content.verdict message for L1, containing `"verdict": "approved"` and `ruleset_version`; and before the first a asset.release message for L1 | holds |
| The ad waits for your release | a interaction.log message for L1, containing `campaign_publish_held` | holds |
| and is published only after your release | absolute_signal.released containing `campaign.publish`; and before the first a campaign.publish message for L1 | holds |
| The published ad is on the record | a campaign.publish message for L1 | holds |
| The seller is told the listing is active | a client.message.send message for L1, containing `status.update` and `"status": "active"` | holds |
| The go-live you authorized is recorded | a status.update message for L1, containing `"status": "active"` | holds |
| No message was dropped along the way | no dead.letter | holds |

### Checked by another run

| What success means, or the gate | The run that checks it | Result |
|---|---|---|
| A flagged compliance verdict publishes nothing and reaches you with the findings | tuple 12-11: compliance flags campaign copy, publish nothing; tell the broker with 17's findings and wait for corrected signed copy | holds |
| A pricing question from a client goes to you | tuple 11-06: client asks a pricing/strategy question in any channel, Legal Line; template acknowledgment + human handoff | holds |
| Photos that contradict the data sheet halt the asset and reach you | tuple 04-01: photos contradict the data sheet, halt the asset; clarification with both artifacts attached | holds |
| With the disclosure status unclear, nothing publishes | tuple 12-04: CCP status unclear for a listing, no publish; the gate is hard | holds |

### Needs an outside system that is not connected

- The MLS entry and the portals are checked live. No MLS or portal is connected. Agent 05 records the go-live you authorized and stops there; confirming it on the MLS stays with you

## P02 Price Adjustment

**VERIFIED.** B1 (budget 445,000) is matched only once the price drops to 440,000; B2, matched at 450,000, is told of the change, not matched twice; the ad carries no price, so you are not asked about it.

### Checked by this run

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for L1, containing `"playbook": "P02"` | holds |
| The run ends as completed | playbook.completed for L1, containing `"playbook": "P02"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for L1, containing `"playbook": "P02"` | holds |
| The price you signed is recorded on the listing | a status.update message for L1, containing `440000` | holds |
| The seller is told the new price | a client.message.send message for L1, containing `status.update` and `440000` | holds |
| A price change does not stop the marketing | no interaction.log message for L1, containing `marketing_halted` | holds |
| The match agent gets the changed price | a listing.data message for L1, containing `"changed_field": "price"` and `440000` | holds |
| A buyer already matched is not matched a second time | exactly 1 x a client.message.request message for B2, containing `new_match` | holds |
| and is told the new price | a client.message.request message for B2, containing `listing_update` and `440000` | holds |
| You are not asked about an ad that carries no price | no clarification.request message for L1, containing `old price` | holds |
| A buyer the new price now fits gets the match | exactly 1 x a client.message.request message for B1, containing `new_match` | holds |
| and gets no change notice for a listing they never had | no client.message.request message for B1, containing `listing_update` | holds |
| No message was dropped along the way | no dead.letter | holds |

### Checked by another run

| What success means, or the gate | The run that checks it | Result |
|---|---|---|
| A published ad found stale is corrected or retracted the same day | tuple 12-09: published asset found factually stale, correct or retract within the same day; log the delta | holds |
| A comparables package first, if you want one | playbook P23, above or below | holds |

### Needs an outside system that is not connected

- The MLS and the portals show the new price. No MLS or portal is connected; updating them stays with you

## P03 Under-Contract Transition

**PARTLY VERIFIED.**

### Checked by this run

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for L1, containing `"playbook": "P03"` | holds |
| The run ends as completed | playbook.completed for L1, containing `"playbook": "P03"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for L1, containing `"playbook": "P03"` | holds |
| The executed contract is on file before the status changes | a interaction.log message for L1, containing `document_filed` and `executed_contract`; and before the first a status.update message for L1, containing `"status": "pending"` | holds |
| Pending is recorded on the listing | a status.update message for L1, containing `"status": "pending"` | holds |
| The seller is told the listing is pending | a client.message.send message for L1, containing `status.update` and `"status": "pending"` | holds |
| An ad still waiting for your release is not published; you are asked to decline it | a clarification.request message for L1, containing `still held for your release` and `Decline it` | holds |
| Contract-to-close starts when you load the dates | playbook.started for L1, containing `"playbook": "P09"` | holds |
| The deadline map is loaded with its milestones | a interaction.log message for L1, containing `timeline_loaded` and `inspection` and `appraisal` and `financing_contingency` and `closing` | holds |
| Each of the four deadlines goes to the calendar | exactly 4 x a deadline.alert message for L1 | holds |
| The first document requests go out | exactly 3 x a client.message.send message for L1, containing `document_request` | holds |
| No message was dropped along the way | no dead.letter | holds |

### Checked by another run

| What success means, or the gate | The run that checks it | Result |
|---|---|---|
| A status change without its required document is refused | tuple 05-05: status change requested without its required artifact, refuse; artifact first | holds |

### The success statement says it; the product does not do it

- The seller is told what happens next. The message is the status notice (a template name and the status). The product writes no next-steps text

### Not shown by any run

- Vendors are booked for the milestones. The synthetic roster has no inspector or appraiser, so nothing is booked and you are asked (that question is on the record)

## P04 Open House Cycle

**VERIFIED, WITH PARTS NOT BUILT.** The walk-in arrives as an inquiry and runs P11 on its own client.

### Checked by this run

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for L1, containing `"playbook": "P04"` | holds |
| The run ends as completed | playbook.completed for L1, containing `"playbook": "P04"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for L1, containing `"playbook": "P04"` | holds |
| The open house is on the calendar | a calendar.event message for L1, containing `open_house` | holds |
| With no approved sign vendor, nothing is booked and you are asked | a clarification.request message for L1, containing `no approved roster vendor` | holds |
| A walk-in is captured as a lead on its own client record | playbook.started for W1, containing `"playbook": "P11"` | holds |
| The walk-in's consent is recorded at capture | a interaction.log message for W1, containing `consent` and `"call": "yes"` | holds |
| A walk-in at our own listing is not refused as outside the brokerage | no escalation.raised for W1, containing `outside brokerage scope` | holds |
| A hot walk-in reaches you with the five-minute call clock | escalation.raised for W1, containing `escalation.hot_lead` and `"sla_s": 300` | holds |
| The attendance and feedback you record are on the listing's record | a interaction.log message for L1, containing `open_house_event` and `kitchen praised` | holds |
| No message was dropped along the way | no dead.letter | holds |

### Checked by another run

| What success means, or the gate | The run that checks it | Result |
|---|---|---|
| A possible duplicate is checked against the record before a new file is opened | tuple 01-05: possible duplicate identity unconfirmed, record.request first; still unconfirmed = new context + flag, never merge | holds |

### The success statement says it; the product does not do it

- The open house is promoted. No agent sends a promotion for an open house; Agent 12 has no open-house code
- Every walk-in is captured. Nothing reads a sign-in sheet. A walk-in is one inquiry that you or a form enter

## P05 Expired/Withdrawn Wind-down

**VERIFIED, WITH PARTS NOT BUILT.**

### Checked by this run

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for L1, containing `"playbook": "P05"` | holds |
| The run ends as completed | playbook.completed for L1, containing `"playbook": "P05"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for L1, containing `"playbook": "P05"` | holds |
| Withdrawn is recorded on the listing | a status.update message for L1, containing `"status": "withdrawn"` | holds |
| The seller is told | a client.message.send message for L1, containing `status.update` and `withdrawn` | holds |
| A live ad is halted | a interaction.log message for L1, containing `marketing_halted` and `live, halt sent` | holds |
| The halt waits for your release, like any public send | exactly 2 x absolute_signal.hold containing `campaign.publish` | holds |
| After your release the halt goes out, with the reason | a campaign.publish message for L1, containing `"action": "halt"` and `listing_status_withdrawn` | holds |
| No message was dropped along the way | no dead.letter | holds |

### Checked by another run

| What success means, or the gate | The run that checks it | Result |
|---|---|---|
| No one is sent a greeting who is not on the list you supplied | tuple 16-04: greeting requested for someone not on the supplied list, refuse; the list is the authority | holds |
| An ad still waiting for your release when the listing leaves the market is not published; you are asked to decline it | playbook P03, above or below | holds |

### The success statement says it; the product does not do it

- The seller hears it in your words. The message is a template name and the status. The wording is yours to supply

### Needs an outside system that is not connected

- A live ad is taken down on every platform and each takedown is verified. No ad platform is connected

## P06 New Buyer Onboarding

**VERIFIED, WITH PARTS NOT BUILT.** Owner change 2026-10-21: the run starts at the buyer's first criteria, so the wait for the signed agreement is inside it; our listing goes live, the match is held (no agreement), you record the agreement, and the next clock run sends the first match.

### Checked by this run

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for B1, containing `"playbook": "P06"` | holds |
| The run ends as completed | playbook.completed for B1, containing `"playbook": "P06"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for B1, containing `"playbook": "P06"` | holds |
| No match goes to a buyer without a signed buyer agreement on file | a interaction.log message for B1, containing `match_held_no_buyer_agreement` | holds |
| You are told the matches are waiting for the agreement | a clarification.request message for B1, containing `no signed buyer agreement` | holds |
| Once you record the agreement, the held match goes to the buyer, and not before | a config.update message for B1, containing `buyer_agreement_on_file`; and before the first a client.message.send message for B1, containing `new_match` | holds |
| The buyer gets it once | exactly 1 x a client.message.send message for B1, containing `new_match` | holds |
| No message was dropped along the way | no dead.letter | holds |

### The success statement says it; the product does not do it

- The agreement document is filed and checked to open. The agreement is a setting you sign. No document is filed for it; Agent 08 has no buyer-agreement document type
- The buyer's criteria are captured in their own words. The criteria are your signed entry. Nothing captures them from the buyer's own message

## P07 Tour Day Coordination

**VERIFIED, WITH PARTS NOT BUILT.** Feedback is asked for the day after the showing, which also tells Agent 18 the showing happened.

### Checked by this run

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for B1, containing `"playbook": "P07"` | holds |
| The run ends as completed | playbook.completed for B1, containing `"playbook": "P07"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for B1, containing `"playbook": "P07"` | holds |
| The showing goes on the calendar with its buffer | a calendar.event message for B1, containing `"event": "showing"` and `"buffer_minutes": 30` | holds |
| The buyer gets a confirmation | a client.message.send message for B1, containing `showing_confirmation` | holds |
| Feedback is asked for the day after | a client.message.request message for B1, containing `feedback_request` | holds |
| The buyer's feedback is recorded in their own words | a interaction.log message for B1, containing `feedback_received` and `bedrooms too small` | holds |
| A showing that was followed up is not marked a no-show | no showing.no_show message for B1 | holds |
| The seller of our own listing is told a showing is booked, with the time and nothing about the buyer | exactly 1 x a client.message.send message for L1, containing `showing_booked_seller` and `2026-10-21T15:00` | holds |
| For a listing that is not ours, no seller is messaged | no client.message.request message for SYN-L001 | holds |
| No message was dropped along the way | no dead.letter | holds |

### Checked by another run

| What success means, or the gate | The run that checks it | Result |
|---|---|---|
| Overlapping showings are sequenced with a buffer, never double-booked | tuple 06-09: overlapping showings requested, sequence with buffer; never double-book and hope | holds |
| Feedback is asked twice at most | tuple 06-10: feedback request unanswered after two asks, stop; nagging showing agents burns the network | holds |
| Feedback that contradicts the buyer's criteria is asked about, never written into the profile | tuple 13-01: client feedback contradicts stated criteria, ask the client via 11; never rewrite the profile silently | holds |
| A message outside contact hours waits for the next window | tuple 11-07: message would go out after legal contact hours, queue for the next window; urgency claim requires human override | holds |

### The success statement says it; the product does not do it

- The other side's agent is told. For a listing that is not ours, the listing agent is not a client and there is no channel to them (the Duet brief's Agent 21)

## P08 Offer-to-Acceptance

**VERIFIED, WITH PARTS NOT BUILT.**

### Checked by this run

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for L1, containing `"playbook": "P08"` | holds |
| The run ends as completed | playbook.completed for L1, containing `"playbook": "P08"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for L1, containing `"playbook": "P08"` | holds |
| Each offer stage you report is recorded | exactly 2 x a interaction.log message for L1, containing `offer_status` | holds |
| Every stage comes to you for review | exactly 2 x a clarification.request message for L1, containing `offer status update - human review` | holds |
| The agents send nothing about the offer to anyone | no client.message.send message for L1, containing `offer` | holds |
| No message was dropped along the way | no dead.letter | holds |

### Checked by another run

| What success means, or the gate | The run that checks it | Result |
|---|---|---|
| After an accepted offer, under-contract starts on your signed status change with the contract on file | playbook P03, above or below | holds |

### The success statement says it; the product does not do it

- Every offer document is chased to completeness. There is no offer document type. The stages are your signed entries, and nothing tracks an offer's deadline

## P09 Contract-to-Close

**PARTLY VERIFIED.** The settlement statement arrives from the title company through Agent 11, from a sender you listed; the inspection never got its report, so the close waits for you and continues on your decision.

### Checked by this run

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for L1, containing `"playbook": "P09"` | holds |
| The run ends as completed | playbook.completed for L1, containing `"playbook": "P09"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for L1, containing `"playbook": "P09"` | holds |
| The deadline map is loaded | a interaction.log message for L1, containing `timeline_loaded` and `inspection` and `closing` | holds |
| Each deadline goes to the calendar | exactly 2 x a deadline.alert message for L1 | holds |
| No vendor outside your approved list is booked; you are asked | a clarification.request message for L1, containing `no approved roster vendor for kind 'inspector'` | holds |
| The settlement statement is filed, from a sender you named | a interaction.log message for L1, containing `document_filed` and `closing_settlement_statement` | holds |
| A close with a milestone still open waits for you | a agent.status message for L1, containing `still open` and `inspection` | holds |
| Your decision to close with it open is recorded as yours | a interaction.log message for L1, containing `milestones_waived_at_closing` and `inspection` and `broker decision` | holds |
| The close is recorded | a transaction.closed message for L1 | holds |
| The settlement figures pass on as the statement gave them | a transaction.closed message for L1, containing `"commission_amount": 27000` and `"sale_price": 450000` | holds |
| No message was dropped along the way | no dead.letter | holds |

### Checked by another run

| What success means, or the gate | The run that checks it | Result |
|---|---|---|
| Deadlines that land on one day are each alerted, never rolled into one | tuple 07-04: multiple deadlines land the same day, alert each individually; never summarize into one alert | holds |
| A money milestone not confirmed by its deadline is escalated | tuple 07-11: earnest money receipt not confirmed by deadline, escalate; money milestones never get benefit of the doubt | holds |
| A financing contingency date that passes with no removal on file reaches you | tuple 07-08: financing contingency date passes with no removal on file, alert human same hour; contingency math is never assumed waived | holds |
| A document chase that runs out ends with you, never in silence | tuple 08-05: chase attempts exhausted, escalate; silence is never converted into 'received' | holds |
| A vendor whose credential has expired is flagged before any next booking | tuple 09-02: credential expires mid-engagement, flag before any next scheduling | holds |
| A document with wire instructions is quarantined and goes to the legal line | tuple 08-09: document contains visible wire instructions, quarantine + legal-line escalation; do not forward, do not store in general records | holds |

### Not shown by any run

- A vendor is booked for a milestone. The synthetic roster has no inspector, so none is booked here; P01 shows a booking (the photographer)

## P10 Close + Post-Close Handoff

**PARTLY VERIFIED.** The settlement statement arrives from the title company; the 30-day check-in goes out on the clock.

### Checked by this run

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for L1, containing `"playbook": "P10"` | holds |
| The run ends as completed | playbook.completed for L1, containing `"playbook": "P10"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for L1, containing `"playbook": "P10"` | holds |
| The close reaches the books, the client record and the follow-up program | exactly 3 x a transaction.closed message for L1 | holds |
| Consent is checked before the first check-in | a record.request message for L1, containing `consent_check`; and before the first a client.message.send message for L1, containing `post_close_checkin_30day` | holds |
| The 30-day, 90-day and 365-day check-ins each go out on the clock | exactly 3 x a interaction.log message for L1, containing `post_close_checkin_sent` | holds |
| and is recorded | a interaction.log message for L1, containing `post_close_checkin_sent` and `"day": 30` | holds |
| No message was dropped along the way | no dead.letter | holds |

### Checked by another run

| What success means, or the gate | The run that checks it | Result |
|---|---|---|
| A recorded figure that differs from the contract is escalated with the clause | tuple 15-01: recorded figure differs from contract language, escalate with the clause verbatim | holds |

### Not shown by any run

- The client record becomes past-client with anniversary dates armed. Not on this run's record, and not looked for in the code

## P11 Speed-to-Lead

**PARTLY VERIFIED.**

### Checked by this run

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for T1, containing `"playbook": "P11"` | holds |
| The run ends as completed | playbook.completed for T1, containing `"playbook": "P11"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for T1, containing `"playbook": "P11"` | holds |
| Consent is recorded at first contact | a interaction.log message for T1, containing `consent` and `"email": "yes"` | holds |
| The tier decision is on the record | decision.lead for T1 | holds |
| It is scored against your signed rubric, with the rubric version on the decision | a interaction.log message for T1, containing `"rubric_version": "synth-v1"` and `"tier": "WARM"` | holds |
| A warm lead goes to nurture | a lead.nurture message for T1 | holds |
| Its first message is compliance-reviewed | a content.verdict message for T1, containing `"verdict": "approved"` | holds |
| and then sent | exactly 1 x a client.message.send message for T1, containing `sequence_touch` | holds |
| A hot lead reaches you with the five-minute call clock | escalation.raised for T2, containing `escalation.hot_lead` and `"sla_s": 300` | holds |
| The agents send a hot lead nothing; the call is yours | no client.message.send message for T2 | holds |
| No message was dropped along the way | no dead.letter | holds |

### Checked by another run

| What success means, or the gate | The run that checks it | Result |
|---|---|---|
| A possible duplicate is checked against the record before a new file is opened | tuple 01-05: possible duplicate identity unconfirmed, record.request first; still unconfirmed = new context + flag, never merge | holds |
| A hot lead left unanswered past the clock is re-alerted once, then paged | tuple 00-10: escalation queue item unacknowledged past SLA, re-alert once then page the owner channel; never silently expire an escalation | holds |
| A question that arrives by social media enters the same way | tuple 20-05: question arrives via DM vs public, both route to 01; channel recorded in provenance | holds |

### Not shown by any run

- Two inquiries at once from one person are captured once. Tuple 01-01 is a known VARIANCE: they are captured twice

### Needs an outside system that is not connected

- The call itself. No phone system is connected; the item on your list is the alert

## P12 Geographic Farm Campaign

**VERIFIED, WITH PARTS NOT BUILT.**

### Checked by this run

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for F1, containing `"playbook": "P12"` | holds |
| The run ends as completed | playbook.completed for F1, containing `"playbook": "P12"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for F1, containing `"playbook": "P12"` | holds |
| The campaign is compliance-reviewed | a content.verdict message for F1, containing `"verdict": "approved"` | holds |
| It waits for your release | a interaction.log message for F1, containing `campaign_publish_held` | holds |
| Your signed release is on the record | disclosure.authorized containing `campaign.publish` | holds |
| It is published after your release | a campaign.publish message for F1 | holds |
| Its audience is the geography only, general targeting | a campaign.publish message for F1, containing `"geography": "44101"` and `"targeting": "general"` | holds |
| No message was dropped along the way | no dead.letter | holds |

### Checked by another run

| What success means, or the gate | The run that checks it | Result |
|---|---|---|
| Demographic targeting is refused outright | tuple 12-08: campaign targets a geography, farm rules apply; demographic targeting parameters are refused outright | holds |
| Neighbor data is used at aggregate level only; inferences about a household are refused | tuple 19-10: neighbor data requested for farm outreach, aggregate level only; individual household inferences refused | holds |

### The success statement says it; the product does not do it

- Agents 19, 10 and 03 take part. docs/PLAYBOOKS.md names them for P12. In the product the campaign is Agent 12 and Agent 17

### Needs an outside system that is not connected

- The campaign runs on the ad platform. No ad platform is connected; published means released onto the record

## P13 Referral/Anniversary Cycle

**PARTLY VERIFIED.**

### Checked by this run

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for C1, containing `"playbook": "P13"` | holds |
| The run ends as completed | playbook.completed for C1, containing `"playbook": "P13"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for C1, containing `"playbook": "P13"` | holds |
| The date on the client's record triggers the touch | a client.message.request message for C1, containing `birthday_greeting` | holds |
| Consent is checked before it is sent | a record.request message for C1, containing `consent_check`; and before the first a client.message.send message for C1, containing `birthday_greeting` | holds |
| The greeting is sent | exactly 1 x a client.message.send message for C1, containing `birthday_greeting` | holds |
| A client who opted out of every channel is sent nothing | no client.message.send message for C2 | holds |
| An anniversary works the same way | exactly 1 x a client.message.send message for C3, containing `purchase_anniversary_greeting` | holds |
| No message was dropped along the way | no dead.letter | holds |

### Checked by another run

| What success means, or the gate | The run that checks it | Result |
|---|---|---|
| A past client who signals new business becomes a lead | tuple 16-03: past client signals new business, lead.captured to 02; never negotiate | holds |
| A referral reward is never mentioned without a compliance verdict | tuple 16-08: referral reward mention requested, 17 gate first; inducement rules vary by state | holds |

### Not shown by any run

- Referral requests go out on their cadence. None is due in this run

## P14 Complaint Response

**VERIFIED.** A routine message to the same person during the complaint is held (stand-in line from 06); the run ends when you release the hold.

### Checked by this run

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for S1, containing `"playbook": "P14"` | holds |
| The run ends as completed | playbook.completed for S1, containing `"playbook": "P14"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for S1, containing `"playbook": "P14"` | holds |
| The complaint reaches you | escalation.raised for S1, containing `escalation.complaint` | holds |
| A hold on every routine message to that person is armed | a interaction.log message for S1, containing `complaint_hold_armed` | holds |
| A routine message during the complaint is held | a interaction.log message for S1, containing `touch_held_complaint_hold` | holds |
| The agents send that person nothing | no client.message.send message for S1 | holds |
| No reply is drafted | no content.review message for S1 | holds |
| The hold lifts on your signed word | a interaction.log message for S1, containing `complaint_hold_released` | holds |
| No message was dropped along the way | no dead.letter | holds |

### Checked by another run

| What success means, or the gate | The run that checks it | Result |
|---|---|---|
| A thread that is spreading reaches you at priority, with no drafts | tuple 20-03: negative thread going viral, escalation.complaint at priority; no drafts | holds |
| An angry client goes straight to you with their words, and outbound stops | tuple 11-14: client is angry, straight to the human: escalation.complaint with the words verbatim, logged to 14, outbound held; nothing is sent to the client - the response is human | holds |

### Needs an outside system that is not connected

- The mention is read from the social platform. No social platform is connected; the mention is entered

## P15 CMA / Listing-Appointment Prep

**PARTLY VERIFIED.** A comparables request for an address that is not a live listing of ours is P15.

### Checked by this run

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for A1, containing `"playbook": "P15"` | holds |
| The run ends as completed | playbook.completed for A1, containing `"playbook": "P15"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for A1, containing `"playbook": "P15"` | holds |
| The comparables package reaches you with its count and whether it is thin | a data.package message for A1, containing `"comp_count": 6` and `"thin": false` | holds |
| Every comparable carries its source and retrieval date | a data.package message for A1, containing `MLS-SYN` and `retrieval_date` | holds |
| The package carries no price recommendation | no data.package message for A1, containing `recommended_price` | holds |
| The delivery is on the record | a interaction.log message for A1, containing `package_delivered` | holds |
| No message was dropped along the way | no dead.letter | holds |

### Not shown by any run

- The listing appointment is on the calendar (Agent 18). No appointment is entered in this run

### Needs an outside system that is not connected

- The comparables come from a data source. No comp source is connected. Agent 10 builds the package only from comparables you hand it, as this run does

## P16 Morning Operations

**PARTLY VERIFIED.** The morning clock: 18 asks 14, 15, 19 and 10 for their sections (decision 8, 2026-10-21) and sends you one briefing.

### Checked by this run

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for briefing, containing `"playbook": "P16"` | holds |
| The run ends as completed | playbook.completed for briefing, containing `"playbook": "P16"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for briefing, containing `"playbook": "P16"` | holds |
| One morning briefing reaches you | a report.package message for briefing, containing `morning` | holds |
| It has its sections and names none as missing | a report.package message for briefing, containing `overnight_leads` and `yesterdays_books` and `prospects_waiting` and `market_changes` and `"sections_missing": []` | holds |
| Yesterday's new lead is in the briefing, with its tier | a report.package message for briefing, containing `"briefing_type": "morning"` and `"count": 1` and `T9` and `WARM` | holds |
| No message was dropped along the way | no dead.letter | holds |

### Checked by another run

| What success means, or the gate | The run that checks it | Result |
|---|---|---|
| A briefing item whose source is missing is stated as a gap | tuple 18-02: a briefing item's source envelope is missing, state the gap in the briefing | holds |

### Not shown by any run

- The books, prospects and market sections report a full day correctly. Only the overnight-leads section has content in this run
- Record conflicts listed are real conflicts. Open item for the owner: over the 24 playbook runs the record-conflict flag fired 10 times, each on ordinary activity (two different messages, a status change)

### Needs an outside system that is not connected

- Market movement with a source on every figure. No market data source is connected

## P17 End-of-Day Books

**PARTLY VERIFIED.** The evening clock (decision 9, 2026-10-21): 14's end-of-day books go to 15, which adds the day's figures and sends you one report.

### Checked by this run

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for eod-report, containing `"playbook": "P17"` | holds |
| The run ends as completed | playbook.completed for eod-report, containing `"playbook": "P17"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for eod-report, containing `"playbook": "P17"` | holds |
| One end-of-day report reaches you with the record's books and the day's figures | a report.package message for eod-report, containing `"report_type": "eod_books"` and `"figures"` and `"crm"` | holds |
| Agent 14's books go to Agent 15 first | exactly 2 x a report.package message for eod-report, containing `"report_type": "eod"` | holds |
| The day's activity is in the report, dated | a report.package message for eod-report, containing `"report_type": "eod_books"` and `"contexts_covered": 1` and `T9` and `"date": "2026-10-16"` | holds |
| No message was dropped along the way | no dead.letter | holds |

### Not shown by any run

- A logging gap is named, never smoothed over. Tuple 14-03 is NOT REACHABLE since owner decision D-A6; the gap check is tested with state set directly
- The record is hashed. Not checked by a line here

## P18 Seller Weekly Report

**VERIFIED, WITH PARTS NOT BUILT.**

### Checked by this run

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for S1, containing `"playbook": "P18"` | holds |
| The run ends as completed | playbook.completed for S1, containing `"playbook": "P18"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for S1, containing `"playbook": "P18"` | holds |
| The weekly report is prepared on the weekday you signed | a client.message.request message for S1, containing `seller_weekly_report` | holds |
| Your continue comes before the report is sent | hitl.decision.authorized for S1, containing `APPROVE`; and before the first a client.message.send message for S1, containing `seller_weekly_report` | holds |
| The report goes to the seller once | exactly 1 x a client.message.send message for S1, containing `seller_weekly_report` | holds |
| No message was dropped along the way | no dead.letter | holds |

### Checked by another run

| What success means, or the gate | The run that checks it | Result |
|---|---|---|
| The counts are the week's real showings and feedback | tuple 06-12: broker's signed seller-report weekday arrives, count each listed property's showings and feedback for the week and hold the report for the broker; continue sends it through 11, cancel skips; once per week per listing | holds |

### The success statement says it; the product does not do it

- Market movement and next steps are in the report. The report holds the showing and feedback counts only

## P19 Property Access Custody

**VERIFIED, WITH PARTS NOT BUILT.**

### Checked by this run

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for L1, containing `"playbook": "P19"` | holds |
| The run ends as completed | playbook.completed for L1, containing `"playbook": "P19"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for L1, containing `"playbook": "P19"` | holds |
| An access grant is recorded with who, until when, and the custody reference | a config.update message for L1, containing `access_grant` and `Pat Inspector` and `2026-10-20` and `lockbox-L1` | holds |
| Closing the grant is recorded | a config.update message for L1, containing `access_closed` | holds |
| No message was dropped along the way | no dead.letter | holds |

### Checked by another run

| What success means, or the gate | The run that checks it | Result |
|---|---|---|
| A grant past its end date that you have not closed is flagged once | tuple 14-12: an access window has ended and the broker has not closed it, flag it once; never daily | holds |
| An access code asked for in a message is never sent | tuple 06-06: access code or lockbox combo requested in a message, never transmit; access instructions route through the custody protocol only | holds |
| The grant record holds who, until when and the custody reference, and nothing else | tuple 14-11: broker-signed access grant, record party, window end and custody reference only; reject any other field and any value that looks like the secret itself | holds |

### The success statement says it; the product does not do it

- Codes are rotated. Nothing in the product rotates or holds a code; the record is a custody reference

## P20 Vacant Property Watch

**VERIFIED, WITH PARTS NOT BUILT.**

### Checked by this run

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for L1, containing `"playbook": "P20"` | holds |
| The run ends as completed | playbook.completed for L1, containing `"playbook": "P20"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for L1, containing `"playbook": "P20"` | holds |
| Marking the listing vacant starts the watch | a interaction.log message for L1, containing `vacant_watch_started` | holds |
| The clock asks for a property check | a vendor.request message for L1, containing `property_check` and `vacant_watch` | holds |
| The check's booking waits for your release, like the photographer's | exactly 2 x absolute_signal.hold containing `vendor.schedule` | holds |
| Marking it occupied ends the watch | a interaction.log message for L1, containing `vacant_watch_ended` and `marked occupied` | holds |
| No message was dropped along the way | no dead.letter | holds |

### Checked by another run

| What success means, or the gate | The run that checks it | Result |
|---|---|---|
| A visit claimed with no proof artifact stays open | tuple 09-08: completion claimed without proof artifact, status stays open; deliverable.release requires the proof | holds |

### The success statement says it; the product does not do it

- Utility status is tracked. No code for it
- Unusual activity is surfaced. No code for it

## P21 Lead Re-Score Cycle

**VERIFIED.**

### Checked by this run

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for T1, containing `"playbook": "P21"` | holds |
| The run ends as completed | playbook.completed for T1, containing `"playbook": "P21"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for T1, containing `"playbook": "P21"` | holds |
| A warm lead in nurture is re-scored on the 7-day clock | a lead.rescored message for T1 | holds |
| The re-score decision is logged with the rubric version | exactly 2 x a interaction.log message for T1, containing `"rubric_version": "synth-v1"` and `"tier": "WARM"` | holds |
| A lead still warm stays in nurture on its sequence | a lead.nurture message for T1, containing `"reassignment": true` | holds |
| No message was dropped along the way | no dead.letter | holds |

### Checked by another run

| What success means, or the gate | The run that checks it | Result |
|---|---|---|
| A lead that leaves warm on a re-score is taken out of the re-score pool and logged | tuple 03-13: a re-score did not return the lead to nurture, it left WARM; take it out of the re-score pool and log it to 14 | holds |
| A lead that opted out, or whose sequence is paused, is not re-scored | tuple 03-15: lead opted out or its sequence is paused, no re-score | holds |
| A re-score on a file with an open escalation is held | tuple 02-11: re-score request on a context with an open escalation, hold; the human's read outranks the rubric mid-escalation | holds |

## P22 Buyer Feedback & Match Refresh

**PARTLY VERIFIED.** The tour's feedback opens the refresh; the next listing that fits closes it.

### Checked by this run

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for B1, containing `"playbook": "P22"` | holds |
| The run ends as completed | playbook.completed for B1, containing `"playbook": "P22"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for B1, containing `"playbook": "P22"` | holds |
| The tour's run is closed by the feedback | playbook.completed for B1, containing `"playbook": "P07"` and `completed` | holds |
| The feedback is on the buyer's record | a interaction.log message for B1, containing `feedback_received` and `bedrooms too small` | holds |
| The next listing that fits goes to the buyer | a client.message.request message for B1, containing `new_match` and `"listing_id": "L1"` | holds |
| No message was dropped along the way | no dead.letter | holds |

### Checked by another run

| What success means, or the gate | The run that checks it | Result |
|---|---|---|
| Feedback that contradicts the buyer's criteria is asked about, never written into the profile | tuple 13-01: client feedback contradicts stated criteria, ask the client via 11; never rewrite the profile silently | holds |
| Criteria that compliance does not approve are not used for matching | tuple 13-11: compliance does not approve buyer criteria, do not use them for matching; tell the broker which criteria and why | holds |
| A criterion that tracks a protected class is refused and goes to the legal line | tuple 13-02: a criterion correlates with a protected class, refuse the criterion + escalation.legal_line + verbatim log | holds |

### Not shown by any run

- It happens the same day. Not checked by a line here

## P23 Price-Review Evidence Assembly

**VERIFIED, WITH PARTS NOT BUILT.** A comparables request on a live listing of ours is P23.

### Checked by this run

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for L1, containing `"playbook": "P23"` | holds |
| The run ends as completed | playbook.completed for L1, containing `"playbook": "P23"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for L1, containing `"playbook": "P23"` | holds |
| The comparables package reaches you with its count and whether it is thin | a data.package message for L1, containing `"comp_count": 6` and `"thin": false` | holds |
| Every comparable carries its source and retrieval date | a data.package message for L1, containing `MLS-SYN` and `retrieval_date` | holds |
| No number that you did not write: no price recommendation | no data.package message for L1, containing `recommended_price` | holds |
| No message was dropped along the way | no dead.letter | holds |

### Checked by another run

| What success means, or the gate | The run that checks it | Result |
|---|---|---|
| Your decision is recorded as your signed price | playbook P02, above or below | holds |

### The success statement says it; the product does not do it

- Your listing's own activity (showings, feedback, days on market) is in the evidence. The package holds comparables only; Agent 10 has no code for a listing's showing history
- Financial context on request. No code for it

### Needs an outside system that is not connected

- The comparables and absorption figures come from a data source. No comp source is connected; the package is built from comparables you hand in

## P24 Prospecting Outreach

**VERIFIED, WITH PARTS NOT BUILT.**

### Checked by this run

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for P1, containing `"playbook": "P24"` | holds |
| The run ends as completed | playbook.completed for P1, containing `"playbook": "P24"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for P1, containing `"playbook": "P24"` | holds |
| An opportunity from a source you approved reaches you | a prospect.opportunity message for P1, containing `mls-expired-feed` | holds |
| It arrives already checked against the do-not-call list | a prospect.opportunity message for P1, containing `"dnc_status": "not_on_dnc"` | holds |
| It says plainly that no comp source is connected | a prospect.opportunity message for P1, containing `none - no comp source connected` | holds |
| No one is contacted | no client.message.request message for P1 | holds |
| No message was dropped along the way | no dead.letter | holds |

### Checked by another run

| What success means, or the gate | The run that checks it | Result |
|---|---|---|
| A prospect on the do-not-call list is suppressed and logged | tuple 19-08: prospect appears on DNC, suppress, log; the miss goes in the books as suppressed-by-rule | holds |
| An expired listing reaches you and compliance before any contact | tuple 19-06: expired listing surfaced, human + compliance gate before ANY contact; prior-brokerage rules bind | holds |
| An expired listing that relists with another broker is closed as an opportunity | tuple 19-04: an expired listing relists with another broker, update the record; the opportunity is closed | holds |

### The success statement says it; the product does not do it

- Graduation from probation takes logged cases and your ratification. No code for a probation period or a graduation

### Needs an outside system that is not connected

- Opportunities are read from the expired and FSBO feeds. No feed is connected; the opportunity is entered
