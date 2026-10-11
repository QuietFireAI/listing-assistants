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
                     now_iso: str | None = None) -> list[dict]:
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
    now_iso = now_iso or f"{today}T23:59:59"
    results: list[dict] = []
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

    hub.audit.append("sweep.completed",
                     {"today": today, "sweeps_run": len(results),
                      "errors": sum(1 for r in results if r.get("error"))})
    return results
