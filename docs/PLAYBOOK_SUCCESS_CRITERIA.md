# Playbook success criteria: what each run checks, and what it does not

Written by `python synth/tuples/run_tuples.py --set playbooks`; do not edit by hand.
Edit `synth/playbooks/specs/PLAYBOOKS.jsonl` and run it again.

Each playbook runs once, from its trigger to its end, in a fresh state, through
`tools/console.py session` with synthetic data. Every line under "Checked" is a
part of that playbook's success statement in [WHAT_SUCCESS_MEANS.md](WHAT_SUCCESS_MEANS.md),
tied to what must be on the audit record afterwards. The same lines run in the test
suite (`tests_listing/test_playbook_runs.py`), so a line that stops holding fails CI.

- **VERIFIED**: every checked line holds, and every part of the success statement is
  either checked or needs an outside system that is not connected (named below).
- **PARTLY VERIFIED**: every checked line holds; parts of the success statement are
  not shown by this run (named below).
- **FAILED**: a checked line does not hold.

One run is one path. Human gates this run does not reach are listed; the tuple runs
([synth/tuples/REPORT.md](../synth/tuples/REPORT.md)) exercise the gates one at a time.
Nothing here was run against a live MLS, a live ad platform or real clients.

| Playbook | Owner's sign-off of the run table | Status | Lines checked | Not shown | Needs an outside system | Gates not reached |
|---|---|---|---|---|---|---|
| P01 New Listing Onboarding | RATIFIED | VERIFIED | 13 | 0 | 1 | 4 |
| P02 Price Adjustment | RATIFIED | PARTLY VERIFIED | 13 | 2 | 1 | 0 |
| P03 Under-Contract Transition | RATIFIED | PARTLY VERIFIED | 12 | 2 | 0 | 1 |
| P04 Open House Cycle | RATIFIED | PARTLY VERIFIED | 11 | 3 | 0 | 0 |
| P05 Expired/Withdrawn Wind-down | RATIFIED | PARTLY VERIFIED | 9 | 3 | 1 | 0 |
| P06 New Buyer Onboarding | RATIFIED | PARTLY VERIFIED | 8 | 3 | 0 | 0 |
| P07 Tour Day Coordination | RATIFIED | PARTLY VERIFIED | 9 | 4 | 0 | 1 |
| P08 Offer-to-Acceptance | RATIFIED | PARTLY VERIFIED | 7 | 2 | 0 | 0 |
| P09 Contract-to-Close | RATIFIED | PARTLY VERIFIED | 12 | 4 | 0 | 1 |
| P10 Close + Post-Close Handoff | RATIFIED | PARTLY VERIFIED | 8 | 3 | 0 | 0 |
| P11 Speed-to-Lead | RATIFIED | PARTLY VERIFIED | 12 | 3 | 1 | 0 |
| P12 Geographic Farm Campaign | RATIFIED | PARTLY VERIFIED | 9 | 2 | 1 | 1 |
| P13 Referral/Anniversary Cycle | RATIFIED | PARTLY VERIFIED | 8 | 3 | 0 | 0 |
| P14 Complaint Response | RATIFIED | PARTLY VERIFIED | 10 | 2 | 1 | 0 |
| P15 CMA / Listing-Appointment Prep | RATIFIED | PARTLY VERIFIED | 8 | 1 | 1 | 0 |
| P16 Morning Operations | PROPOSED | PARTLY VERIFIED | 6 | 2 | 1 | 0 |
| P17 End-of-Day Books | PROPOSED | PARTLY VERIFIED | 6 | 3 | 0 | 0 |
| P18 Seller Weekly Report | RATIFIED | PARTLY VERIFIED | 7 | 3 | 0 | 0 |
| P19 Property Access Custody | RATIFIED | PARTLY VERIFIED | 6 | 3 | 0 | 0 |
| P20 Vacant Property Watch | RATIFIED | PARTLY VERIFIED | 8 | 3 | 0 | 0 |
| P21 Lead Re-Score Cycle | RATIFIED | PARTLY VERIFIED | 7 | 2 | 0 | 2 |
| P22 Buyer Feedback & Match Refresh | RATIFIED | PARTLY VERIFIED | 7 | 3 | 0 | 1 |
| P23 Price-Review Evidence Assembly | RATIFIED | PARTLY VERIFIED | 7 | 3 | 1 | 0 |
| P24 Prospecting Outreach | RATIFIED | PARTLY VERIFIED | 8 | 1 | 1 | 2 |

