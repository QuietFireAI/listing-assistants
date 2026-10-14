"""The Broker Desk (tools/desk.py), added 2026-10-12.

In-process: the showcase replays all ten operator scenes with the broker's
presses done through the desk's own actions, and the page's numbers match
the audit log. Over HTTP (a real desk process): the page and state are
served, the access code is enforced with --lan, and the desk lock stops a
console session and the daily clock from forking the state.
"""
import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)

import desk as desk_mod  # noqa: E402


def press_through(d):
    """Plays the whole showcase, pressing Send / Continue / Cancel on the
    desk exactly where the scenes do. Returns (steps, presses, errors)."""
    steps = presses = 0
    errors = []
    for _ in range(500):
        s = d.state()
        sc = s["showcase"]
        if sc["done"]:
            return steps, presses, errors
        if sc["waiting_for_you"]:
            line = sc["line"]
            if line["do"] == "release":
                items = [i for i in s["needs_you"] if i["type"] == "held"
                         and i["ctx"] == line["ctx"]
                         and (not line.get("intent") or i["intent"] == line["intent"])]
                for i in items:
                    r = d.act({"action": "send", "id": i["id"]})
                    presses += 1
                    if r.get("status") != "ack":
                        errors.append(("send", r))
            else:
                items = [i for i in s["needs_you"] if i["type"] == "wait" and i["ctx"] == line["ctx"]]
                for i in items:
                    r = d.act({"action": "decide", "id": i["id"], "decision": line["decision"],
                               "route_to": line.get("route_to")})
                    presses += 1
                    if isinstance(r, dict) and r.get("error"):
                        errors.append(("decide", r))
            assert items, ("nothing to press for", line)
        r = d.act({"action": "showcase.step"})
        steps += 1
        if r.get("error") is True:
            errors.append(("step", sc["next"], r.get("result")))
    raise AssertionError("showcase did not finish")


@pytest.fixture(scope="module")
def played(tmp_path_factory):
    d = desk_mod.Desk(str(tmp_path_factory.mktemp("desk") / "show"), showcase=True)
    try:
        steps, presses, errors = press_through(d)
        yield d, steps, presses, errors
    finally:
        d.close()


def test_showcase_plays_all_ten_scenes_with_your_presses(played):
    d, steps, presses, errors = played
    assert errors == []
    assert presses == 5          # the scenes' release and decide lines
    assert d.state()["showcase"]["done"]


def test_proof_numbers_match_the_audit_log(played):
    d, *_ = played
    s = d.state()
    log = d.sw.hub.audit.read()
    released = {e["envelope_id"] for e in log if e["kind"] == "absolute_signal.released"}
    gated = [e for e in log if e["kind"] == "envelope.persisted" and e["to_agent"] == "external"
             and e["intent"] in ("vendor.schedule", "campaign.publish")]
    assert s["proof"]["chain_ok"] is True
    assert s["proof"]["gated_out"] == len(gated) > 0
    assert s["proof"]["gated_out_signed"] == len(gated)
    assert all(e["envelope_id"] in released for e in gated)
    assert s["proof"]["held_now"] == len(d.sw.hub._absolute_holds)
    assert s["proof"]["client_messages"] == sum(
        1 for e in log if e["kind"] == "envelope.persisted" and e["intent"] == "client.message.send")


def test_listing_cards_follow_the_record(played):
    d, *_ = played
    cards = {c["ctx"]: c for c in d.state()["listings"]}
    s4 = {st["key"]: st["state"] for st in cards["S4"]["steps"]}
    assert all(s4[k] == "done" for k in ("signed", "booked", "photos", "copy", "live", "marketing"))
    assert any("flagged" in f for f in cards["S5"]["flags"])
    assert cards["S7"]["steps"][-1]["state"] == "done"          # transaction.closed on file


def test_send_signs_and_releases_once(played):
    d, *_ = played
    held = [i for i in d.state()["needs_you"] if i["type"] == "held"]
    assert held, "the scenes leave messages held"
    target = held[0]
    r = d.act({"action": "send", "id": target["id"]})
    assert r["status"] == "ack"
    log = d.sw.hub.audit.read()
    auth = [e for e in log if e["kind"] == "disclosure.authorized"
            and e["held_envelope_id"] == target["id"]]
    assert len(auth) == 1
    assert target["id"] not in {i["id"] for i in d.state()["needs_you"]}
    again = d.act({"action": "send", "id": target["id"]})
    assert "no longer held" in again["error"]


