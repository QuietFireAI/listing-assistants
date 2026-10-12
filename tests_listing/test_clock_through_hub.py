"""Owner rule (2026-10-11): all correspondence with any agent, incoming or
outgoing, goes through the dispatcher or HITL. The daily clock and the
console's briefing/EOD used to call agent methods directly."""
import importlib.util
import inspect
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from test_playbooks_e2e_all import full_swarm                              # noqa: E402
from test_playbooks_e2e import spoke_env                                    # noqa: E402
from dispatcher.clock import CHECKS, send_tick                              # noqa: E402
from dispatcher.sweep_runner import run_daily_sweeps                        # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ticks(hub):
    audit = hub.audit.read()
    acks = {e["envelope_id"] for e in audit if e["kind"] == "ack"}
    return {e["to_agent"]: e["envelope_id"] in acks for e in audit
            if e["kind"] == "envelope.persisted" and e["intent"] == "clock.tick"}


def test_daily_sweeps_reach_every_agent_through_the_hub(tmp_path):
    hub, _signer, spokes, _ext = full_swarm(str(tmp_path))
    hub.on_turn_start()
    run_daily_sweeps(hub, spokes, today="2026-08-05")
    daily = {a for a, checks in CHECKS.items() if any(c[4] for c in checks)}
    seen = ticks(hub)
    assert set(seen) == daily and all(seen.values())
    for e in hub.audit.read():
        if e["kind"] == "envelope.persisted" and e["intent"] == "clock.tick":
            assert e["from_agent"] == "clock"


def test_only_the_clock_may_send_a_tick(tmp_path):
    hub, _signer, _spokes, _ext = full_swarm(str(tmp_path))
    res = hub.send(spoke_env("11", "07", "clock.tick", "x", {"today": "2026-08-05"}))
    assert res["status"] == "reject" and "tuple illegal" in res["reason"]


def test_on_demand_eod_report_runs_only_when_named(tmp_path):
    hub, _signer, _spokes, _ext = full_swarm(str(tmp_path))
    out = send_tick(hub, "14", "2026-08-05")
    assert out["hub"]["status"] == "ack" and out["results"] == []
    out = send_tick(hub, "14", "2026-08-05", checks=["eod_report"])
    assert out["hub"]["status"] == "ack" and out["results"][0]["sweep"] == "eod_report"


def test_sweep_runner_and_console_call_no_agent_methods_directly():
    for rel in ("dispatcher/sweep_runner.py", "tools/console.py", "tools/run_sweeps.py"):
        src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        assert not re.search(r"spokes\[\"\d\d\"\]\.\w+\(", src), rel
        assert not re.search(r"\bs\d\d\.\w+\(", src), rel


# --- added after the post-fix mutation run (2026-10-11) ----------------------

def test_document_chase_runs_per_doc_type_through_the_tick(tmp_path):
    hub, _signer, spokes, _ext = full_swarm(str(tmp_path))
    spokes["08"].pending_requests["ctx-docs"] = {"appraisal": {"chase_count": 0},
                                                 "inspection": {"chase_count": 0}}
    out = send_tick(hub, "08", "2026-08-05")
    assert out["hub"]["status"] == "ack"
    # J4 (2026-10-12) added 08's daily disclosure check, once per context
    assert [r["sweep"] for r in out["results"]] == ["chase_timeout", "chase_timeout",
                                                     "disclosure_deadline"]
    assert not any(r.get("error") for r in out["results"])
    assert spokes["08"].pending_requests["ctx-docs"]["appraisal"]["chase_count"] == 1
    assert spokes["08"].pending_requests["ctx-docs"]["inspection"]["chase_count"] == 1


def test_named_check_runs_alone_and_returns_its_report(tmp_path):
    hub, _signer, spokes, _ext = full_swarm(str(tmp_path))
    out = send_tick(hub, "18", "2026-08-05", checks=["morning_briefing"])
    assert [r["sweep"] for r in out["results"]] == ["morning_briefing"]
    assert out["results"][0]["result"]["briefing_type"] == "morning"
    out = send_tick(hub, "14", "2026-08-05", checks=["eod_report"])
    assert out["results"][0]["result"]["report_type"] == "eod" and "error" not in out["results"][0]