## P01 New Listing Onboarding

**VERIFIED.**

### Checked

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for L1, containing `"playbook": "P01"` | holds |
| The run ends as completed | playbook.completed for L1, containing `"playbook": "P01"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for L1, containing `"playbook": "P01"` | holds |
| The photographer's booking waits for your release | absolute_signal.hold containing `vendor.schedule` | holds |
| and goes out only after it | absolute_signal.released containing `vendor.schedule` | holds |
| Photos move on only with their proof artifact | a deliverable.release message for L1, containing `sha256-photo-L1` | holds |
| The listing description is reviewed for fair housing | a content.verdict message for L1, containing `"verdict": "approved"` and `ruleset_version` | holds |
| The ad waits for your release | a interaction.log message for L1, containing `campaign_publish_held` | holds |
| and is published only after it | absolute_signal.released containing `campaign.publish` | holds |
| The published ad is on the record | a campaign.publish message for L1 | holds |
| The seller is told the listing is active | a client.message.send message for L1, containing `status.update` and `"status": "active"` | holds |
| The go-live you authorized is recorded | a status.update message for L1, containing `"status": "active"` | holds |
| No message was dropped along the way | no dead.letter | holds |

### Needs an outside system that is not connected

- The MLS entry and the portals are checked live. No MLS or portal is connected. Agent 05 records the go-live you authorized and stops there; confirming it on the MLS stays with you

### Human gates this run does not reach

- A flagged compliance verdict stops the marketing path. This run's description is approved
- A pricing question from any party goes to you. No one asks one in this run
- Photos that contradict the property data go to you. The photo data agrees with the listing in this run
- Exempt-status marketing needs the signed seller disclosure first. The listing in this run is not exempt

## P02 Price Adjustment

**PARTLY VERIFIED.** B1 (budget 445,000) is matched only once the price drops to 440,000; B2, matched at 450,000, is told of the change, not matched twice; the ad carries no price, so you are not asked about it.

### Checked

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

### Not shown by this run

- Refreshed marketing no longer quotes the old figure. The ad in this run carries no price, so there is nothing to refresh; an ad that quotes a price is not run here
- A comparables package first, if you want one. That is P23; this run starts at your signed price

### Needs an outside system that is not connected

- The MLS and the portals show the new price. No MLS or portal is connected; updating them stays with you

## P03 Under-Contract Transition

**PARTLY VERIFIED.**

### Checked

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for L1, containing `"playbook": "P03"` | holds |
| The run ends as completed | playbook.completed for L1, containing `"playbook": "P03"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for L1, containing `"playbook": "P03"` | holds |
| The executed contract is on file | a interaction.log message for L1, containing `document_filed` and `executed_contract` | holds |
| Pending is recorded on the listing | a status.update message for L1, containing `"status": "pending"` | holds |
| The seller is told the listing is pending | a client.message.send message for L1, containing `status.update` and `"status": "pending"` | holds |
| An ad still waiting for your release is not published; you are asked to decline it | a clarification.request message for L1, containing `still held for your release` and `Decline it` | holds |
| Contract-to-close starts when you load the dates | playbook.started for L1, containing `"playbook": "P09"` | holds |
| The deadline map is loaded with its milestones | a interaction.log message for L1, containing `timeline_loaded` and `inspection` and `appraisal` and `financing_contingency` and `closing` | holds |
| Each of the four deadlines goes to the calendar | exactly 4 x a deadline.alert message for L1 | holds |
| The first document requests go out | exactly 3 x a client.message.send message for L1, containing `document_request` | holds |
| No message was dropped along the way | no dead.letter | holds |

### Not shown by this run

- The seller is told what happens next. The message is the status notice (a template id and the status); no next-steps text is produced
- Vendors are booked for the milestones. The synthetic roster has no inspector or appraiser, so nothing is booked and you are asked (that question is on the record)

### Human gates this run does not reach

- Pending is refused without the executed contract on file. This run supplies the contract before the status change

## P04 Open House Cycle

**PARTLY VERIFIED.** The walk-in arrives as an inquiry and runs P11 on its own client.

### Checked

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

### Not shown by this run

