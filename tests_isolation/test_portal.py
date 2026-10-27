"""Agent isolation V1 (owner decisions 2026-10-26): every agent alone behind
its portal, the dispatcher the only way through.

These tests run the real pieces: the swarm with each agent in its own
process on its own Unix socket (dispatcher/portal_dispatcher.py), and, for
the violations, a rogue program on one agent's line that tries what a
broken or tampered agent might. Each violation must be refused, recorded,
stop that agent, and raise an alert carrying this system's id and an error
code to look up on the record.

The same check over every playbook and tuple (all identical records in both
modes) is run by synth/tuples/run_tuples.py with LISTINGASSISTANTS_PORTAL=
process; test_portal_mode_playbooks below runs two playbooks that way in CI.
"""
import os
import socket
import struct
import sys
import tempfile
import threading
import time

import pytest

if os.name == "nt":
    pytest.skip("agent portals use Unix sockets (Linux containers, the NAS)",
                allow_module_level=True)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dispatcher.core import Envelope  # noqa: E402
from dispatcher.portal import (DISPATCHER_TO_AGENT, MAX_FRAME, Peer,  # noqa: E402
                               PortalError, RemoteError)
from dispatcher.portal_agent import AgentHub, connect  # noqa: E402
from dispatcher.portal_dispatcher import RemoteSpoke, process_launcher  # noqa: E402
from dispatcher.swarm import build_swarm  # noqa: E402


def _env(frm, to, intent, ctx, payload):
    return Envelope(from_agent=frm, to_agent=to, intent=intent, client_context_id=ctx,
                    payload=payload, provenance={"source": frm, "captured_at": "runtime"})


def _swarm(tmp, rogue=None, call_timeout_s=120.0):
    """rogue: (agent id, behaviour(peer, envelope)) runs that agent as a
    rogue program on its line; every other agent is the real one."""
    short = tempfile.mkdtemp(prefix="la-p-")        # Unix socket paths must stay short
    real = process_launcher(sys.executable, ROOT)

    def launch(aid, path):
        if rogue is not None and aid == rogue[0]:
            t = threading.Thread(target=_rogue, args=(path, aid, rogue[1]), daemon=True)
            t.start()
            return t
        return real(aid, path)
    return build_swarm(os.path.join(tmp, "audit.jsonl"),
                       portal={"sockets_dir": short, "launcher": launch,
                               "call_timeout_s": call_timeout_s})


def _rogue(path, aid, behaviour):
    peer = Peer(connect(path), {}, DISPATCHER_TO_AGENT, name=f"rogue {aid}")
    peer.handlers = {
        "init": lambda agent_id, kwargs: {"registered": [aid], "resumers": [], "state": {"n": 0}},
        "deliver": lambda envelope: {"result": behaviour(peer, envelope),
                                     "tick_results": [], "state": None},
        "state": lambda: {"n": 0},
        "restore": lambda attrs: {"restored": sorted(attrs), "state": None},
    }
    try:
        peer.serve_forever()
    except PortalError:
        pass


def _kinds(sw):
    return [e["kind"] for e in sw.hub.audit.read()]


def _entries(sw, kind):
    return [e for e in sw.hub.audit.read() if e["kind"] == kind]


MENTION = {"channel": "social", "text": "nice house"}


def test_agents_run_alone_and_a_lead_goes_through(tmp_path):
    sw = _swarm(str(tmp_path))
    try:
        assert all(isinstance(s, RemoteSpoke) for s in sw.spokes.values())
        assert sorted(sw.team.processes) == sorted(sw.spokes)
        pids = {p.pid for p in sw.team.processes.values()}
        assert len(pids) == 20 and os.getpid() not in pids
        r = sw.hub.send(_env("external", "01", "lead.inbound", "L-1",
                             {"channel": "web_form", "name": "Pat", "email": "p@x.test",
                              "consent": {"email": "yes"}, "message": "is 12 Oak available?"}))
        assert r["status"] == "ack"
        assert "L-1" in dict(sw.spokes["01"].pending) or _entries(sw, "drawer.filed")
        assert not [k for k in _kinds(sw) if k in ("portal.violation", "portal.agent_stopped")]
        assert _entries(sw, "portal.team")[0]["system_id"].startswith("LA-")
    finally:
        sw.close()


