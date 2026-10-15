"""Unanswered escalations (Agent 00 tuple "escalation queue item
unacknowledged past SLA, re-alert once then page the owner channel; never
silently expire an escalation"), and clock skew (tuple "clock skew detected
between components, hold time-triggered playbooks").

Owner decisions 2026-10-14: an escalation nobody has acknowledged is
re-alerted once at REALERT_MINUTES (30) and the owner channel is paged at
OWNER_PAGE_MINUTES (60). Clock skew beyond SKEW_TOLERANCE_SECONDS (60)
holds every time-triggered check.

Everything here reads the audit log, the one record of what was raised and
what you marked done, so it survives a restart and needs no state of its own.

Acknowledging: the Broker Desk's Done button and the console's
{"do": "ack", "queue": ..., "ctx": ...} both write `desk.acknowledged` with
the item's key (key_of). Nothing else counts as an acknowledgement; an
escalation is never expired by time.

When it runs: inside every daily sweep, on the console's {"do": "watch"},
and from `python tools/run_sweeps.py --watch`, which is meant for a
scheduler entry every few minutes (a 30-minute re-alert needs a check more
often than once a day).
"""
from __future__ import annotations

import datetime
import hashlib
import json
import time

# TUNABLE (owner-ratified 2026-10-14). See docs/TUNING_MANUAL.md.
REALERT_MINUTES = 30
OWNER_PAGE_MINUTES = 60
SKEW_TOLERANCE_SECONDS = 60

_AUDIT_FIELDS = ("kind", "ts", "prev_hash", "entry_hash", "queue")


def key_of(queue: str, record: dict) -> str:
    """The item key the Broker Desk uses for a queue item (tools/desk.py
    key_of); the same algorithm, so a Done on the desk acknowledges here."""
    body = json.dumps(record, sort_keys=True, default=str)
    return hashlib.sha256(f"{queue}|{body}".encode()).hexdigest()[:16]


def _record_of(entry: dict) -> dict:
    return {k: v for k, v in entry.items() if k not in _AUDIT_FIELDS}


def acknowledge(hub, queue: str, ctx: str, by: str | None = None) -> list[str]:
    """Marks every unacknowledged item of `queue` for client context `ctx`
    done, the same record the desk's Done writes. Returns the keys."""
    log = hub.audit.read()
    acked = {e.get("item") for e in log if e.get("kind") == "desk.acknowledged"}
    done = []
    for rec in list(hub.queues.get(queue, [])):
        if not isinstance(rec, dict) or rec.get("client_context_id") != ctx:
            continue
        k = key_of(queue, rec)
        if k in acked or k in done:
            continue
        hub.audit.append("desk.acknowledged", {"item": k, "title": queue,
                                               "client_context_id": ctx, "by": by})
        done.append(k)
    return done


def check_unacknowledged(hub, now: float | None = None) -> dict:
    """Re-alerts once at REALERT_MINUTES, pages the owner once at
    OWNER_PAGE_MINUTES, for every escalation not yet acknowledged."""
    now = time.time() if now is None else now
    log = hub.audit.read()
    acked = {e.get("item") for e in log if e.get("kind") == "desk.acknowledged"}
    realerted = {e.get("raised_entry") for e in log if e.get("kind") == "escalation.realerted"}
    paged = {e.get("raised_entry") for e in log if e.get("kind") == "escalation.owner_paged"}
    out = {"realerted": [], "owner_paged": [], "open": 0}
    for e in log:
        if e.get("kind") != "escalation.raised":
            continue
        queue, rec = e.get("queue"), _record_of(e)
        if key_of(queue, rec) in acked:
            continue
        out["open"] += 1
        age_min = (now - e["ts"]) / 60.0
        entry = e.get("entry_hash")
        if age_min >= REALERT_MINUTES and entry not in realerted:
            hub.audit.append("escalation.realerted",
                             {"raised_entry": entry, "queue": queue,
                              "client_context_id": rec.get("client_context_id"),
                              "age_minutes": round(age_min, 1)})
            hub._notify(queue, {**rec, "REALERT": f"unacknowledged {age_min:.0f} min"})
            out["realerted"].append(entry)
        if age_min >= OWNER_PAGE_MINUTES and entry not in paged:
            hub.audit.append("escalation.owner_paged",
                             {"raised_entry": entry, "queue": queue,
                              "client_context_id": rec.get("client_context_id"),
                              "age_minutes": round(age_min, 1)})
            hub._notify("escalation.owner_page",
                        {**rec, "escalated_from": queue,
                         "OWNER_PAGE": f"unacknowledged {age_min:.0f} min"})
            out["owner_paged"].append(entry)
    return out


def clock_skew(hub, now: float | None = None) -> dict:
    """Compares this process's clock with the newest time on the audit log,
    which other processes (the desk, the console) also write. A log entry
    stamped more than SKEW_TOLERANCE_SECONDS in the future means two clocks
    disagree; time-triggered work holds. Returns {"ok": bool, "skew_s": x}."""
    now = time.time() if now is None else now
    newest = max((e.get("ts", 0) for e in hub.audit.read()), default=0)
    skew = newest - now
    return {"ok": skew <= SKEW_TOLERANCE_SECONDS, "skew_s": round(skew, 1),
            "newest_log_time": datetime.datetime.fromtimestamp(newest).isoformat() if newest else None,
            "this_clock": datetime.datetime.fromtimestamp(now).isoformat()}
