# Walkthrough notes (P03 onward), for the owner's single review
P01 signed 2026-10-21. P02 signed 2026-10-21.

## P03 Under-Contract Transition
- Run: contract filed via a client reply (11 -> 08 -> 07), signed status pending,
  marketing halted, seller told, timeline loaded (P03 ends, P09 starts).
- FIXED: the listing's ad, still held for release, could have been released after
  the halt and published an ad for a pending listing. 12 now asks you to decline
  it, and sends no platform halt for an ad that never went out.

## P05 Expired/Withdrawn Wind-down
- Run: signed withdrawal, seller told, marketing halted, record updated.
- FIXED: same held-ad case as P03.

## P04 Open House Cycle (built 2026-10-20)
- Run: you schedule it on the active listing; calendar, signage order through
  the roster, log; a walk-in inquiry runs P11 on its own; you record the result.
- FIXED: Agent 01 treated an inquiry about the brokerage's own new listing as
  "outside our scope" and sent it to the legal line, because its scope was only
  the signed list. Agent 05 now tells Agent 01 every listing it records (route
  05 -> 01 listing.data added).
- NOT IN THE RUN: promotion of the open house (a signed campaign through 12) and
  a review of the materials by 17; the signage vendor needs a roster entry.

## P06 New Buyer Onboarding
- Run: buyer's consent and criteria, you record the signed buyer agreement (the
  run starts there, as PLAYBOOKS.md says), one of our listings goes live and the
  buyer gets the first match.
- CHANGED: the table started P06 on the buyer's criteria; PLAYBOOKS.md starts it
  on the agreement. Now on the agreement.
- DECISION FOR YOU: PLAYBOOKS.md says P06 "hard-stops without the agreement".
  The code stops showings without it (Agent 11 and 13), but still sends listing
  matches before it. Hold matches until the agreement, or keep sending them?
- DECISION FOR YOU (from P02): beyond budget, the buyer's other criteria (area,
  beds) only rank matches; a listing in the wrong area is still sent. Should a
  stated area or bed count exclude a listing, and is "3 beds" exactly 3 or at
  least 3?

## P07 Tour Day Coordination
- Run: buyer asks for a showing through Agent 11; 06 confirms it, books the
  calendar, the buyer is told; the next day the clock asks for feedback (which
  also tells 18 the showing happened, so no false no-show); the buyer replies.
- FIXED: the buyer's feedback words were logged empty (06 read "response", 11
  sends "message").
- CHANGED: the table ended P07 on a log kind Agent 06 never writes
  ("showing_feedback"); it writes "feedback_received". P07's end and P22's start
  now use that, so P22 follows a real tour (before, only a stand-in line did it).

## P22 Buyer Feedback & Match Refresh
- Run: the tour's feedback opens it; the next listing that fits the buyer
  closes it with a match.
- NOTE: feedback does not change the buyer's criteria unless it says so in
  words on the criteria-change list ("bedrooms too small" is not on it).

## P08 Offer-to-Acceptance
- Run: you record the offer received, then rejected; 07 logs each stage to 14.
  Accepted hands on to P03 (the contract and status pending).
- NOTE: each stage you sign also lands in your question queue as "offer status
  update - human review" (your decision #5 of 2026-07). You signed it yourself,
  so it may be noise; keep it or drop it?

## P09 Contract-to-Close
- Run: you load the timeline; 07 tracks each deadline (18 gets them), asks 08
  for each milestone's document (08 asks the client through 11), orders the
  inspector through the roster; the title company's settlement statement comes
  in through 11 from a sender you listed; 07 closes and hands on to P10.
- CHANGED (spec only): the settlement statement now arrives the real way (a
  client reply with the document from the listed title sender), not as a
  stand-in Agent 08 line.
- DECISION FOR YOU: 07 closed the deal although the inspection milestone never
  got its report. Close anyway (contingency waived in practice), or hold the
  closing for you naming the open milestones?

## P10 Close + Post-Close Handoff
- Run: the deal closes; 16 (referral program), 14 (record) and 15 (commission,
  27,000 from the statement) get it; 30 days later the check-in goes out.
