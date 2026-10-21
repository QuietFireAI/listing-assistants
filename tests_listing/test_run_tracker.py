"""The playbook run tracker (dispatcher/run_tracker.py, owner decision
2026-10-15; built 2026-10-20). Built on the product's own swarm
(dispatcher/swarm.py), with a signed broker key, the way the console and the
Broker Desk build it. The console sessions for every playbook, start to end,
are synth/playbooks/specs/PLAYBOOKS.jsonl (test_playbook_runs.py runs them)."""
import json
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dispatcher.core import Envelope                                   # noqa: E402
from dispatcher.signatures import Ed25519Signer, Ed25519Verifier      # noqa: E402
from dispatcher.swarm import build_swarm                               # noqa: E402
from dispatcher import run_tracker                                     # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _swarm(tmp_path, state_db=False, signer=None, table=None):
    signer = signer or Ed25519Signer()
    sw = build_swarm(os.path.join(str(tmp_path), "audit.jsonl"),
                     state_db=os.path.join(str(tmp_path), "state.db") if state_db else None,
                     verifier=Ed25519Verifier(signer.public_key_bytes()).verifier(),
                     playbook_table=table)
    return sw, signer


def _two_match_table(tmp_path):
    """The signed table has no message that starts two playbooks since the
    owner's comps decision (2026-10-21). For the two-match hold, a table
    where a comparables request starts P02, P15 and P23 again."""
    t = json.load(open(os.path.join(ROOT, "identity", "playbooks.json")))
    comp = {"intent": "data.request", "from": "human", "to": "10", "eq": {"mode": "comp"}}
    for pid in ("P02", "P15", "P23"):
        t["playbooks"][pid]["starts"] = t["playbooks"][pid]["starts"][:1] if pid == "P02" else []
        t["playbooks"][pid]["starts"].append(dict(comp))
    path = os.path.join(str(tmp_path), "two-match-table.json")
    open(path, "w").write(json.dumps(t))
    return path


def _env(frm, to, intent, ctx, payload):
    return Envelope(from_agent=frm, to_agent=to, intent=intent, client_context_id=ctx,
                    payload=payload, provenance={"source": frm, "captured_at": "runtime",
                                                 "verbatim_available": True})


def _signed(signer, to, intent, ctx, payload):
    e = _env("human", to, intent, ctx, payload)
    signer.sign(e)
    return e


def _decide(sw, signer, ctx, decision, fields=None, agent="00"):
    [w] = [w for w in sw.hitl.get_pending_waits(ctx) if w["agent_id"] == agent]
    payload = {"wait_id": w["wait_id"], "decision": "REJECT_AND_ABORT" if decision == "cancel" else
               ("APPROVE_WITH_OVERRIDE" if fields else "APPROVE")}
    if fields:
        payload["updated_fields"] = fields
    auth = _env("human", agent, "hitl.decision.authority", ctx, payload)
    signer.sign(auth)
    return sw.hitl.resume_operation(auth)


def _kinds(sw, kind, ctx=None):
    return [e for e in sw.hub.audit.read() if e["kind"] == kind
            and (ctx is None or e.get("client_context_id") == ctx)]


def _comp(ctx, **extra):
    return _env("human", "10", "data.request", ctx,
                {"mode": "comp", "license_scope": "internal", "today": "2026-10-15",
                 "comps": [{"address": f"{i + 1} Synth Ln", "sold_price": 440000 + i * 5000,
                            "source": "MLS-SYN", "retrieval_date": "2026-10-12"}
                           for i in range(6)], **extra})


def _listing(sw, signer, ctx, live=True):
    sw.hub.send(_signed(signer, "17", "config.update", "setup",
                        {"ruleset": {"prohibited_phrases": [], "state_rules": {}}, "version": "t1"}))
    sw.hub.send(_signed(signer, "05", "listing.change.authorized", ctx,
                        {"new_listing": {"address": f"{ctx} Test Ln, Testville, OH", "beds": 3,
                                         "baths": 2, "sqft_tax_record": 1800, "price": 450000},
                         "authorize_go_live": live, "today": "2026-10-15"}))


# ------------------------------------------------------------------ the table
def test_the_table_is_proposed_and_matches_the_track():
    sw_table = json.load(open(os.path.join(ROOT, "identity", "playbooks.json")))
    assert sw_table["_status"].startswith("PROPOSED")
    assert sorted(sw_table["playbooks"]) == [f"P{i:02d}" for i in range(1, 25)]


