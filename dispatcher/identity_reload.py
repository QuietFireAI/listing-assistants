"""Reloading the identity under live traffic (Agent 00 tuple "identity reload
requested mid-run, refuse until open runs complete or owner forces; a track
change under live traffic derails").

Before 2026-10-15 there was no way to reload the identity at all, so the
tuple had nothing to refuse. Now the console's {"do": "reload_identity"}
re-reads identity/routes.json into the running hub - but only when nothing
is in flight: no message held for your release, no thread paused for your
decision, no playbook run open. Otherwise it is refused, on the log, with
what is open. {"do": "reload_identity", "force": true} is the owner forcing
it anyway; that is on the log too, with what was open at the time.
"""
from __future__ import annotations

import os

from .core import Routes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def open_work(sw) -> dict:
    hub = sw.hub
    held = sorted(hub._absolute_holds)
    waits = [w["wait_id"] for w in sw.hitl.get_pending_waits()] if getattr(sw, "hitl", None) else []
    runs = sorted(getattr(sw, "runs", None).open_runs()) if getattr(sw, "runs", None) else []
    return {"held_messages": held, "paused_threads": waits, "open_runs": runs}


def reload_identity(sw, force: bool = False, by: str | None = None) -> dict:
    hub = sw.hub
    work = open_work(sw)
    busy = any(work.values())
    if busy and not force:
        hub.audit.append("identity.reload_refused", {"by": by, **{k: len(v) for k, v in work.items()},
                                                     "open": work})
        return {"reloaded": False,
                "reason": "open work on the track - finish or decide it first, or force",
                **{k: len(v) for k, v in work.items()}}
    path = os.path.join(ROOT, "identity", "routes.json")
    new = Routes(path)
    hub.routes = new
    hub.audit.append("identity.reloaded", {"by": by, "forced": bool(force and busy),
                                           "open_at_reload": work,
                                           "routes": len(new.entries), "version": new.version})
    return {"reloaded": True, "forced": bool(force and busy),
            **{k: len(v) for k, v in work.items()}}
