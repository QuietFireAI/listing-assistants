"""The Broker Desk in live mode with a test script (--script), added
2026-10-12: session files played into YOUR desk, signed with YOUR key,
stopping at your moves (Send, Continue/Cancel, Don't send); the script's
place survives a restart, so no line is applied twice."""
import json
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)

import desk as desk_mod  # noqa: E402

SCENE4 = os.path.join(ROOT, "scenes", "scene04_new_listing.jsonl")
LOGIN = "broker@example.test"


def live_state(tmp_path):
    """A broker's own folder: key from `console.py init`, name from
    `console.py onboard`, and a ratified copy of the scenes' vendor roster."""
    state = str(tmp_path / "state")
    env = {**os.environ, "LISTINGASSISTANTS_STATE_DIR": state}
    for args in (["init"], ["onboard", "--name", "Test Broker", "--login", LOGIN]):
        out = subprocess.run([sys.executable, "tools/console.py", *args], cwd=ROOT, env=env,
                             capture_output=True, text=True)
        assert out.returncode == 0, out.stdout + out.stderr
    cfg = str(tmp_path / "config")
    shutil.copytree(os.path.join(ROOT, "scenes", "config"), cfg)
    p = os.path.join(cfg, "vendor_panel.json")
    roster = json.load(open(p, encoding="utf-8"))
    roster["_status"] = "RATIFIED 2026-10-12 test copy"
    json.dump(roster, open(p, "w", encoding="utf-8"))
    return state, cfg


def play(d, limit=None):
    """Steps the script, pressing your moves on the desk as a broker would.
    Returns (steps, presses, errors); stops after `limit` steps if given."""
    steps = presses = 0
    errors = []
    for _ in range(500):
        s = d.state()
        sc = s["showcase"]
        if sc["done"] or (limit is not None and steps >= limit):
            return steps, presses, errors
        if sc["waiting_for_you"]:
            line = sc["line"]
            if line["do"] in ("release", "decline"):
                items = [i for i in s["needs_you"] if i["type"] == "held" and i["ctx"] == line["ctx"]
                         and (not line.get("intent") or i["intent"] == line["intent"])]
                for i in items:
                    action = "send" if line["do"] == "release" else "decline"
                    r = d.act({"action": action, "id": i["id"], "reason": "test script"})
                    presses += 1
                    if r.get("error"):
                        errors.append((action, r))
            else:
                items = [i for i in s["needs_you"] if i["type"] == "wait" and i["ctx"] == line["ctx"]]
                for i in items:
                    r = d.act({"action": "decide", "id": i["id"], "decision": line["decision"],
                               "route_to": line.get("route_to")})
                    presses += 1
            assert items, ("nothing to press for", line)
        r = d.act({"action": "showcase.step"})
        steps += 1
        if r.get("error") is True:
            errors.append(("step", r.get("result")))
    raise AssertionError("script did not finish")


def test_script_plays_into_your_live_desk_with_your_key(tmp_path):
    state, cfg = live_state(tmp_path)
    d = desk_mod.Desk(state, cfg, scripts=[SCENE4])
    try:
        s = d.state()
        assert s["mode"] == "live" and s["showcase"]["kind"] == "script"
        assert s["showcase"]["title"] == "scene04_new_listing.jsonl"
        steps, presses, errors = play(d)
        assert errors == [] and presses == 2          # the booking and the campaign
        s = d.state()
        assert s["showcase"]["done"]
        card = next(c for c in s["listings"] if c["ctx"] == "S4")
        st = {x["key"]: x["state"] for x in card["steps"]}
        assert all(st[k] == "done" for k in ("signed", "booked", "photos", "copy", "live", "marketing"))
        log = d.sw.hub.audit.read()
        auths = [e for e in log if e["kind"] == "disclosure.authorized"]
        assert len(auths) == 2
        assert s["proof"]["gated_out"] == s["proof"]["gated_out_signed"] == 2
        assert s["operator"]["login"] == LOGIN                # your desk, not the showcase's
        assert d.sw.hub.audit.verify_chain()["ok"]
    finally:
        d.close()