def test_an_agent_cannot_speak_as_another(tmp_path):
    def act(peer, env):
        peer.call("send", {"envelope": _env("13", "02", "lead.captured", "X", {})})
    sw = _swarm(str(tmp_path), rogue=("20", act))
    try:
        sw.hub.send(_env("external", "20", "social.mention", "M-1", MENTION))
        [v] = _entries(sw, "portal.violation")
        assert v["agent"] == "20" and v["violation"] == "impersonation"
        [stop] = _entries(sw, "portal.agent_stopped")
        assert stop["code"].startswith("V20-") and stop["system_id"].startswith("LA-")
        [alert] = sw.hub.queues["portal.violation"]
        assert alert["alert_code"] == stop["code"] and alert["system_id"] == stop["system_id"]
        # the message from "13" never reached the hub
        assert not [e for e in _entries(sw, "envelope.persisted") if e.get("from_agent") == "13"]
        # stopped: the next message to 20 waits for a person, nothing reaches it
        r = sw.hub.send(_env("external", "20", "social.mention", "M-2", MENTION))
        assert r["status"] == "dead.letter" and "stopped" in r["reason"]
    finally:
        sw.close()


def test_a_route_not_on_the_track_stops_the_agent(tmp_path):
    def act(peer, env):
        # 20 is not a sender of lead.captured (identity/routes.json)
        return peer.call("send", {"envelope": _env("20", "02", "lead.captured", "X", {})})
    sw = _swarm(str(tmp_path), rogue=("20", act))
    try:
        sw.hub.send(_env("external", "20", "social.mention", "M-1", MENTION))
        [v] = _entries(sw, "portal.violation")
        assert v["violation"] == "route_not_on_track" and "lead.captured" in v["detail"]
        assert [e for e in _entries(sw, "reject") if "tuple illegal" in e["reason"]]
        assert "20" in sw.team.stopped
    finally:
        sw.close()


def test_an_unknown_kind_of_message_is_held_and_stops_the_agent(tmp_path):
    def act(peer, env):
        return peer.call("send", {"envelope": _env("20", "external", "contacts.export", "X", {})})
    sw = _swarm(str(tmp_path), rogue=("20", act))
    try:
        sw.hub.send(_env("external", "20", "social.mention", "M-1", MENTION))
        assert _entries(sw, "hold.clarification")          # held for a person, never sent
        [v] = _entries(sw, "portal.violation")
        assert v["violation"] == "route_not_on_track"
        assert "20" in sw.team.stopped
    finally:
        sw.close()


@pytest.mark.parametrize("ask,violation", [
    (lambda p: p.call("read_key", {}), "off_menu"),
    (lambda p: p.call("decide", {"client_context_id": "X", "payload": {}, "rubric": {},
                                 "confidence_threshold": 0.5, "allow_external": True}), "off_menu"),
    (lambda p: p.call("log_note", {"kind": "state.saved", "data": {}}), "record_kind"),
    (lambda p: p.call("trace", {"agent_id": "05", "envelope_id": "e", "thought": "t",
                                "result": "r"}), "impersonation"),
])
def test_off_menu_asks_are_refused_and_stop_the_agent(tmp_path, ask, violation):
    seen = {}

    def act(peer, env):
        try:
            ask(peer)
        except RemoteError as e:
            seen["refused"] = str(e)
    sw = _swarm(str(tmp_path), rogue=("20", act))
    try:
        sw.hub.send(_env("external", "20", "social.mention", "M-1", MENTION))
        assert seen.get("refused")
        [v] = _entries(sw, "portal.violation")
        assert v["violation"] == violation
        assert "20" in sw.team.stopped
        assert "state.saved" not in _kinds(sw)
    finally:
        sw.close()


def test_a_crash_stops_the_agent_and_holds_the_message(tmp_path):
    def act(peer, env):
        peer.sock.shutdown(socket.SHUT_RDWR)                # the agent dies mid-message
        peer.close()
    sw = _swarm(str(tmp_path), rogue=("20", act))
    try:
        r = sw.hub.send(_env("external", "20", "social.mention", "M-1", MENTION))
        assert r["status"] == "dead.letter"
        [stop] = _entries(sw, "portal.agent_stopped")
        assert stop["stopped_for"] == "crash" and stop["held_envelope_id"] == r["envelope_id"]
        assert sw.hub.queues["portal.crash"][0]["alert_code"].startswith("C20-")
        assert sw.hub.queues["dead.letter"]
        assert not _entries(sw, "portal.violation")         # a crash is not a violation
    finally:
        sw.close()


def test_an_agent_that_does_not_answer_in_time_is_stopped(tmp_path):
    def act(peer, env):
        time.sleep(3)
    sw = _swarm(str(tmp_path), rogue=("20", act), call_timeout_s=1.0)
    try:
        r = sw.hub.send(_env("external", "20", "social.mention", "M-1", MENTION))
        assert r["status"] == "dead.letter"
        [stop] = _entries(sw, "portal.agent_stopped")
        assert stop["stopped_for"] == "crash" and "in time" in stop["reason"]
    finally:
        sw.close()


