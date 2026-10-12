# ListingAssistants Roadmap

Released tags: `archetype-v1.0.0`, `v1.1.0`. The audit-fix branch of
2026-10-11 is not tagged; tagging the release commit is the owner's step.

## Done on 2026-10-11 (moved off this list)

- HITL protocol wired: Agents 01, 11 and 20 hold threads for the broker's
  signed continue or cancel.
- State survives a restart: snapshots in the SQLite store, vouched for by
  the audit chain.
- Untriggered code resolved by owner decision: Agent 03 sends nurture
  touches from the daily clock; Agent 19 requests comps for every
  opportunity; Agent 20 drafts from the broker's templates for approval;
  Agent 13's neighborhood path and Agent 20's `behavioral.signal` lane were
  removed. A client reply with no named owner holds for the broker.

## 1. Wiring the remaining optional modules

Each module below is tested on its own and called by no agent yet. Wiring
one is a ratified change in this repository: routes in
`identity/routes.json`, tuples in the agent's DECISIONS.md, then code and
tests.

- Client drawers: have agents file their records (documents filed by 08,
  messages sent by 11, holds and decisions) into the client's drawer; the
  dashboard and `manage_hitl_queue.py` then show live data.
- SQLite CRM, consent and ledger tables: have Agents 14 and 15 write to them
  (their records are saved today inside the state snapshot).
- JEV adapter: have Agent 02 score through it (local engine by default).
- Hermes seam and checkpoint manifest: need a locally served model.

## 2. Identity-provider signer binding

`config/authority_signers.json` binds signers to an identity provider with
MFA. Connecting an identity provider that stamps each signed envelope with
the login, MFA and session is what arms it.

## 3. Uncalled scheduled checks

These have code but nothing calls them: `Agent 08.check_disclosure_deadline`
(no source of disclosure deadlines exists yet), and
`Agent 03.request_market_update` / `Agent 11.request_market_update` (market
updates to clients through Agent 10). Each needs an owner decision: put it
on the daily clock (`dispatcher/clock.py`) with its data source, or remove
it. (P13's date triggers were wired to the clock on 2026-10-11.)

## 4. Signed actions over MCP

The MCP server signs for a host only in `--demo-signing` mode. A production
lane where the host forwards an envelope signed with the broker's own key is
not built.

## 5. Providers and hardware

- Connect the external adapters (MLS writes, client messaging, ad publishing)
  to your providers; until then they queue visibly.
- Twilio credentials for the SMS notifier.
- Storage: keep drawers and the SQLite file on a local disk, on an encrypted
  volume if encryption at rest is required.
- Offline updates: the signing and verification tools exist
  (`tools/sign_manifest.py`, `tools/verify_update_pack.py`); the transport
  (for example an encrypted USB drive) is an operating procedure.

## 6. Commercial real estate (future archetype)

The hub, closed-track routing, signed authority and hash-chained audit log
are sector-agnostic. A commercial identity would need its own agents, routes
and tuples for offering memorandums, confidentiality agreements, NOI / cap
rate / DSCR analysis, lease abstraction, and the commercial statutory frame
(securities rules, accredited-investor thresholds, environmental diligence,
zoning).