def test_a_restart_resumes_the_script_and_applies_no_line_twice(tmp_path):
    state, cfg = live_state(tmp_path)
    d = desk_mod.Desk(state, cfg, scripts=[SCENE4])
    try:
        play(d, limit=3)                                      # the two configs and the signed listing
        mid = d.state()["showcase"]["pos"]
        assert mid >= 3
    finally:
        d.close()
    d = desk_mod.Desk(state, cfg, scripts=[SCENE4])
    try:
        assert d.state()["showcase"]["pos"] == mid            # resumed, not restarted
        play(d)
        log = d.sw.hub.audit.read()
        cfg_lines = sum(1 for ln in open(SCENE4, encoding="utf-8")
                        if ln.strip() and json.loads(ln)["do"] in ("config", "authorize"))
        signed = [e for e in log if e["kind"] == "envelope.persisted" and e["from_agent"] == "human"
                  and e["intent"] in ("config.update", "listing.change.authorized")]
        assert len(signed) == cfg_lines                       # each signed line once
    finally:
        d.close()


def test_a_changed_script_starts_from_its_first_line(tmp_path):
    state, cfg = live_state(tmp_path)
    mine = str(tmp_path / "mine.jsonl")
    shutil.copy(SCENE4, mine)
    d = desk_mod.Desk(state, cfg, scripts=[mine])
    try:
        play(d, limit=2)
    finally:
        d.close()
    with open(mine, "a", encoding="utf-8") as f:
        f.write('{"do": "show", "what": "held"}\n')
    d = desk_mod.Desk(state, cfg, scripts=[mine])
    try:
        assert d.state()["showcase"]["pos"] == 0
    finally:
        d.close()


def test_a_decline_line_waits_for_dont_send(tmp_path):
    state, cfg = live_state(tmp_path)
    mine = str(tmp_path / "say_no.jsonl")
    lines = [ln for ln in open(SCENE4, encoding="utf-8") if ln.strip()]
    assert '"release", "ctx": "S4", "intent": "campaign.publish"' in lines[-2]
    lines[-2] = '{"do": "decline", "ctx": "S4", "intent": "campaign.publish"}\n'
    open(mine, "w", encoding="utf-8").write("".join(lines))
    d = desk_mod.Desk(state, cfg, scripts=[mine])
    try:
        for _ in range(100):                     # play up to the decline line
            s = d.state()
            sc = s["showcase"]
            if sc["waiting_for_you"]:
                if sc["line"]["do"] == "decline":
                    break
                for i in s["needs_you"]:         # the booking: Send
                    if i["type"] == "held" and i["intent"] == sc["line"]["intent"]:
                        d.act({"action": "send", "id": i["id"]})
            d.act({"action": "showcase.step"})
        assert sc["line"]["do"] == "decline" and "Don't send" in sc["next"]
        assert d.act({"action": "showcase.step"}).get("waiting_for_you")   # it waits for you
        _, presses, errors = play(d)
        assert errors == [] and presses == 1
        log = d.sw.hub.audit.read()
        assert [e["intent"] for e in log if e["kind"] == "disclosure.declined"] == ["campaign.publish"]
        assert d.state()["proof"]["gated_out"] == 1       # only the booking went out
    finally:
        d.close()


def test_a_broken_script_line_is_refused_with_its_line_number(tmp_path):
    state, cfg = live_state(tmp_path)
    bad = str(tmp_path / "bad.jsonl")
    open(bad, "w", encoding="utf-8").write('{"do": "show", "what": "held"}\n{"to": "05"}\n')
    with pytest.raises(SystemExit, match="line 2"):
        desk_mod.Desk(state, cfg, scripts=[bad])
    # refused before the lock was taken: nothing left behind
    assert not os.path.exists(os.path.join(state, "desk.lock"))


def test_script_and_showcase_together_are_refused(tmp_path):
    with pytest.raises(SystemExit, match="leave out --showcase"):
        desk_mod.Desk(str(tmp_path / "s"), showcase=True, scripts=[SCENE4])
