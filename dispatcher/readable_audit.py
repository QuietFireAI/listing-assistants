"""readable_audit - the plain-language log, fed by the hash-chained audit log.

Added 2026-10-12 (owner: "wire the optional modules"). Before this the
readable logger (dispatcher/readable_logger.py) was called only by tools and
the Hermes loop, so the swarm's real activity never reached it.

How it is wired
  build_swarm() gives the hub a ReadableAuditLog instead of a plain
  AuditLog. Every entry is first appended to the hash chain exactly as
  before (same class, same bytes, same verification); then a one-line
  plain-language description is written to <log dir>/stream.log, and to
  drawers/<client>/audit/activity.log when that client has a drawer.

  The chain stays the record. The readable log is a view of it: bookkeeping
  entries (acks, hub reflections, turn checks, duplicate notifications) are
  left out of the view, never out of the chain. A failure to write the
  view never blocks or alters the chain entry; it is counted in
  mirror_errors, and the console prints that count at the end of every
  session.

  The end-of-day ledger (write_eod) is built from the chain itself for the
  requested date, so it covers every session that day, not only this
  process, and its integrity section verifies the chain.
"""
from __future__ import annotations

import datetime
from typing import Optional

from .core import AuditLog

# Chain entries that are bookkeeping, not events a broker reads.
SKIP_KINDS = frozenset({"ack", "hub.reflection", "turn.start", "beforeturn.check",
                        "human.notified"})


def _who(agent) -> str:
    a = str(agent)
    if a == "human":
        return "You"
    if a == "external":
        return "the outside world"
    if a == "queue":
        return "your queue"
    if a == "clock":
        return "the daily clock"
    return f"Agent {a}" if a.isdigit() else a


def describe(kind: str, rec: dict) -> Optional[tuple[str, str, Optional[str], Optional[str]]]:
    """Returns (category, message, client_context_id, agent_id), or None for
    bookkeeping kinds that stay on the chain only."""
    if kind in SKIP_KINDS:
        return None
    ctx = rec.get("client_context_id")
    if kind == "envelope.persisted":
        frm, to = rec.get("from_agent"), rec.get("to_agent")
        return ("DISPATCH", f"{_who(frm)} -> {_who(to)}: {rec.get('intent')}", ctx,
                str(frm) if str(frm).isdigit() else None)
    if kind == "spoke.trace":
        return ("DECISION", f"Agent {rec.get('agent')}: {rec.get('result')}", None, rec.get("agent"))
    if kind in ("reject", "integrity.violation"):
        return ("ALERT", f"Hub refused message {str(rec.get('envelope_id'))[:8]}: {rec.get('reason')}",
                ctx, None)
    if kind == "escalation.raised":
        # "Raised", not "Paged you": raising is not reaching you. Whether a
        # person was reached is its own line - pager.sent, or
        # human.notify_failed below (repair plan 1.1, 2026-10-13).
        return ("ALERT", f"Raised for you ({rec.get('queue')})", ctx, None)
    if kind == "human.notify_failed":
        why = (rec.get("error") or rec.get("notifier_http_status")
               or rec.get("notifier_error") or rec.get("notifier_status"))
        return ("ALERT", f"Could not reach you about {rec.get('queue')} ({why}) - "
                         f"it is waiting on your queue", ctx, None)
    if kind == "audit.tail_quarantined":
        return ("SYSTEM", f"Record repaired: a write cut off at line {rec.get('line')} "
                          f"({rec.get('bytes')} bytes) was moved to {rec.get('side_file')}; "
                          f"{rec.get('complete_entries')} complete entries kept", None, None)
    if kind == "absolute_signal.hold":
        return ("HOLD", f"Outbound {rec.get('intent')} to {rec.get('audience')} held for your signed release",
                ctx, None)
    if kind == "hold.queued":
        return ("HOLD", f"{rec.get('intent')} waiting for you", ctx, None)
    if kind in ("absolute_signal.released", "disclosure.authorized"):
        return ("RELEASE", f"{rec.get('intent')} released on your signature", ctx, None)
    if kind == "hitl.decision.authorized":
        return ("DECISION", f"Your signed decision {rec.get('decision')} applied to Agent "
                            f"{rec.get('agent')}'s hold", ctx, rec.get("agent"))
    if kind.startswith("state."):
        return ("STATE", f"{kind}: " + ", ".join(f"{k}={v}" for k, v in rec.items()
                                                  if k in ("snapshot_id", "agents", "reason")), None, None)
    if kind.startswith("config."):
        return ("CONFIG", f"{kind}: agent {rec.get('agent')} {rec.get('file') or rec.get('keys') or ''} "
                          f"{rec.get('verdict') or ''}".strip(), ctx, None)
    if kind.startswith("drawer."):
        return ("VAULT", f"{kind}: {rec.get('category', '')}/{rec.get('filename', '')} "
                         f"{rec.get('reason', '')}".strip(), ctx, rec.get("agent"))
    if kind.startswith("decision."):
        return ("DECISION", f"{kind}: {rec.get('engine')} tier={rec.get('tier')} "
                            f"confidence={rec.get('confidence')}", ctx, rec.get("agent"))
    if kind.startswith("drafting."):
        return ("DECISION", f"{kind}: {rec.get('reason') or rec.get('mode') or ''}".strip(),
                ctx, rec.get("agent"))
    if kind in ("handoff.failed", "dead.letter", "agentopenmind.tainted", "sweep.error"):
        return ("ALERT", f"{kind}: {rec.get('reason') or rec.get('intent') or rec.get('error') or ''}".strip(),
                ctx, rec.get("agent") or rec.get("from_agent"))
    if kind == "loop.suspended":
        return ("HOLD", f"Hub suspended a repeating exchange: {rec.get('reason', '')}".strip(), ctx, None)
    if kind == "pager.sent":
        return ("DISPATCH", f"Paged you by text ({rec.get('queue')})", ctx, None)
    if kind == "pager.failed":
        return ("ALERT", f"Text page failed ({rec.get('queue')}): "
                         f"{rec.get('http_status') or rec.get('error')}", ctx, None)
    if kind == "sweep.completed":
        return ("CLOCK", f"Daily clock ran for {rec.get('today')}: {rec.get('sweeps_run')} agents, "
                         f"{rec.get('errors')} errors", None, None)
    if kind == "jev.key_present":
        return ("SYSTEM", f"JEV key set: {rec.get('reason')}", None, None)
    if kind.endswith(".unarmed") or kind.startswith("jev."):
        return ("SYSTEM", f"Off: {rec.get('reason')}", None, None)
    return ("OTHER", kind, ctx, None)


