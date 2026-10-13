"""What the listing product says about who was reached, and what it does with
a damaged record (core repair plan 1.1 and 1.2, owner decisions D3 and D4,
2026-10-13).

D3: the record says a person was notified only when the notifier reports it
was delivered (the pager: "sent"; the console screen: "shown"). A page that
fails is recorded as human.notify_failed - nobody was reached.

D4: a record (audit log) with an unreadable line stops every entry point
before anything is written, names the line, and - for a write cut off at
the end - points to `console.py repair-record`, which a person runs.
"""
import http.server
import json
import os
import subprocess
import sys
import threading
import urllib.error
import urllib.parse as up
import urllib.request

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)

LEAD = {"do": "send", "from": "external", "to": "01", "intent": "lead.inbound", "ctx": "RT1",
        "payload": {"channel": "web_form", "name": "Pat Private", "phone": "555-0177",
                    "demands_human": True, "message": "my budget is 900k call me",
                    "today": "2026-10-12", "consent": {"call": "yes"}}}


def _console(tmp_path, *args):
    env = {**os.environ, "LISTINGASSISTANTS_STATE_DIR": str(tmp_path / "state")}
    p = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "console.py"), *args],
                       capture_output=True, text=True, env=env, cwd=ROOT)
    return p.returncode, [json.loads(l) for l in p.stdout.splitlines() if l.startswith("{")], p


def _onboarded(tmp_path):
    assert _console(tmp_path, "init")[0] == 0
    assert _console(tmp_path, "onboard", "--name", "Test Broker", "--login", "tb@example.com")[0] == 0


def _script(tmp_path, *lines):
    s = tmp_path / "s.jsonl"
    s.write_text("".join(json.dumps(l) + "\n" for l in lines), encoding="utf-8")
    return str(s)


def _audit(tmp_path):
    return [json.loads(l) for l in open(tmp_path / "state" / "console-audit.jsonl", encoding="utf-8")]


def _fake_twilio(code):
    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(code)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *a):
            pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def _pager_on(tmp_path, base):
    tok = tmp_path / "tok"
    tok.write_text("secret-token\n", encoding="utf-8")
    rc, out, p = _console(tmp_path, "pager", "--account-sid", "AC123", "--auth-token-file", str(tok),
                          "--from-number", "+15550000001", "--to-number", "+15550000002",
                          "--api-base", base)
    return rc, out, p


# ------------------------------------------------------------- D3: who was reached
def test_console_notifier_reports_what_happened():
    from console import _notify_human
    assert _notify_human("q", {}, None) == {"status": "shown", "channel": "screen"}
    assert _notify_human("q", {}, lambda q, r: {"status": "sent"}) == {"status": "sent"}
    failed = {"status": "failed", "http_status": 401}
    assert _notify_human("q", {}, lambda q, r: failed) == failed


def _landings(audit):
    """Everything put on a human queue: messages delivered to "queue", and
    escalations. Each must have exactly one notification outcome."""
    return [e for e in audit if (e["kind"] == "envelope.persisted" and e.get("to_agent") == "queue")
            or e["kind"] == "escalation.raised"]


def test_pager_off_every_queue_landing_is_recorded_as_shown_on_screen(tmp_path):
    _onboarded(tmp_path)
    rc, out, p = _console(tmp_path, "session", _script(tmp_path, LEAD), "--no-state")
    assert out[-1]["errors"] == 0, p.stdout[-800:]
    audit = _audit(tmp_path)
    landed = _landings(audit)
    notified = [e for e in audit if e["kind"] == "human.notified"]
    assert landed, "this lead lands on a human queue (clarification.request)"
    assert len(notified) == len(landed)
    assert all(e.get("transport_status") == "shown" for e in notified)
    assert not [e for e in audit if e["kind"] == "human.notify_failed"]
    assert not [e for e in notified if e.get("transport") == "not reported"]