- NOTE: PLAYBOOKS.md lists Agent 12 in P10; nothing reaches 12 at close (the
  listing's marketing was already halted at "pending"). The MLS status "sold"
  still needs your signed change with the closing artifact.

## P11 Speed-to-Lead
- Run: a web inquiry; 01 captures it with consent and checks duplicates, 02
  scores it WARM (60), 03 puts it in the nurture sequence after 17 approves the
  wording; a HOT lead goes straight to you (P04's walk-in shows that path).
- DECISION FOR YOU: the WARM lead's first message (day 0 of the sequence) goes
  out only when the daily clock runs, so a web inquiry can wait up to a day for
  any reply. Send the day-0 message at once (inside contact hours), or keep the
  daily clock?

## P12 Geographic Farm Campaign
- Run: you sign a farm campaign for zip 44101 (general audience); 17 approves
  it; the ad waits for your release; you release it and it publishes.
- FIXED (tracker): the run counted as finished when the ad was only held for
  your release. A held message now ends a run only once you release it.
- DECISION FOR YOU (from 2026-10-20): a farm campaign that names no listing is
  not held by the Clear Cooperation rule. Confirm.

## P13 Referral/Anniversary Cycle
- Run: you record a client's birthday and the client is on 16's supplied list;
  on the day, 14 triggers it, 16 asks 11 to send the greeting (consent checked),
  and it goes out. A client not on the list, opted out or with an adverse event
  gets no touch, and the block is logged.

## P14 Complaint Response
- Run: a public complaint; 20 logs it verbatim and raises it to you; 11 holds
  every outbound touch to that person; a routine message meanwhile is held;
  you mark it done and release the hold.
- CHANGED: the run ended when you marked the escalation done, while the hold
  on outbound messages was still on. It now ends when you release the hold
  (signed resolve_complaint_hold to Agent 11), as PLAYBOOKS.md says.
- NOTE: marking the complaint done and releasing the hold are two separate acts
  today; the Broker Desk has the first, the second is a signed setting.

## P15 CMA / Listing-Appointment Prep  and  P23 Price-Review Evidence
- Run: you ask Agent 10 for comparables (naming the playbook); 10 checks each
  comparable's source and date, says when there are too few ("thin"), and sends
  you the package with no price opinion and no number of its own.
- FIXED (tests and sessions, not the product): the comparables in the tests
  carried no source date Agent 10 reads, so all were dropped and an empty
  package passed. They now carry it and the package must hold them.
- DECISION 3 FOR YOU: a comparables request starts P02, P15 and P23 at once,
  so unless it names one it is held for you to pick. Options: keep picking each
  time; or a default (for example: on one of your live listings, P23; on no
  listing yet, P15; P02 only from a signed price change).

## P16 Morning Operations
- Run: the daily clock; 18 sends you the morning brief (calendar, what is
  waiting and on whom, decisions waiting for you, deadline conflicts, and any
  item whose source is missing from the log).
- GAP FOR YOU: PLAYBOOKS.md's brief also has overnight leads (14), market
  changes (10), prospect suggestions (19) and yesterday's books (15). Today
  the brief is Agent 18's part only. Proposal: each of those agents adds its
  section on the morning clock and 18 assembles one brief. Build it?

## P17 End-of-Day Books
- Run: on request (show eod), 14 sends the day's books: interactions, contexts,
  tier snapshot, and any client with records but no log entry, named as a gap.
- GAP FOR YOU: PLAYBOOKS.md includes 15's financial changes and the
  missed-item sweep; today it is 14's part only, and it runs only when asked
  (the daily clock does not run it). Run it on the evening clock and add 15's
  part?

## P18 Seller Weekly Report
- Run: on your set weekday the clock builds each seller's report (showings and
  feedback counts, numbers only) and holds it for you; you continue and 11
  sends it (consent checked). Cancel skips the week and is logged.

## P19 Property Access Custody
- Run: you record an access grant (who, until when, which lockbox reference;
  never the code itself, a grant that looks like it carries the code is
  refused), then close it. The daily clock flags a grant past its window that
  you have not closed.

## P20 Vacant Property Watch
- Run: you mark the listing vacant; on the interval (7 days) 05 orders a
  condition check through the roster (the booking waits for your release);
  you mark it occupied and the watch ends. A check counts only with proof.

## P21 Lead Re-Score Cycle
- Run: a nurtured lead's timeline counts down on the clock; 03 re-scores it
  through 02 every 7 days; here it stays WARM and goes back to nurture. A lead
  that turns HOT goes to you.

## P24 Prospecting Outreach (probation)
- Run: a prospect feed item in your zip and from an approved source; 19 sends
  it to you (every case is yours in probation); suppressed contacts are logged
  and dropped.
- NOTE: you get the prospect twice: once on discovery and again after 19 asks
  10 for comparables. Keep both or only the second?