def test_clearing_a_stopped_agent_restarts_it_with_its_state(tmp_path):
    sw = _swarm(str(tmp_path))
    try:
        sw.hub.send(_env("external", "01", "lead.inbound", "L-1",
                         {"channel": "web_form", "name": "Pat", "email": "p@x.test",
                          "consent": {"email": "yes"}}))
        before = sw.spokes["01"].__portal_state__()
        sw.team.violation("01", "test", "stopped by the test")
        assert "01" in sw.team.stopped
        old = sw.team.processes["01"]
        out = sw.team.clear("01", by="jeff@example.test")
        assert out["ok"] and "01" not in sw.team.stopped
        assert sw.team.processes["01"].pid != old.pid
        assert sw.spokes["01"].__portal_state__() == before
        r = sw.hub.send(_env("external", "01", "lead.inbound", "L-2",
                             {"channel": "web_form", "name": "Sam", "email": "s@x.test",
                              "consent": {"email": "yes"}}))
        assert r["status"] == "ack"
        assert _entries(sw, "portal.agent_cleared")[0]["by"] == "jeff@example.test"
    finally:
        sw.close()


def test_the_dispatcher_cannot_change_an_agents_memory_by_accident(tmp_path):
    sw = _swarm(str(tmp_path))
    try:
        with pytest.raises(TypeError):
            sw.spokes["18"].waiting["x"] = {}               # a copy: refused, not silently ignored
    finally:
        sw.close()


def test_an_agent_sees_only_the_menu():
    hub = AgentHub(None, "05")
    for name in ("drawers", "routes", "queues", "unwrapped", "signer", "audit._prev"):
        with pytest.raises(AttributeError, match="not on the portal menu"):
            obj = hub
            for part in name.split("."):
                obj = getattr(obj, part)
    with pytest.raises(AttributeError):
        hub.anything = 1


def test_a_frame_over_the_limit_cuts_the_line():
    a, b = socket.socketpair()
    peer = Peer(a, {}, DISPATCHER_TO_AGENT, name="test")
    b.sendall(struct.pack(">I", MAX_FRAME + 1))
    with pytest.raises(PortalError, match="over the limit"):
        peer.serve_forever()
    assert peer.closed
    b.close()


def test_the_page_carries_the_system_id_and_code_only():
    from dispatcher.pager import page_text
    t = page_text("portal.violation", {"client_context_id": "portal", "agent": "05",
                                       "alert_code": "V05-1A2B3C", "system_id": "LA-ABC123"})
    assert t == ("ListingAssistants LA-ABC123: portal.violation V05-1A2B3C. "
                 "Agent 05 is stopped until you clear it.")


@pytest.mark.parametrize("pb", ["P01", "P14"])
def test_portal_mode_playbooks(pb, monkeypatch):
    """The same playbook, agents in their own processes: it passes and the
    record matches the one-process run line for line."""
    sys.path.insert(0, os.path.join(ROOT, "synth", "tuples"))
    import json
    import run_tuples
    wd = tempfile.mkdtemp(prefix="la-pm-")
    tpl = run_tuples.make_template(wd)
    [spec] = run_tuples.load_specs([pb], spec_set="playbooks")
    monkeypatch.delenv("LISTINGASSISTANTS_PORTAL", raising=False)
    os.makedirs(os.path.join(wd, "a"))
    os.makedirs(os.path.join(wd, "b"))
    ra = run_tuples.run_one(spec, tpl, os.path.join(wd, "a"))
    monkeypatch.setenv("LISTINGASSISTANTS_PORTAL", "process")
    rb = run_tuples.run_one(spec, tpl, os.path.join(wd, "b"))
    assert ra["result"] == rb["result"] == "PASS", (ra, rb)

    def lines(d):
        out = []
        for ln in open(os.path.join(wd, d, pb, "console-audit.jsonl"), encoding="utf-8"):
            e = json.loads(ln)
            if e["kind"] == "portal.team":
                continue
            out.append((e["kind"], e.get("intent"), e.get("agent"), e.get("from_agent"),
                        e.get("to_agent"), e.get("status")))
        return out
    assert lines("a") == lines("b")


def test_a_stopped_agent_stays_stopped_after_the_dispatcher_restarts(tmp_path):
    def act(peer, env):
        peer.call("send", {"envelope": _env("13", "02", "lead.captured", "X", {})})
    tmp = str(tmp_path)
    sw = _swarm(tmp, rogue=("20", act))
    sw.hub.send(_env("external", "20", "social.mention", "M-1", MENTION))
    assert "20" in sw.team.stopped
    sw.close()
    sw = _swarm(tmp)                      # the real agent 20 is ready to connect
    try:
        assert "20" in sw.team.stopped and "20" not in sw.team.processes
        [held] = _entries(sw, "portal.agent_held_stopped")
        assert held["agent"] == "20" and "impersonation" in held["why"]
        r = sw.hub.send(_env("external", "20", "social.mention", "M-2", MENTION))
        assert r["status"] == "dead.letter" and "stopped" in r["reason"]
        assert sw.team.clear("20", by="jeff@example.test")["ok"]
        r = sw.hub.send(_env("external", "20", "social.mention", "M-3", MENTION))
        assert r["status"] == "ack"
    finally:
        sw.close()


