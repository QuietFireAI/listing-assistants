"""clock - time-based checks delivered through the dispatcher.

Owner rule (2026-10-11): all correspondence with any agent, incoming or
outgoing, goes through the dispatcher or HITL. Before this module the daily
clock (`sweep_runner.run_daily_sweeps`) and the console's "show briefing /
eod" called agent methods directly, so those runs never crossed the hub and
never appeared on the audit log as messages.

Now the clock is a sender on the closed track: `clock -clock.tick-> agent`
(identity/routes.json). The hub validates, persists and acks each tick like
any other envelope. The receiving agent hands the tick to `handle_tick`,
which runs that agent's checks for the contexts it tracks.

Tick payload:
  {"today": "YYYY-MM-DD", "now_iso": "...", "checks": [names] (optional)}
Without "checks", an agent runs its daily checks (CHECKS entries with
daily=True). On-demand checks (the EOD report) run only when named.

Each check runs inside a guard: one failing check never stops the others,
and every failure is appended to the audit log as `sweep.error`. Results
are kept for the sender by envelope id (`take_results`), because a hub ack
carries no payload.
"""
from __future__ import annotations

from typing import Any

# agent -> [(check name, method, context source, args, daily)]
#   context source: attribute holding the contexts to walk, None = run once
#   args: names resolved from the tick ("ctx", "today", "now_iso", "doc_type")
CHECKS: dict[str, list[tuple]] = {
    "01": [("record_response_timeout", "check_record_response_timeout", "pending", ("ctx", "today"), True)],
    "03": [("nurture_touches", "send_due_touches", "active_sequences", ("ctx", "today", "now_iso"), True)],
    "06": [("showing_feedback", "request_showing_feedback", "confirmed_showings", ("ctx", "today"), True)],
    "07": [("deadlines", "check_deadlines", "timelines", ("ctx", "today"), True),
           ("vendor_holdups", "check_vendor_holdups", "timelines", ("ctx", "today"), True)],
    "08": [("chase_timeout", "check_chase_timeout", "pending_requests", ("ctx", "doc_type"), True)],
    "13": [("match_digest_flush", "flush_match_digest", "matches_today", ("ctx",), True)],
    "14": [("eod_report", "generate_report", None, ("eod",), False),
           ("date_triggers", "check_client_dates", "client_dates", ("ctx", "today"), True)],
    "16": [("post_close_milestones", "check_post_close_milestones", "closed_transactions", ("ctx", "today"), True)],
    "17": [("review_sla", "check_sla", "pending_reviews", ("ctx", "today"), True)],
    "18": [("showing_no_show", "check_showing_no_show", "showings", ("ctx", "now_iso"), True),
           ("morning_briefing", "generate_briefing", None, ("morning",), True)],
}

TICK_INTENT = "clock.tick"
CLOCK_SENDER = "clock"

_RESULTS: dict[str, list[dict]] = {}


def take_results(envelope_id: str) -> list[dict]:
    return _RESULTS.pop(envelope_id, [])


def handle_tick(spoke: Any, agent_id: str, env: Any) -> None:
    """Called from an agent's handle() for intent clock.tick."""
    payload = env.payload or {}
    today = payload.get("today")
    now_iso = payload.get("now_iso") or (f"{today}T23:59:59" if today else None)
    wanted = payload.get("checks")
    results: list[dict] = []
    hub = spoke.hub

    def run(name, fn, *args):
        try:
            results.append({"agent": agent_id, "sweep": name, "result": fn(*args)})
        except Exception as exc:  # one broken check never silences the rest
            hub.audit.append("sweep.error", {"agent": agent_id, "sweep": name,
                                             "error": f"{type(exc).__name__}: {exc}"})
            results.append({"agent": agent_id, "sweep": name, "result": None, "error": str(exc)})

    for name, method, source, argnames, daily in CHECKS.get(agent_id, []):
        if (wanted is None and not daily) or (wanted is not None and name not in wanted):
            continue
        fn = getattr(spoke, method)
        if source is None:
            run(name, fn, *argnames)
            continue
        state = getattr(spoke, source, {}) or {}
        for ctx in list(state):
            if "doc_type" in argnames:
                for doc_type in list(state.get(ctx, {})):
                    run(name, fn, ctx, doc_type)
                continue
            vals = {"ctx": ctx, "today": today, "now_iso": now_iso}
            run(name, fn, *[vals[a] for a in argnames])
    _RESULTS[env.envelope_id] = results


def send_tick(hub: Any, agent_id: str, today: str, now_iso: str | None = None,
              checks: list[str] | None = None) -> dict:
    """Sends one clock.tick through the hub and returns
    {"hub": <hub result>, "results": [...]}."""
    from .core import Envelope
    payload = {"today": today, "now_iso": now_iso or f"{today}T23:59:59"}
    if checks is not None:
        payload["checks"] = list(checks)
    env = Envelope(from_agent=CLOCK_SENDER, to_agent=agent_id, intent=TICK_INTENT,
                   client_context_id=f"clock-{today}-{agent_id}", payload=payload,
                   provenance={"source": "clock", "captured_at": "runtime"})
    res = hub.send(env)
    return {"hub": res, "results": take_results(env.envelope_id)}
