"""The dispatcher checks of 2026-10-15, unit by unit (the console sessions are
tuples 00-10, 00-11, 00-14 in tests_listing/test_playbook_runs.py).

- an unacknowledged escalation is re-alerted once at 30 minutes and the
  owner paged once at 60; marking it done (the desk's Done, the console's
  ack) stops both; nothing expires it
- the escalation watch and the Broker Desk compute an item's key the same
  way, so a Done on the desk counts here
- clock skew past 60 seconds holds the time-triggered checks
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from dispatcher import escalation_watch as ew                # noqa: E402
from dispatcher.core import AuditLog, Routes                 # noqa: E402
from dispatcher.hub import Hub                               # noqa: E402

ROUTES = os.path.join(os.path.dirname(__file__), "..", "identity", "routes.json")


def _hub(tmp_path):
    pages = []
    hub = Hub(Routes(ROUTES), AuditLog(str(tmp_path / "a.jsonl")),
              human_notifier=lambda q, r: pages.append((q, r)) or {"status": "sent"})
    return hub, pages


def test_the_values_are_the_owner_decisions():
    assert (ew.REALERT_MINUTES, ew.OWNER_PAGE_MINUTES, ew.SKEW_TOLERANCE_SECONDS) == (30, 60, 60)


def test_the_watch_and_the_desk_key_an_item_the_same_way():
    import desk
    rec = {"client_context_id": "T1", "reason": "x", "n": 3}
    assert ew.key_of("escalation.complaint", rec) == desk.key_of("escalation.complaint", rec)


def test_realert_once_then_page_the_owner_once(tmp_path):
    hub, pages = _hub(tmp_path)
    hub.escalate("escalation.complaint", {"client_context_id": "T1", "reason": "upset"})
    t0 = [e for e in hub.audit.read() if e["kind"] == "escalation.raised"][0]["ts"]
    assert ew.check_unacknowledged(hub, now=t0 + 29 * 60) == {"realerted": [], "owner_paged": [], "open": 1}
    r = ew.check_unacknowledged(hub, now=t0 + 31 * 60)
    assert len(r["realerted"]) == 1 and not r["owner_paged"]
    assert not ew.check_unacknowledged(hub, now=t0 + 45 * 60)["realerted"], "re-alerted once only"
    r = ew.check_unacknowledged(hub, now=t0 + 61 * 60)
    assert len(r["owner_paged"]) == 1
    assert not ew.check_unacknowledged(hub, now=t0 + 600 * 60)["owner_paged"], "paged once only"
    assert [q for q, _ in pages].count("escalation.owner_page") == 1
    assert ew.check_unacknowledged(hub, now=t0 + 6000 * 60)["open"] == 1, "never expired by time"


def test_marking_it_done_stops_the_realert(tmp_path):
    hub, pages = _hub(tmp_path)
    hub.escalate("escalation.complaint", {"client_context_id": "T1", "reason": "upset"})
    t0 = [e for e in hub.audit.read() if e["kind"] == "escalation.raised"][0]["ts"]
    assert len(ew.acknowledge(hub, "escalation.complaint", "T1", "broker")) == 1
    assert ew.acknowledge(hub, "escalation.complaint", "T1", "broker") == [], "done once"
    r = ew.check_unacknowledged(hub, now=t0 + 90 * 60)
    assert r == {"realerted": [], "owner_paged": [], "open": 0}


def test_clock_skew_past_a_minute_is_not_ok(tmp_path):
    hub, _ = _hub(tmp_path)
    newest = max(e["ts"] for e in hub.audit.read())
    assert ew.clock_skew(hub, now=newest - 30)["ok"]
    bad = ew.clock_skew(hub, now=newest - 61)
    assert not bad["ok"] and bad["skew_s"] > 60
