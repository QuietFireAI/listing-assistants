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
        src = open(os.path.join(ROOT, rel)).read()
        assert not re.search(r"spokes\[\"\d\d\"\]\.\w+\(", src), rel
        assert not re.search(r"\bs\d\d\.\w+\(", src), rel
