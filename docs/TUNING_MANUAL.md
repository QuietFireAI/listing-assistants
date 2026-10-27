# Tuning Manual - ListingAssistants

> **Words used here.** Tuple, playbook, swarm, hold, release and the other technical words are explained in plain language in [GLOSSARY.md](GLOSSARY.md).

## Runtime & mount status (2026-10-12)

| Item | Status |
|---|---|
| Listing runtime | **WORKING BUILD** - dispatcher + 20 spokes, 1321 tests, all playbooks P01-P24 e2e (incl. the P01 new-listing lifecycle with photo/compliance/Clear-Cooperation gates). Every playbook scores leads through the JEV adapter (Agent 02). Client drawers, the HITL protocol, model drafting (Hermes seam) and the SQLite store are wired by `dispatcher/swarm.py`, which the console runs; their tests are in `tests_listing/test_wiring_2026_10_12.py` and `tests_listing/test_mutation_hardening_2026_10_12.py`. The playbook e2e builder uses a bare hub without them. The update-pack verifier is a tool (`tools/verify_update_pack.py`) with its own tests. |
| Live demo | `tools/run_demo.py` - one listing, six acts, real hub: signed authorization, fair-housing flag caught, go-live verified, pricing question escalated, chain verified. |
| MCP mount | **WORKING** - `dispatcher/identity_mcp.py` (4-tool closed surface, boot conformance gate), proven by `tools/mcp_roundtrip.py` live stdio round trip. Mounts on Hermes/OpenClaw/Claude Desktop (docs/MOUNTING.md). Full live-host install not yet exercised; the MCP protocol is. |
| Front door | `listing.authorize` runs P01 when signed; the host cannot route inside the swarm. Over MCP the server signs it only in `--demo-signing` mode (docs/MOUNTING.md, "Signing over MCP"). |
| Brand | ListingAssistants ([ListingAssistants.com](https://ListingAssistants.com)), formerly `listing-agents`. |


Every numeric/timing parameter in this codebase that a human might
reasonably want to retune, in one place. Compiled by a direct code sweep
(constructor signatures + inline threshold comparisons), not from memory -
if a parameter existed and wasn't listed here on the first pass, that was
a real gap, not an intentional omission.

**Re-swept 2026-07-17** (3rd full pass): found 6 more constructor-level
parameters missed in the first sweep because they're dict/set-shaped, not
simple numerics - the original grep pattern only caught `int`/`float`
defaults. Also found 2 core-level (dispatcher-agents, not this repository)
parameters that were self-flagged in their own code comments as
provisional and never actually ratified - discussed directly with the
owner the same day and ratified as deliberate placeholders (see their own
section below), rather than either silently treated as settled or left
open.

**How to retune any of these:** each one is a constructor keyword argument.
Change it at the point where the agent is instantiated (wherever your
deployment wires up the swarm), e.g.:

```python
Spoke02LeadQualification(hub, hot_lead_sla_seconds=180)
```

No source-code edits required for anything in this table - that's the
point of exposing them as constructor parameters instead of hardcoding
them inline.

---

## TOP OF LIST - Deliberate placeholders & unratified configs (read before deployment)

Re-swept 2026-10-14 from the code and from what the swarm writes when it
starts: every placeholder is in this table, and every stand-in or unarmed
mode is in **Stand-ins and unarmed modes** below. The core's own list is in
dispatcher-agents `docs/TUNING_MANUAL.md`.

| Item | Where | Status | What blocks / what to do |
|---|---|---|---|
| Text pages | `python tools/console.py pager` → `console-state/pager.json` (0600) | **OFF until you set it** | The console's pager (`dispatcher/pager.py`) asks for the Twilio details; pages carry queue + client context only. The core `dispatcher/notifier.py` placeholders (env vars, `+1-555-555-0100`) are not used by the console. |
| Re-score cadence (P21) | `Spoke03LeadNurture.RESCORE_INTERVAL_DAYS` | **7 days** | WARM leads in nurture are re-scored this often. |
| Vacant check interval (P20) | `Spoke05MLSListingManagement.VACANT_CHECK_INTERVAL_DAYS` | **1 day** (owner decision 2026-10-21, was 7: conditions change fast; signed `watch_interval_days` per listing overrides) | Agent 09 does not book a new check while the last one is open (held for your release, or sent with no proven delivery); you are told once per open check |
| Disclosure warning lead (J4) | `Spoke08DocumentCollection.DISCLOSURE_LEAD_DAYS` | **3 days** | Warned once on the legal line. |
| `loop_threshold=20` | core `dispatcher/hub.py` | **RATIFIED as deliberate placeholder (owner, 2026-07-17)** | No empirical basis existed to pick a better number; revisit after production traffic. |
| MANNERS `N=10` | `dispatcher/manners_reinjection.py` `BACKSTOP_N` | **RATIFIED (2026-07-17); wired in this product 2026-10-14** | Every 10 envelopes an agent handles with no other re-injection, the turn backstop fires (`manners.reinjection`, trigger `turn_backstop`). The core still counts nothing itself (D7); this product does. Counts live in the process; a restart starts them at 0. |
| `config/authority_signers.json` | this repo | **UNRATIFIED - fails closed** | Template for identity-provider logins with MFA. No identity provider is connected in this build, so leave it unratified; the hub checks the key's signature and records that the login binding is off. |
| `config/vendor_panel.json` | this repo | **UNRATIFIED - fails closed** | Template in Agent 09's format (`vendors: vendor_id -> {kind, license_expiry, insurance_expiry, regulated}`); needs your actual vendors. Same fail-closed rule. The operator scenes use `scenes/config/vendor_panel.json`, a synthetic roster you ratify by hand. |
| External adapters (`vendor.schedule`, `client.message.send`, `campaign.publish`) | the `external` destination on the closed track | **NOT WIRED** | Held until your signed release, then queued to `external`; tracked in the adapter table below until connected to real providers. |
| `approved_by` fields | `config/message_templates.json` | **RATIFIED 2026-07-18** (owner blanket sign-off in `_status`) | No code reads this file yet; Agent 11 sends template ids and variables, and wording is the deployment's adapter's job. |

### Stand-ins and unarmed modes (re-swept 2026-10-14)

Each row says how the mode shows itself. The boot lines are the first
entries of the audit log every time the swarm starts.

| Mode | Where | What happens | How it shows itself | To replace |
|---|---|---|---|---|
| Exit gate unarmed (pre-response-selfcheck) | core hub; the swarm passes no reviewer | Outbound text is not reviewed by a second reader; the gate is not called | `selfcheck.unarmed` once at boot | A reviewer model passed as `selfcheck_model` |
| No human notifier | a hub or swarm built without one: the MCP server (`dispatcher/identity_mcp.py`), the playbook test builder, and the daily clock (`tools/run_sweeps.py`) with the pager off, since the clock passes the pager as its notifier | Escalations land on queues and reach no person while that process runs; the clock's queue items are saved with the agent state and show on the Broker Desk or console when one is next opened | `notifier.unarmed` at boot (2026-10-14) | The console always passes one (next row); for the clock, turn the pager on |
| Pager off | `tools/console.py`, no `console-state/pager.json` | Human-queue landings are printed on the session screen (and listed on the Broker Desk) and recorded as `shown`, not as a person reached | `human.notified` with `transport_status: shown`; `onboard` prints `sms_pager: off` | `python tools/console.py pager` |
| JEV local rules | `dispatcher/decision_adapter.py` | Leads are scored by the local rubric engine. The adapter takes the key from `JEV_API_KEY` or, failing that, `config/integrations.json`; the model name from `JEV_MODEL` (default `jev-1.13.0`). The core hub's own boot line reads only the environment variable, so with the key in `integrations.json` the log shows `jev.unarmed_fallback` ("unconfigured") next to `decision.engine` saying a key is present; the `decision.engine` line is the adapter's | `jev.unarmed_fallback` and `decision.engine` at boot; every result carries `is_fallback` and a fallback warning | A key plus a signed `decision_engine.allow_external: true` |
| Signer registry not armed | `config/authority_signers.json` unratified | The key's Ed25519 signature is checked; which login signed is not | `signer.unarmed` on each authority envelope and HITL decision; `onboard` prints it under `not_armed` | Ratify the file with real IdP logins, then `hub.arm_signer_registry()` |
| Model drafting off | `dispatcher/model_drafting.py` | Agent 04 writes remarks by its rules | `drafting.model_status` with `model_ready: false` at boot | `--model-url`, an examined checkpoint, and a signed `drafting.mode: model` |
| Agent state not saved | the MCP server without `LISTING_STATE_DB`, the console with `--no-state`, tests | Agent state, held messages and waits live in the process only | `state.ephemeral` at boot | `LISTING_STATE_DB`; the console saves to `console-state/swarm-state.sqlite` unless `--no-state` |
| Unratified config files | `config/vendor_panel.json`, `config/transaction_milestones.json`, `config/cadence_settings.json` | Refused: Agent 09's roster stays empty, so every vendor request is refused; Agents 07 and 08 keep their ratified constructor defaults | `config.load` with `verdict: unratified` at boot | Edit, ratify (`_status` RATIFIED, date, name) |
| Config files no code reads | `config/message_templates.json`, `config/milestone_map.json`, `config/integrations_template.json` | Nothing: they record decisions and intended providers | Stated in this manual and the Operator Guide | Wiring that reads them |
| External destinations | `vendor.schedule`, `client.message.send`, `campaign.publish` | Kept in a list in the process; nothing leaves the machine | The deliveries are on the audit log; `show external` lists them | A real adapter (table below) |
| Provider registry | `dispatcher/provider_gateway.py`, `config/integrations.json` | Holds provider settings and masks secrets; no network calls, no agent reads it | Operator Guide §13 | Wiring per provider |
| MCP demo signing | `python -m dispatcher.identity_mcp --demo-signing` | The server signs authority calls for the host; demo only | `authority.server_signed` on the chain for each envelope it signs (added 2026-10-14; before, a server signature looked like a broker's), and `server_signs_for_host: true` in the identity description | Run without the flag; the host signs |
| Synthetic showcase | `tools/desk.py --showcase`, `scenes/config/vendor_panel.json` | The ten operator scenes on synthetic data and a synthetic vendor roster | Marked synthetic on the desk and in the roster's `_status` | Not for real work |
| Not built: portal and MLS feedback (Agent 05, three tuples), scrape-source blocking (Agent 10 tuple 6), farm rules for geographic targeting (Agent 12 tuple 8; the demographic refusal is built), a missing briefing source and a human instruction against a contract deadline (Agent 18 tuples 2 and 3) | `listing_spokes_05.py`, `_10.py`, `_12.py`, `_18.py` | No code path; those tuples cannot fire | Named in each agent's docstring | A real integration to build against |
| MANNERS re-injection | `dispatcher/manners_reinjection.py`, wired 2026-10-14 (owner decision) | Phase gates fire at P01's three phases (Agent 05) and at every signed human release, decline, HITL decision or other accepted signed authority (a price change, a config.update), once per event; the turn backstop every 10 turns per agent. A re-injection goes on the chain; the agents are deterministic code with nothing to inject into, and Agent 04's drafting prompt carries the whole MANNERS.md text on every call (the broker's exam questions to a checkpoint do not). `post_compaction` cannot fire: this product has no context compaction or summarization event | `manners.reinjection` with trigger and position | - |
| Process settings | `LISTING_CONFIG_DIR`, `LISTING_STATE_DB`, `IDENTITY_ROOT` (MCP server); `LISTINGASSISTANTS_STATE_DIR` (console, default `console-state/`); pager send timeout 10 s (`dispatcher/pager.py`) | Defaults used when unset: `config/`, no saved state, this repository, `console-state/` | Not on the log | Set the variable |
| Boot attestation not enforced | the test suite; the showcase desk (only in a folder it created; it refuses any folder holding your key); the MCP server when no operator key is found (`LISTINGASSISTANTS_STATE_DIR` pointed at a keyless folder turns its check off; it writes only its own temporary log) | No signed list is checked. The console, the Broker Desk, the daily clock, `repair-record`, and the MCP server with an operator key do check, and refuse to start on any difference (Operator Guide §16) | `boot.attestation` with `enforced: false` and the running hash | Start through the console, the desk or the clock |
| Core parts not called | KPIs, the core after-action report, priority and siding, heartbeat, territories, sleep-marks (boot attestation is called since 2026-10-14) | Not used by this product | dispatcher-agents README, "What runs in listing-assistants today" | Wiring per part |

Ratification path for the config files: review content → edit → change
`_status` to `RATIFIED` with date + sign-off → load. Fail-closed until
then is the invariant, not an inconvenience.

### Fixed in code (swept 2026-10-14)

A code sweep of every named value, default argument and numeric comparison
in `dispatcher/` and `tools/` found these fixed values. None of them is a
constructor argument or a signed setting. Changing one means editing the
source, after which every install must be attested again
(`python tools/console.py attest`).

**Trigger phrase lists.** These lists are how an agent recognizes a
message that must go to you. A message is matched by lower-case substring
(Agent 14's list by whole word), so a phrase not on the list is not
recognized. The synthetic sample run of
2026-10-14 showed this: "Please wire the earnest money instructions" did
not match Agent 11's wire list.

| Agent | List | Phrases | What a match does |
|---|---|---|---|
| 01 | `_LEGAL_LINE_WORDS` (`listing_spokes.py`) | 8: what should i offer, should i list at, negotiate, contract language, legal opinion, is this legal, represent me in, counter their offer | Legal-line escalation; the lead is not captured |
| 01 | `_DEMANDS_HUMAN_WORDS` | 11: speak to a human, talk to a human, talk to a person, speak to a person, get me a person, real person, speak to someone, human agent, not a robot, let me talk to someone, human now | Legal-line escalation; capture continues |
| 14 | `_SECRET_WORDS` (`listing_spokes.py`, whole words, not substrings) | 6: code, combo, combination, password, pin, passcode | An access record (P19) whose values contain one is rejected whole; access secrets never ride a message |
| 03 | `_LEGAL_LINE_WORDS` (`listing_spokes_03.py`) | 5: what should i offer, should i list at, negotiate, contract terms, legal opinion. Not the same list as Agent 01's | Legal-line escalation |
| 04 | `_SUPERLATIVE_WORDS` | 6: best block, best in town, best neighborhood, safest, most desirable, top school | In the requested language: declined in the copy |
| 04 | `_PROTECTED_CLASS_REQUEST_WORDS` | 6: school quality, school rating, neighborhood demographics, family-friendly, great schools, school district rating | In the requested language: refused in the copy, which still goes to compliance review |
| 06 | `_ACCESS_REQUEST_WORDS` | 6: let them in, access code, lockbox combo, gate code, just let, combo for the | Legal-line escalation; no access is given |
| 07, 08 | `_WIRE_WORDS` | 6: wire instructions, wiring details, wire transfer, updated wire, routing number, account number for closing | Legal-line escalation; Agent 08 also quarantines the document |
| 11 | `_WIRE_WORDS` | 5: the same without "account number for closing" | Legal-line escalation |
| 10 | `_OPINION_WORDS` | 4: what number would you go with, your opinion, what would you price it, the number you'd go with | Refusal, then escalation on repeat (`opinion_press_threshold`) |
| 10 | `_APPRAISAL_SUBSTITUTION_WORDS` | 4: is this worth, what's it actually worth, give me a value, instead of an appraisal | The data package carries a not-an-appraisal note and compliance (17) is told |
| 11 | `_ADVICE_WORDS` | 6: what would you do, should i offer, what's it worth, negotiate, legal opinion, pricing strategy | Legal-line escalation; the client gets a hand-off note and the thread waits for you |
| 13 | `_PROTECTED_CLASS_WORDS` | 10: school quality, school rating, demographics, families with, no children, race, religion, national origin, ethnic, families only | Legal-line escalation |
| 13 | `_SELLER_POSITION_WORDS` | 4: what would the seller take, seller's bottom line, what will they accept, seller's minimum | Legal-line escalation; nothing about the other party is shared |
| 13 | `_PRICE_OPINION_WORDS` | 4: is this a good price, good deal, worth the price, should i pay | Legal-line escalation |
| 15 | `_TRUST_ESCROW_WORDS` | 5: earnest money, trust account, escrow, wire the funds, disbursement | Legal-line escalation; trust and escrow accounting is out of scope |
| 16 | `_NEW_BUSINESS_WORDS` | 4: thinking of selling, looking to buy again, want to list, ready to move | A new lead to Agent 02 under a new context |
| 16 | `_PRICING_WORDS` | 3: what's my house worth, what is my house worth, what would it sell for now | Legal-line escalation |
| 16 | `_INCENTIVE_WORDS` | 4: gift card, referral bonus, pay you for, reward for referring | Legal-line escalation |
| 20 | `_PRICING_LEGAL_WORDS` | 5: the price is, we can offer, contract terms, legal advice, guarantee | A drafted public reply containing one is never published; legal-line escalation |
| 11, 20 | `ANGRY_WORDS` (`message_tags.py`, PROVISIONAL 2026-10-14) | 12: ridiculous, unacceptable, furious, angry, outraged, fed up, disgusted, incompetent, how dare, sue you, report you, scam | Complaint to you at once and an outbound hold; nothing is sent to the client |
| 11, 20 | `NEGATIVE_WORDS` (PROVISIONAL) | 12: not happy, unhappy, disappointed, frustrated, frustrating, annoyed, not thrilled, upset, not impressed, poor service, nobody called, no one called | Complaint to you at once and an outbound hold; the reply also goes to the owning agent marked for P14 |
| 11 | `CRITERIA_CHANGE_WORDS` (PROVISIONAL) | 9: forget the, changed my mind, actually i want, actually we want, no longer need, doesn't matter anymore, matters more, more important than, we've decided we want | Passed to the owning agent; Agent 13 asks the client to confirm and changes nothing |
| 11 | `REFERRAL_REWARD_WORDS` (PROVISIONAL) | 8: referral reward, referral fee, finder's fee, finders fee, reward if, for referring, kickback, referral incentive | Passed to the owning agent; Agent 16 sends the words to compliance (a gift idea goes to the legal line first) |
| Hermes seam | `WIRE_PHRASES`, `FAIR_HOUSING_PHRASES`, `PRICE_PHRASES` (`hermes_seam.py`) | 4, 11 and 3 phrases | Score a model draft; a score of 0.5 or more quarantines a correction (below) |

**Other fixed values.**

| Value | Where | What it does |
|---|---|---|
| `CHANNEL_RANK = {"call": 3, "text": 2, "web_form": 1}` | `listing_spokes.py` | Agent 01's tuple order (live call > text > web form) when the same field arrives twice |
| Tier oscillation: the last 3 tiers | `listing_spokes_02.py` | A tier that returns to the one it just left (A, B, A) goes to you (Agent 02 tuple) |
| `VALID_MLS_FIELDS`, `VALID_STATUSES`, ended statuses | `listing_spokes_05.py` | The MLS fields Agent 05 records and the statuses it accepts |
| `DOC_MILESTONE_MAP` | `listing_spokes_08.py` | Which document type completes which transaction milestone |
| `_DEFAULT_TRANSACTION_MILESTONES` | `listing_spokes_07.py` | Agent 07's milestones; the same content as `config/transaction_milestones.json` (section above) |
| `confidence_threshold = 0.45` | `decision_adapter.py` | The default of `decision_engine.confidence_floor` (Parameters of the wired modules) |
| Policy quarantine at 0.5 | `hermes_seam.py` `HermesLearningLoop` | A broker correction scoring 0.5 or more on the phrase screen is quarantined, not learned |
| Brokerage directives: 5 | `hermes_seam.py` `format_curriculum_prompt` | How many of your brokerage directives go into the model's prompt |
| `DEFAULT_HERMES_SYSTEM_PROMPT` | `hermes_seam.py` | The system prompt of every model draft |
| `GOLDEN_BROKER_EXAM`: 4 questions | `model_checkpoint_manager.py` | Fair housing, wire defense, pricing boundary, NAR settlement; a checkpoint must pass all four |
| Local model hosts `localhost`, `127.0.0.1`, `::1` | `model_drafting.py` | Any other host is refused without `--allow-remote-model` |
| Pager `api_base` default `https://api.twilio.com`; numbers 8 to 16 characters with a leading `+` | `pager.py` | Where pages go; the number format check |
| Desk addresses `127.0.0.1`, `localhost`, `[::1]` | `tools/desk.py` `LOCAL_NAMES` | The only addresses the desk on this computer answers (2026-10-14) |
| Desk display limits: 30 items per tally, 25 activity lines, 160 characters per shortened value | `tools/desk.py` | What the page shows; the record keeps everything |
| `log_root = "logs"` | `readable_logger.py` | Where `restore_point.py` and `show_logs.py` write and read their readable log |
| `max_workers = 8` | `concurrent_dispatcher.py` | A module no part of the product calls; only its own tests use it |
| Demo ruleset | `tools/run_demo.py` | The six-act demo's fair-housing rule; demo only |

### Found 2026-10-14 (synthetic sample run and integration snapshot)

Fixed the same day (`tests_listing/test_tuple_gaps_2026_10_14.py`):
- **Agent shopping.** Agent 01 now forwards `is_agent_shopping` (only a real
  `true`) to Agent 02, so the agent-to-agent tuple fires on intake.
- **Country code.** A phone is keyed by its digits, with a leading 1 on an
  11-digit number dropped, so `+12165550101` and `(216) 555-0101` are one
  person for the duplicate check.
- **Do-not-contact list.** It is compared in the same normalized form, on
  the phone and the email both.

Not fixed:

| What | Where | Effect |
|---|---|---|
| Agent 02's "lead demands a human" tuple is not reached from intake | Agent 01 escalates a demand for a person itself (legal line) and does not forward it | No agent sets `demands_human` on a message to Agent 02, so its tuple "(lead demands a human, hot path regardless of score)" cannot fire. Forwarding it would page you twice for one request (legal line from 01, hot lead from 02); the owner decides |
| A second inquiry after capture starts from nothing | Agent 01 merges fields only while a capture is pending | A later inquiry that repeats no budget or timeline scores UNKNOWN |
| The MCP server takes a host's signature and never uses it | `dispatcher/identity_mcp.py` `identity.authority` (integration snapshot 2026-10-14) | `signature_hex` is compared only with the demo string; the hub trusts only a key the server makes at each start. Without `--demo-signing` the MCP server can describe the trade and show the record, nothing else |

### Tuple runs (2026-10-14)

Every tuple in agents 00 to 20 (`DECISIONS.md`) and in `SWARM.md`, 272 in
all, has a spec in `synth/tuples/specs/` and was run through the console
the way a broker drives it: inquiries, client replies, vendor events,
platform metrics, mentions, discovery feeds, signed settings and
authorizations, releases and the daily clock. Run them with
`python synth/tuples/run_tuples.py` (it writes `synth/tuples/REPORT.md`);
`--show 01-02` prints one tuple's session file to run by hand with
`python tools/console.py session <file>`. The results: 224 PASS,
2 VARIANCE, 22 NOT REACHABLE, 20 NOT BUILT, 4 RETIRED. CI checks that every
tuple has its spec and reruns the 32 specs whose code changed
(`tests_listing/test_tuple_runs_2026_10_14.py`).

Fixed during the runs:
- Agent 03: a re-score after an engagement spike carries the lead's stored
  answers (timeline counted down by the days elapsed); an undated re-score
  that keeps the tier WARM no longer restarts the sequence at day 0.
  Agent 12's spike signal carries the date.
- Agent 05: an approved asset that disagrees with the MLS record gets one
  correction and never goes live; a second disagreement goes to you.
  Agent 04 drafts the corrected square footage from the MLS record, which
  ended a 04/05 correction loop.
- Agent 06 asks for showing feedback after the showing date, not on the day
  it is booked. Agent 11 sends a client's request for access (a lockbox
  code, "just let them in") to the legal line.
- Agent 07: an overdue earnest-money milestone goes to the legal line.
- Agent 09: when the only roster vendors of a kind have lapsed credentials,
  that goes to the legal line naming them (it was reported as "no approved
  vendor").
- Agent 10 counts the comps it leaves out as stale (`dropped_stale`).
- Agent 12 logs `campaign_publish_held` when the hub holds a campaign for
  your release (it logged "published").
- Agent 14 flags conflicting facts only within one kind of event (every
  log entry was flagged against the one before it), and a write refused on
  a frozen record is traced as not appended.
- Agent 15: a forecast request with no horizon gets a clarification (it
  raised an error); an unsigned projection keeps its computed label.
- Agent 17 records a review waiting for a ruleset, so the SLA alert can
  fire (it never could).
- Agent 19 compares owner contacts with its do-not-contact list in
  normalized form.

Plumbing pass the same day:
- 07-03 is wired: a document's own date for its milestone
  (`stated_deadline`) travels from Agent 11 through 08 to 07, which compares
  it with the timeline. A disagreement leaves the milestone unsatisfied and
  sends you both dates.
- 18-06 is wired: Agent 18 tracks deadlines by source (Agent 07's timeline,
  or the date a document states), so the two dates are both kept, both get
  a protected block, and the conflict is alerted. It was keyed by milestone
  only, so the briefing listed every timeline whose milestones fell on
  different days as a conflict, and an amended date read as two sources.
- Agent 11 confirms a channel change to the client only when Agent 14 now
  records consent on that channel. A client who opted out keeps the "no"
  (tuple 14) and you are told; the client was told the change was made.

Your decisions the same day (see "Ratified 2026-10-14" below for the
settings and lists):
- A phrase tagger reads client words at intake. Any adverse message (angry
  or negative) goes to you as a complaint at once and holds every outbound
  touch for that client, whatever else it asks: an angry message with a
  pricing question also goes to the legal line, and the automatic hand-off
  note is not sent. Agent 11 passes the criteria-change and referral-reward
  labels to the owning agent. Wired: 13-01, 16-08, 16-10; 11-10 and 11-14
  now fire on the words alone. A social mention with no sentiment label is
  read the same way.
- Compliance is told the content type and state, checks every ad for your
  brokerage identification, flags content types the ruleset does not cover
  and states counsel has not reviewed, and refuses template-class
  pre-approval. Agent 12 adds your brokerage identification to every ad and
  holds an approved ad until one is set. Wired: 17-01, 17-04, 17-05, 17-07,
  17-09.
- Showings read occupancy, status and state from the signed listing record
  for your own listings; a listing whose occupancy is not on record is
  treated as occupied. Notice is measured from when the client wrote
  (`sent_at`). Agent 05 now answers a status check by the listing, not by
  the buyer's context (it answered "unknown" for every showing). Wired:
  06-05, 06-07, 06-11.
- Agent 05 applies a signed change to beds, baths, square feet, remarks,
  address or photos, logs the prior value, and sends Agent 04 the updated
  listing when the description is drafted from that field.

For the owner:

| Tuple(s) | What the run showed | Decision needed |
|---|---|---|
| 01-01 (VARIANCE) | Two inquiries for one context are captured and scored separately | Merge a later inquiry into the first by channel rank (Agent 14 returns the prior capture), or keep them apart |
| 04-03 (VARIANCE) | Copy you supply is escalated but never sent to compliance or used in the draft | How your own copy enters a listing description |
| 02-03 | Forwarding a demand for a person from 01 to 02 would page you twice | One page or two |
| 06-08, 10-05, 12-06 | The agent reads a field no sender sets (showing agent, license scope, unconfirmed data) | Which upstream agent or setting supplies each; 10-05 and 12-06 are closed upstream and could be retired |
| 09-05 | Vendor slot contention needs a slot: a vendor and an appointment time. No appointment date reaches Agent 09 (see the Agent 09 row), and each roster vendor serves one kind, so two agents never ask for the same vendor | Appointment dates for vendors, and how many jobs a vendor takes in one slot |
| 11-03 | No two agents report a status on the same thing to Agent 11: 05 reports listing status, 07 deadlines, 08 documents | Which reports can conflict, or retire the tuple |
| 11-04 | Quiet hours apply only to client replies that carry an hour; deadline alerts and clock-driven sends are treated as noon | Stamp the hour on agent sends |
| 18-09 | Agents 06 and 09 mark every calendar event's timezone as confirmed | Whether a local time counts as confirmed |
| 12-03 | Engagement is keyed by platform: two platforms always "conflict", and the same platform reported twice keeps only the last figure | What counts as a conflict |
| 16-03 | A past client's new business goes straight to Agent 02, skipping Agent 01's consent and duplicate checks | Route it through 01 |
| Agent 09 | A vendor's calendar event is dated the day of the request; no appointment date reaches 09 | Where the appointment date comes from |
| Agent 03 | A sequence paused by a spike stays paused when the re-score keeps WARM | Resume or stay paused |
| Agent 14 | A frozen record still takes consent changes (the end-of-day report names it as a logging gap) | Whether a freeze also holds consent |
| Agent 17 | A review that waited for a ruleset is not rerun when one arrives; the SLA alert repeats daily | Rerun, or leave to you |
| SW-01 to SW-04, SW-12, SW-14 | Priority classes, siding, the after-action report and playbook matching exist in the core but this product's runtime does not call them | Wiring per part |

---

## Ratified (owner-approved 2026-07-16)

| Agent | Parameter | Value | Controls |
|---|---|---|---|
| 01 (Lead Capture) | `record_response_timeout_days` | `1` | Days a dedupe check (record.request to 14) can go unanswered before retrying once, then holding with handoff.failed |
| 02 (Lead Qualification) | `hot_lead_sla_seconds` | `300` (5 min) | Response-time SLA for a HOT-tier lead before an alert fires |
| 03 (Lead Nurture) | `frequency_cap_per_week` | `3` | Max nurture-sequence touches per client per calendar week |
| 03 (Lead Nurture) | `legal_contact_hours` | `(8, 21)` | Allowed daily window (24h clock) for sending a scheduled nurture touch - outside it, or on a flagged legal holiday, the touch holds rather than sending |
| 03 (Lead Nurture) | nurture sequences (signed `config.update` `nurture_sequences`, not a constructor arg) | none | Each sequence's touches (`day`, `text`). No definition = nothing sent. The daily clock sends each due touch once. |
| 04 (Listing Description) | `mls_char_limit` | `800` | Character budget before length-cut logic engages (adjectives cut before facts, attributions never cut) |
| 06 (Showing Scheduler) | `feedback_ask_cap` | `2` | Max times a showing-feedback request is sent before giving up |
| 06 (Showing Scheduler) | `no_show_pattern_threshold` | `2` | No-shows from the same showing agent before flagging a pattern |
| 07 (Transaction Coordinator) | `vendor_holdup_days` | `7` | Days a vendor-scheduling wait can sit unconfirmed before escalating |
| 08 (Document Collection) | `document_chase_cap` | `3` | Chase attempts on a missing document before escalating as genuinely missing |
| 10 (Market Data) | `comp_minimum` | `5` | Comps required before a set is *not* flagged "thin" |
| 10 (Market Data) | `staleness_days` | `30` | Age at which a comp is dropped as stale rather than shipped |
| 10 (Market Data) | `retention_days` | `730` (2 yrs) | Historic-data window beyond which "absent" is the answer, never reconstructed |
| 10 (Market Data) | `opinion_press_threshold` | `2` | Repeated pricing-opinion asks before escalating (1st ask = refuse only) |
| 11 (Client Communication) | `quiet_hours` | `(21, 8)` | Window (24h clock) during which non-exempt sends queue instead of going out |
| 17 (Compliance) | `sla_days` | `1` | Turnaround SLA for a compliance verdict before an SLA-breach alert fires |
| 17 (Compliance) | `near_miss_pattern_threshold` | `3` | Flagged verdicts from the same submitting agent before a pattern report goes to the owner |
| 18 (Calendar & Task) | `max_events_per_day` | `8` | Calendar capacity before a day is treated as overloaded |
| 18 (Calendar & Task) | `no_show_grace_minutes` | `60` | Minutes past a showing slot with no post-showing signal from 06 before 18 reports a calendar-detected `showing.no_show` (invoked by the daily `clock.tick` that `dispatcher/sweep_runner.py` `run_daily_sweeps` sends through the hub; checks listed in `dispatcher/clock.py`). PROVISIONAL - no empirical basis, revisit with after-action data |

## Found 2026-07-17, not yet reviewed by owner (dict/set-shaped, missed in the first sweep)

These are real constructor parameters, already live with working defaults
- but unlike the table above, they were never individually walked through
with you on 2026-07-16. Flagging them as such rather than silently
folding them into "Ratified," since a dict-shaped default is a business
rule, not just a number, and deserves its own look.

| Agent | Parameter | Current default | Controls |
|---|---|---|---|
| 03 (Lead Nurture) | `spike_threshold` (in `behavioral.signal` payload, not a constructor arg - see "Per-message defaults" below) | `50` | Engagement-score threshold that pauses a nurture sequence and triggers a rescore (tuples 5/8) - a **separate** value from Agent 12's own `spike_threshold` below, despite the identical name and default |
| 05 (MLS & Listing Mgmt) | `required_artifacts` | `{"sold": "closing_artifact", "pending": "signed_contract_artifact"}` | Which artifact must be on file before a status change to that value is allowed |
| 06 (Showing Scheduler) | `min_notice_hours` | `{"default": 24}` | Minimum notice required for a showing on an occupied property; per-state overrides go in this dict (e.g. `{"CA": 48, "default": 24}`) |
| 08 (Document Collection) | `expected_senders` | `{}` (empty) | Per-context allowlist of who may submit a sensitive document type (preapproval letter, proof of funds, closing statement). **Empty by default means every sensitive document is quarantined until a context has an explicit allowlist entry** - correct, fail-closed behavior, but means this agent quarantines everything sensitive out of the box until populated. |
| 09 (Vendor Coordination) | `roster` | `{}` (empty) | Approved-vendor list (id -> kind/license/insurance/regulated). **Empty by default means every single vendor request is refused** (tuple 6: not on approved list) until this is populated - this agent does nothing useful out of the box. |
| 11 (Client Communication) | `exempt_alert_classes` | `set()` (empty) | Alert classes exempt from the quiet-hours gate (e.g. a genuinely time-critical alert type that should wake the human instead of queuing) - none configured means nothing is exempt, everything queues during quiet hours |

## Per-message defaults (not agent-level config - legitimately vary by caller/platform)

These aren't retuned at agent construction time; each caller can override
them per envelope. The values below are just the fallback when a caller
doesn't specify one.

| Agent | Field | Default | Where it's set | Controls |
|---|---|---|---|---|
| 03 (Lead Nurture) | `spike_threshold` (in `behavioral.signal` payload) | `50` | `listing_spokes_03.py` `behavioral.signal` branch | See note in the table above - distinct from Agent 12's, same name and default by coincidence, not shared code |
| 06 (Showing Scheduler) | `buffer_minutes` (in `showing.request` payload) | `30` | `listing_spokes_06.py` `_schedule()` | Minimum spacing enforced between two showings on the same context before they're treated as conflicting. Missed in the original sweep - became load-bearing only once the buffer-enforcement fix landed (2026-07-16); before that it was captured but never compared against anything, so its default value had no functional effect. |
| 12 (Marketing Campaign) | `spike_threshold` (in `platform.metrics` payload) | `50` | `listing_spokes_12.py` `platform.metrics` branch | Engagement value above which a spike feeds back into nurture (Agent 03) |
| 19 (Prospecting) | `rank_threshold` (in `discovery.feed` payload) | `0.5` | `listing_spokes_19.py` `discovery.feed` branch | Minimum rank-basis-strength before a rank is included rather than presented unranked |

To change the *fallback* value for any of these (not a one-off
override), edit the source line directly - there's no single agent-level
constructor knob for these, by design, since different platforms may
legitimately warrant different defaults.

## Ratified as deliberate placeholders (owner, 2026-07-17) - core, not this repo

These two live in **dispatcher-agents** (the shared core, not this repo),
which is why they weren't caught in a sweep of this repository alone before.
Both were previously self-flagged in their own code/doc comments as never
having been truly decided - "PROVISIONAL AND ARBITRARY, no empirical
basis" was the literal language at the source. **Discussed directly with
the owner 2026-07-17: both ratified as deliberate placeholders, not left
open.** Neither number has empirical backing - that was true before
ratification and remains true now - but "nobody has decided" and "we've
decided to accept this placeholder" are different states, and these are
now the second one. Revisit when real after-action/fade-rate data exists.

| Location | Parameter | Value | Controls |
|---|---|---|---|
| `dispatcher-agents/dispatcher/hub.py` `Hub.__init__` | `loop_threshold` | `20` | Max envelopes per `(client_context_id, intent)` pair before the hub suspends the loop into `clarification.request`, treating it as a possible runaway |
| `MANNERS.md` (this repo) §Re-injection | backstop `N` | `10` | Agent turns (envelopes handled) allowed with no other re-injection before the turn backstop fires. Wired 2026-10-14 in `dispatcher/manners_reinjection.py` |

## Ratified 2026-07-17 (owner decisions #1, #3, #4, #6 - this session)

| Agent | Parameter | Value | Controls |
|---|---|---|---|
| 15 (Financial Tracking) | `commission_rate` | `0.08` | DEFAULT rate used ONLY when a close carries `sale_price` but no explicit `commission_amount`. Explicit amount always wins; computed amounts are labeled `computed_at_default_rate_*`, never presented as recorded figures. Owner-ratified starting point (decision #1); revisit against real closings |
| 04 (Listing Description) | `config/description_cut_priority.json` | `["adjectives", "unattributed_facts"]` | Cut order when remarks exceed `mls_char_limit` (first entry cut first). Attributions never cut - structurally absent from the cut classes (decision #3). File finally exists; tuple 11 always named it |
| 04 (Listing Description) | photo/data contradiction detection | symmetric set difference | When `photo_detected_features` is present, ANY feature in the data sheet not in the photos, or in the photos not in the data sheet, halts the asset into clarification (decision #4, delegated). A caller-supplied `photo_data_contradictions` flag also halts; neither path suppresses the other. Not a numeric knob - documented here so its behavior is known outside the source |
| dispatcher-agents `SignerRegistry.check` | `effective` date enforcement | temporal, fail-closed | A signer entry with no effective date, an unparseable one, or a future-dated one DENIES (decision #8 answer: the field was schema-present, enforcement-absent - `check()` never read it). `today` defaults to the real system date; tests pass it explicitly |

### Added 2026-07-18 (owner decisions #2 refinement, #7)

| Agent | Parameter | Value | Controls |
|---|---|---|---|
| 13 (Buyer Search & Match) | `max_matches_per_buyer_per_day` | `5` | Individual match pings per buyer per day. Beyond it, matches join a ranked end-of-day digest (`flush_match_digest`, sweep-called): ranked by stated-criteria-met desc, ties newest-first. Nothing silently dropped - every match logs to 14 individually (decision #7) |
| 06 (Showing Scheduler) | protected-deadline bump tier gate | `HOT` only | A protected-deadline claim only earns a HITL bump OFFER when `lead_tier` (relayed by 13 from 14's CRM records, where 02 logged it - never client-writable) is HOT. Not hot or unknown: plain conflict sequencing, no offer (decision #2). The bump itself still executes only on the human's signed `confirm_protected_bump` |

## Ratified 2026-10-14 (owner decisions: tags, compliance inputs, showing facts, MLS fields)

| Where | Setting | Default | What it does |
|---|---|---|---|
| `dispatcher/message_tags.py` | the four phrase lists above | as listed | Tags client words at intake (Agent 11) and unlabeled social mentions (Agent 20). An explicit label from an upstream classifier is honored too. Phrases common in neutral messages ("worst case", "still waiting") are left off: an adverse tag holds every outbound touch for that client until you release it (`resolve_complaint_hold`) |
| Agents 12 and 17 | `brokerage_identification` (signed setting, or constructor argument) | none | The text every ad carries. Agent 12 adds it to every ad and holds an approved ad until it is set; Agent 17 flags an ad that lacks it, or any ad when it has none on file |
| Agent 17 ruleset | `covers` (optional list) | absent: every type covered | Content types the ruleset addresses: `listing_description`, `advertising`, `nurture_sequence`, `buyer_criteria`, `client_message`, `social_reply`. A type not listed is flagged as uncovered |
| Agent 17 ruleset | `states_reviewed` (optional list) | absent: no state check | States counsel has reviewed; content for any other state, or with no state, is blocked and goes to the legal line |
| Agent 17 | `preapprove_template_class` (signed request) | - | Always refused with a clarification; verdicts are per item |
| Agent 06 | `showing_facts_source` (signed setting) | `listing_record` | Where a showing's occupancy, status and state come from: your listing record for your own listings, or `requester` (the request's own fields). An onboarding choice; you may change it |
| Agent 06 | unknown occupancy on your own listing | treated as occupied | The minimum-notice rule applies |
| Agent 05 | `REDRAFT_FIELDS` | beds, baths, sqft, address | A signed change to one of these sends Agent 04 the updated listing to redraft the description |

---

## Ratified 2026-10-15 (owner decisions: escalation re-alert, clock skew, queue cap, run tracker)

| Where | Setting | Default | What it does |
|---|---|---|---|
| `dispatcher/escalation_watch.py` | `REALERT_MINUTES` | 30 | An escalation nobody has marked done is re-alerted once, on the same queue (`escalation.realerted`) |
| `dispatcher/escalation_watch.py` | `OWNER_PAGE_MINUTES` | 60 | Then the owner channel is paged once (`escalation.owner_page`, `escalation.owner_paged`). Nothing expires an escalation by time |
| `dispatcher/escalation_watch.py` | `SKEW_TOLERANCE_SECONDS` | 60 | A live-clock sweep whose clock is more than this behind the newest audit entry holds every time-triggered check (`clock.skew_hold`) and asks you |
| scheduler | `python tools/run_sweeps.py --watch` every 5 minutes | not installed | The re-alert needs a check more often than the daily sweep; the console's `{"do": "watch"}` runs the same check |
| `dispatcher/run_tracker.py` | `CAP_OPEN_QUESTIONS` | 25 | With this many questions waiting (paused threads plus clarification requests not marked done), a message from outside the agents that would start a new playbook run waits; you are told once (`escalation.queue_full`). Released by priority class when the count drops |
| `identity/playbooks.json` | the playbook table | **PROPOSED 2026-10-20**, not ratified | Starts, ends, agents, hand-offs (`supersedes`) and conflicts for P01-P24, written from docs/PLAYBOOKS.md. Runs record `table: PROPOSED` and so does every after-action report until you ratify the file's `_status` line |
| `identity/playbooks.json` | a comparables request (`data.request`, mode comp, from you to Agent 10) | P23 on a live listing of ours, P15 otherwise | Owner decision 3 (2026-10-21). "Live" = the client is one of our listings and Agent 05's MLS record says active. P02 starts only from your signed price change. A request that names its playbook (`payload.playbook`) still decides it |
| `identity/playbooks.json` | conflicts | P05 with P01, P02, P04, P12, P18; P14 with P13, P18, P21, P22, P24 | A new run of one while the other is open on the same client holds both until you sequence them |
| Agent 12 | farm campaign (a `new_campaign` with `audience.geography` and no `listing_id`) | Clear Cooperation gate does not apply | Confirmed by the owner 2026-10-21 (playbook walkthrough, decision 2). Until 2026-10-20 a farm campaign waited forever for an MLS confirmation no farm gets. It now publishes after compliance review and your release; targeting other than `general` goes to the legal line |
| Agent 12 | a listing change that is not a status (`status.update` carrying `price`) | marketing kept running | Was: read as "not active" and every live ad was halted. Now logged, and with live ads you are asked to check them for the old value |
| Agent 06 | `open_house` / `open_house_result` (signed settings) | - | P04's entry and close: schedules the open house on an active listing (calendar, signage through the roster, log) and records the result |
| Agent 13 | a new match for a buyer with no signed buyer agreement on file with 14 | held | Owner decision 4 (2026-10-21). The match waits; you are told once per buyer (clarification and 18's waiting list); each held match is logged to 14. The daily clock asks 14 again and the held matches go out once the agreement is recorded (signed `buyer_agreement_on_file` to 14) |
| Agent 13 | stated criteria | exclude | Owner decision 5 (2026-10-21). A criterion the listing carries but does not meet makes it no match. A number is a minimum (beds 3 = at least 3); true/false and text must be equal (exact text, "North" is not "north"). Budget is the maximum. A field the listing does not carry is unknown, never a pass or a fail (a hard criterion still holds it to ask) |
| Agent 07 | the settlement statement arrives with milestones still open | held, naming them | Owner decision 6 (2026-10-21). Continue closes the deal and records the open milestones as waived by you; cancel leaves the transaction open |
| Agent 03 | the day-0 nurture touch | at once, inside contact hours | Owner decision 7 (2026-10-21). Sent when Compliance clears the sequence, inside `legal_contact_hours` (8 to 21). The time used is the start message's `now_iso`; without one, this computer's local clock. Outside the hours it waits for the next clock check. Later touches stay on the clock |
| Agent 18 | the morning briefing | four sections | Owner decision 8 (2026-10-21): overnight leads (14, every lead captured since the last briefing, once), yesterday's books (15), prospects waiting (19, until you mark them handled with a signed `prospects_handled`), market changes (10, listing data received since the last briefing, once). A section with no answer is named under `sections_missing` |
| `tools/run_sweeps.py --evening` | the evening clock | not installed | Owner decision 9 (2026-10-21): Agent 14's end-of-day books go to Agent 15, which adds the day's figures (commissions and expenses recorded that day) and sends you one report. Schedule it, for example `0 18 * * *`; the console's `{"do": "sweep", "today": "...", "evening": true}` runs the same |
| Agent 19 | the opportunity and its comparables | one message | Owner decision 10 (2026-10-21, P24): the comps are asked before the prospect reaches you, so each prospect comes once, with its comps on it; a package that arrives later still comes as an update |

## External adapters - NOT YET WIRED (owner decision #6: tracked here until clean)

Three intents route to the virtual destination `external`. The swarm
(`dispatcher/swarm.py`) registers a stand-in handler that keeps each
delivered envelope in a list in the running process; `python tools/console.py`
`{"do": "show", "what": "external"}` shows it. Nothing leaves the machine,
the list is not saved across restarts, and each delivery is on the audit
log. A real adapter replaces the stand-in by registering its own handler
for `"external"`:

| Intent | Sender | What's dark until an adapter exists |
|---|---|---|
| `vendor.schedule` | 09 | Every vendor booking (photography, inspector, appraiser…) |
| `client.message.send` | 11 | Every client-facing message the swarm composes |
| `campaign.publish` | 12 | Every campaign publish AND retract action |

Update this table (and delete rows) as each adapter lands. A deployment
with these dark is a swarm that talks to itself.

## Also worth knowing about (not tuning-manual material, but adjacent)

- **`dispatcher/notifier.py`** (vendored core): `TWILIO_ACCOUNT_SID` /
  `TWILIO_AUTH_TOKEN` default to placeholder strings and the numbers to
  the fictional `+1-555-555-0100` block. While a credential is empty or a
  placeholder (`PLACEHOLDER...`, `YOUR_...`), or the destination is in the
  555-0100..0199 block, the core notifier sends nothing and says why
  (2026-10-14).
  The console does not use it: its pages go through `dispatcher/pager.py`
  with the details you give `python tools/console.py pager`.

## Config files (separate from code - business content, not tuning knobs)

<!-- diagram:config-tunman - drawn in tools/doc_diagrams.py; edit it there, not here -->
```mermaid
flowchart LR
    T["config file ships<br/>as a draft"] --> E["you edit it to<br/>your business"]
    E --> RAT["_status: RATIFIED<br/>with a date and your name"]
    RAT --> LD["loaded - config.load<br/>on the audit log"]
    T -. "still a draft" .-> SK["skipped and named<br/>on the audit log"]
    SET["a signed setting<br/>(console config)"] --> AG{"key the agent<br/>knows?"}
    AG -- yes --> AP["applied"]
    AG -- no --> HO["held for you,<br/>nothing changes"]
    classDef ok fill:#dafbe1,stroke:#1a7f37,color:#1f2328
    classDef you fill:#f2cc60,stroke:#9a6700,color:#1f2328
    class LD,AP ok
    class SK,HO you
```
<!-- /diagram:config-tunman -->

Six JSON files under `config/` hold business content that genuinely
can't be guessed by code: `vendor_panel.json`, `authority_signers.json`,
`cadence_settings.json`, `message_templates.json`, `milestone_map.json`,
`transaction_milestones.json`. Five of the six now have proposed draft
content grounded in what the code actually implements or the playbooks
already ratified - review, edit, and change `_status` to `RATIFIED` when
approved. `vendor_panel.json` and `authority_signers.json` remain
genuinely empty - they need your actual vendor relationships and IdP
logins, which no amount of drafting on my end can substitute for.

`cadence_settings.json` (2026-07-17): now covers all 15 tunables in the
Ratified table above, not 9 - added `no_show_pattern`, `pricing_opinion_
press`, and `near_miss_pattern`, the three "N occurrences before X"
thresholds missed in the first draft.

`transaction_milestones.json` (new, 2026-07-17): covers Agent 07's
post-contract transaction milestones (inspection, appraisal, title,
etc.) - deliberately split from `milestone_map.json`, which only ever
covered the pre-contract *listing* lifecycle (intake through
showing_active). These aren't overlapping duplicates of the same thing;
they're genuinely two different milestone concepts, now each with their
own real config. Unlike the other five, this one **actually wires into
running code** - `Spoke07TransactionCoordinator` now accepts
`transaction_milestone_config` as a real constructor parameter (default
reproduces the exact prior hardcoded values), and this file's `entries`
are exactly that default's content in ratifiable JSON form. Editing the
JSON alone doesn't change agent behavior yet - whoever wires the swarm
still needs to load this file and pass its content into the constructor,
same as every other config file in this list - but there's now a real
parameter to receive it, not just documentation describing what's
hardcoded. Not covered: the per-milestone business logic in Agent 07's
doc.status handling and the financing_contingency deadline case - see
the file's own `_not_covered_here` field and the class docstring for why.

## Maintenance note

Since 2026-10-11 this repository is the single source for the config files
(the listing-agents-blueprint copies are no longer maintained). Edit them
here only.

If you add a new agent or a new threshold, add it to this table in the
same commit - that's the whole point of keeping this centralized instead
of scattered across code comments. A parameter not in this table is a
parameter nobody outside the source code knows exists.

---

## ABSOLUTE SIGNAL - disclosure gate (added 2026-08-01)

<!-- diagram:audience-tunman - drawn in tools/doc_diagrams.py; edit it there, not here -->
```mermaid
flowchart LR
    M["An outbound message"] --> W{"Who is on<br/>the far end?"}
    W -- "your client (principal)" --> S["Sent"]
    W -- "the other side (counterparty):<br/>a vendor, a buyer's agent" --> H1["Held for your<br/>signed release"]
    W -- "the public:<br/>an ad, a feed" --> H2["Held for your<br/>signed release"]
    W -- "not labelled" --> H3["Held - the default<br/>is the guarded one"]
    classDef you fill:#f2cc60,stroke:#9a6700,color:#1f2328
    classDef ok fill:#dafbe1,stroke:#1a7f37,color:#1f2328
    class H1,H2,H3 you
    class S ok
```

*In this repository: `client.message.send` is principal, `vendor.schedule` counterparty, `campaign.publish` public (`identity/routes.json`). The gate reads the label, not the words.*
<!-- /diagram:audience-tunman -->

| Item | Where | Status | Notes |
|---|---|---|---|
| Route `audience` field | `identity/routes.json` (external routes) | **RATIFIED** | `principal` passes the gate; `counterparty`/`public` HOLD for human release. Missing/unknown → fail-closed to `counterparty`. |
| `audience_verified` flag | `identity/routes.json` | **PER-ROUTE** | `false` = provisional classification, surfaced on the hold. All 3 listing external routes are verified `true`. |
| Disclosure release intent | `disclosure.authority` | **CONSTANT** | Signed authority intent that clears exactly one held message. Reuses the execution-authority stack (Ed25519 sig + signer registry + MFA). No route entry needed (verified directly, re-sends the original). |
| Canonical signal text | `dispatcher/absolute_signal.py` `SIGNAL_TEXT` | **SINGLE SOURCE** | MANNERS.md Manner 15 and docs/FINANCIAL_CAPABILITY.md defer to this. sha256-checked by tests here. Never hand-edit downstream copies. |

---

## Parameters of the wired modules (revised 2026-10-12)

Since 2026-10-12 the swarm builder wires these modules: Agent 02 scores
through the JEV adapter, six agents file into client drawers, Agent 04 can
draft with an examined model, and every audit entry is also written to the
plain-language log. Runtime settings arrive as signed `config.update`
messages; the rest are process options.

### Lead rubric (`dispatcher/lead_rubric.py`, used by Agent 02 and the JEV fallback)

The rubric arrives as a signed `config.update` to Agent 02. All seven keys
are required; a rubric missing any of them is rejected by Agent 02 and held
by the JEV fallback. There are no built-in defaults.

| Key | Meaning |
|---|---|
| `budget_threshold` | budget at or above this earns `budget_weight` |
| `budget_weight` | points for budget |
| `timeline_days_threshold` | timeline at or below this many days earns `timeline_weight` |
| `timeline_weight` | points for timeline |
| `financing_weight` | points when financing progress is `preapproved` |
| `hot_threshold` | score above this is HOT; exactly equal drops to WARM and is flagged for a human |
| `warm_threshold` | score above this is WARM; exactly equal drops to COLD and is flagged |

### JEV adapter (`dispatcher/decision_adapter.py`)

| Parameter | Default | Effect |
|---|---|---|
| `decision_engine.confidence_floor` (signed, to 02) | `0.45` | results below it (or with no readable confidence) hold the lead for your continue/cancel |
| `decision_engine.allow_external` (signed, to 02) | `false` | live HTTPS calls happen only when this is `true` and a key is set |
| `JEV_API_KEY` | unset | key for the live service |
| `JEV_ENDPOINT_URL` | `https://api.typesafe.ai/v1/decisions` | must be `https://` |
| `JEV_FORCE_PYTHON` | `0` | `1` forces the local engine |
| `timeout` | `3.0` s | live call timeout; a failure falls back to the local engine |

### Client drawers (`dispatcher/client_drawer.py`)

| Parameter | Default | Effect |
|---|---|---|
| `drawers_root` (swarm builder) | `drawers` next to the audit log (`console-state/drawers`) | directory holding one subdirectory per client |

Client ids and file names must be single safe path segments; categories are
a fixed set. A cross-client filing raises `ComminglingBreachError`. Files are
stored unencrypted; `verify_hashes()` checks stored SHA-256 values on demand.

### Model drafting (`dispatcher/model_drafting.py`, Agent 04)

| Parameter | Default | Effect |
|---|---|---|
| `drafting.mode` (signed, to 04) | `rules` | `model` turns on model-written remarks when a model is configured and the active checkpoint passed the exam on it |
| `--model-url`, `--model-name` (console) | unset | the locally served model; other hosts refused without `--allow-remote-model` |
| `checkpoints_dir` (swarm builder) | `checkpoints` next to the audit log | the manifest Agent 04's gate reads |
| `mls_char_limit` (Agent 04) | `800` | model remarks longer than this are not used |

### Readable log (`dispatcher/readable_audit.py`)

| Parameter | Default | Effect |
|---|---|---|
| `readable_dir` (swarm builder) | `readable` next to the audit log | where `stream.log` and `daily/eod_ledger_<date>.md` are written |

### HITL protocol (`dispatcher/hitl_protocol.py`)

No timing parameters. A wait stays PENDING until a signed
`hitl.decision.authority` envelope resolves it; Agent 18's morning briefing
lists unresolved waits whenever a briefing is generated.

### Checkpoint manifest and SQLite store

`dispatcher/model_checkpoint_manager.py` and `dispatcher/persistence_sqlite.py`
have no tuning parameters beyond their file locations (`checkpoints_dir`,
`db_path`). Keep `db_path` on a local disk. Rolling the checkpoint pointer
back to the baseline turns model drafting off, because the baseline was
never examined.
