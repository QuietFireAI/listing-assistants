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
| P02 | PLAYBOOK | intake | PASS | P02 Price Adjustment: start to end |  |
| P03 | PLAYBOOK | intake | PASS | P03 Under-Contract Transition: start to end |  |
| P04 | PLAYBOOK | intake | PASS | P04 Open House Cycle: start to end | the walk-in arrives as an inquiry and runs P11 on its own client |
| P05 | PLAYBOOK | intake | PASS | P05 Expired/Withdrawn Wind-down: start to end |  |
| P06 | PLAYBOOK | intake | PASS | P06 New Buyer Onboarding: start to end | the new listing arrives from Agent 05 (stand-in line) |
| P07 | PLAYBOOK | intake | PASS | P07 Tour Day Coordination: start to end |  |
| P08 | PLAYBOOK | intake | PASS | P08 Offer-to-Acceptance: start to end |  |
| P09 | PLAYBOOK | intake | PASS | P09 Contract-to-Close: start to end | the settlement statement arrives as Agent 08's doc.status (stand-in line) |
| P10 | PLAYBOOK | intake | PASS | P10 Close + Post-Close Handoff: start to end | the settlement statement arrives as Agent 08's doc.status (stand-in line) |
| P11 | PLAYBOOK | intake | PASS | P11 Speed-to-Lead: start to end |  |
| P12 | PLAYBOOK | intake | PASS | P12 Geographic Farm Campaign: start to end |  |
| P13 | PLAYBOOK | intake | PASS | P13 Referral/Anniversary Cycle: start to end |  |
| P14 | PLAYBOOK | intake | PASS | P14 Complaint Response: start to end |  |
| P15 | PLAYBOOK | intake | PASS | P15 CMA / Listing-Appointment Prep: start to end | the request names its playbook (data.request comp also starts P02 and P23) |
| P16 | PLAYBOOK | intake | PASS | P16 Morning Operations: start to end |  |
| P17 | PLAYBOOK | intake | PASS | P17 End-of-Day Books: start to end |  |
| P18 | PLAYBOOK | intake | PASS | P18 Seller Weekly Report: start to end |  |
| P19 | PLAYBOOK | intake | PASS | P19 Property Access Custody: start to end |  |
| P20 | PLAYBOOK | intake | PASS | P20 Vacant Property Watch: start to end |  |
| P21 | PLAYBOOK | intake | PASS | P21 Lead Re-Score Cycle: start to end |  |
| P22 | PLAYBOOK | intake | PASS | P22 Buyer Feedback & Match Refresh: start to end | the showing feedback and the new listing arrive from Agents 06 and 05 (stand-in lines) |
| P23 | PLAYBOOK | intake | PASS | P23 Price-Review Evidence Assembly: start to end |  |
| P24 | PLAYBOOK | intake | PASS | P24 Prospecting Outreach: start to end |  |
