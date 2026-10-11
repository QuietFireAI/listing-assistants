# Release Notes - ListingAssistants (next release, untagged)

Branch `audit-fixes-2026-10-11`, built on `33a835c`. The tag is the owner's
step. Every item below has a test in `tests_listing/`; the full change list,
with before/after and evidence, is in the audit-fix autopsy report.

## What this release is

ListingAssistants: twenty deterministic agents for the coordination work of a
residential listing business, on a closed track. One dispatcher hub routes
every message to and from an agent, each route is pre-approved in
`identity/routes.json`, authority actions need a verified signature, and every
message lands on a hash-chained audit log. 24 playbooks, each with an
end-to-end test.

## Changes in this release

- **All agent traffic through the dispatcher.** The daily clock and the
  console's briefing and EOD reports reach agents as `clock.tick` messages
  through the hub (new route). Every agent send is checked: a rejected or
  undeliverable handoff records `handoff.failed` and goes to the human
  clarification queue.
- **Client replies.** Agent 11 routes replies only to agents that handle
  them (03, 04, 12, 13, 16, 20; 04 and 12 log the reply and hold it for the
  broker). Anything else goes to the broker with the client's words.
- **Lead scoring.** One rubric (`dispatcher/lead_rubric.py`) for Agent 02
  and the JEV adapter. An expired pre-approval letter earns no financing
  points, including a separately stated "preapproved".
- **Configs.** Draft config files are not loaded; each skip is logged.
  `config/authority_signers.json` is an unratified template again.
- **MCP server.** It signs authority actions for a host only in
  `--demo-signing` mode. Leftover medical-billing code removed.
- **Optional modules, corrected** (still not called by any agent):
  client drawers (safe paths, client-bound filing, hash verification),
  signed HITL decisions, offline update packs (public-key verification,
  unlisted files and downgrades refused, `tools/sign_manifest.py`), SQLite
  store (exact decimal money, append-only ledgers, consent history with human
  confirmation of re-opt-in), JEV adapter (fail-closed confidence, explicit
  opt-in for external calls), Hermes seam (no fabricated reasoning or
  drafts), checkpoint manifest (no exam without a model), EOD report
  (integrity computed or labeled "not computed").
- **Docs** rewritten to match the code; deleted risk disclosures restored.

## Corrections to the archetype-v1.0.0 / v1.1.0 notes

Those notes described capabilities the code did not have: encrypted
drawers, state that survives reboots, JEV and Hermes powering agents,
real-time WhatsApp/Signal alerts, a "dual-key" update verifier, a ratified
signer registry, an MCP tool `tools/call_jev_decision`, and "21 spoke
agents". The autopsy report lists each one with what the code actually did.

## Verify

```bash
pip install -r requirements.txt
python -m pytest tests_listing/        # expect: 751 passed
python tools/run_demo.py
python tools/mcp_roundtrip.py
```
