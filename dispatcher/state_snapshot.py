"""state_snapshot - the swarm's state survives a restart.

Added 2026-10-11 (owner decision #12). Before this, every agent's state,
the hub's held outbound messages, its duplicate check and the pending human
decisions lived only in process memory: a restart (or a new console
session) started from nothing while the audit log said otherwise.

What is saved
  - every agent's own attributes (its hub link excluded)
  - the hub's runtime state: seen envelope ids, sequence counters, loop
    counts, held outbound messages and one-shot releases, human queues
  - the HITL manager's waits, alerts and errors, when one is wired
  - the playbook run tracker's runs and held or waiting messages (2026-10-20)
Not saved: the hub's in-memory analysis buffers (reflection_artifacts,
spoke_traces). Their content is on the audit log.

Format: JSON, never pickle. Sets, tuples, non-string dict keys, Envelopes
and HITL WaitStates are written with explicit type tags; any other
non-JSON value raises (a type nobody planned for is not saved by guess).

Integrity: the swarm stores each snapshot in the SQLite store's
append-only state_snapshots table and appends `state.saved` (snapshot id +
SHA-256 of the body) to the hash-chained audit log. At start-up the newest
snapshot is used only if (1) the audit chain verifies, (2) the last
`state.saved` entry on the chain names that snapshot id and hash, and
(3) the body still hashes to it. Anything else raises StateIntegrityError
and nothing is restored: a person decides what happens to that file.

Configuration versus state: an attribute a fresh agent sets from its
constructor or a ratified config file is saved with its at-save value AND
the fresh value it had then. If nothing at runtime changed it, the next
start keeps the NEW fresh value (so an edited, re-ratified config file
takes effect); if a signed message changed it at runtime, the saved value
is restored.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

HUB_STATE_ATTRS = ("seen_ids", "seq", "loop_counts", "_absolute_holds",
                   "_absolute_released", "queues")
HITL_STATE_ATTRS = ("active_waits", "notification_log", "errors")


class StateIntegrityError(RuntimeError):
    """The saved state does not match what the audit chain recorded."""


def encode(value: Any) -> Any:
    from .core import Envelope
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [encode(v) for v in value]
    if isinstance(value, tuple):
        return {"__tuple__": [encode(v) for v in value]}
    if isinstance(value, (set, frozenset)):
        return {"__set__": sorted((encode(v) for v in value), key=json.dumps)}
    if isinstance(value, dict):
        if all(isinstance(k, str) for k in value) and not any(k.startswith("__") and k.endswith("__") for k in value):
            return {k: encode(v) for k, v in value.items()}
        return {"__dict__": [[encode(k), encode(v)] for k, v in value.items()]}
    if isinstance(value, Envelope):
        import dataclasses
        return {"__envelope__": encode({f.name: getattr(value, f.name)
                                        for f in dataclasses.fields(Envelope)})}
    if type(value).__name__ == "WaitState":
        return {"__waitstate__": encode({**vars(value)})}
    raise TypeError(f"state_snapshot cannot save a {type(value).__name__}: {value!r:.80}")


def decode(value: Any) -> Any:
    if isinstance(value, list):
        return [decode(v) for v in value]
    if not isinstance(value, dict):
        return value
    if len(value) == 1:
        (tag, inner), = value.items()
        if tag == "__tuple__":
            return tuple(decode(v) for v in inner)
        if tag == "__set__":
            return {decode(v) for v in inner}
        if tag == "__dict__":
            return {decode(k): decode(v) for k, v in inner}
        if tag == "__envelope__":
            return _envelope_from_record(decode(inner))
        if tag == "__waitstate__":
            from .hitl_protocol import WaitState
            d = decode(inner)
            ws = WaitState.__new__(WaitState)
            ws.__dict__.update(d)
            return ws
    return {k: decode(v) for k, v in value.items()}


def _envelope_from_record(rec: dict):
    from .core import Envelope
    return Envelope(**rec)


def agent_state(spoke: Any) -> dict:
    # an agent running behind its portal (dispatcher/portal_dispatcher.py,
    # 2026-10-26) reports its own state; the dispatcher keeps the last report
    reported = getattr(type(spoke), "__portal_state__", None)
    if reported is not None:
        return reported(spoke)
    return {k: v for k, v in vars(spoke).items() if k != "hub"}


def capture(hub: Any, spokes: dict, hitl: Any, baseline: dict, runs: Any = None) -> dict:
    """runs: the playbook run tracker (dispatcher/run_tracker.py), when wired."""
    return {
        "runs": encode(runs.state()) if runs is not None else None,
        "format": 1,
        "hub": {a: encode(getattr(hub, a)) for a in HUB_STATE_ATTRS},
        "agents": {aid: encode(agent_state(sp)) for aid, sp in spokes.items()},
        "baseline": baseline,
        "hitl": ({a: encode(getattr(hitl, a)) for a in HITL_STATE_ATTRS}
                 if hitl is not None else None),
    }


def body_and_hash(snapshot: dict) -> tuple[str, str]:
    body = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    return body, hashlib.sha256(body.encode("utf-8")).hexdigest()


def check_against_chain(audit: Any, snap_row: dict) -> None:
    """Raises StateIntegrityError unless the chain verifies and its last
    state.saved entry names this snapshot and its hash."""
    chain = audit.verify_chain()
    if not chain.get("ok"):
        raise StateIntegrityError(f"audit chain does not verify ({chain}); saved state not restored")
    last = None
    for e in audit.read():
        if e.get("kind") == "state.saved":
            last = e
    if last is None:
        raise StateIntegrityError(
            f"state snapshot {snap_row['id']} exists but the audit log records no state.saved - "
            f"the store and this log do not belong together")
    if last.get("snapshot_id") != snap_row["id"] or last.get("sha256") != snap_row["sha256"]:
        raise StateIntegrityError(
            f"newest snapshot {snap_row['id']} ({snap_row['sha256'][:12]}) is not the one the audit log "
            f"last recorded ({last.get('snapshot_id')}, {str(last.get('sha256'))[:12]})")
    actual = hashlib.sha256(snap_row["body"].encode("utf-8")).hexdigest()
    if actual != snap_row["sha256"]:
        raise StateIntegrityError(f"snapshot {snap_row['id']} body was altered after it was saved")


def restore(hub: Any, spokes: dict, hitl: Any, snapshot: dict, fresh_baseline: dict) -> dict:
    """Applies a verified snapshot. Returns {agent: [attrs restored]}."""
    for a in HUB_STATE_ATTRS:
        if a in snapshot["hub"]:
            setattr(hub, a, decode(snapshot["hub"][a]))
    saved_baseline = snapshot.get("baseline", {})
    restored = {}
    for aid, attrs in snapshot["agents"].items():
        spoke = spokes.get(aid)
        if spoke is None:
            continue
        names = []
        for k, enc in attrs.items():
            if saved_baseline.get(aid, {}).get(k, object()) == enc and k in fresh_baseline.get(aid, {}):
                continue   # unchanged since construction: the fresh (current config) value stands
            setattr(spoke, k, decode(enc))
            names.append(k)
        restored[aid] = names
    if hitl is not None and snapshot.get("hitl"):
        for a in HITL_STATE_ATTRS:
            if a in snapshot["hitl"]:
                setattr(hitl, a, decode(snapshot["hitl"][a]))
    return restored
