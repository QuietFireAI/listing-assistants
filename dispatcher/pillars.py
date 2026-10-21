"""Pillar wiring (five pillars since 2026-10-20) - the detection tier running IN the runtime.

Every pillar is imported from its own package in dispatcher/pillar_lib/
(owner decision 2026-10-20: one product, the pillars folded in from their
repositories at the commits the suite last passed; see
dispatcher/pillar_lib/README.md). They are never re-implemented here.
Each binds to a named seam:

  before-turn              -> Hub.on_turn_start (turn entry)
  open-mind                -> analysis.analyze_reflections (hub thought-vs-action)
  agent-open-mind          -> Hub.ingest_spoke_trace taint gate (spoke entry)
  pre-response-selfcheck   -> exit gate on outbound deliveries
  sleep-marks              -> territory transfer (crew change)

One pillar (pre-response-selfcheck) needs a reviewer model to run its
check; that is deployment configuration. UNARMED IS AUDITED, never
silent: a gate that is off says so on the log. splitvantage, the sixth,
was removed by owner decision 2026-10-20.
"""
from __future__ import annotations

from .pillar_lib.before_turn import BEFORE_TURN_QUESTIONS
from .pillar_lib.sleep_marks.marker import SleepMark
from .pillar_lib.pre_response_selfcheck.reader_shift import ReaderShift


# ------------------------------------------------------------- before-turn
def before_turn_check(hub, last_n: int = 3) -> dict:
    """Pillar contract at turn entry: re-read your own recent thinking, then
    answer the check questions before acting. The hub's 'recent thinking' is
    its reflection artifacts; the questions come from the pillar package."""
    recent = [a["thought"] for a in hub.reflection_artifacts[-last_n:]]
    rec = {"thoughts_reviewed": len(recent),
           "questions": list(BEFORE_TURN_QUESTIONS),
           "recent_thoughts": recent}
    hub.audit.append("beforeturn.check", rec)
    return rec


# --------------------------------------------------- pre-response-selfcheck
def exit_gate(hub, env, model=None, audience: str = "cold_reader"):
    """Reader-shift exit gate on an outbound envelope's human-facing text.
    With a model: run the pillar's check; FAIL verdict -> envelope held in
    clarification (never delivered), verdict audited with the flagged line.
    Without a model: the gate is UNARMED and says so on the log."""
    text = " ".join(str(v) for v in env.payload.values() if isinstance(v, str))
    if model is None:
        hub.audit.append("selfcheck.unarmed",
                         {"envelope_id": env.envelope_id,
                          "reason": "no reviewer model configured - gate off, "
                                    "declared not silent"})
        return {"armed": False, "passed": None}
    verdict = ReaderShift.check(text or "(no text payload)",
                                audience=audience, model=model)
    rec = {"envelope_id": env.envelope_id, "passed": verdict.passed,
           "line": verdict.line, "fix": verdict.suggested_fix,
           "audience": audience}
    hub.audit.append("selfcheck.verdict", rec)
    if not verdict.passed:
        hub.queue_and_notify(
            "clarification.request",
            {**env.to_record(), "held_by": "pre-response-selfcheck",
             "flagged_line": verdict.line})
    return {"armed": True, **rec}


# -------------------------------------------------------------- sleep-marks
def capture_sleepmark(hub, context_summary: str) -> dict:
    """Crew change: capture the hub's reasoning state as a SleepMark. Open
    questions = what is actually unresolved on the queues; reasoning traces
    = the hub's own recent reflections. Constructed from log-backed state,
    never from memory of prior sessions."""
    open_q = [f"{q}: {len(items)} open item(s)"
              for q, items in hub.queues.items() if items]
    traces = [{"step": i, "thinking": a["thought"]}
              for i, a in enumerate(hub.reflection_artifacts[-5:])]
    mark = SleepMark(conversation_id="hub",
                     context_summary=context_summary,
                     reasoning_traces=traces,
                     open_questions=open_q,
                     reflection_text=context_summary)
    rec = {"context_summary": context_summary,
           "open_questions": open_q, "traces": len(traces)}
    hub.audit.append("sleepmark.captured", rec)
    return {"mark": mark.__dict__, **rec}


def restore_sleepmark(hub, mark: dict) -> dict:
    hub.audit.append("sleepmark.restored",
                     {"context_summary": mark.get("context_summary"),
                      "open_questions": mark.get("open_questions", [])})
    return mark