def test_a_failed_page_is_recorded_as_nobody_reached(tmp_path):
    srv, base = _fake_twilio(201)              # accepts the setup's details
    try:
        _onboarded(tmp_path)
        assert _pager_on(tmp_path, base)[0] == 0
    finally:
        srv.shutdown()
    srv, base = _fake_twilio(401)              # then refuses every page
    try:
        cfg = tmp_path / "state" / "pager.json"
        c = json.loads(cfg.read_text(encoding="utf-8"))
        c["api_base"] = base
        cfg.write_text(json.dumps(c), encoding="utf-8")
        rc, out, p = _console(tmp_path, "session", _script(tmp_path, LEAD), "--no-state")
    finally:
        srv.shutdown()
    audit = _audit(tmp_path)
    failed = [e for e in audit if e["kind"] == "human.notify_failed"]
    landed = _landings(audit)
    assert landed and len(failed) == len(landed), p.stdout[-800:]
    assert all(e["notifier_status"] == "failed" and e["notifier_http_status"] == 401 for e in failed)
    assert not [e for e in audit if e["kind"] == "human.notified"]
    assert [e for e in audit if e["kind"] == "pager.failed"]
    assert all("secret-token" not in json.dumps(e) for e in audit)
    from dispatcher.readable_audit import describe
    assert describe("human.notify_failed", failed[0])[1].startswith("Could not reach you about ")
    import desk as desk_mod                    # the desk's feed shows it too
    feed = [f for f in desk_mod.ReadModel(None).activity(audit) if f["text"].startswith("Could not reach you")]
    assert len(feed) == len(failed) and all(f["kind"] == "hold" for f in feed)


def test_a_delivered_page_is_recorded_as_sent(tmp_path):
    srv, base = _fake_twilio(201)
    try:
        _onboarded(tmp_path)
        assert _pager_on(tmp_path, base)[0] == 0
        rc, out, p = _console(tmp_path, "session", _script(tmp_path, LEAD), "--no-state")
    finally:
        srv.shutdown()
    notified = [e for e in _audit(tmp_path) if e["kind"] == "human.notified"]
    assert notified and all(e["transport_status"] == "sent" for e in notified), p.stdout[-800:]


# ------------------------------------------------------------ D4: a damaged record
def _with_record(tmp_path):
    _onboarded(tmp_path)
    rc, out, p = _console(tmp_path, "session", _script(tmp_path, LEAD))
    assert rc == 0, p.stdout[-800:]
    return tmp_path / "state" / "console-audit.jsonl"


def test_a_cut_off_record_stops_the_session_names_the_line_and_writes_nothing(tmp_path):
    log = _with_record(tmp_path)
    with open(log, "ab") as f:
        f.write(b'{"ts": 1, "kind": "envelope.persi')
    before = log.read_bytes()
    lines = before.count(b"\n") + 1
    rc, out, _ = _console(tmp_path, "session", _script(tmp_path, LEAD))
    assert rc == 2
    e = out[0]
    assert e["error"].startswith("the record (audit log) is damaged - nothing was started")
    assert e["line"] == lines and e["cut_off_last_write"] is True
    assert "repair-record" in e["action"]
    assert log.read_bytes() == before

    rc, out, _ = _console(tmp_path, "verify")
    assert rc == 1 and out[0]["chain"]["break_at"] == lines and "repair-record" in out[0]["action"]
    rc, out, _ = _console(tmp_path, "repair-record", "--check")
    assert rc == 1 and log.read_bytes() == before

    rc, out, _ = _console(tmp_path, "repair-record")
    assert rc == 0 and out[0]["repaired"] is True and out[0]["chain"]["ok"] is True
    side = tmp_path / "state" / out[0]["side_file"]
    assert side.read_bytes() == b'{"ts": 1, "kind": "envelope.persi'
    assert _audit(tmp_path)[-1]["kind"] == "audit.tail_quarantined"
    import desk as desk_mod                    # the repair shows on the desk's feed
    feed = [f["text"] for f in desk_mod.ReadModel(None).activity(_audit(tmp_path))]
    assert feed[0].startswith(f"Record repaired: a write cut off at line {lines} (33 bytes) was moved to "
                              f"console-audit.jsonl.torn-")
    rc, out, p = _console(tmp_path, "session", _script(tmp_path, LEAD))
    assert rc == 0 and out[-1]["chain"]["ok"], p.stdout[-800:]
    assert _console(tmp_path, "verify")[0] == 0


