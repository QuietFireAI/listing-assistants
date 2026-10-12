# Push Log

Every commit pushed to the four in-scope repos, in chronological order.
Created 2026-07-17 per direct instruction, after a legitimate question
about whether pushes were actually landing when claimed. Existing history
below was reconstructed retroactively from each repo's real `git log`
output (timestamps and hashes are actual commit metadata, not
reconstructed from memory). Going forward, a new row is added to this
file in the SAME commit that makes the change it describes - not
after the fact, not in a separate pass.

**Repos in scope:** `listing-agents`, `listing-agents-blueprint`,
`dispatcher-agents`, `dispatcher-agents-blueprint`. No other repos
(freight-agents, freight-agents-blueprint, the six pillar packages)
are tracked here - those are explicitly out of scope per direct
instruction.

**How to verify any row yourself:** `git clone` the repo, `git log
--format="%H %ai %s"`, and confirm the hash/timestamp/message match.
Don't take this file's word for it - that's the whole point of it
existing.

| Timestamp (UTC) | Repo | Commit | What |
|---|---|---|---|
| 2026-07-16 01:52:58 UTC | listing-agents | `af97abb0c2` | Working listing-agents build: agents 01, 14, 02-09 - built and tested against full spec |
| 2026-07-16 01:58:13 UTC | listing-agents | `b969d9d4ff` | Add Agent 10 (Market Data): comp/neighborhood packages, provenance-gated, no-opinion-field structural design |
| 2026-07-16 02:06:00 UTC | listing-agents | `147dd8e2f5` | Fix systemic fail-open defaults across agents 08, 09, 10 |
| 2026-07-16 02:13:13 UTC | listing-agents-blueprint | `707e46fc1e` | Fix 8 real gaps in ratified routes.json, found during build-out |
| 2026-07-16 02:16:58 UTC | listing-agents | `b24272c03b` | Add Agent 11 (Client Communication) - single voice for routine client updates, implements reply-routing-by-content for real |
| 2026-07-16 02:35:49 UTC | listing-agents | `5e8c5dba0f` | Re-review fix: route client-requested showings through 13, not directly to 06 |
| 2026-07-16 02:39:42 UTC | listing-agents | `dc8311a2df` | Fix showing.request properly instead of routing around it |
| 2026-07-16 02:51:30 UTC | listing-agents | `f2387eb028` | Add Agent 18 (Calendar & Task) + real HITL wait-status visibility |
| 2026-07-16 03:01:22 UTC | listing-agents | `990b0c4571` | Complete agent.status retrofit across all remaining agents (02, 03, 06, 09, 11) |
| 2026-07-16 14:00:29 UTC | dispatcher-agents | `e1cdaf0c91` | Fix two real hub-core bugs: clarification.request silently dead-lettering, crashed handlers with no active notification |
| 2026-07-16 14:00:59 UTC | listing-agents | `ee35f80967` | Fix two real hub-core bugs found while addressing HITL error-visibility gap |
| 2026-07-16 14:08:49 UTC | listing-agents | `f91de8b59d` | Add real SMS human_notifier (Twilio), re-review agent 11 fix |
| 2026-07-16 14:08:51 UTC | dispatcher-agents | `61afe89026` | Add real SMS human_notifier (Twilio) - real implementation with a clearly-marked, trivially-replaceable placeholder destination number (NANP 555-01xx reserved-for-fiction range). 6 new tests, 84/84 passing. |
| 2026-07-16 14:14:54 UTC | listing-agents | `702cc2a33d` | Add Agent 12 (Marketing Campaign) - CCP gate, compliance-first publishing, verdict-locked assets |
| 2026-07-16 14:26:06 UTC | listing-agents | `926cfa88f4` | Agent 12 re-review: fix two real bugs found, not just add tests |
| 2026-07-16 14:33:24 UTC | listing-agents | `6c3055939d` | Add Agent 13 (Buyer Search & Match) - verbatim criteria, anti-steering, buyer agreement gate |
| 2026-07-16 14:56:02 UTC | listing-agents | `4bb758b14c` | Add Agent 15 (Financial Tracking) - highest PII sensitivity, wire-adjacent full stop, verified-only figures |
| 2026-07-16 15:01:50 UTC | listing-agents | `a43cf5d68b` | Fix real bugs found by systematic sweep, not by trusting 'clean pass' |
| 2026-07-16 15:09:06 UTC | listing-agents | `5fd208abda` | Add Agent 16 (After-Close & Referral) - all six standing checks actually run and shown this time |
| 2026-07-16 19:27:24 UTC | listing-agents | `334f721f40` | Add Agent 17 (Compliance & Fair Housing) - the contract every other agent has been building against |
| 2026-07-16 19:35:52 UTC | listing-agents | `7a0aa98640` | Agent 17 re-review: real bug found and fixed by tracing the resubmission logic by hand |
| 2026-07-16 19:44:12 UTC | listing-agents | `4ef521f51f` | Add Agent 19 (Prospecting) - deep pass done before reporting done, not after being asked twice |
| 2026-07-16 19:50:56 UTC | listing-agents | `b60a6b9472` | Agent 19 re-review: found and fixed a real cross-agent contract bug, not a false-confidence pass |
| 2026-07-16 19:56:22 UTC | listing-agents | `b84cb5a838` | Add Agent 20 (Social Media Monitoring) - the last of 20. Deep pass done before writing tests, not after. |
| 2026-07-16 20:50:37 UTC | listing-agents | `adb41da8f0` | Wire agent.status as a standard capability across all agents with a real wait, not selectively |
| 2026-07-16 21:24:48 UTC | listing-agents | `354823bf72` | Ratify 15 tunables, expose 6 more that were hardcoded inline, propose real config drafts, add TUNING_MANUAL.md |
| 2026-07-16 21:25:39 UTC | listing-agents-blueprint | `2702ad3297` | Patch identity/routes.json with all routing gaps found and fixed during the working build |
| 2026-07-17 00:18:53 UTC | listing-agents-blueprint | `944406fba5` | Add lead.inbound route: direct call/web-form/text intake into Agent 01 |
| 2026-07-17 00:19:06 UTC | listing-agents | `6ebade48fb` | Add lead.inbound route: direct call/web-form/text intake into Agent 01 |
| 2026-07-17 00:35:33 UTC | dispatcher-agents | `53affa853d` | Fix stale counts and a real path bug found during listing-agents review |
| 2026-07-17 00:42:08 UTC | listing-agents-blueprint | `4a71f02ace` | Reconcile generate_skills.py drift: 22 routes, agent.status entirely missing |
| 2026-07-17 00:42:14 UTC | listing-agents | `aa715c59d1` | Sync SKILL.md files with reconciled generate_skills.py output (blueprint 4a71f02) |
| 2026-07-17 01:13:46 UTC | listing-agents-blueprint | `16178a57d9` | Agent 05 review fixes: add 05->17 compliance.notice route (tuple 11) |
| 2026-07-17 01:13:59 UTC | listing-agents | `64fd128da2` | Fix four real gaps found in Agent 05 review, not just flag them |
| 2026-07-17 01:52:51 UTC | listing-agents | `04667b1f50` | Fix three real gaps found in Agent 02 review |
| 2026-07-17 01:55:08 UTC | listing-agents | `d7cf1c668b` | Fix real bug in Agent 03: frequency complaint silently killed the sequence |
| 2026-07-17 01:57:40 UTC | listing-agents | `79778f9445` | Fix two real bugs in Agent 06's double-booking logic |
| 2026-07-17 02:10:58 UTC | listing-agents | `4ea62f79b3` | Resolve Agent 03 tuples 4/10 ambiguity: confirmed distinct scenarios (owner, 2026-07-16) |
| 2026-07-17 02:58:02 UTC | listing-agents | `0635d49300` | Add missing buffer_minutes entry to TUNING_MANUAL.md (standing KPI miss) |
| 2026-07-17 03:01:45 UTC | listing-agents | `9188b73d15` | Fix real fail-open bug in Agent 08: unconfigured sender allowlist skipped verification entirely |
| 2026-07-17 05:51:28 UTC | listing-agents-blueprint | `0db40869bd` | Add vendor.cancellation_notice route: Agent 09 review, tuple 1 fix |
| 2026-07-17 05:51:48 UTC | listing-agents | `3371d663ce` | Agent 09 review: real fix for tuple 1's dead notification path |
| 2026-07-17 08:02:30 UTC | listing-agents | `377b744277` | Fix three real gaps in Agent 10, document one structural gap honestly |
| 2026-07-17 08:09:11 UTC | listing-agents | `0125671b9b` | Fix two real gaps in Agent 11, flag one genuine playbook conflict |
| 2026-07-17 08:23:22 UTC | listing-agents | `12b5a771a2` | Agent 12 review: fix real retract gap, document a structural one |
| 2026-07-17 08:25:18 UTC | listing-agents | `533e73f8fd` | Agent 13 review: confirm prior fixes solid, document one structural gap |
| 2026-07-17 08:27:49 UTC | listing-agents | `2840d7777f` | Fix real gap in Agent 15: tax-conflict flag never persisted |
| 2026-07-17 08:36:13 UTC | listing-agents | `d98881295b` | Fix real gap in Agent 16: blocked touches were silently swallowed |
| 2026-07-17 08:38:42 UTC | listing-agents | `9fbf56e288` | Fix real gap in Agent 17: near-miss counter never reset |
| 2026-07-17 08:44:40 UTC | listing-agents | `6e63ee87d8` | Fix real gap in Agent 16: 4 of 5 touch types silently swallowed blocks |
| 2026-07-17 08:50:40 UTC | listing-agents | `ad44c1551b` | Agents 17-20 review: verified solid, one structural gap documented |
| 2026-07-17 12:06:37 UTC | listing-agents | `543558c725` | 3rd-pass tuning-manual sweep: 6 more real gaps, 2 core items never actually ratified |
| 2026-07-17 12:08:48 UTC | listing-agents | `b1bfc6c6a0` | Add missing showing_bumped_notice entry to message_templates.json |
| 2026-07-17 12:26:43 UTC | dispatcher-agents | `a857e2c723` | Ratify loop_threshold=20 and MANNERS N=10 as deliberate placeholders (owner, 2026-07-17) |
| 2026-07-17 12:26:59 UTC | listing-agents | `a4dfeeadb3` | Ratify loop_threshold=20 and MANNERS N=10 (owner, 2026-07-17); bump routes.json version |
| 2026-07-17 12:27:05 UTC | listing-agents-blueprint | `eee797c3a9` | Ratify MANNERS N=10 (owner, 2026-07-17); bump routes.json version to 0.19 |
| 2026-07-17 12:48:33 UTC | listing-agents | `69e4c667a7` | Wire Agent 07's transaction milestones for real (owner decision, 2026-07-17) |
| 2026-07-17 12:48:44 UTC | listing-agents-blueprint | `a4c8679540` | Sync config/*.json with listing-agents (mirrors 69e4c66) |
| 2026-07-17 13:18:21 UTC | dispatcher-agents | `bc702d5f78` | Fix real gap in hub.py: suspended loops had no recovery path at all |
| 2026-07-17 14:43:59 UTC | dispatcher-agents | `6a869d123b` | Fix systemic notification gap: 8 call sites silently queued without notifying |
| 2026-07-17 17:54:13 UTC | listing-agents | `c15846eea4` | Agent 01: fix the fail-open bug and close every gap found this time, not just report it |
| 2026-07-17 17:54:19 UTC | listing-agents-blueprint | `ef70b5c345` | Add Agent 01 as legal sender of client.message.request (tuple 15) |
| 2026-07-17 18:13:00 UTC | listing-agents | `2664234c0f` | Agent 14: fix 4 zero-code gaps, correct 1 misleading comment, verify 1 false alarm |
| 2026-07-17 18:26:37 UTC | dispatcher-agents-blueprint | `cc278f6a2a` | Populate dispatcher-agents-blueprint for the first time (owner decision, 2026-07-17) |
| 2026-07-17 18:33:50 UTC | listing-agents | `6e62876e03` | Agent 02 review: verify prior fixes solid, close one real gap in tuple 6 |
| 2026-07-17 18:41:00 UTC | listing-agents | *(this commit)* | Create PUSH_LOG.md, backfilled with every real commit from 2026-07-16 onward across all 4 in-scope repos |
| 2026-07-17 18:48:00 UTC | listing-agents | *(this commit)* | Agent 03 review: fix 3 real gaps (tuples 2/6 missing client confirmations, tuple 7 zero-code legal-hours/holiday gate) |
| 2026-08-02 01:12:33 UTC | dispatcher-agents | `0bafaa9` | ABSOLUTE SIGNAL: disclosure gate (hold counterparty/public) + signed release_disclosure path (Ed25519+registry+MFA) + canonical rebuttal + FINANCIAL_CAPABILITY.md; 125 tests pass |
| 2026-08-02 01:12:33 UTC | listing-agents | `aeb9a3d` | ABSOLUTE SIGNAL: sync gate/release, tag 3 external routes with audience, MANNERS Manner 15, rewrite 12 tests to hold->release->complete contract; 420 tests pass |
| 2026-08-02 01:12:33 UTC | listing-agents | *(this commit)* | Demo: Act 1 + Act 4 reframed to show gate hold -> human signed release -> publish (video-ready); repo docs |

**Correction (2026-10-11, audit):** eight rows added on 2026-10-08/09 named commits `audit-obj1-3`, `feat-b1-jev` ... `docs-all-current` with rounded timestamps. No commits with those names exist; they were removed. The rows below are the real commits between `f45fa7d` and `33a835c`, taken from `git log` (commit date, UTC), in the order they were made.

| Timestamp (UTC) | Repo | Commit | What |
|---|---|---|---|
| 2026-10-09 03:48:10 UTC | listing-assistants | `2958a1cebb` | Remediation & Launch Suite: JEV AI adapter, Hermes cognitive seam, Client Drawers, HITL protocol, SQLite persistence, Apricorn verifier, 557 tests passing |
| 2026-10-09 04:02:06 UTC | listing-assistants | `57bf4a5eac` | HITL Real-Time Alerts & AM Briefing Recap: immediate decision notice dispatch and Agent 18 unresolved recap |
| 2026-10-09 11:46:01 UTC | listing-assistants | `a4976e0612` | docs: articulate all 6 strategic additions in AGENT_USER_MANUAL and OPERATOR_TUNING_GUIDE |
| 2026-10-09 11:50:26 UTC | listing-assistants | `0596a44eb3` | docs: refresh all repository documentation to current state with JEV AI deep parity |
| 2026-10-09 12:09:47 UTC | listing-assistants | `03c2ef712c` | feat: standardize HITL decision outcomes, add forensic snapshot tool, and add GitHub drop docs |
| 2026-10-09 12:29:34 UTC | listing-assistants | `756d2d32df` | feat: Add un-stubbed client dashboard, human-readable real-time/EOD logging, release docs, and changelog |
| 2026-10-09 12:44:38 UTC | listing-assistants | `52138bc0db` | feat: Add HermesLearningLoop with variance tracking, dual training logging, and learning architecture whitepaper |
| 2026-10-09 12:54:09 UTC | listing-assistants | `7877be06c1` | feat: Add ModelCheckpointManager, daily warm restore points (AWS-style snapshots), hot-swap rollback, and Golden Broker Exam |
| 2026-10-09 13:03:25 UTC | listing-assistants | `31a657e8f5` | docs: Embed learning loop, clean room, restore points, and two-tier architecture diagrams across README, Agent User Manual, and Operator Tuning Guide |
| 2026-10-09 13:28:47 UTC | listing-assistants | `6e95f099c1` | feat(archetype): ratify signer registry, implement ConcurrentHubDispatcher, add developer architectural docs |
| 2026-10-09 13:46:15 UTC | listing-assistants | `43ae945f85` | docs: Add Windows Quickstart Guide for cold-start installations and touchscreen testing |
| 2026-10-09 15:12:01 UTC | listing-assistants | `4e71bead86` | docs: Add Broker & Team Leader FAQ and Fiduciary Terms of Use & Supervisory Boundaries |
| 2026-10-09 15:14:56 UTC | listing-assistants | `a77807e6d7` | docs: Expand Single-Responsibility, 4 Divisions, 227 Tuples, 24 Playbooks, and P01 Spotlight in README |
| 2026-10-09 15:38:01 UTC | listing-assistants | `4f79dae288` | feat: Add Escalate to Support, Pocket Dispatcher remote messaging, and field command parser |
| 2026-10-09 15:41:08 UTC | listing-assistants | `40ede47726` | feat: Add Ongoing Broker Personalization feedback loop and training assimilation |
| 2026-10-09 15:47:05 UTC | listing-assistants | `554fb1b2dc` | feat: Add 3 real-world field scenarios and External Provider Gateway BYOK template |
| 2026-10-09 15:59:51 UTC | listing-assistants | `d9868b9095` | docs: Update OPERATOR_TUNING_GUIDE with Provider Gateway, Field Orchestration, and 577 tests |
| 2026-10-09 16:13:25 UTC | listing-assistants | `1ce219d5cc` | docs: Add Physical Hard Drive Architecture, SHA-256 tamper evidence, and zero-cloud differentiation |
| 2026-10-09 17:59:08 UTC | listing-assistants | `57cb6da24a` | feat(jev): implement 0.45 confidence floor, deterministic underflow stops, and dual-notification flow |
| 2026-10-09 19:35:00 UTC | listing-assistants | `e5d308a1fd` | docs: enforce front-and-center fiduciary notice, unwired financial execution, and 21-member roster specifications |
| 2026-10-09 19:42:40 UTC | listing-assistants | `04df1b0781` | ci: replace legacy developer debugging notes with professional production validation specifications |
| 2026-10-09 20:06:54 UTC | listing-assistants | `ec11db309a` | docs: add WEBSITE_PROJECT_HANDOFF for launch and web design thread |
| 2026-10-10 01:14:30 UTC | listing-assistants | `3bf789c4d2` | feat(jev): wire live HTTPS REST client with JEV_API_KEY support and seamless offline failover |
| 2026-10-10 01:23:22 UTC | listing-assistants | `d30375b8d3` | feat(fallback): enforce explicit fallback status tagging across JEV adapter, Agent 00 boot audit, Spoke 02, and all docs |
| 2026-10-10 01:46:27 UTC | listing-assistants | `d97ce79dd5` | docs: establish v1.1.2 roadmap for physical hardening and BYOK validation |
| 2026-10-10 01:49:25 UTC | listing-assistants | `2478835f5b` | docs: align test badge with verified 586-test count |
| 2026-10-10 01:51:48 UTC | listing-assistants | `c08f1e4749` | docs: add Commercial Real Estate (CRE) archetype extension to roadmap horizon |
| 2026-10-10 02:28:26 UTC | listing-assistants | `0a394b9147` | docs: formalize compounding IP asset equity and  platform fee in learning loop architecture |
| 2026-10-10 14:00:45 UTC | listing-assistants | `33a835ce67` | security: complete AST audit, CVE check, and penetration smoke suite (592 passing) |
| 2026-10-11 17:37:09 UTC | listing-assistants | `ca46cd30e5` | fix(drawers): path containment, context binding, no identity overwrite; real traversal tests |
| 2026-10-11 17:41:17 UTC | listing-assistants | `378ee836f2` | fix(hitl): signed decisions only, legal wait-clear, honest statuses, CLI stops faking success |
| 2026-10-11 17:42:56 UTC | listing-assistants | `39686d9c3c` | fix(update-verifier): pubkey CLI, reject unlisted/unsafe files, no env bypass, downgrade check; add sign_manifest.py |
| 2026-10-11 17:45:06 UTC | listing-assistants | `a1396217cb` | fix(config): signer registry back to unratified template; draft configs no longer load; remove untupled 10 subject mode and dead 11 loader |
| 2026-10-11 17:50:43 UTC | listing-assistants | `7dd108cc4c` | JEV: one lead rubric, fail-closed confidence, explicit opt-in for off-box calls (audit JEV-1..4) |
| 2026-10-11 17:53:10 UTC | listing-assistants | `d438b28540` | Hermes seam: no fabricated thoughts or drafts, taint gate fires on missing <think>, no pillar stand-ins (audit H-2..H-5) |
| 2026-10-11 17:55:21 UTC | listing-assistants | `7602612f0c` | SQLite store: exact decimal money, append-only triggers, consent history, no silent drawer identity overwrite, WAL (audit S-1..S-4) |
| 2026-10-11 17:57:46 UTC | listing-assistants | `75ea87a826` | Checkpoints: no exam without a model, no fabricated 100% scores, adapter must exist, posture-aware grading (audit C-1..C-3) |
| 2026-10-11 17:59:09 UTC | listing-assistants | `cc43784fb5` | EOD report: integrity lines computed from the AuditLog chain or labeled not computed; safe client path segment (audit LOG-1, D-4) |
| 2026-10-11 18:00:38 UTC | listing-assistants | `048f4a85c3` | Agent 11: lead.reply only to agents with a handler; others and non-acked sends go to a human with the client's words (audit OPS-1) |
| 2026-10-11 18:03:41 UTC | listing-assistants | `d8fd867d20` | Handoff rule: every spoke send that is rejected or dead-lettered raises handoff.failed and holds for a human (audit TU-2) |
| 2026-10-11 18:06:00 UTC | listing-assistants | `c367d36b81` | Tests: every declared lane with an emitter delivered in the full swarm; 139/142 lanes covered (audit LC-1) |
| 2026-10-11 18:11:03 UTC | listing-assistants | `c5b1e6854f` | Docs: restore deleted disclosures, remove claims the code does not support, fix references and clone URLs (audit ED-1..ED-8, DOC-2..DOC-4) |
| 2026-10-11 18:11:20 UTC | listing-assistants | `20ab7ae970` | Docs: correct generator attribution (gen_docs.py lives in listing-agents-blueprint) |
| 2026-10-11 18:13:47 UTC | listing-assistants | `2be72ea8dc` | README rewritten to match the code; run_sweeps documents its real flags and the empty-swarm limit (audit RD-1..RD-11, OPS-8) |
| 2026-10-11 18:17:07 UTC | listing-assistants | `245def6245` | MCP server no longer signs authority actions for the host unless started with --demo-signing (new finding MCP-1); broker manual rewritten to match the code |
| 2026-10-11 18:20:00 UTC | listing-assistants | `60bde5d0c6` | Operator guide rewritten with executed examples; console loads the vendor roster only when ratified |
| 2026-10-11 21:43:07 UTC | listing-assistants | `9191474330` | Owner decisions: expired letter voids stated financing; re-opt-in after opt-out needs human confirmation; lead.reply handlers for 04 and 12. Also: JEV doc rewritten, four unsupported docs moved out, drawer inspect reports real hash results |
| 2026-10-11 22:01:59 UTC | listing-assistants | `ad7de715d3` | All agent traffic through the dispatcher: clock.tick route replaces direct sweep/console calls (owner rule); medical-billing code removed from the MCP server |
| 2026-10-11 22:07:12 UTC | listing-assistants | `b72db41b93` | Docs: quickstart, testing guide, roadmap, security, contributing, release notes and changelog corrected; push log rows for nonexistent commits replaced with real history; drawer inspection reports real results |
| 2026-10-11 22:07:47 UTC | listing-assistants | `50c509a018` | concurrent_dispatcher: docstring states the hub lock serializes work (measured 4.04 s for 8 x 0.5 s) |
| 2026-10-11 22:09:48 UTC | listing-assistants | `5f6633a711` | Tests: Hermes learning-loop tests skip when the pillar packages are absent (keeps the CI unarmed job at exactly 1 expected failure) |
| 2026-10-11 22:10:27 UTC | listing-assistants | `183966035d` | Operator guide: console audit log exists after the first session |
| 2026-10-11 22:24:18 UTC | listing-assistants | `77bc77cc39` | Mutation follow-up: rubric defaults removed (callers guarantee keys); tests kill rubric, handoff, clock, sweep and config survivors |
| 2026-10-11 22:28:39 UTC | listing-assistants | `6391dc8ce7` | Mutation follow-up: client drawer tests kill get_drawer/has_drawer/verify_hashes/attribution survivors |
| 2026-10-11 22:34:57 UTC | listing-assistants | `92fd12755b` | Mutation follow-up: HITL tests kill armed-registry, sender/intent, validation and escalation survivors |
| 2026-10-11 22:35:12 UTC | listing-assistants | `f16616ca0e` | Mutation follow-up: SQLite tests kill category filter, schema mismatch, message and close survivors |
| 2026-10-11 22:38:00 UTC | listing-assistants | `f660287fe4` | Mutation follow-up: JEV adapter tests kill confidence, placeholder-key, env, HTTP request and floor survivors |
| 2026-10-11 22:47:24 UTC | listing-assistants | `e436f8c0d9` | Mutation follow-up: EOD report, checkpoint manifest and Hermes export tests kill bookkeeping survivors |
| 2026-10-11 22:54:39 UTC | listing-assistants | `a33b6a8e50` | Mutation follow-up: Agent 11 lead.reply call sites and 04/12 handler state tests |
| 2026-10-11 22:55:00 UTC | listing-assistants | `49551c686d` | Fix test from previous commit: check every 04/12 trace, not only the last |
| 2026-10-11 22:57:40 UTC | listing-assistants | `b7750c4947` | Docs: test count 751 (verified run) |
| 2026-10-12 00:00:55 UTC | listing-assistants | `7a59014276` | Scene run fixes: console release/held/config-dir and live human-queue pager; vendor roster in Agent 09's format; 08 maps milestones to documents and takes signed expected senders; 01 flags same person under a new context and takes signed scope/DNC; 13 matches new listings against every buyer |
| 2026-10-12 00:06:38 UTC | listing-assistants | `2600b5f99a` | Real-traffic fixes: undated vendor requests book nothing; 18 refuses dayless events; unhandled replies to 13/16 held for the broker; every unrecognized signed config held; 11 forwards all document fields; 07/19/20 leave a trace when they act on nothing |
| 2026-10-12 00:09:08 UTC | listing-assistants | `42e3b1e0fc` | Showings: conflicts across buyers of the same listing; broker records buyer agreement and identity at 14; 11 passes listing and CRM tier to 06; 13 holds agreement-less showing requests; 07 escalates a vendor hold-up once |
| 2026-10-12 00:15:47 UTC | listing-assistants | `967ff7a054` | Restart survival: the swarm's state is saved to the SQLite store and restored only when the audit chain vouches for it; one swarm builder for console and daily clock; four resolve-before-open ghost waits fixed; exhausted document chase escalates once |
| 2026-10-12 00:18:48 UTC | listing-assistants | `ef202f8920` | Continue/cancel holds through the HITL protocol: a possible duplicate person (01) and a client reply with no handling owner (11) hold the whole thread until the broker signs continue or cancel; console decide/show waits; holds survive restart |
| 2026-10-12 00:23:13 UTC | listing-assistants | `6c70d53b6b` | Owner decisions 7a-7e: Lead Nurture sends broker-signed sequences from the daily clock after 17 clears them; Agent 13's neighborhood path removed (fair-housing steering risk); Agent 19 requests comps for every opportunity and passes them to the broker; Agent 20 drafts only from broker templates, 17 reviews, approved drafts hold for the broker; Agent 20 no longer a behavioral.signal sender |
| 2026-10-12 00:24:57 UTC | listing-assistants | `fd1146a5fc` | Ten ready-to-film operator scenes (scenes/*.jsonl, synthetic data, roster the operator ratifies on camera) and a test that runs them through the console, session by session, asserting every Expected |
| 2026-10-12 00:26:03 UTC | listing-assistants | `c0556f452b` | Unit tests for the 2026-10-11 repairs through the production swarm builder: holds and signed decisions, state round trip and refusals, snapshot codec, config validation, buyer matching, held replies, document mapping, once-only escalations, nurture, social drafts, comps |
| 2026-10-12 00:26:53 UTC | listing-assistants | `15526e81ac` | Drop housekeeping: TelsonBase removed from the agent SKILL.md files, identity module, LICENSE and MOUNTING (not part of this drop; dispatcher/core.py keeps its line until dispatcher-agents changes it); SKILL.md name listing-assistants; stale SESSION_HANDOFF_6.md moved out of the repo; identity module points at the real playbook, route and authority files |
| 2026-10-12 00:27:26 UTC | listing-assistants | `43059ea435` | Console onboard: asked once after init (name, login), bound to the key fingerprint; signed console actions carry the operator login; says plainly that the IdP signer registry and the SMS pager are not armed |
| 2026-10-12 00:28:30 UTC | listing-assistants | `d3b87544f1` | Agent SKILL.md files amended for owner decisions 7a-7e; docs/JOB_DESCRIPTIONS.md now generated in this repo (tools/gen_job_descriptions.py, single source) with a test that fails when it drifts - its route lists had not been regenerated since clock.tick was added |
| 2026-10-12 03:17:17 UTC | listing-assistants | `0558acfad5` | SWARM.md: manifest maintained here (test checks counts and intent list against routes.json; clock.tick was missing); points at the playbook and core files that exist |
| 2026-10-12 03:20:46 UTC | listing-assistants | `88a9aa26fd` | P13 runs from the daily clock: broker-signed client dates at Agent 14 (MM-DD yearly or YYYY-MM-DD once), fired once per day; docs synced (operator testing manual rewritten around the ten scene files, README, broker manual, operator guide with the signed-configuration table, tuning manual, roadmap, HITL docstring) |
| 2026-10-12 03:22:52 UTC | listing-assistants | `a6facc1fcf` | MCP server builds through the shared swarm: all 20 agents, HITL, roster only from a ratified file (it had a made-up vendor and listing scope hard-coded and re-registered bare handlers); testing guide, START_HERE and PLAYBOOKS header synced |
| 2026-10-12 03:24:08 UTC | listing-assistants | `c6a054861f` | Docs say plainly that P18-P21 have no trigger in a running swarm yet (README claimed every playbook test drives its real trigger); roadmap lists them; dedupe and complaint-draft passages match the code |
| 2026-10-12 03:25:01 UTC | listing-assistants | `9c48ef6c6d` | Release notes, changelog, contributing, Windows quickstart and tuning manual synced with the repairs and the single-source decision |
| 2026-10-12 03:27:43 UTC | listing-assistants | `ab53dedb16` | Docs: test count 788 (verified on a fresh copy with a fresh venv from requirements.txt) |
| (this commit) | listing-assistants | (this commit; a commit cannot contain its own hash - read it with `git log -1`) | Push log rows for the audit-fixes push |
| 2026-10-12 11:30:41 UTC | listing-assistants | `fa187f8c4f` | README: P01 diagram renders on GitHub (a ';' in a message label ended the statement); test guards Mermaid blocks |
| 2026-10-12 11:36:09 UTC | listing-assistants | `dcf35b97ab` | Readable log wired: every chain entry described in stream.log and the client's drawer log; EOD ledger built from the chain (console show eod); a re-sent config already in effect no longer pages as unrecognized (Scene 4) |
| 2026-10-12 11:40:08 UTC | listing-assistants | `dbda49a0b8` | Client drawers wired: 04/05/07/08/14/15 file each client's records into that client's drawer (on the chain with SHA-256; refusals held); HITL holds always recorded; dashboard and inspector read the console's drawers; dashboard stages match the filed records |
| 2026-10-12 11:43:38 UTC | listing-assistants | `503c822db9` | JEV adapter wired into Agent 02: every lead scored through it and recorded on the chain (decision.lead); local engine = 02's rubric so tiers are unchanged; live JEV only on a broker-signed opt-in plus a key; low confidence holds the lead for continue/cancel |
| 2026-10-12 11:50:13 UTC | listing-assistants | `59584c3692` | Model drafting wired into Agent 04 behind three gates (broker-signed drafting mode, a configured model client, an ACTIVE checkpoint that passed the broker exam on the served model); drafts checked for reasoning, length and added numbers, then reviewed by 17 like every draft; restore_point --exam asks the served model; console --model-url/--model-name. Also fixed (present before): a capitalized flagged phrase bounced between 04 and 17 twenty times until the hub suspended the loop (nothing released, 41 pages) - removal is now case-insensitive and an unlocatable flag holds for the broker |
| 2026-10-12 11:54:25 UTC | listing-assistants | `c56b65d8e6` | Docs and tools synced with the wiring: README module tables, operator guide (drawers, decision engine, model drafting, exam, logs), testing manual (what to look at, optional Scene 11), tuning manual, broker manual, quickstart, mounting, JEV doc, roadmap, security, release notes, changelog; 02/04 SKILL.md amended and JOB_DESCRIPTIONS regenerated; show_logs/dashboard/inspector/HITL queue read the console's state; more chain kinds described in plain language |
| 2026-10-12 11:58:31 UTC | listing-assistants | `a026d5e11b` | Docs: test count 829 (fresh copy, fresh venv) |
| (this commit) | listing-assistants | (this commit; read its hash with `git log -1`) | Push log rows for the module-wiring push |
| 2026-10-12 12:58:24 UTC | listing-assistants | `1da7bf6dc8` | J5: market-update paths removed from Agents 03 and 11 and their routes; market data goes only to the broker and Agent 19 |
| 2026-10-12 12:59:41 UTC | listing-assistants | `6cea16f787` | J4: seller disclosure is a document milestone; 08 warns once on the legal line three days before a pending disclosure is due (daily clock) |
| 2026-10-12 13:04:13 UTC | listing-assistants | `608f1f6b27` | J3: P18-P21 start from the daily clock (weekly seller report held for the broker, access custody, vacant watch, WARM lead re-score) |
| 2026-10-12 13:05:34 UTC | listing-assistants | `343239bb9c` | J9: six pillar packages pinned to commits (fresh venv from requirements.txt verified) |
| 2026-10-12 13:07:16 UTC | listing-assistants | `d947510433` | J8: console text pager (`console.py pager`, `--test`, `--off`); pages carry the queue name and client context id only |
| 2026-10-12 13:09:39 UTC | listing-assistants | `0ebf4f6dc7` | DECISIONS.md: 23 tuples added with the owner's sign-off, 2 retired (J5); SKILL.md amended; JOB_DESCRIPTIONS regenerated |
| 2026-10-12 13:14:54 UTC | listing-assistants | `9c61af076d` | Docs synced with the J decisions |
| 2026-10-12 14:09:39 UTC | listing-assistants | `2d784b91b5` | Mutation-hardening tests for the 2026-10-12 code, first pass |
| 2026-10-12 14:47:43 UTC | listing-assistants | `b75b60d0f3` | Mutation-hardening tests, second pass; doc test counts; TUNING_MANUAL status line corrected |
| 2026-10-12 14:55:52 UTC | listing-assistants | `5bdb546353` | Console onboard/pager with no terminal: plain error instead of a traceback |
| 2026-10-12 15:09:01 UTC | listing-assistants | `7491e3d043` | Mutation record (logic 60.9% -> 95.1%, string 38.6% -> 82.7%); clock test; test count 939 (fresh copy) |
| (this commit) | listing-assistants | (this commit; read its hash with `git log -1`) | Push log rows for the J-items push |
| 2026-10-12 16:14:03 UTC | dispatcher-agents | `f7a5347ab0` | J10: signatures cover provenance; HMAC tier removed; JEV boot line jev.key_present; text-command parser removed; core.py no longer names TelsonBase; hub lock contract documented and tested; docs synced; identity path listing-assistants (52 routes) |
| 2026-10-12 16:16:29 UTC | listing-assistants | `082fa195d4` | J10: core f7a5347 synced; readable log, tests, README, SECURITY, FINANCIAL_CAPABILITY, JEV doc, release notes, changelog; test count 940 |
| (this commit) | listing-assistants | (this commit; read its hash with `git log -1`) | Push log rows for the J10 push |
| 2026-10-12 16:30:31 UTC | listing-assistants | `c9f0d8f3ce` | Agent docs checked against the code: SKILL.md headers, route tables (test keeps all 21 in step with routes.json), not-yet-built components marked; narrative docs drop MLS live-verification and RSVP claims; test count 961 |
| (this commit) | listing-assistants | (this commit; read its hash with `git log -1`) | Push log row for the agent-docs push |
| 2026-10-12 17:02:23 UTC | listing-assistants | `90b2950434` | Agent docs second pass against the code (all 21 SKILL.md, DECISIONS code-status notes); code fixes where the doc's rule was right (11 opt-out check, 01/02/03/12/13/16 broker notices, 09 stop-work message, 12 stale-asset records); 971 passed |
| (this commit) | listing-assistants | (this commit; read its hash with `git log -1`) | Push log row for the agent-docs second pass |
| 2026-10-12 17:14:19 UTC | listing-assistants | `a4f27be006` | Agent docs, third pass: DECISIONS code-status notes (00, 03, 06, 07, 11, 18); 11 doc corrections; 09 roster alternatives; 18 proposed order; test count 974 |
| (this commit) | listing-assistants | (this commit; read its hash with `git log -1`) | Push log row for the agent-docs third pass |
| 2026-10-12 17:45:05 UTC | dispatcher-agents | `97b5fe6109` | Hub: a failed audit write no longer marks the envelope as seen (retry was answered duplicate, never delivered); test; EVIDENCE row; counts 132+5 / 137 |
| 2026-10-12 17:45:45 UTC | listing-assistants | `46bc2296ce` | Core synced (hub persist fix); 00 SKILL.md, JOB_DESCRIPTIONS, changelog |
| (this commit) | listing-assistants | (this commit; read its hash with `git log -1`) | Push log rows for the persist-fix push |
| 2026-10-12 18:18:38 UTC | listing-assistants | `f516d2e583` | Owner decisions: consent required for every client message (11), signed consent_record at 14, angry client straight to the broker with no reply; 8 DECISIONS tuples with sign-off, 1 retired; scenes record consent; docs; test count 984 |
| (this commit) | listing-assistants | (this commit; read its hash with `git log -1`) | Push log row for the consent push |
| 2026-10-12 19:03:48 UTC | listing-assistants | `0d454c1794` | Operator testing manual: running order and every scene line by line, checked against a fresh run |
| (this commit) | listing-assistants | (this commit; read its hash with `git log -1`) | Push log row for the manual push |
| 2026-10-12 19:20:44 UTC | freight-agents | `732896fa44` | Core sync (dispatcher-agents 97b5fe6) + tools/sync_core.py; `message.send` counterparty (owner decision); core boot test; pinned requirements; README rows for files the repo never had removed; docs; Manner 15 (sign-off pending); 29 passed, 1 skipped |
| 2026-10-12 19:20:48 UTC | medbilling-agents | `4f00be7764` | Core sync + sync tool; `patient.message.send` principal, `claim.submit` counterparty; 04/07 record only acked sends; P03 releases with a signed authority; demo act 2 shows hold and release; docs; Manner 15 (sign-off pending); 35 passed |
| 2026-10-12 19:20:51 UTC | claim-agents | `b8996b375c` | Core sync + sync tool; `claimant.message.send` counterparty; 04 records only acked sends; P05 releases with a signed authority; docs; Manner 15 (sign-off pending); 25 passed, 1 skipped |
| 2026-10-12 19:20:54 UTC | hr-agents | `e6b020524a` | Core vendored (16 files) + sync tool; `employee.message.send` principal; core boot test; requirements; docs (route count 30 -> 38); Manner 15 (sign-off pending); 7 passed, 1 skipped |
| 2026-10-12 19:20:58 UTC | enrollment-agents | `7525b742fa` | Core vendored + sync tool; `family.message.send` principal; core boot test; requirements; docs (route count 31 -> 39); Manner 15 (sign-off pending); 7 passed, 1 skipped |
| 2026-10-12 19:21:01 UTC | practice-agents | `79671fabfb` | Core vendored + sync tool; `patient.message.send` principal, `claim.submit` counterparty; core boot test; requirements; 09 SKILL edge; docs; Manner 15 (sign-off pending); 7 passed |
| 2026-10-12 19:21:04 UTC | mortgage-agents | `0bd2a52c65` | Core vendored + sync tool; `borrower.message.send` principal; core boot test; requirements; docs; Manner 15 (sign-off pending); 6 passed, 1 skipped |
| 2026-10-12 19:21:07 UTC | property-mgmt-agents | `d0c49c9dff` | Core vendored + sync tool; `tenant.message.send` counterparty; core boot test; requirements; 04 SKILL edge; docs; Manner 15 (sign-off pending); 7 passed, 1 skipped |
| (this commit) | listing-assistants | (this commit; read its hash with `git log -1`) | sync_core.py checks 16 files (adds absolute_signal.py) and is the shared copy for all identity repos; README count; changelog; push log rows for the eight identity-repo pushes |
| 2026-10-12 19:35:52 UTC | freight-agents | `bcc45bfb76` | Playbooks P01-P14, generators, verify_swarm, tuple index, ROSTER, AFTER_ACTION from freight-agents-blueprint 5eabfda (regenerated: version lines only); CI workflow; Manner 15 ratified |
| 2026-10-12 19:35:55 UTC | medbilling-agents | `a6d5eaf66e` | MCP server signs for a host only with --demo-signing (listing MCP-1 port); dead listing wiring removed; test_mcp_signing (5); CI; Manner 15 ratified; 40 passed |
| 2026-10-12 19:35:58 UTC | claim-agents | `029f05d3c5` | Same MCP port as medbilling; CI; Manner 15 ratified; 30 passed, 1 skipped |
| 2026-10-12 19:36:01 UTC | hr-agents | `a665a1d4c1` | CI workflow; Manner 15 ratified; README playbook range P01-P14 |
| 2026-10-12 19:36:05 UTC | enrollment-agents | `fa486cdeae` | CI workflow; Manner 15 ratified; README playbook range P01-P14 |
| 2026-10-12 19:36:08 UTC | practice-agents | `675ad82a6e` | generate_skills.py reads ROUTES/AGENTS from practice_data.py (one copy); CI; Manner 15 ratified |
| 2026-10-12 19:36:11 UTC | mortgage-agents | `5328b6800c` | generate_skills.py reads ROUTES/AGENTS from mortgage_data.py (one copy); CI; Manner 15 ratified |
| 2026-10-12 19:36:15 UTC | property-mgmt-agents | `82a56fa4ac` | generate_skills.py reads ROUTES/AGENTS from property_data.py (one copy); CI; Manner 15 ratified |
| 2026-10-12 19:38:45 UTC | freight-agents | `55fd364d39` | requirements: pyyaml (first CI run failed: verify_swarm "pyyaml not installed"); CI green |
| 2026-10-12 19:38:49 UTC | medbilling-agents | `7cc25a65de` | requirements: pyyaml; CI green |
| 2026-10-12 19:38:52 UTC | claim-agents | `5d4dac919e` | requirements: pyyaml; CI green |
| 2026-10-12 19:38:56 UTC | hr-agents | `b3a9186924` | requirements: pyyaml; CI green |
| 2026-10-12 19:38:59 UTC | enrollment-agents | `df3fde85b9` | requirements: pyyaml; CI green |
| 2026-10-12 19:39:02 UTC | practice-agents | `b1c093432a` | requirements: pyyaml; CI green |
| 2026-10-12 19:39:05 UTC | mortgage-agents | `d8285af186` | requirements: pyyaml; CI green |
| 2026-10-12 19:39:09 UTC | property-mgmt-agents | `7507eec25f` | requirements: pyyaml; CI green |
| (this commit) | listing-assistants | (this commit; read its hash with `git log -1`) | Diagrams: README in all 21 agent folders (from routes.json), a real-run sequence for each of the 24 playbooks, hand-drawn pictures on 15 doc pages; gen_diagrams --check + test; 74 diagrams render; 988 passed; push log rows for the identity-repo batch |
| 2026-10-12 21:37:25 UTC | freight-agents | `0458c52f27` | Diagrams: agent and playbook folder READMEs, playbook priority map, pictures on README/ROSTER/DEPLOY/INSTALL/INTEGRATIONS/AFTER_ACTION/TUNING_MANUAL; tools/gen_diagrams.py + test; 32 passed, 1 skipped |
| 2026-10-12 21:37:29 UTC | medbilling-agents | `43dbc21610` | Diagrams as freight, plus real playbook runs P01-P14 in docs/PLAY-BY-PLAY.md and pictures on the docs pages; 43 passed |
| 2026-10-12 21:37:32 UTC | claim-agents | `f7084d53fe` | Diagrams as medbilling; real runs for P01, P05-P14 (tests named p02-p04 exercise other things, so those playbooks get no run picture); 33 passed, 1 skipped |
| 2026-10-12 21:37:36 UTC | hr-agents | `4c1a267f36` | Diagrams as freight; 10 passed, 1 skipped |
| 2026-10-12 21:37:39 UTC | enrollment-agents | `357f294fc3` | Diagrams as freight; 10 passed, 1 skipped |
| 2026-10-12 21:37:43 UTC | practice-agents | `321499f662` | Diagrams as freight; 10 passed |
| 2026-10-12 21:37:46 UTC | mortgage-agents | `a1cab5588c` | Diagrams as freight; 9 passed, 1 skipped |
| 2026-10-12 21:37:50 UTC | property-mgmt-agents | `202ef8ee34` | Diagrams as freight; 10 passed, 1 skipped |
| (this commit) | listing-assistants | (this commit; read its hash with `git log -1`) | Push log rows for the identity-repo diagrams |
| 2026-10-12 21:46:22 UTC | claim-agents | `dc6dd105b0` | Real e2e tests for P02/P03/P04 (3 pass; 6 xfail name the steps not built); misnumbered p02-p04 tests renamed; run pictures from the new tests; 36 passed, 1 skipped, 6 xfailed |
| 2026-10-12 21:46:32 UTC | freight-agents | `3ad2c2313e` | gen_diagrams parity (run tests looked up in every test_playbooks_*.py) |
| 2026-10-12 21:46:35 UTC | medbilling-agents | `7588f6fa09` | gen_diagrams parity |
| 2026-10-12 21:46:38 UTC | hr-agents | `29bbcd73cd` | gen_diagrams parity |
| 2026-10-12 21:46:42 UTC | enrollment-agents | `1418597bca` | gen_diagrams parity |
| 2026-10-12 21:46:45 UTC | practice-agents | `7c131056a0` | gen_diagrams parity |
| 2026-10-12 21:46:49 UTC | mortgage-agents | `ab93023cee` | gen_diagrams parity |
| 2026-10-12 21:46:52 UTC | property-mgmt-agents | `e174e08841` | gen_diagrams parity |
| (this commit) | listing-assistants | (this commit; read its hash with `git log -1`) | Push log rows for the claim tests and generator parity |
| (this commit) | listing-assistants | (this commit; read its hash with `git log -1`) | Broker Desk: tools/desk.py + desk.html (Needs you with signed Send / Continue / Cancel / Done, listing tracks, hot-lead clocks, team, proof strip; --showcase replays the ten scenes; --lan with access code); console apply_action shared; desk lock honoured by console and run_sweeps; test_desk.py (6); docs + screenshots; 994 passed |
