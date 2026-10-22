"""agent-open-mind importable core.

The CLI (scripts/) reads sub-agent minds interactively. This module is the
same principle as a library, for runtimes (the TelsonBase dispatcher imports
it): Absent Thoughts = Tainted Result.
"""

TAINT_PRINCIPLE = ("A sub-agent result whose thinking trace is absent is "
                   "tainted: flagged for review, never silently admitted, "
                   "never scored as if a trace existed.")


def taint_check(trace: dict) -> dict:
    """Gate a spoke trace. trace: {agent, envelope_id, thought, result}.
    Returns {tainted: bool, reason: str|None}. Fail-closed on absence."""
    thought = (trace.get("thought") or "").strip()
    if not thought:
        return {"tainted": True,
                "reason": "absent thought trace - tainted result, "
                          "held for review (agent-open-mind gate)"}
    return {"tainted": False, "reason": None}
