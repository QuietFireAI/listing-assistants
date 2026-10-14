"""The text pager pages from everything that runs the swarm (2026-10-13).

Found while writing docs/GLOSSARY.md: the Broker Desk showed "Text pager to
you: on" whenever console-state/pager.json existed, but only console
sessions passed the pager to the swarm - the desk and the daily clock paged
nobody. Now all three load it through console.load_pager, the desk's chip
says on only when its swarm pages, and an unusable pager.json stops the desk
and the clock instead of being ignored.
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)

import desk as desk_mod  # noqa: E402
import run_sweeps  # noqa: E402
from dispatcher import pager as pg  # noqa: E402

CFG = {"account_sid": "AC9", "auth_token": "tok", "from_number": "+15550000001",
       "to_number": "+15550000002"}


@pytest.fixture
def texts(monkeypatch):
    sent = []

    def fake_send(cfg, text, **kw):
        sent.append((cfg["to_number"], text))
        return {"status": "sent", "http_status": 201}
    monkeypatch.setattr(pg, "send_page", fake_send)
    return sent


def write_pager(state_dir, cfg=CFG):
    os.makedirs(state_dir, exist_ok=True)
    with open(os.path.join(state_dir, "pager.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f)


def chip(d):
    conns = d.model.build()["proof"]["connections"]
    return next(c for c in conns if c["name"] == "Text pager to you")["state"]


def test_the_desk_pages_when_the_pager_is_on(tmp_path, texts):
    state = str(tmp_path / "s")
    write_pager(state)
    d = desk_mod.Desk(state, showcase=True)
    try:
        assert chip(d) == "on"
        d.sw.hub.queue_and_notify("clarification.request",
                                  {"client_context_id": "S9", "reason": "test"})
        assert texts == [("+15550000002", pg.page_text("clarification.request",
                                                         {"client_context_id": "S9"}))]
        log = os.path.join(state, "console-audit.jsonl")
        kinds = [json.loads(line)["kind"] for line in open(log, encoding="utf-8")]
        assert "pager.sent" in kinds
    finally:
        d.close()


def test_the_desk_says_off_and_pages_nobody_without_it(tmp_path, texts):
    d = desk_mod.Desk(str(tmp_path / "s"), showcase=True)
    try:
        assert chip(d) == "off"
        d.sw.hub.queue_and_notify("clarification.request", {"client_context_id": "S9"})
        assert texts == []
    finally:
        d.close()


def test_an_unusable_pager_file_stops_the_desk_and_leaves_no_lock(tmp_path):
    state = str(tmp_path / "s")
    write_pager(state, {"account_sid": "AC9"})
    with pytest.raises(SystemExit, match="pager.json is not usable"):
        desk_mod.Desk(state, showcase=True)
    assert not os.path.exists(os.path.join(state, "desk.lock"))


def test_the_daily_clock_pages_when_the_pager_is_on(tmp_path, texts, monkeypatch, capsys):
    state = str(tmp_path / "console-state")
    write_pager(state)
    from console_state import init_state
    init_state(state)                          # the clock checks the attested install
    import dispatcher.sweep_runner as sr

    def fake_sweeps(hub, spokes, today, now_iso):
        hub.queue_and_notify("escalation.hot_lead", {"client_context_id": "C7"})
        return []
    monkeypatch.setattr(sr, "run_daily_sweeps", fake_sweeps)
    audit = os.path.join(state, "console-audit.jsonl")
    rc = run_sweeps.main(["--audit-log", audit,
                          "--state-db", os.path.join(state, "swarm-state.sqlite")])
    assert rc == 0
    assert texts == [("+15550000002", pg.page_text("escalation.hot_lead",
                                                     {"client_context_id": "C7"}))]
    kinds = [json.loads(line)["kind"] for line in open(audit, encoding="utf-8")]
    assert "pager.sent" in kinds


def test_an_unusable_pager_file_stops_the_clock(tmp_path, capsys):
    state = str(tmp_path / "console-state")
    write_pager(state, {"account_sid": "AC9"})
    from console_state import init_state
    init_state(state)                          # past the install check, to the pager's
    rc = run_sweeps.main(["--audit-log", os.path.join(state, "console-audit.jsonl"),
                          "--state-db", os.path.join(state, "swarm-state.sqlite")])
    assert rc == 2
    assert "pager.json is not usable" in capsys.readouterr().out