- The open house is promoted. This run schedules the open house and records its result; no promotion goes out for it
- Walk-ins are de-duplicated. One walk-in in this run
- Every walk-in is captured. The walk-in arrives as one inquiry you (or a form) enter; nothing reads a sign-in sheet

## P05 Expired/Withdrawn Wind-down

**PARTLY VERIFIED.**

### Checked

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for L1, containing `"playbook": "P05"` | holds |
| The run ends as completed | playbook.completed for L1, containing `"playbook": "P05"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for L1, containing `"playbook": "P05"` | holds |
| Withdrawn is recorded on the listing | a status.update message for L1, containing `"status": "withdrawn"` | holds |
| The seller is told | a client.message.send message for L1, containing `status.update` and `withdrawn` | holds |
| Marketing for the listing is halted | a interaction.log message for L1, containing `marketing_halted` | holds |
| An ad never released is not published; you are asked to decline it | a clarification.request message for L1, containing `still held for your release` and `Decline it` | holds |
| No ad is published for the withdrawn listing | no campaign.publish message for L1 | holds |
| No message was dropped along the way | no dead.letter | holds |

### Not shown by this run

- A live ad is halted. In this run the ad was still waiting for your release when the listing was withdrawn, so no released ad is halted here
- The seller hears it in your words. The message is a template id and the status; the wording is yours to supply
- A former client is not auto-enrolled in anything. Nothing in this run tries to

### Needs an outside system that is not connected

- A live ad is taken down on every platform and each takedown is verified. No ad platform is connected

## P06 New Buyer Onboarding

**PARTLY VERIFIED.** Owner change 2026-10-21: the run starts at the buyer's first criteria, so the wait for the signed agreement is inside it; our listing goes live, the match is held (no agreement), you record the agreement, and the next clock run sends the first match.

### Checked

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for B1, containing `"playbook": "P06"` | holds |
| The run ends as completed | playbook.completed for B1, containing `"playbook": "P06"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for B1, containing `"playbook": "P06"` | holds |
| No match goes to a buyer without a signed buyer agreement on file | a interaction.log message for B1, containing `match_held_no_buyer_agreement` | holds |
| You are told the matches are waiting for the agreement | a clarification.request message for B1, containing `no signed buyer agreement` | holds |
| Once you record the agreement, the held match goes to the buyer | a client.message.request message for B1, containing `new_match` and `"listing_id": "L1"` | holds |
| The buyer gets it once | exactly 1 x a client.message.send message for B1, containing `new_match` | holds |
| No message was dropped along the way | no dead.letter | holds |

### Not shown by this run

- The agreement document is filed and checked to open. In this run you record the agreement with a signed setting; no document is filed
- The buyer's criteria are recorded as their own words. The criteria are your signed entry; the record line that marks them as stated by the buyer is not checked here
- Matches flow from day one. One listing, one match in this run

## P07 Tour Day Coordination

**PARTLY VERIFIED.** Feedback is asked for the day after the showing, which also tells Agent 18 the showing happened.

### Checked

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
| No message was dropped along the way | no dead.letter | holds |

### Not shown by this run

- Several showings across several listings are sequenced in one day. One showing in this run
- Every party gets a confirmation. Only the buyer is messaged; no listing agent or seller is
- Feedback is asked twice at most. One ask in this run; the cap is tuple 06-10
- The buyer's profile changes only from what they explicitly said. The feedback here changes no criterion and nothing checks that it could not

### Human gates this run does not reach

- After 21:00 the confirmation is held for quiet hours until 08:00. The run's clock is pinned to noon. Measured with the clock at 23:15: the confirmation is held and this playbook does not finish until the morning run

## P08 Offer-to-Acceptance

**PARTLY VERIFIED.**