class ReadableAuditLog(AuditLog):
    """An AuditLog that also writes the plain-language view. The chain
    append happens first and is unchanged."""

    def __init__(self, path: str, readable):
        self.readable = readable
        self.mirror_errors: list[str] = []
        super().__init__(path)

    def append(self, kind: str, record: dict) -> None:
        super().append(kind, record)
        try:
            d = describe(kind, record)
            if d is not None:
                cat, msg, ctx, agent = d
                self.readable.log_event(cat, msg, client_context_id=ctx, agent_id=agent)
        except Exception as e:  # the view failing must not touch the chain; counted, reported
            self.mirror_errors.append(f"{kind}: {type(e).__name__}: {e}")


def events_from_chain(audit: AuditLog, date_str: str) -> list[dict]:
    """The chain's entries for one local date, described for the ledger."""
    out = []
    for e in audit.read():
        ts = datetime.datetime.fromtimestamp(e.get("ts", 0)).strftime("%Y-%m-%d %H:%M:%S")
        if not ts.startswith(date_str):
            continue
        d = describe(e.get("kind", "?"), e)
        if d is None:
            continue
        cat, msg, ctx, agent = d
        out.append({"timestamp": ts, "category": cat, "agent_id": agent,
                    "client_context_id": ctx, "message": msg, "details": {}})
    return out


def write_eod(audit: AuditLog, readable, date_str: Optional[str] = None) -> dict:
    """Writes <log dir>/daily/eod_ledger_<date>.md from the chain and
    verifies the chain in its integrity section."""
    date_str = date_str or datetime.datetime.now().strftime("%Y-%m-%d")
    return readable.generate_eod_report(date_str, audit_log=audit,
                                        events=events_from_chain(audit, date_str))
