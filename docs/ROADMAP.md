# ListingAssistants Roadmap

Released tags: `archetype-v1.0.0`, `v1.1.0`. The audit-fix branch of
2026-10-11 is not tagged; tagging the release commit is the owner's step.

## 1. Wiring the optional modules

Each module below is tested on its own and called by no agent yet. Wiring
one is a ratified change: routes in `identity/routes.json`, tuples in the
agent's DECISIONS.md (listing-agents-blueprint), then code and tests.

- Client drawers: have agents file their artifacts into the client's drawer.
- HITL protocol: have agents pause through `HITLManager` and register
  resumption handlers.
- SQLite store: have Agents 14 and 15 write interactions, consent and ledger
  entries to it.
- JEV adapter and Hermes seam: decide whether any agent uses them, and with
  which tuples.

## 2. State that survives a restart

Agent state, the hub's duplicate check and outbound holds live in memory.
Rebuild them from the audit log at start-up, or persist them, so a restart
keeps holds and does not re-deliver a retried envelope.

## 3. Routes with no trigger

- 20 -behavioral.signal-> 03 has no sender.
- Agent 03 scheduled nurture touches, Agent 13 neighborhood-data requests,
  Agent 19 market-context requests and Agent 20 social draft replies have
  code but nothing that triggers them. Each needs an inbound intent on the
  closed track.
- A client reply with no named owner defaults to Agent 13 (open owner
  decision).

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