### Checked

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for L1, containing `"playbook": "P08"` | holds |
| The run ends as completed | playbook.completed for L1, containing `"playbook": "P08"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for L1, containing `"playbook": "P08"` | holds |
| Each offer stage you report is recorded | exactly 2 x a interaction.log message for L1, containing `offer_status` | holds |
| Every stage comes to you for review | exactly 2 x a clarification.request message for L1, containing `offer status update - human review` | holds |
| The agents send nothing about the offer to anyone | no client.message.send message for L1, containing `offer` | holds |
| No message was dropped along the way | no dead.letter | holds |

### Not shown by this run

- Offer documents are tracked. No offer document is submitted in this run; the stages are your signed entries
- An accepted offer hands on to under-contract. The offer in this run is rejected

## P09 Contract-to-Close

**PARTLY VERIFIED.** The settlement statement arrives from the title company through Agent 11, from a sender you listed; the inspection never got its report, so the close waits for you and continues on your decision.

### Checked

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

### Not shown by this run

- A deadline that passes unsatisfied alerts as overdue. No deadline passes in this run
- A financing contingency date passing with no removal on file reaches you as a legal-line item. This run's dates are inspection and closing only
- Documents are chased on a capped cadence that ends with you. No reminder cycle runs here; the cap is tuple 08-05
- Vendors are booked from your roster with credentials checked. The synthetic roster has no inspector, so none is booked

### Human gates this run does not reach

- Wire instructions in a document are quarantined. No document in this run carries any

## P10 Close + Post-Close Handoff

**PARTLY VERIFIED.** The settlement statement arrives from the title company; the 30-day check-in goes out on the clock.

### Checked

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for L1, containing `"playbook": "P10"` | holds |
| The run ends as completed | playbook.completed for L1, containing `"playbook": "P10"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for L1, containing `"playbook": "P10"` | holds |
| The close reaches the books, the client record and the follow-up program | exactly 3 x a transaction.closed message for L1 | holds |
| Consent is checked before the check-in | a record.request message for L1, containing `consent_check` | holds |
| The 30-day check-in is sent on the clock | exactly 1 x a client.message.send message for L1, containing `post_close_checkin_30day` | holds |
| and is recorded | a interaction.log message for L1, containing `post_close_checkin_sent` and `"day": 30` | holds |
| No message was dropped along the way | no dead.letter | holds |

### Not shown by this run

- The 90-day and 365-day check-ins are sent. The run's clock stops at day 30
- The commission is reconciled against an independent record of the close. No reconciliation line is on this run's record
- The client record becomes past-client with anniversary dates armed. Not on this run's record

## P11 Speed-to-Lead

**PARTLY VERIFIED.**

### Checked

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

### Not shown by this run

- A lead is de-duplicated before it can count twice. Each person inquires once in this run. Tuple 01-01 (two inquiries at once for one person) is a known VARIANCE: two captures where the tuple expects one
- The five-minute clock is kept at 9 at night. The run's clock is pinned to noon
- A lead spotted on social media enters the same way. Both inquiries here come by web form

### Needs an outside system that is not connected

- The call itself. No phone system is connected; the item on your list is the alert

## P12 Geographic Farm Campaign

**PARTLY VERIFIED.**

### Checked

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

### Not shown by this run

- Audience parameters are never derived from identified owner records. Nothing in this run checks where the audience came from
- Agents 03, 10 and 19 take part. Only 12 and 17 act in this run

### Needs an outside system that is not connected

- The campaign runs on the ad platform. No ad platform is connected; published means released onto the record

### Human gates this run does not reach

- Demographic targeting is refused. This run's audience is general

## P13 Referral/Anniversary Cycle

**PARTLY VERIFIED.**

### Checked

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for C1, containing `"playbook": "P13"` | holds |
| The run ends as completed | playbook.completed for C1, containing `"playbook": "P13"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for C1, containing `"playbook": "P13"` | holds |
| The date on the client's record triggers the touch | a client.message.request message for C1, containing `birthday_greeting` | holds |
| Consent is checked before it is sent | a record.request message for C1, containing `consent_check` | holds |
| The greeting is sent | exactly 1 x a client.message.send message for C1, containing `birthday_greeting` | holds |
| A client who opted out of every channel is sent nothing | no client.message.send message for C2 | holds |
| No message was dropped along the way | no dead.letter | holds |

### Not shown by this run

- Anniversaries and holidays work the same way. This run uses a birthday
- Referral requests go out on their cadence. None is due in this run
- A referral that comes back becomes a lead. None comes back in this run

## P14 Complaint Response

**PARTLY VERIFIED.** A routine message to the same person during the complaint is held (stand-in line from 06); the run ends when you release the hold.

### Checked

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

### Not shown by this run

- A complaint that is spreading reaches you at priority. One mention in this run
- A complaint received directly by Agent 11 is handled the same way. This run's complaint is a social mention

### Needs an outside system that is not connected

- The mention is read from the social platform. No social platform is connected; the mention is entered

## P15 CMA / Listing-Appointment Prep

**PARTLY VERIFIED.** A comparables request for an address that is not a live listing of ours is P15.

### Checked

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

### Not shown by this run

- The listing appointment is on the calendar (Agent 18). No appointment is entered in this run

### Needs an outside system that is not connected

- The comparables come from a data source. No comp source is connected. Agent 10 builds the package only from comparables you hand it, as this run does

## P16 Morning Operations

**PARTLY VERIFIED.** The morning clock: 18 asks 14, 15, 19 and 10 for their sections (decision 8, 2026-10-21) and sends you one briefing.

### Checked

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for briefing, containing `"playbook": "P16"` | holds |
| The run ends as completed | playbook.completed for briefing, containing `"playbook": "P16"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for briefing, containing `"playbook": "P16"` | holds |
| One morning briefing reaches you | a report.package message for briefing, containing `morning` | holds |
| It has its sections and names none as missing | a report.package message for briefing, containing `overnight_leads` and `yesterdays_books` and `prospects_waiting` and `market_changes` and `"sections_missing": []` | holds |
| No message was dropped along the way | no dead.letter | holds |

