"""HandoffGuard (audit TU-2, 2026-10-11): "No ack = the handoff did not
happen." Before, all 295 spoke hub.send() results were discarded."""
import importlib
import inspect
import os

import pytest

from dispatcher.core import Envelope, Routes, AuditLog
from dispatcher.handoff_guard import HandoffGuard, guard
from dispatcher.hub import Hub

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROUTES = os.path.join(ROOT, "identity", "routes.json")


def hub_at(tmp_path):
    return Hub(Routes(ROUTES), AuditLog(str(tmp_path / "audit.jsonl")))


def env(frm, to, intent, ctx="ctx-1", payload=None):
    return Envelope(from_agent=frm, to_agent=to, intent=intent, client_context_id=ctx,
                    payload=payload or {}, provenance={"source": f"spoke-{frm}", "captured_at": "runtime"})


def failures(hub):
    return [e for e in hub.audit.read() if e["kind"] == "handoff.failed"]


def test_reject_raises_handoff_failed_and_holds_for_a_human(tmp_path):
    hub = hub_at(tmp_path)
    g = guard(hub, "12")
    res = g.send(env("12", "07", "lead.reply"))            # not on the closed track
    assert res["status"] == "reject"
    [f] = failures(hub)
    assert f["agent"] == "12" and f["status"] == "reject" and f["clarification_sent"] is True
    [held] = hub.queues["clarification.request"]
    assert held["from_agent"] == "12" and held["payload"]["reason"].startswith("handoff.failed: lead.reply -> 07: reject")
    assert held["payload"]["failed_envelope"]["intent"] == "lead.reply"
    assert any(t["result"] == "held: handoff.failed" for t in hub.spoke_traces)


def test_dead_letter_no_handler_and_crash(tmp_path):
    hub = hub_at(tmp_path)
    g = guard(hub, "05")
    g.send(env("05", "18", "agent.status", payload={"waiting_on": "x"}))
    assert "no handler registered for 18" in hub.queues["clarification.request"][0]["payload"]["reason"]

    def boom(e):
        raise RuntimeError("handler broke")
    hub.register("18", boom)
    g.send(env("05", "18", "agent.status", payload={"waiting_on": "y"}))
    assert "handler broke" in hub.queues["clarification.request"][1]["payload"]["reason"]
    assert len(failures(hub)) == 2


def test_ack_and_held_pass_through_untouched(tmp_path):
    hub = hub_at(tmp_path)
    seen = []
    hub.register("18", seen.append)
    g = guard(hub, "05")
    assert g.send(env("05", "18", "agent.status", payload={"waiting_on": "x"}))["status"] == "ack"
    assert g.send(env("05", "queue", "clarification.request", payload={"reason": "r"}))["status"] == "held"
    assert failures(hub) == [] and len(hub.queues["clarification.request"]) == 1 and len(seen) == 1


def test_failed_clarification_is_recorded_without_recursion(tmp_path):
    hub = hub_at(tmp_path)
    g = guard(hub, "05")
    bad = env("05", "queue", "clarification.request", payload={"reason": "r"})
    bad.client_context_id = ""                                  # schema reject
    assert g.send(bad)["status"] == "reject"
    [f] = failures(hub)
    assert f["clarification_sent"] is False and hub.queues["clarification.request"] == []


def test_guard_forwards_the_hub_interface(tmp_path):
    hub = hub_at(tmp_path)
    g = guard(guard(hub, "01"), "02")                           # re-wrap unwraps
    assert g.unwrapped is hub and g.queues is hub.queues and g.audit is hub.audit
    g.register("02", lambda e: None)
    assert "02" in hub.handlers


def test_every_spoke_holds_a_guarded_hub(tmp_path):
    hub = hub_at(tmp_path)
    classes = []
    for mod in ["listing_spokes"] + [f"listing_spokes_{n:02d}" for n in range(2, 21) if n != 14]:
        m = importlib.import_module(f"dispatcher.{mod}")
        classes += [c for _, c in inspect.getmembers(m, inspect.isclass)
                    if c.__module__ == m.__name__ and c.__name__.startswith("Spoke")]
    assert len(classes) == 20
    for cls in classes:
        s = cls(hub)
        assert isinstance(s.hub, HandoffGuard), cls.__name__
        assert s.hub.unwrapped is hub
