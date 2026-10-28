"""sweep_runner.py - the clock layer the swarm never had.

Gap named 2026-07-18: every time-based protection in this identity -
dedupe timeouts, deadline checks, no-show detection, SLA enforcement,
chase timeouts, post-close check-ins, digest flushes - was a check_*
method WAITING FOR A CALLER. Tests called them directly, so every suite
was green while a deployed swarm would never have noticed a stuck lead
or a missed showing. Real code that never ran.

This module is that caller. One entry point, run_daily_sweeps(hub,
spokes, today), walks every registered sweep against every live context.
Clock discipline is preserved: the runner never invents time - the
deployment's scheduler (cron, systemd timer, the console's own loop)
supplies `today`/`now_iso`, exactly the way tests always did. What
changes is that production now has the same caller tests had.

Every sweep runs inside a guard: one failing sweep NEVER silences the
rest (a broken check in agent 07 must not stop agent 18's no-show
detection), and every failure is declared on the audit log - never
swallowed. Results are returned per-sweep for the caller's own logging.

Wiring: SPOKE ATTRIBUTE NAMES are the contract. Each entry names the
attribute the spoke object must expose. Context discovery reads each
spoke's own state dicts - a sweep runs for the contexts its spoke
actually tracks, never a guessed universe.
"""
from __future__ import annotations


def run_daily_sweeps(hub, spokes: dict, today: str,
                     now_iso: str | None = None, live: bool = False) -> list[dict]:
    """spokes: {"01": spoke01, "06": spoke06, ...} - whichever subset is
    deployed; it names which agents receive a tick. today: ISO date from
    the deployment's scheduler. now_iso: ISO datetime for intra-day checks
    (no-show grace); defaults to today's end-of-day.

    Since 2026-10-11 (owner rule: all correspondence with an agent goes
    through the dispatcher or HITL) each agent is reached by a
    `clock -clock.tick-> agent` envelope through the hub - persisted, acked
    and on the audit log - instead of a direct method call. The checks
    themselves and their per-check error guard live in dispatcher/clock.py.
    A tick the hub does not ack is a sweep error, declared on the audit log."""
    from .clock import CHECKS, send_tick
    from .escalation_watch import check_unacknowledged, clock_skew
    now_iso = now_iso or f"{today}T23:59:59"
    results: list[dict] = []
    # Clock skew (Agent 00 tuple, owner decision 2026-10-14: 1 minute). Only
    # a live run reads the wall clock; a scripted sweep (a console line with
    # its own date, a replay) is not compared. Skewed: nothing time-triggered
    # runs, and you are asked.
    if live:
        skew = clock_skew(hub)
        if not skew["ok"]:
            hub.audit.append("clock.skew_hold", {"today": today, **skew})
            hub.queue_and_notify("clarification.request", {
                "reason": f"clock skew {skew['skew_s']}s: the audit log has entries "
                          f"stamped {skew['newest_log_time']}, this clock reads "
                          f"{skew['this_clock']} - every time-triggered check is held "
                          f"until the clocks agree",
                "client_context_id": "clock", **skew})
            return [{"agent": "00", "sweep": "clock_skew", "result": "held", **skew}]
    for agent in CHECKS:
        if agent not in spokes or not any(c[4] for c in CHECKS[agent]):
            continue
        out = send_tick(hub, agent, today, now_iso)
        status = out["hub"].get("status")
        if status != "ack":
            err = f"clock.tick to {agent} not acked: {status} {out['hub'].get('reason', '')}".strip()
            hub.audit.append("sweep.error", {"agent": agent, "sweep": "clock.tick", "error": err})
            results.append({"agent": agent, "sweep": "clock.tick", "result": None, "error": err})
            continue
        results.extend(out["results"])

    # unanswered escalations: re-alert at 30 min, page the owner at 60
    results.append({"agent": "00", "sweep": "unacknowledged_escalations",
                    "result": check_unacknowledged(hub)})
    hub.audit.append("sweep.completed",
                     {"today": today, "sweeps_run": len(results),
                      "errors": sum(1 for r in results if r.get("error"))})
    return results


def run_evening_sweep(hub, spokes: dict, today: str, now_iso: str | None = None) -> list[dict]:
    """Owner decision 9 (2026-10-21): the evening clock. Agent 14 runs the
    end-of-day books and sends them to Agent 15, which adds the day's
    figures and sends you one report. Same tick, same guard and the same
    audit trail as the daily clock."""
    from .clock import send_tick
    results: list[dict] = []
    if "14" not in spokes:
        return [{"agent": "14", "sweep": "eod_report", "result": None,
                 "error": "Agent 14 is not running - no end-of-day books"}]
    out = send_tick(hub, "14", today, now_iso or f"{today}T18:00:00", checks=["eod_report"])
    status = out["hub"].get("status")
    if status != "ack":
        err = f"clock.tick to 14 not acked: {status} {out['hub'].get('reason', '')}".strip()
        hub.audit.append("sweep.error", {"agent": "14", "sweep": "clock.tick", "error": err})
        results.append({"agent": "14", "sweep": "clock.tick", "result": None, "error": err})
    else:
        results.extend(out["results"])
    hub.audit.append("sweep.completed",
                     {"today": today, "evening": True, "sweeps_run": len(results),
                      "errors": sum(1 for r in results if r.get("error"))})
    return results


def run_quiet_hours_release(hub, spokes: dict, today: str, now_iso: str) -> list[dict]:
    """Messages Agent 11 held for quiet hours (owner decision D-A4) go out on
    the first clock run outside quiet hours. The documented daily run is at
    07:00, inside the ratified quiet hours (21:00 to 8:00), so a daily run
    alone never released them (found 2026-10-28 re-checking the manual).
    The every-few-minutes watch run and the evening run call this too; it
    sends a tick only when Agent 11 is holding something."""
    from .clock import send_tick
    s11 = spokes.get("11")
    if s11 is None or not getattr(s11, "quiet_held", None):
        return []
    out = send_tick(hub, "11", today, now_iso, checks=["quiet_hours_release"])
    status = out["hub"].get("status")
    if status != "ack":
        err = f"clock.tick to 11 not acked: {status} {out['hub'].get('reason', '')}".strip()
        hub.audit.append("sweep.error", {"agent": "11", "sweep": "clock.tick", "error": err})
        return [{"agent": "11", "sweep": "clock.tick", "result": None, "error": err}]
    return out["results"]