def test_dont_send_signs_a_decline_and_nothing_goes_out(played):
    d, *_ = played
    held = [i for i in d.state()["needs_you"] if i["type"] == "held"]
    assert held, "the scenes leave messages held"
    target = held[-1]
    before = d.state()["proof"]
    r = d.act({"action": "decline", "id": target["id"], "reason": "wrong photographer"})
    assert r["status"] == "declined" and r["envelope_id"] == target["id"]
    log = d.sw.hub.audit.read()
    dec = [e for e in log if e["kind"] == "disclosure.declined"
           and e["held_envelope_id"] == target["id"]]
    assert len(dec) == 1 and dec[0]["reason"] == "wrong photographer"
    # the signed key on the chain names the decision and who signed it
    persisted = {e["envelope_id"] for e in log if e["kind"] == "envelope.persisted"}
    assert target["id"] not in persisted                      # never went out
    after = d.state()
    assert target["id"] not in {i["id"] for i in after["needs_you"]}
    assert after["proof"]["held_now"] == before["held_now"] - 1
    assert after["proof"]["declined"] == before["declined"] + 1
    assert after["proof"]["gated_out"] == before["gated_out"]
    assert any("signed Don't send" in a["text"] and "wrong photographer" in a["text"]
               for a in after["activity"])
    # too late to change your mind into a send: it is gone
    assert "no longer held" in d.act({"action": "send", "id": target["id"]})["error"]
    assert d.sw.hub.audit.verify_chain()["ok"]


def test_console_decline_line_does_the_same(played):
    import console
    d, *_ = played
    held = [i for i in d.state()["needs_you"] if i["type"] == "held"]
    assert held
    t = held[0]
    r, err = console.apply_action(d.sw, d.signer, d.operator,
                                  {"do": "decline", "ctx": t["ctx"], "intent": t["intent"],
                                   "reason": "seller pulled it"})
    assert not err and r and all(x["hub"]["status"] == "declined" for x in r)
    assert t["id"] in {x["declined"] for x in r}
    assert t["id"] not in d.sw.hub._absolute_holds


def test_done_records_who_and_takes_the_item_off_the_list(played):
    d, *_ = played
    q = next(i for i in d.state()["needs_you"] if i["type"] == "queue")
    d.act({"action": "ack", "id": q["id"], "title": q["title"], "ctx": q["ctx"]})
    entry = [e for e in d.sw.hub.audit.read() if e["kind"] == "desk.acknowledged"][-1]
    assert entry["item"] == q["id"] and entry["by"] == "showcase@example.test"
    assert q["id"] not in {i["id"] for i in d.state()["needs_you"]}
    assert d.sw.hub.audit.verify_chain()["ok"]


# ---------------------------------------------------------------- over HTTP
def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


WINDOWS = os.name == "nt"


def stop(p):
    """A clean stop on both systems: SIGTERM on Linux/macOS; on Windows,
    Ctrl+Break to the desk's own process group (terminate() there is a
    hard kill that would leave desk.lock behind)."""
    if WINDOWS:
        import signal
        p.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        p.terminate()
    p.wait(timeout=20)


def start(args, state_dir):
    port = free_port()
    extra = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if WINDOWS else {}
    p = subprocess.Popen([sys.executable, os.path.join(ROOT, "tools", "desk.py"), *args,
                          "--state-dir", state_dir, "--port", str(port)],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=ROOT,
                         **extra)
    # read the startup line on a thread with a deadline: a desk that never
    # announces itself fails this test instead of hanging the suite
    lines = queue.Queue()
    threading.Thread(target=lambda: [lines.put(ln) for ln in p.stdout], daemon=True).start()
    url, seen, deadline = None, [], time.time() + 60
    while url is None and time.time() < deadline:
        try:
            line = lines.get(timeout=max(0.1, deadline - time.time()))
        except queue.Empty:
            break
        seen.append(line)
        if line.startswith('{"desk"'):
            url = json.loads(line)["desk"].replace("<this-computer>", "127.0.0.1")
    if url is None:
        p.kill()
        raise AssertionError("desk did not announce itself within 60s: " + "".join(seen)[-2000:])
    return p, url, port