def test_a_table_asking_for_a_crossing_the_track_refuses_is_not_used(tmp_path):
    bad = json.load(open(os.path.join(ROOT, "identity", "playbooks.json")))
    bad["playbooks"]["P15"]["ends"] = [{"intent": "data.package", "from": "10", "to": "external"}]
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad))
    sw, _ = _swarm(tmp_path)
    rt = run_tracker.RunTracker(sw, table_path=str(path))
    assert rt.table is None
    [refused] = [e for e in _kinds(sw, "playbook.table_refused") if e.get("problems")]
    assert any("10 -> external data.package" in p for p in refused["problems"])
    assert sw.hub.queues["integrity.violation"][-1]["kind"] == "playbook_table_defect"


# -------------------------------------------------------------- starts and ends
def test_a_run_starts_steps_ends_and_writes_its_report(tmp_path):
    sw, signer = _swarm(tmp_path)
    sw.hub.send(_comp("A1", playbook="P15"))
    [run] = sw.runs.runs.values()
    assert run["playbook"] == "P15" and run["status"] == "completed"
    # the run ends on the package; what that message set off (Agent 10's
    # log entry) is recorded too, as the run's tail
    assert [s["intent"] for s in run["steps"]] == ["data.request", "data.package", "interaction.log"]
    [w] = _kinds(sw, "after_action.written", "A1")
    text = open(w["path"], encoding="utf-8").read()
    assert "data.package: executed=yes" in text and "## playbook table\n- P15: PROPOSED" in text
    assert w["sha256"] and w["outcome"] == "completed"


def test_an_unsigned_authority_starts_nothing_the_hub_refuses_it(tmp_path):
    sw, signer = _swarm(tmp_path)
    forged = _env("human", "05", "listing.change.authorized", "L1",
                  {"new_listing": {"beds": 3, "price": 1}, "today": "2026-10-15"})
    sw.hub.send(forged)
    assert sw.runs.runs == {} and not _kinds(sw, "playbook.started")
    assert [e for e in _kinds(sw, "reject")]


# ------------------------------------------------------------------ two matches
def test_two_matches_run_neither_and_you_choose(tmp_path):
    sw, signer = _swarm(tmp_path, table=_two_match_table(tmp_path))
    res = sw.hub.send(_comp("A1"))
    assert res["status"] == "held" and res["candidates"] == ["P02", "P15", "P23"]
    assert not [e for e in _kinds(sw, "envelope.persisted", "A1") if e["intent"] == "data.request"]
    assert sw.runs.runs == {}
    out = _decide(sw, signer, "A1", "continue", {"playbook": "P23"})
    assert out["handler_result"].startswith("P23 started")
    assert [r["playbook"] for r in sw.runs.runs.values()] == ["P23"]
    assert [e for e in _kinds(sw, "envelope.persisted", "A1") if e["intent"] == "data.package"]


def test_a_choice_outside_the_matches_is_held_again_and_cancel_drops(tmp_path):
    sw, signer = _swarm(tmp_path, table=_two_match_table(tmp_path))
    sw.hub.send(_comp("A1"))
    out = _decide(sw, signer, "A1", "continue", {"playbook": "P99"})
    assert "held again" in out["handler_result"] and sw.runs.runs == {}
    out = _decide(sw, signer, "A1", "cancel")
    assert out["handler_result"] == "dropped"
    assert _kinds(sw, "playbook.start_dropped", "A1") and sw.runs.runs == {}


# --------------------------------------------------------------------- conflict
def _open_house(signer, ctx="L1"):
    return _signed(signer, "06", "config.update", ctx,
                   {"open_house": {"start": "2026-10-25T13:00", "end": "2026-10-25T15:00"}})


def _withdraw(signer, ctx="L1"):
    return _signed(signer, "05", "listing.change.authorized", ctx,
                   {"field": "status", "value": "withdrawn", "human_confirmation_ref": "w",
                    "live_verified": True, "today": "2026-10-16"})


def _live_listing_with_open_house(tmp_path):
    sw, signer = _swarm(tmp_path)
    _listing(sw, signer, "L1")
    sw.hub.send(_env("external", "09", "vendor.event", "L1",
                     {"kind": "photography", "event_kind": "deliverable_report",
                      "doc_type": "photo_package", "proof_artifact_present": True,
                      "content_hash": "h"}))
    assert sw.spokes["05"].mls_records["L1"]["status"] == "active"
    sw.hub.send(_open_house(signer))
    assert [r for r in sw.runs.runs.values() if r["playbook"] == "P04" and r["status"] == "open"]
    return sw, signer