def test_damage_before_the_end_is_refused_by_the_repair_and_nothing_changes(tmp_path):
    log = _with_record(tmp_path)
    lines = log.read_bytes().split(b"\n")
    lines[2] = b"{damaged"
    log.write_bytes(b"\n".join(lines))
    before = log.read_bytes()
    rc, out, _ = _console(tmp_path, "session", _script(tmp_path, LEAD))
    assert rc == 2 and out[0]["line"] == 3 and out[0]["cut_off_last_write"] is False
    assert "not a cut-off write" in out[0]["action"]
    rc, out, _ = _console(tmp_path, "repair-record")
    assert rc == 2 and out[0]["repaired"] is False and out[0]["changed"] == "nothing"
    assert log.read_bytes() == before
    assert not [f for f in os.listdir(tmp_path / "state") if ".torn-" in f]


def test_the_daily_clock_stops_on_a_damaged_record(tmp_path):
    log = _with_record(tmp_path)
    with open(log, "ab") as f:
        f.write(b'{"half')
    before = log.read_bytes()
    p = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "run_sweeps.py"),
                        "--audit-log", str(log),
                        "--state-db", str(tmp_path / "state" / "swarm-state.sqlite"),
                        "--today", "2026-10-13"], capture_output=True, text=True, cwd=ROOT)
    assert p.returncode == 2, p.stderr[-800:]
    out = json.loads(p.stdout.strip().splitlines()[-1])
    assert out["cut_off_last_write"] is True and "repair-record" in out["action"]
    assert log.read_bytes() == before


def test_the_desk_refuses_to_start_on_a_damaged_record_and_leaves_no_lock(tmp_path):
    import desk as desk_mod
    log = _with_record(tmp_path)
    with open(log, "ab") as f:
        f.write(b'{"half')
    with pytest.raises(SystemExit) as ei:
        desk_mod.Desk(str(tmp_path / "state"))
    msg = json.loads(str(ei.value))
    assert msg["cut_off_last_write"] is True and "repair-record" in msg["action"]
    assert not (tmp_path / "state" / "desk.lock").exists()


def test_the_desk_page_names_damage_that_happens_while_it_runs(tmp_path):
    import desk as desk_mod
    log = _with_record(tmp_path)
    owner = desk_mod.OwnerThread(lambda: desk_mod.Desk(str(tmp_path / "state")))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), desk_mod.make_handler(owner, None))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        assert json.loads(urllib.request.urlopen(url + "/api/state").read())["proof"]["chain_ok"]
        with open(log, "ab") as f:
            f.write(b'{"half')
        with pytest.raises(urllib.error.HTTPError) as ei:
            urllib.request.urlopen(url + "/api/state")
        assert ei.value.code == 503
        body = json.loads(ei.value.read())
        assert body["cut_off_last_write"] is True and body["line"] >= 2
        req = urllib.request.Request(url + "/api/act", data=json.dumps({"action": "verify"}).encode(),
                                     headers={"Content-Type": "application/json"})
        r = json.loads(urllib.request.urlopen(req).read())
        assert r["ok"] is False and r["reason"] == "not a readable entry" and r["torn_tail"] is True
    finally:
        srv.shutdown()
        srv.server_close()
        lockfile = tmp_path / "state" / "desk.lock"
        if lockfile.exists():
            lockfile.unlink()