def test_the_alert_door_sends_only_short_codes(tmp_path):
    from dispatcher import alert_door
    door = alert_door.Door(str(tmp_path / "pager.json"))
    assert door.page("portal.violation", "portal", "V05-1A2B3C", "LA-ABC123", "05") == \
        {"status": "failed", "error": "no pager set up in the alert door"}
    for bad in ({"client_context_id": "Pat Smith 12 Oak St"}, {"alert_code": "x" * 80},
                {"agent": "05; rm -rf"}):
        with pytest.raises(ValueError):
            door.page("portal.violation", **{"client_context_id": "portal", **bad})


def test_the_dispatcher_pages_through_the_alert_door(tmp_path):
    """The dispatcher side (DoorPager) and the door (serve) on a real line:
    the page the door would send, and the record of the attempt."""
    from dispatcher import alert_door, pager as pg
    sent = []
    pg_path = tmp_path / "pager.json"
    pg.save_config(str(pg_path), {"account_sid": "AC1", "auth_token": "t", "from_number": "+15550000001",
                                  "to_number": "+15550000002", "api_base": "http://127.0.0.1:9"})
    real_send = pg.send_page
    pg.send_page = lambda cfg, text, **k: sent.append(text) or {"status": "sent"}
    path = os.path.join(tempfile.mkdtemp(prefix="la-d-"), "alert.sock")
    threading.Thread(target=alert_door.serve, args=(path, str(pg_path)), daemon=True).start()
    for _ in range(100):
        if os.path.exists(path):
            break
        time.sleep(0.05)
    notes = []

    class Audit:
        def append(self, kind, data):
            notes.append((kind, data))
    try:
        p = alert_door.DoorPager(path)
        p.audit = Audit()
        res = p("portal.violation", {"client_context_id": "portal", "agent": "05",
                                     "alert_code": "V05-1A2B3C", "system_id": "LA-ABC123",
                                     "detail": "anything else here never leaves"})
        assert res == {"status": "sent"}
        assert sent == ["ListingAssistants LA-ABC123: portal.violation V05-1A2B3C. "
                        "Agent 05 is stopped until you clear it."]
        assert notes[0][0] == "pager.sent" and notes[0][1]["via"] == "alert door"
        res = p("clarification.request", {"client_context_id": "Pat Smith at 12 Oak"})
        assert res["status"] == "failed" and notes[-1][0] == "pager.failed"
        assert len(sent) == 1                       # the bad one never left
    finally:
        pg.send_page = real_send


def test_the_desk_shows_a_stopped_agent_and_restarts_it_after_review(tmp_path, monkeypatch):
    import json
    import urllib.request
    sys.path.insert(0, os.path.join(ROOT, "tests_listing"))
    from test_desk import start, stop
    from test_mcp_desk_mode import _live
    from dispatcher.core import AuditLog
    state = _live(tmp_path)
    log = AuditLog(os.path.join(state, "console-audit.jsonl"))
    log.append("portal.agent_stopped", {"agent": "20", "stopped_for": "violation",
                                        "code": "V20-TEST01", "system_id": "LA-TEST",
                                        "reason": "stopped until you review it"})
    monkeypatch.setenv("LISTINGASSISTANTS_PORTAL", "process")
    monkeypatch.setenv("LISTINGASSISTANTS_PORTAL_DIR", tempfile.mkdtemp(prefix="la-k-"))
    p, url, port = start([], state)
    try:
        s = json.load(urllib.request.urlopen(url + "api/state"))
        [t20] = [t for t in s["team"] if t["id"] == "20"]
        assert t20["state"] == "problem" and "stopped" in t20["note"]
        req = urllib.request.Request(url + "api/act", method="POST",
                                     data=json.dumps({"action": "restart_agent", "agent": "20"}).encode(),
                                     headers={"Content-Type": "application/json"})
        out = json.load(urllib.request.urlopen(req))
        assert out.get("ok") is True, out
        s = json.load(urllib.request.urlopen(url + "api/state"))
        [t20] = [t for t in s["team"] if t["id"] == "20"]
        assert t20["state"] != "problem"
    finally:
        stop(p)
    kinds = [json.loads(ln)["kind"] for ln in open(os.path.join(state, "console-audit.jsonl"))]
    assert "portal.agent_cleared" in kinds and "portal.agent_restarted" in kinds
