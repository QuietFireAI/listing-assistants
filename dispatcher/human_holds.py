"""human_holds - one way for an agent to stop and wait for the broker.

Owner rule (2026-10-11): all correspondence goes through the dispatcher or
a human; where an agent cannot proceed on its own it holds the whole thread
and waits for the broker to CONTINUE or CANCEL it.

hold_for_human() pauses through the HITL manager the swarm wires as
hub.hitl (dispatcher/swarm.py): the wait is announced to Agent 18, traced
on the audit chain and pushed to the human channel. Nothing more happens on
that thread until the broker signs a hitl.decision.authority:

    continue -> decision APPROVE (or APPROVE_WITH_OVERRIDE carrying the one
                field the hold asks for, e.g. route_to)
    cancel   -> decision REJECT_AND_ABORT

and the HITL manager calls the holding agent's resumption handler, which
does exactly what the hold says it will. A hub without a HITL manager
(single-agent unit tests) gets a clarification.request instead, which says
in so many words that nothing in that process can resume it.
"""
from __future__ import annotations

from typing import Any

from .core import Envelope

REQUIRED_DECISION = "CONTINUE_OR_CANCEL"
CONTINUE_DECISIONS = frozenset({"APPROVE", "APPROVE_AS_IS", "APPROVE_WITH_OVERRIDE",
                                "CONTINUE_WITH_UPDATE"})
CANCEL_DECISIONS = frozenset({"REJECT", "REJECT_AND_ABORT"})


def hold_for_human(hub: Any, agent_id: str, ctx: str, paused_intent: str,
                   reason: str, payload: dict) -> dict:
    """Returns {"held": wait_id} or {"held": None, "clarification": result}."""
    hitl = getattr(hub, "hitl", None)
    if hitl is None:
        res = hub.send(Envelope(
            from_agent=agent_id, to_agent="queue", intent="clarification.request",
            client_context_id=ctx,
            payload={"reason": reason, "held": payload,
                     "note": "no HITL manager in this process - this hold cannot be "
                             "continued or cancelled here"},
            provenance={"source": f"spoke-{agent_id}", "captured_at": "runtime",
                        "verbatim_available": True}))
        return {"held": None, "clarification": res}
    ws = hitl.pause_operation(ctx, agent_id, paused_intent, reason, payload,
                              required_decision=REQUIRED_DECISION)
    return {"held": ws.wait_id}


def decision_of(payload: dict) -> str:
    """'continue', 'cancel' or 'other' for a resumption handler."""
    d = str((payload or {}).get("decision", "")).upper()
    if d in CONTINUE_DECISIONS:
        return "continue"
    if d in CANCEL_DECISIONS:
        return "cancel"
    return "other"


def register_resumer(hub: Any, agent_id: str, handler) -> None:
    """Registers handler(wait_state, decision_payload) for this agent's holds,
    when the swarm wired a HITL manager."""
    hitl = getattr(hub, "hitl", None)
    if hitl is not None:
        hitl.register_resumption_handler(agent_id, handler)
