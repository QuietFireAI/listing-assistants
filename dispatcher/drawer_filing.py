"""drawer_filing - how agents file a client's records into that client's drawer.

Added 2026-10-12 (owner: wire the optional modules). Before this, no agent
wrote to a client drawer; dispatcher/client_drawer.py was used only by the
HITL protocol and operator tools.

  build_swarm() creates one ClientDrawerManager (default: "drawers" next to
  the audit log) and hangs it on the hub as hub.drawers, the same way the
  HITL manager is hub.hitl. Agents call file_record(); nothing else writes
  to drawers.

What is filed, by whom (one JSON file per record, SHA-256 in the manifest):
  05  artifacts/   the signed listing package (also sets the drawer's
                   property address and seller name when the package has them)
  04  artifacts/   the description as released after 17 approved it
  07  timeline/    the transaction timeline as loaded
  08  documents/   every document filed clean (the payload as received)
  14  interactions/ every CRM entry (append-only, one file per entry)
  15  financials/  every expense entry
  HITL audit/      pause and resolution records (hitl_protocol, unchanged)

Rules
  - A drawer is provisioned the first time anything is filed for a client.
    Name and address start blank and are filled in from the first record
    that carries them; a later, different value never overwrites a filled
    one (the conflict is recorded as drawer.identity_conflict and held for
    the broker).
  - Every filing is on the hash chain (drawer.filed with the file's
    SHA-256). A refusal (unsafe client id, cross-client attempt, disk
    error) is recorded as drawer.refused and held for the broker - never
    swallowed.
  - Files are plain JSON on disk, NOT encrypted. Protect the volume.
  - A hub with no drawer store (bare test hubs) files nothing and says so
    in the return value; the production swarm always has one.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from .core import Envelope


def _hold(hub: Any, agent_id: str, ctx: str, reason: str, detail: dict) -> None:
    hub.send(Envelope(from_agent=agent_id, to_agent="queue", intent="clarification.request",
                      client_context_id=ctx, payload={"reason": reason, **detail},
                      provenance={"source": f"spoke-{agent_id}", "captured_at": "runtime",
                                  "verbatim_available": True}))


def _identity(hub: Any, drawers: Any, agent_id: str, ctx: str, identity: Optional[dict]) -> None:
    """Provisions the drawer if absent; fills blank name/address only."""
    want = {k: str(v) for k, v in (identity or {}).items()
            if k in ("client_name", "property_address", "role") and v not in (None, "")}
    if not drawers.has_drawer(ctx):
        drawers.provision_drawer(ctx, client_name=want.get("client_name", ""),
                                 property_address=want.get("property_address", ""),
                                 role=want.get("role", "client"), assigned_agent="00")
        hub.audit.append("drawer.provisioned", {"agent": agent_id, "client_context_id": ctx,
                                                "identity_fields": sorted(want)})
        return
    if not want:
        return
    m = drawers.get_drawer(ctx).get_manifest()
    have = {"client_name": m.get("client_name", ""), "property_address": m.get("property_address", "")}
    fill, conflicts = {}, {}
    for k in ("client_name", "property_address"):
        if k in want:
            if not have[k]:
                fill[k] = want[k]
            elif have[k] != want[k]:
                conflicts[k] = {"on_file": have[k], "new": want[k]}
    if fill:
        drawers.provision_drawer(ctx, client_name=fill.get("client_name", have["client_name"]),
                                 property_address=fill.get("property_address", have["property_address"]),
                                 role=m.get("role", "client"), assigned_agent="00",
                                 metadata=m.get("metadata"), update_identity=True)
        hub.audit.append("drawer.identity_filled", {"agent": agent_id, "client_context_id": ctx,
                                                    "fields": sorted(fill)})
    if conflicts:
        hub.audit.append("drawer.identity_conflict", {"agent": agent_id, "client_context_id": ctx,
                                                      "conflicts": conflicts})
        _hold(hub, agent_id, ctx, "client drawer identity conflict - the value on file was kept; "
                                  "you decide which is right", {"conflicts": conflicts})


def file_record(hub: Any, agent_id: str, ctx: str, category: str, name: str,
                record: Any, identity: Optional[dict] = None) -> dict:
    """Files one record as <category>/<name>.json in the client's drawer.
    Returns {"filed": bool, ...}; refusals are on the chain and held."""
    drawers = getattr(hub, "drawers", None)
    if drawers is None:
        return {"filed": False, "reason": "no drawer store on this hub"}
    filename = f"{name}.json"
    try:
        _identity(hub, drawers, agent_id, ctx, identity)
        body = json.dumps(record, sort_keys=True, indent=2, default=str)
        drawers.record_agent_artifact(ctx, agent_id, category, filename, body,
                                      metadata={"agent": agent_id},
                                      acting_client_context_id=ctx)
    except Exception as e:  # recorded and held, never swallowed
        why = f"{type(e).__name__}: {e}"
        hub.audit.append("drawer.refused", {"agent": agent_id, "client_context_id": ctx,
                                            "category": category, "filename": filename,
                                            "reason": why})
        _hold(hub, agent_id, ctx, "client drawer filing refused", {"error": why,
                                                                  "category": category})
        return {"filed": False, "reason": why}
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    hub.audit.append("drawer.filed", {"agent": agent_id, "client_context_id": ctx,
                                      "category": category, "filename": filename,
                                      "sha256": digest})
    return {"filed": True, "category": category, "filename": filename, "sha256": digest}
