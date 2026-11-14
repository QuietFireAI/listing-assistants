"""The hub's loop limit counts within one cascade, not for the life of the
install (2026-11-13).

Found in review: loop_counts counted every (client_context_id, intent) for
the life of the install and was saved with the state. Agent 18 sends the
morning briefing on the one context "briefing" every day (4 briefing.request
and 5 report.package a day), so the daily clock suspended the briefing from
day 5 and every day after; a buyer file (S8-buyerC, agent.status) was
suspended the same way after 60 days of the clock on the operator scenes.

A loop is the same message repeating inside one chain of reactions (the
04/17 flag bounce of test_wiring_2026_10_12). The count now covers the
outermost send() and every send nested in its delivery, and starts again
with the next outermost send()."""
import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dispatcher.core import AuditLog, Envelope, Routes
from dispatcher.hub import Hub

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROUTES = os.path.join(ROOT, "identity", "routes.json")


def _env(frm, to, intent, ctx, payload=None):
    return Envelope(from_agent=frm, to_agent=to, intent=intent, client_context_id=ctx,
                    payload=payload or {}, provenance={"source": "test", "captured_at": "runtime"})


def _hub(tmp_path):
    return Hub(Routes(ROUTES), AuditLog(str(tmp_path / "loop.jsonl")))


def _kinds(hub, kind):
    return [e for e in hub.audit.read() if e.get("kind") == kind]


def test_the_morning_briefing_reaches_you_every_day_for_30_days(tmp_path):
    from dispatcher.swarm import build_swarm
    from dispatcher.sweep_runner import run_daily_sweeps
    sw = build_swarm(str(tmp_path / "a.jsonl"))
    day0 = datetime.date(2026, 12, 1)
    days = [(day0 + datetime.timedelta(days=i)).isoformat() for i in range(30)]
    for today in days:
        run_daily_sweeps(sw.hub, sw.spokes, today)
    assert _kinds(sw.hub, "loop.suspended") == []
    delivered = {e["payload"]["today"] for e in _kinds(sw.hub, "envelope.persisted")
                 if e["intent"] == "report.package" and e["from_agent"] == "18"
                 and e["to_agent"] == "human" and e["client_context_id"] == "briefing"
                 and e["payload"].get("briefing_type") == "morning"}
    assert delivered == set(days)
    acked = {e["envelope_id"] for e in _kinds(sw.hub, "ack")}
    briefings = [e for e in _kinds(sw.hub, "envelope.persisted")
                 if e["intent"] == "report.package" and e["to_agent"] == "human"
                 and e["client_context_id"] == "briefing"]
    assert briefings and all(e["envelope_id"] in acked for e in briefings)


def test_a_long_running_file_is_not_suspended_by_separate_messages(tmp_path):
    hub = _hub(tmp_path)
    hub.register("17", lambda env: None)
    out = [hub.send(_env("04", "17", "content.review", "S8-buyerC", {"n": i}))
           for i in range(hub.loop_threshold + 15)]
    assert [r["status"] for r in out] == ["ack"] * (hub.loop_threshold + 15)
    assert _kinds(hub, "loop.suspended") == []


def test_a_loop_inside_one_cascade_is_still_suspended(tmp_path):
    """Two agents bouncing a review and a verdict inside one delivery: the
    hub stops it at the threshold, as before."""
    hub = _hub(tmp_path)
    seen = {"review": 0}

    def a17(env):
        seen["review"] += 1
        hub.send(_env("17", "04", "content.verdict", env.client_context_id, {"verdict": "flagged"}))

    def a04(env):
        hub.send(_env("04", "17", "content.review", env.client_context_id, {"draft": "again"}))

    hub.register("17", a17)
    hub.register("04", a04)
    first = hub.send(_env("04", "17", "content.review", "C1", {"draft": "first"}))
    assert first["status"] == "ack"
    susp = _kinds(hub, "loop.suspended")
    assert len(susp) == 1 and susp[0]["count"] == hub.loop_threshold + 1
    assert susp[0]["client_context_id"] == "C1"
    assert seen["review"] == hub.loop_threshold
    assert any(q["client_context_id"] == "C1" for q in hub.queues["clarification.request"])
    # the next cascade starts its own count
    hub.register("17", lambda env: None)
    assert hub.send(_env("04", "17", "content.review", "C1", {"draft": "fixed"}))["status"] == "ack"


def test_counts_restored_from_an_older_save_do_not_suspend_the_next_message(tmp_path):
    hub = _hub(tmp_path)
    hub.register("17", lambda env: None)
    hub.loop_counts[("briefing", "content.review")] = 500   # as an older save left it
    assert hub.send(_env("04", "17", "content.review", "briefing"))["status"] == "ack"
    assert _kinds(hub, "loop.suspended") == []