def test_http_page_state_lock_and_access_code(tmp_path):
    state = str(tmp_path / "show")
    p, url, port = start(["--showcase", "--lan"], state)
    try:
        base = f"http://127.0.0.1:{port}"
        with pytest.raises(urllib.error.HTTPError) as no_code:
            urllib.request.urlopen(base + "/api/state")
        assert no_code.value.code == 403
        token = url.split("?t=")[1]
        page = urllib.request.urlopen(f"{base}/?t={token}").read().decode()
        assert "Broker Desk" in page
        s = json.load(urllib.request.urlopen(f"{base}/api/state?t={token}"))
        assert s["mode"] == "showcase" and s["showcase"]["total"] > 0
        req = urllib.request.Request(f"{base}/api/act?t={token}", method="POST",
                                     data=json.dumps({"action": "send", "id": "nope"}).encode())
        assert "no longer held" in json.load(urllib.request.urlopen(req))["error"]
        # a real step over HTTP: runs the swarm and saves its SQLite state,
        # from a server thread, through the desk's owner thread
        for _ in range(3):
            step = urllib.request.Request(f"{base}/api/act?t={token}", method="POST",
                                          data=json.dumps({"action": "showcase.step"}).encode())
            r = json.load(urllib.request.urlopen(step))
            assert r.get("stepped") and r.get("error") is not True, r
        assert json.load(urllib.request.urlopen(f"{base}/api/state?t={token}"))["showcase"]["pos"] >= 3
        # the lock: a console session and the daily clock refuse this folder
        env = {**os.environ, "LISTINGASSISTANTS_STATE_DIR": state}
        script = tmp_path / "s.jsonl"
        script.write_text('{"do": "show", "what": "held"}\n', encoding="utf-8")
        out = subprocess.run([sys.executable, "tools/console.py", "session", str(script)],
                             cwd=ROOT, env=env, capture_output=True, text=True)
        assert out.returncode == 2 and "Broker Desk is running" in out.stdout
        clock = subprocess.run([sys.executable, "tools/run_sweeps.py",
                                "--audit-log", os.path.join(state, "console-audit.jsonl"),
                                "--state-db", os.path.join(state, "swarm-state.sqlite")],
                               cwd=ROOT, capture_output=True, text=True)
        # a showcase folder is not attested: the clock's install check comes
        # first and refuses it (the clock's lock check is tested on an
        # attested folder in test_manners_wiring.py)
        assert clock.returncode == 2 and "install not attested" in clock.stdout
    finally:
        stop(p)
    assert not os.path.exists(os.path.join(state, "desk.lock"))   # removed on a clean stop


def test_a_stalled_connection_does_not_freeze_the_page(tmp_path):
    """A tablet on bad Wi-Fi that opens a connection and stops mid-request
    must not block anyone else's page (it did while the server was
    single-threaded)."""
    p, url, port = start(["--showcase"], str(tmp_path / "show"))
    stalled = socket.create_connection(("127.0.0.1", port))
    try:
        stalled.sendall(b"GET /api/state HTTP/1.1\r\nHost: x\r\n")   # never finished
        time.sleep(0.3)
        t0 = time.time()
        s = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=10))
        assert s["mode"] == "showcase" and time.time() - t0 < 5
    finally:
        stalled.close()
        stop(p)


def test_lock_left_by_a_dead_desk_is_ignored_and_a_live_one_holds(tmp_path):
    """The pid check behind the lock, on whatever system runs the suite -
    on Windows it is the OpenProcess/GetExitCodeProcess branch, where
    os.kill(pid, 0) would have ended the process instead of asking."""
    import console
    state = str(tmp_path)
    lock = os.path.join(state, "desk.lock")
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait(timeout=30)
    with open(lock, "w", encoding="utf-8") as f:
        f.write(str(gone.pid))
    assert console.desk_running(state) is None            # a crashed desk does not lock you out
    alive = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        with open(lock, "w", encoding="utf-8") as f:
            f.write(str(alive.pid))
        assert console.desk_running(state) == alive.pid
        assert alive.poll() is None                       # asking did not end it
    finally:
        alive.kill()
        alive.wait(timeout=30)