### Not shown by this run

- The briefing's contents are right. This run's day is empty (no leads, no books, no prospects), so it shows the briefing is assembled from every section, not that a full day is reported correctly
- Record conflicts listed are real conflicts. Open item for the owner: over the 24 playbook runs the record-conflict flag fired 10 times, each on ordinary activity (two different messages, a status change)

### Needs an outside system that is not connected

- Market movement with a source on every figure. No market data source is connected

## P17 End-of-Day Books

**PARTLY VERIFIED.** The evening clock (decision 9, 2026-10-21): 14's end-of-day books go to 15, which adds the day's figures and sends you one report.

### Checked

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for eod-report, containing `"playbook": "P17"` | holds |
| The run ends as completed | playbook.completed for eod-report, containing `"playbook": "P17"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for eod-report, containing `"playbook": "P17"` | holds |
| One end-of-day report reaches you with the record's books and the day's figures | a report.package message for eod-report, containing `"report_type": "eod_books"` and `"figures"` and `"crm"` | holds |
| Agent 14's books go to Agent 15 first | exactly 2 x a report.package message for eod-report, containing `"report_type": "eod"` | holds |
| No message was dropped along the way | no dead.letter | holds |

### Not shown by this run

- The day's activity is in the report. This run's day is empty
- A logging gap is named, never smoothed over. Tuple 14-03 is NOT REACHABLE since owner decision D-A6; the gap check is tested with state set directly
- The record is dated and hashed. Not checked by a line here

## P18 Seller Weekly Report

**PARTLY VERIFIED.**

### Checked

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for S1, containing `"playbook": "P18"` | holds |
| The run ends as completed | playbook.completed for S1, containing `"playbook": "P18"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for S1, containing `"playbook": "P18"` | holds |
| The weekly report is prepared on the weekday you signed | a client.message.request message for S1, containing `seller_weekly_report` | holds |
| Your continue is on the record | hitl.decision.authorized for S1, containing `APPROVE` | holds |
| The report goes to the seller once | exactly 1 x a client.message.send message for S1, containing `seller_weekly_report` | holds |
| No message was dropped along the way | no dead.letter | holds |

### Not shown by this run

- The counts are the week's real showings and feedback. This run's week has none (0 showings, 0 with feedback); counting from real showings is tuple 06-12
- Nothing is sent before your continue. The record shows the decision and one send; a line cannot check their order. The order is checked in tests_listing/test_wiring_2026_10_12.py (P18 test)
- Market movement and next steps are in the report. The report holds the showing and feedback counts only

## P19 Property Access Custody

**PARTLY VERIFIED.**