def test_a_conflicting_start_holds_both_and_your_first_ends_the_other(tmp_path):
    sw, signer = _live_listing_with_open_house(tmp_path)
    res = sw.hub.send(_withdraw(signer))
    assert res["status"] == "held" and sw.spokes["05"].mls_records["L1"]["status"] == "active"
    [p04] = [r for r in sw.runs.runs.values() if r["playbook"] == "P04"]
    assert p04["status"] == "held"
    # the open run's next entry waits while both are held
    res = sw.hub.send(_signed(signer, "06", "config.update", "L1",
                              {"open_house_result": {"attendees": 3}}))
    assert res["status"] == "held" and _kinds(sw, "playbook.entry_waiting", "L1")
    _decide(sw, signer, "L1", "continue", {"first": "P05"})
    assert p04["status"] == "ended_by_your_sequencing"
    assert _kinds(sw, "playbook.entries_dropped")
    assert sw.spokes["05"].mls_records["L1"]["status"] == "withdrawn"
    [w] = [e for e in _kinds(sw, "after_action.written", "L1") if e["playbook"] == "P04"]
    assert any("playbook.sequenced" in d and "first=P05" in d for d in w["your_decisions"])


def test_putting_the_open_run_first_lets_it_finish_then_the_new_one_starts(tmp_path):
    sw, signer = _live_listing_with_open_house(tmp_path)
    sw.hub.send(_withdraw(signer))
    _decide(sw, signer, "L1", "continue", {"first": "P04"})
    assert sw.spokes["05"].mls_records["L1"]["status"] == "active", "the withdrawal waits"
    sw.hub.send(_signed(signer, "06", "config.update", "L1", {"open_house_result": {"attendees": 3}}))
    by = {r["playbook"]: r for r in sw.runs.runs.values()}
    assert by["P04"]["status"] == "completed"
    assert by["P05"]["status"] in ("open", "completed")
    assert sw.spokes["05"].mls_records["L1"]["status"] == "withdrawn"


def test_cancel_on_a_conflict_drops_the_new_message_and_the_open_run_goes_on(tmp_path):
    sw, signer = _live_listing_with_open_house(tmp_path)
    sw.hub.send(_withdraw(signer))
    _decide(sw, signer, "L1", "cancel")
    [p04] = [r for r in sw.runs.runs.values() if r["playbook"] == "P04"]
    assert p04["status"] == "open" and sw.spokes["05"].mls_records["L1"]["status"] == "active"
    assert not [r for r in sw.runs.runs.values() if r["playbook"] == "P05"]


# ------------------------------------------------------------- full queue, siding
def _fill(sw, signer, n):
    for i in range(n):
        sw.hub.send(_signed(signer, "02", "config.update", f"Q{i}", {"bogus_setting": i}))


def _ack(sw, ctx):
    from dispatcher.escalation_watch import acknowledge
    acknowledge(sw.hub, "clarification.request", ctx, "t")
    sw.runs.release_waiting()


def test_a_full_queue_holds_new_starts_and_releases_them_by_class(tmp_path):
    assert run_tracker.CAP_OPEN_QUESTIONS == 25
    sw, signer = _swarm(tmp_path)
    _fill(sw, signer, 25)
    assert sw.runs.open_questions() == 25
    r1 = sw.hub.send(_env("external", "19", "discovery.feed", "P1",
                          {"listing_id": "P1", "zip_code": "44101", "source": "x",
                           "status": "new", "today": "2026-10-16"}))
    r2 = sw.hub.send(_comp("A1", playbook="P15"))
    r3 = sw.hub.send(_comp("A2", playbook="P23"))
    assert all(r["status"] == "held" and r.get("waiting") for r in (r1, r2, r3))
    assert len(_kinds(sw, "escalation.raised")) == len(
        [e for e in _kinds(sw, "escalation.raised") if e["queue"] == "escalation.queue_full"]) == 1
    _ack(sw, "Q0")
    [rel] = _kinds(sw, "playbook.waiting_released")
    # neither A1 nor A2 is a live listing of ours, so both comps requests are
    # P15 (class 3); prospecting P24 is class 4: the two class-3 first, older
    # first
    assert rel["order"][0].startswith("P15:A1") and rel["order"][1].startswith("P15:A2") \
        and rel["order"][2].startswith("P24:P1")
    # both P15 starts go to Agent 10: the later one waited on the siding
    # behind the earlier (equal class, arrival order)
    holds = _kinds(sw, "siding.hold")
    assert [h["run"] for h in holds] == [rel["order"][1]] and holds[0]["sided_by"] == rel["order"][0]
    assert _kinds(sw, "siding.resume")
    assert sorted(r["playbook"] for r in sw.runs.runs.values()) == ["P15", "P15", "P24"]