def test_both_daily_checks_of_one_agent_run(tmp_path):
    hub, _signer, spokes, _ext = full_swarm(str(tmp_path))
    spokes["07"].timelines["ctx-t"] = {}
    out = send_tick(hub, "07", "2026-08-05")
    assert {r["sweep"] for r in out["results"]} == {"deadlines", "vendor_holdups"}


def test_now_iso_reaches_the_check_and_defaults_to_end_of_day(tmp_path):
    from dispatcher.clock import handle_tick
    from dispatcher.core import Envelope
    seen = []

    class Fake18:
        def __init__(self, hub):
            self.hub = hub
            self.showings = {"ctx-s": {}}

        def check_showing_no_show(self, ctx, now_iso):
            seen.append(now_iso)

        def generate_briefing(self, kind):
            return {}

    hub, *_ = full_swarm(str(tmp_path))
    spoke = Fake18(hub)
    for payload, want in (({"today": "2026-08-05"}, "2026-08-05T23:59:59"),
                          ({"today": "2026-08-05", "now_iso": "2026-08-05T10:30:00"}, "2026-08-05T10:30:00")):
        env = Envelope(from_agent="clock", to_agent="18", intent="clock.tick", client_context_id="c",
                       payload=payload, provenance={"source": "clock"})
        handle_tick(spoke, "18", env)
    assert seen == ["2026-08-05T23:59:59", "2026-08-05T10:30:00"]
    # sweep_runner passes its now_iso through, and defaults it to end of day
    sent = []
    real = hub.send
    hub.send = lambda env: (sent.append(env.payload) if env.intent == "clock.tick" else None) or real(env)
    run_daily_sweeps(hub, {"18": object()}, today="2026-08-06", now_iso="2026-08-06T09:00:00")
    run_daily_sweeps(hub, {"18": object()}, today="2026-08-07")
    assert [p["now_iso"] for p in sent] == ["2026-08-06T09:00:00", "2026-08-07T23:59:59"]


def test_check_error_text_is_recorded(tmp_path):
    hub, _signer, spokes, _ext = full_swarm(str(tmp_path))
    spokes["17"].pending_reviews["ctx-x"] = {}
    spokes["17"].check_sla = lambda ctx, today: (_ for _ in ()).throw(RuntimeError("sla boom"))
    out = send_tick(hub, "17", "2026-08-05")
    assert out["results"][0]["error"] == "sla boom"
    errs = [e for e in hub.audit.read() if e["kind"] == "sweep.error"]
    assert errs and errs[-1]["agent"] == "17" and "RuntimeError: sla boom" in errs[-1]["error"]


def test_unacked_tick_is_a_declared_error_and_others_still_run(tmp_path):
    hub, _signer, spokes, _ext = full_swarm(str(tmp_path))
    real = hub.send

    def send(env):
        if env.intent == "clock.tick" and env.to_agent == "01":
            return {"status": "reject", "reason": "simulated"}
        return real(env)
    hub.send = send
    results = run_daily_sweeps(hub, {"01": spokes["01"], "18": spokes["18"]}, today="2026-08-05")
    tick_err = [r for r in results if r["sweep"] == "clock.tick"]
    assert tick_err == [{"agent": "01", "sweep": "clock.tick", "result": None,
                         "error": "clock.tick to 01 not acked: reject simulated"}]
    assert any(r["agent"] == "18" and r["sweep"] == "morning_briefing" for r in results)
    audit = hub.audit.read()
    assert [e for e in audit if e["kind"] == "sweep.error"][-1]["error"] == tick_err[0]["error"]
    done = [e for e in audit if e["kind"] == "sweep.completed"][-1]
    assert done["errors"] == 1 and done["sweeps_run"] == len(results)