### Checked

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for L1, containing `"playbook": "P19"` | holds |
| The run ends as completed | playbook.completed for L1, containing `"playbook": "P19"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for L1, containing `"playbook": "P19"` | holds |
| An access grant is recorded with who, until when, and the custody reference | a config.update message for L1, containing `access_grant` and `Pat Inspector` and `2026-10-20` and `lockbox-L1` | holds |
| Closing the grant is recorded | a config.update message for L1, containing `access_closed` | holds |
| No message was dropped along the way | no dead.letter | holds |

### Not shown by this run

- A grant near or past its end date is flagged. The grant is closed before its end date in this run
- No lockbox code ever rides a message. Nothing in this run offers one; the grant carries a custody reference, not a code
- Audit, rotate and revoke. This run opens one grant and closes it

## P20 Vacant Property Watch

**PARTLY VERIFIED.**

### Checked

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

### Not shown by this run

- A walkthrough with no proof artifact did not happen. The check is never released or reported on in this run
- Utility status is tracked. Not on this run's record
- Unusual activity is surfaced. Not on this run's record

## P21 Lead Re-Score Cycle

**PARTLY VERIFIED.**

### Checked

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for T1, containing `"playbook": "P21"` | holds |
| The run ends as completed | playbook.completed for T1, containing `"playbook": "P21"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for T1, containing `"playbook": "P21"` | holds |
| A warm lead in nurture is re-scored on the 7-day clock | a lead.rescored message for T1 | holds |
| The re-score decision is logged with the rubric version | exactly 2 x a interaction.log message for T1, containing `"rubric_version": "synth-v1"` and `"tier": "WARM"` | holds |
| A lead still warm stays in nurture on its sequence | a lead.nurture message for T1, containing `"reassignment": true` | holds |
| No message was dropped along the way | no dead.letter | holds |

### Not shown by this run

- A lead that has warmed to hot is promoted back to the call path. The lead in this run stays warm
- No lead is left in an unknown state. One lead in this run

### Human gates this run does not reach

- Consent withdrawn since capture: no touch, no promotion. Consent stands in this run
- A re-score into hot with a legal or complaint signal goes to you. None in this run

## P22 Buyer Feedback & Match Refresh

**PARTLY VERIFIED.** The tour's feedback opens the refresh; the next listing that fits closes it.

### Checked

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for B1, containing `"playbook": "P22"` | holds |
| The run ends as completed | playbook.completed for B1, containing `"playbook": "P22"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for B1, containing `"playbook": "P22"` | holds |
| The tour's run is closed by the feedback | playbook.completed for B1, containing `"playbook": "P07"` and `completed` | holds |
| The feedback is on the buyer's record | a interaction.log message for B1, containing `feedback_received` and `bedrooms too small` | holds |
| The next listing that fits goes to the buyer | a client.message.request message for B1, containing `new_match` and `"listing_id": "L1"` | holds |
| No message was dropped along the way | no dead.letter | holds |

### Not shown by this run

- The change to the buyer's criteria is recorded. The feedback in this run changes no criterion
- The refreshed matches are compliance-cleared. No compliance review of the match is on this run's record
- It happens the same day. Not checked by a line here

### Human gates this run does not reach

- Feedback that reads as a discriminatory preference goes to compliance first. None in this run

## P23 Price-Review Evidence Assembly

**PARTLY VERIFIED.** A comparables request on a live listing of ours is P23.

### Checked

| What success means | What must be on the record | Result |
|---|---|---|
| The run starts on the playbook's trigger | playbook.started for L1, containing `"playbook": "P23"` | holds |
| The run ends as completed | playbook.completed for L1, containing `"playbook": "P23"` and `"outcome": "completed"` | holds |
| An after-action report is written for the run | after_action.written for L1, containing `"playbook": "P23"` | holds |
| The comparables package reaches you with its count and whether it is thin | a data.package message for L1, containing `"comp_count": 6` and `"thin": false` | holds |
| Every comparable carries its source and retrieval date | a data.package message for L1, containing `MLS-SYN` and `retrieval_date` | holds |
| No number that you did not write: no price recommendation | no data.package message for L1, containing `recommended_price` | holds |
| No message was dropped along the way | no dead.letter | holds |

### Not shown by this run

- Your listing's own activity is in the evidence. The package in this run holds comparables only
- Financial context on request. Not asked for in this run
- Your decision is recorded. No decision is entered in this run

### Needs an outside system that is not connected

- The comparables and absorption figures come from a data source. No comp source is connected; the package is built from comparables you hand in

## P24 Prospecting Outreach

**PARTLY VERIFIED.**

### Checked

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

### Not shown by this run

- Graduation from probation takes logged cases and your ratification. Not exercised

### Needs an outside system that is not connected

- Opportunities are read from the expired and FSBO feeds. No feed is connected; the opportunity is entered

### Human gates this run does not reach

- A prospect on the do-not-call list is not surfaced for outreach. The prospect in this run is not on it
- A prospect listed with another broker goes to you as a legal-line item. Not the case in this run