# ------------------------------------------------------------------- legal line
def test_an_agent_step_the_track_refuses_halts_the_run_as_a_playbook_defect(tmp_path):
    sw, signer = _live_listing_with_open_house(tmp_path)
    sw.hub.send(_env("06", "external", "client.message.send", "L1", {"template": "x"}))
    [p04] = [r for r in sw.runs.runs.values() if r["playbook"] == "P04"]
    assert p04["status"] == "halted"
    [v] = _kinds(sw, "playbook.integrity_violation", "L1")
    assert "defect in the playbook" in v["reason"]
    assert sw.hub.queues["integrity.violation"][-1]["violation"] == "playbook_step_off_track"


# ------------------------------------------------------- proposed tuples, owner end
def test_an_unlisted_crossing_in_a_run_is_proposed_as_a_tuple(tmp_path):
    sw, signer = _live_listing_with_open_house(tmp_path)
    sw.hub.send(_env("external", "11", "client.reply", "L1",
                     {"message": "Can you run the ad on Instagram too?", "owning_agent": "12",
                      "today": "2026-10-16"}))
    [p04] = [r for r in sw.runs.runs.values() if r["playbook"] == "P04"]
    out = sw.runs.end_by_owner(p04["run_id"], "ended_by_owner", "tester")
    assert out["ended"]
    [w] = [e for e in _kinds(sw, "after_action.written", "L1") if e["playbook"] == "P04"]
    assert w["outcome"] == "ended_by_owner"
    assert len(w["proposed_tuples"]) == 1 and "Instagram" in w["proposed_tuples"][0]
    assert "proposed, not ratified" in open(w["path"], encoding="utf-8").read()


# ------------------------------------------------------------------- restarts
def test_runs_and_a_held_choice_survive_a_restart(tmp_path):
    signer = Ed25519Signer()
    table = _two_match_table(tmp_path)
    sw, _ = _swarm(tmp_path, state_db=True, signer=signer, table=table)
    _listing(sw, signer, "L1", live=False)
    sw.hub.send(_comp("A1"))
    sw.save_state()
    sw.close()
    sw2, _ = _swarm(tmp_path, state_db=True, signer=signer, table=table)
    assert sw2.runs.open_runs() == ["P01-L1-1"]
    out = _decide(sw2, signer, "A1", "continue", {"playbook": "P15"})
    assert out["handler_result"].startswith("P15 started")
    assert [e for e in _kinds(sw2, "envelope.persisted", "A1") if e["intent"] == "data.package"]


def test_the_identity_reload_counts_open_runs(tmp_path):
    from dispatcher.identity_reload import open_work
    sw, signer = _swarm(tmp_path)
    _listing(sw, signer, "L1", live=False)
    assert open_work(sw)["open_runs"] == ["P01-L1-1"]


def test_a_tracker_failure_never_blocks_the_hub(tmp_path, monkeypatch):
    sw, signer = _swarm(tmp_path)
    monkeypatch.setattr(sw.runs.table, "starts_for", lambda env: 1 / 0)
    res = sw.hub.send(_comp("A1", playbook="P15"))
    assert res["status"] == "ack"
    errs = _kinds(sw, "playbook.tracker_error", "A1")
    assert errs and all("ZeroDivisionError" in e["error"] for e in errs) and sw.runs.errors
    assert [e for e in _kinds(sw, "envelope.persisted", "A1") if e["intent"] == "data.package"]


def test_a_playbook_signed_on_its_own_runs_ratified(tmp_path):
    table = json.load(open(os.path.join(ROOT, "identity", "playbooks.json")))
    table["playbooks"]["P15"]["ratified"] = "RATIFIED 2026-10-21 Jeff Phillips (walkthrough)"
    path = tmp_path / "t.json"
    path.write_text(json.dumps(table))
    sw, _ = _swarm(tmp_path)
    rt = run_tracker.RunTracker(sw, table_path=str(path))
    assert rt.table.status_for("P15") == "RATIFIED" and rt.table.status_for("P23") == "PROPOSED"
    assert "P15" in [e for e in _kinds(sw, "playbook.table")][-1]["ratified_playbooks"]



def test_a_comparables_request_is_p23_on_a_live_listing_and_p15_otherwise(tmp_path):
    """Owner decision 2026-10-21 (comps): no hold; the listing decides."""
    sw, signer = _live_listing_with_open_house(tmp_path)
    sw.hub.send(_comp("L1"))
    sw.hub.send(_comp("A9"))
    by_ctx = {r["ctx"]: r["playbook"] for r in sw.runs.runs.values() if r["playbook"] in ("P15", "P23", "P02")}
    assert by_ctx == {"L1": "P23", "A9": "P15"}
    assert not _kinds(sw, "playbook.ambiguous")
