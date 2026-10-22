# Playbook runs

Written by `python synth/tuples/run_tuples.py --set playbooks`. Each playbook ran from its
start to its end in its own fresh state through `tools/console.py session`, after
`synth/tuples/setup.jsonl`; each must start its run, end it as completed, write its
after-action report and show the playbook's own evidence. The table is
`identity/playbooks.json` (PROPOSED until the owner ratifies it).

| Result | Playbooks |
|---|---|
| PASS | 24 |

| Tuple | Agent | Route | Result | Tuple text | Detail |
|---|---|---|---|---|---|
| P01 | PLAYBOOK | intake | PASS | P01 New Listing Onboarding: start to end |  |
| P02 | PLAYBOOK | intake | PASS | P02 Price Adjustment: start to end | B1 (budget 445,000) is matched only once the price drops to 440,000; B2, matched at 450,000, is told of the change, not matched twice; the ad carries no price, so you are not asked about it |
| P03 | PLAYBOOK | intake | PASS | P03 Under-Contract Transition: start to end |  |
| P04 | PLAYBOOK | intake | PASS | P04 Open House Cycle: start to end | the walk-in arrives as an inquiry and runs P11 on its own client |
| P05 | PLAYBOOK | intake | PASS | P05 Expired/Withdrawn Wind-down: start to end |  |
| P06 | PLAYBOOK | intake | PASS | P06 New Buyer Onboarding: start to end | owner change 2026-10-21: the run starts at the buyer's first criteria, so the wait for the signed agreement is inside it; our listing goes live, the match is held (no agreement), you record the agreement, and the next clock run sends the first match |
| P07 | PLAYBOOK | intake | PASS | P07 Tour Day Coordination: start to end | feedback is asked for the day after the showing, which also tells Agent 18 the showing happened |
| P08 | PLAYBOOK | intake | PASS | P08 Offer-to-Acceptance: start to end |  |
| P09 | PLAYBOOK | intake | PASS | P09 Contract-to-Close: start to end | the settlement statement arrives from the title company through Agent 11, from a sender you listed; the inspection never got its report, so the close waits for you and continues on your decision |
| P10 | PLAYBOOK | intake | PASS | P10 Close + Post-Close Handoff: start to end | the settlement statement arrives from the title company; the 30-day check-in goes out on the clock |
| P11 | PLAYBOOK | intake | PASS | P11 Speed-to-Lead: start to end |  |
| P12 | PLAYBOOK | intake | PASS | P12 Geographic Farm Campaign: start to end |  |
| P13 | PLAYBOOK | intake | PASS | P13 Referral/Anniversary Cycle: start to end |  |
| P14 | PLAYBOOK | intake | PASS | P14 Complaint Response: start to end | a routine message to the same person during the complaint is held (stand-in line from 06); the run ends when you release the hold |
| P15 | PLAYBOOK | intake | PASS | P15 CMA / Listing-Appointment Prep: start to end | a comparables request for an address that is not a live listing of ours is P15 |
| P16 | PLAYBOOK | intake | PASS | P16 Morning Operations: start to end | the morning clock: 18 asks 14, 15, 19 and 10 for their sections (decision 8, 2026-10-21) and sends you one briefing |
| P17 | PLAYBOOK | intake | PASS | P17 End-of-Day Books: start to end | the evening clock (decision 9, 2026-10-21): 14's end-of-day books go to 15, which adds the day's figures and sends you one report |
| P18 | PLAYBOOK | intake | PASS | P18 Seller Weekly Report: start to end |  |
| P19 | PLAYBOOK | intake | PASS | P19 Property Access Custody: start to end |  |
| P20 | PLAYBOOK | intake | PASS | P20 Vacant Property Watch: start to end |  |
| P21 | PLAYBOOK | intake | PASS | P21 Lead Re-Score Cycle: start to end |  |
| P22 | PLAYBOOK | intake | PASS | P22 Buyer Feedback & Match Refresh: start to end | the tour's feedback opens the refresh; the next listing that fits closes it |
| P23 | PLAYBOOK | intake | PASS | P23 Price-Review Evidence Assembly: start to end | a comparables request on a live listing of ours is P23 |
| P24 | PLAYBOOK | intake | PASS | P24 Prospecting Outreach: start to end |  |
