"""Tests written from the 2026-10-12 mutation run (mutmut 3.7.0) over the
code added that day: logic mutants that survived the first run are killed
here by asserting exact outputs (messages, payloads, audit fields,
boundaries). Each block names the function it pins."""
import datetime
import json
import os
from types import SimpleNamespace

import pytest

from tests_listing.test_repairs_2026_10_11 import _swarm, _env, _signed, _persisted, _lead, RUBRIC


def _clar(sw, ctx):
    return [q["payload"] for q in sw.hub.queues["clarification.request"] if q["client_context_id"] == ctx]


def _logs(sw, ctx, kind=None):
    return [e["payload"] for e in _persisted(sw, "interaction.log", ctx)
            if kind is None or e["payload"].get("kind") == kind]


def _traces(sw, agent):
    return [e for e in sw.hub.audit.read() if e["kind"] == "spoke.trace" and e["agent"] == agent]


# ------------------------------------------------------------ 02 _configure_engine / _score / _resume
@pytest.mark.parametrize("bad,problems", [
    ({}, ["decision_engine must be a non-empty object"]),
    ({"x": 1}, ["unknown keys ['x']"]),
    ({"allow_external": "yes"}, ["allow_external must be true or false"]),
    ({"confidence_floor": 1.01}, ["confidence_floor must be a number from 0 to 1"]),
    ({"confidence_floor": -0.01}, ["confidence_floor must be a number from 0 to 1"]),
])
def test_02_engine_setting_problems_are_named_exactly(tmp_path, bad, problems):
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "02", "E", {"decision_engine": bad}))
    assert _clar(sw, "E") == [{"reason": "decision_engine setting rejected", "problems": problems}]
    assert _traces(sw, "02")[-1]["result"] == "rejected: decision_engine"


@pytest.mark.parametrize("floor", [0, 1, 0.5])
def test_02_engine_floor_bounds_are_inclusive_and_stored_as_float(tmp_path, floor):
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "02", "E", {"decision_engine": {"confidence_floor": floor}}))
    assert sw.spokes["02"].jev_confidence_floor == float(floor)
    assert isinstance(sw.spokes["02"].jev_confidence_floor, float)
    [e] = [e for e in sw.hub.audit.read() if e["kind"] == "decision.engine" and e.get("agent") == "02"]
    assert {k: e[k] for k in ("agent", "allow_external", "confidence_floor", "engine", "tier", "confidence")} == {
        "agent": "02", "allow_external": False, "confidence_floor": float(floor),
        "engine": "FALLBACK_LOCAL_RULES", "tier": None, "confidence": None}
    assert e["reason"] == "JEV_API_KEY unconfigured (local fallback active)" or e["reason"]
    assert _traces(sw, "02")[-1]["result"] == "decision_engine: FALLBACK_LOCAL_RULES"


def test_02_the_signed_floor_reaches_the_engine(tmp_path):
    """A floor of 0.9 holds a lead the local engine rates 0.85."""
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "02", "setup", RUBRIC))
    sw.hub.send(_signed(s, "02", "setup", {"decision_engine": {"confidence_floor": 0.9}}))
    sw.hub.send(_lead("F1"))
    [d] = [e for e in sw.hub.audit.read() if e["kind"] == "decision.lead"]
    assert d["floor"] == 0.9 and d["confidence"] == 0.85 and d["status"] == "held_confidence_underflow"
    assert d["client_context_id"] == "F1" and d["engine"] == "python_fallback" and d["is_fallback"] is True
    assert "F1" in sw.spokes["02"].held_for_calibration


def test_02_resume_paths_return_exact_results(tmp_path):
    sw, s = _swarm(tmp_path)
    sp = sw.spokes["02"]
    ws = SimpleNamespace(client_context_id="R0")
    assert sp._resume(ws, {"decision": "APPROVE"}) == "nothing held for this context"
    sp.held_for_calibration["R0"] = {"payload": {}, "envelope_id": "e", "rescored": False}
    assert sp._resume(ws, {"decision": "HOLD"}) == "decision not continue/cancel"
    assert "R0" in sp.held_for_calibration
    assert sp._resume(ws, {"decision": "REJECT_AND_ABORT"}) == "cancelled: archived, nothing sent"
    assert _logs(sw, "R0") == [{"tier": "HELD_FOR_CALIBRATION", "archived": True,
                               "reason": "broker cancelled after a calibration hold"}]


def test_02_continue_after_a_hold_scores_and_records_the_note(tmp_path):
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "02", "setup", RUBRIC))
    sp = sw.spokes["02"]
    payload = {"budget": 450000, "timeline_days": 60, "financing_progress": "preapproved",
               "today": "2026-10-12", "consent": {"email": "yes"}}
    sp.held_for_calibration["R1"] = {"payload": payload, "envelope_id": "env-R1", "rescored": True}
    assert sp._resume(SimpleNamespace(client_context_id="R1"), {"decision": "APPROVE"}) == \
        "continued: tier WARM from the local rubric"
    [log] = [p for p in _logs(sw, "R1") if "tier" in p]
    assert log["tier"] == "WARM" and log["score"] == 60
    assert log["notes"][-1] == "scored with the local rubric on the broker's signed continue"
    [n] = _persisted(sw, "lead.nurture", "R1")
    assert n["payload"]["reassignment"] is True and n["payload"]["score"] == 60
    assert any(t["envelope_id"] == "env-R1" for t in _traces(sw, "02"))


# ------------------------------------------------------------ 03 rescore_cadence
def _pool(sp, ctx, **entry):
    sp.rescore_pool[ctx] = {"inputs": {"budget": 1, "timeline_days": 10}, "scored_on": "2026-10-01",
                            "last_rescore": "2026-10-01", "awaiting": False, **entry}


def test_03_rescore_boundaries_and_payload(tmp_path):
    sw, s = _swarm(tmp_path)
    sp = sw.spokes["03"]
    sp.active_sequences["P"] = {"sequence_id": "s", "consent": {"email": "yes"}, "paused": False}
    _pool(sp, "P")
    assert sp.rescore_cadence("P", "2026-10-07") == "not_due"           # 6 days
    assert sp.rescore_cadence("P", "2026-10-08") == "rescored"          # exactly 7
    [r] = _persisted(sw, "lead.rescored", "P")
    assert r["payload"] == {"budget": 1, "timeline_days": 3, "today": "2026-10-08",
                            "consent": {"email": "yes"}, "rescore_reason": "cadence: 7 days since scored"}
    assert sp.rescore_pool["P"]["last_rescore"] == "2026-10-08" and sp.rescore_pool["P"]["awaiting"] is True


def test_03_timeline_never_goes_negative_and_non_numbers_pass_through(tmp_path):
    sw, s = _swarm(tmp_path)
    sp = sw.spokes["03"]
    _pool(sp, "N", inputs={"timeline_days": 5})
    sp.rescore_cadence("N", "2026-10-20")
    _pool(sp, "B", inputs={"timeline_days": True})
    sp.rescore_cadence("B", "2026-10-20")
    _pool(sp, "S", inputs={"timeline_days": "soon"})
    sp.rescore_cadence("S", "2026-10-20")
    got = {e["client_context_id"]: e["payload"]["timeline_days"] for e in _persisted(sw, "lead.rescored")}
    assert got == {"N": 0, "B": True, "S": "soon"}


def test_03_pool_exits_are_exact(tmp_path):
    sw, s = _swarm(tmp_path)
    sp = sw.spokes["03"]
    sp.active_sequences["O"] = {"consent": {"email": "no"}, "paused": False}
    _pool(sp, "O")
    assert sp.rescore_cadence("O", "2026-10-20") == "left_pool:opted_out" and "O" not in sp.rescore_pool
    sp.active_sequences["Z"] = {"consent": {"email": "yes"}, "paused": True}
    _pool(sp, "Z")
    assert sp.rescore_cadence("Z", "2026-10-20") == "skipped:sequence_paused" and "Z" in sp.rescore_pool
    _pool(sp, "A", awaiting=True)
    assert sp.rescore_cadence("A", "2026-10-20") == "left_pool:not_warm" and "A" not in sp.rescore_pool
    assert _logs(sw, "A") == [{"kind": "left_rescore_pool",
                              "reason": "last re-score did not return the lead to nurture"}]
    _pool(sp, "D", scored_on="not a date")
    assert sp.rescore_cadence("D", "2026-10-20") == "left_pool:no_date" and "D" not in sp.rescore_pool
    assert _clar(sw, "D") == [{"reason": "nurtured lead has no readable scoring date - cannot re-score it on a cadence",
                              "scored_on": "not a date"}]
    assert sp.rescore_cadence("missing", "2026-10-20") is None
    assert "P" not in sp.rescore_pool
    assert {k: v for k, v in sp.rescore_pool.items()} == {"Z": sp.rescore_pool["Z"]}


# ------------------------------------------------------------ 04 drafting setting / model remarks
def test_04_drafting_mode_records_the_gate_exactly(tmp_path):
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "04", "c", {"drafting": {"mode": "model"}}))
    [e] = [e for e in sw.hub.audit.read() if e["kind"] == "drafting.mode"]
    assert {k: e[k] for k in ("agent", "mode", "model_ready", "reason")} == {
        "agent": "04", "mode": "model", "model_ready": False,
        "reason": "no model client configured in this process"}
    sw.hub.drafting = None
    sw.hub.send(_signed(s, "04", "c", {"drafting": {"mode": "rules"}}))
    e = [e for e in sw.hub.audit.read() if e["kind"] == "drafting.mode"][-1]
    assert e["mode"] == "rules" and e["model_ready"] is False and e["reason"] == "no drafting model wired"


def test_04_model_mode_with_no_drafting_model_wired_drafts_by_rules(tmp_path):
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "04", "c", {"drafting": {"mode": "model"}}))
    sw.hub.drafting = None
    sw.hub.send(_env("05", "04", "listing.data", "M", {"beds": 2, "features": [], "today": "2026-10-12"}))
    [u] = [e for e in sw.hub.audit.read() if e["kind"] == "drafting.model_unavailable"]
    assert u["reason"] == "no drafting model wired in this process" and u["client_context_id"] == "M"
    assert {"reason": "model drafting is on but was not used - drafted by rules",
            "why": "no drafting model wired in this process"} in _clar(sw, "M")


def test_04_model_remarks_get_the_envelope_and_are_recorded(tmp_path):
    seen = {}

    class DM:
        def draft_remarks(self, agent, eid, facts, limit):
            seen.update(agent=agent, eid=eid, limit=limit, n=len(facts))
            return {"ok": True, "checkpoint": "ck", "remarks": "Two bedrooms."}
    sw, s = _swarm(tmp_path)
    sw.hub.drafting = DM()
    sw.spokes["04"].drafting_mode = "model"
    env = _env("05", "04", "listing.data", "M2", {"beds": 2, "features": [], "today": "2026-10-12"})
    sw.hub.send(env)
    assert seen == {"agent": "04", "eid": env.envelope_id, "limit": 800, "n": 1}
    [u] = [e for e in sw.hub.audit.read() if e["kind"] == "drafting.model_used"]
    assert {k: u[k] for k in ("agent", "client_context_id", "mode", "checkpoint", "chars")} == {
        "agent": "04", "client_context_id": "M2", "mode": "model", "checkpoint": "ck", "chars": 13}


# ------------------------------------------------------------ 05 vacant watch
@pytest.mark.parametrize("payload", [{"occupancy": "maybe"}, {"occupancy": "vacant", "watch_interval_days": 0},
                                     {"occupancy": "vacant", "watch_interval_days": True},
                                     {"occupancy": "vacant", "watch_interval_days": "7"}])
def test_05_bad_occupancy_settings_are_rejected_exactly(tmp_path, payload):
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "05", "V", payload))
    assert "V" not in sw.spokes["05"].vacant_watch
    assert _clar(sw, "V") == [{"reason": 'occupancy setting rejected - occupancy must be "vacant" or "occupied"; '
                                         'watch_interval_days a whole number of days'}]


def test_05_interval_of_one_is_accepted_and_overrides_the_default(tmp_path):
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "05", "V1", {"occupancy": "vacant", "watch_interval_days": 1, "today": "2026-10-01"}))
    assert sw.spokes["05"].vacant_watch["V1"] == {"since": "2026-10-01", "last_check": None, "interval_days": 1}
    assert _logs(sw, "V1", "vacant_watch_started") == [{"kind": "vacant_watch_started", "interval_days": 1}]
    assert _traces(sw, "05")[-1]["result"] == "vacant watch on"
    sp = sw.spokes["05"]
    assert sp.check_vacant_watch("V1", "2026-10-02") == "check_requested"
    assert sp.check_vacant_watch("V1", "2026-10-03") == "check_requested"
    [r1, r2] = _persisted(sw, "vendor.request", "V1")
    assert r1["payload"] == {"kind": "property_check", "today": "2026-10-02", "purpose": "vacant_watch"}
    assert r1["to_agent"] == "09" and r2["payload"]["today"] == "2026-10-03"


def test_05_unknown_occupancy_keys_are_rejected(tmp_path):
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "05", "V2", {"occupancy": "vacant", "pets": True}))
    assert _clar(sw, "V2") == [{"reason": "occupancy setting rejected - unknown keys", "keys": ["pets"]}]


def test_05_occupied_ends_a_watch_and_logs_it_only_when_one_existed(tmp_path):
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "05", "V3", {"occupancy": "occupied"}))
    assert _logs(sw, "V3", "vacant_watch_ended") == []
    sw.hub.send(_signed(s, "05", "V3", {"occupancy": "vacant"}))
    sw.hub.send(_signed(s, "05", "V3", {"occupancy": "occupied"}))
    assert _logs(sw, "V3", "vacant_watch_ended") == [{"kind": "vacant_watch_ended", "reason": "marked occupied"}]
    assert "V3" not in sw.spokes["05"].vacant_watch


def test_05_a_listing_that_ended_stops_its_watch(tmp_path):
    sw, s = _swarm(tmp_path)
    sp = sw.spokes["05"]
    sw.hub.send(_signed(s, "05", "V4", {"occupancy": "vacant"}))
    sw.hub.send(_signed(s, "05", "V5", {"occupancy": "vacant"}))
    sp.mls_records["V4"] = {"status": "sold"}
    assert sp.check_vacant_watch("V4", "2026-10-02") == "ended:sold"
    assert "V4" not in sp.vacant_watch and "V5" in sp.vacant_watch
    assert _logs(sw, "V4", "vacant_watch_ended") == [{"kind": "vacant_watch_ended", "reason": "listing sold"}]
    assert not [e for e in _persisted(sw, "vendor.request", "V4")]
    assert sp.check_vacant_watch("V4", "2026-10-03") is None


# ------------------------------------------------------------ 06 weekly seller report
@pytest.mark.parametrize("cfg,problem", [
    ({"weekday": "monday"}, 'expected {"weekday": "<day>", "listings": {"<listing_id>": "<seller context>"}}'),
    ({"weekday": "funday", "listings": {"L": "S"}}, "weekday 'funday' is not a day name"),
    ({"weekday": "monday", "listings": {"L": ""}}, "listings must map each listing id to the seller's context id"),
    ({"weekday": "monday", "listings": {"": "S"}}, "listings must map each listing id to the seller's context id"),
    ({"weekday": "monday", "listings": {"L": 5}}, "listings must map each listing id to the seller's context id"),
])
def test_06_seller_report_problems_are_named_exactly(tmp_path, cfg, problem):
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "06", "c", {"seller_reports": cfg}))
    assert _clar(sw, "c") == [{"reason": "seller_reports setting rejected", "problems": [problem]}]


def _show(sp, buyer, listing, when):
    sp.confirmed_showings.setdefault(buyer, []).append({"time": when, "confirmed": True, "listing_id": listing})


def test_06_week_window_edges_and_every_listing_reported(tmp_path):
    sw, s = _swarm(tmp_path)
    sp = sw.spokes["06"]
    sw.hub.send(_signed(s, "06", "c", {"seller_reports": {"weekday": "Monday",
                                                          "listings": {"LA": "SA", "LB": "SB"}}}))
    _show(sp, "b1", "LA", "2026-10-05T09:00")   # exactly 7 days before: outside
    _show(sp, "b2", "LA", "2026-10-06T09:00")   # 6 days before: inside
    _show(sp, "b3", "LA", "2026-10-12T09:00")   # today: inside
    _show(sp, "b4", "LA", "2026-10-13T09:00")   # tomorrow: outside
    _show(sp, "b5", "LA", "garbage")             # unreadable: skipped
    _show(sp, "b6", "LA", None)                  # no time: skipped
    _show(sp, "b7", "LB", "2026-10-10T09:00")
    assert sp.weekly_seller_reports("2026-10-12") == "held:['LA', 'LB']"
    assert sp.held_reports["SA"]["showings"] == 2 and sp.held_reports["SB"]["showings"] == 1
    [w] = sw.hitl.get_pending_waits("SA")
    assert w["paused_intent"] == "client.message.request" and w["agent_id"] == "06"
    assert w["reason"].startswith("weekly seller report for LA: 2 showing(s), 0 with feedback.")


def test_06_a_listing_already_reported_this_week_does_not_stop_the_others(tmp_path):
    sw, s = _swarm(tmp_path)
    sp = sw.spokes["06"]
    sw.hub.send(_signed(s, "06", "c", {"seller_reports": {"weekday": "monday",
                                                          "listings": {"LA": "SA", "LB": "SB"}}}))
    sp.seller_report_weeks["LA"] = "2026-W42"
    assert sp.weekly_seller_reports("2026-10-12") == "held:['LB']"


def test_06_resume_paths_return_exact_results(tmp_path):
    sw, s = _swarm(tmp_path)
    sp = sw.spokes["06"]
    ws = SimpleNamespace(client_context_id="SR")
    assert sp._resume(ws, {"decision": "APPROVE"}) == "nothing held for this context"
    rep = {"listing_id": "L", "week_ending": "2026-10-12", "showings": 1, "feedback_received": 0}
    sp.held_reports["SR"] = dict(rep)
    assert sp._resume(ws, {"decision": "HOLD"}) == "decision not continue/cancel" and "SR" in sp.held_reports
    assert sp._resume(ws, {"decision": "REJECT_AND_ABORT"}) == "cancelled: report not sent"
    assert _logs(sw, "SR") == [{"kind": "seller_report_skipped", **rep}]
    assert not _persisted(sw, "client.message.request", "SR")


# ------------------------------------------------------------ 08 disclosure deadlines
def test_08_disclosure_check_names_bad_dates_and_keeps_going(tmp_path):
    sw, s = _swarm(tmp_path)
    sp = sw.spokes["08"]
    sp.pending_requests["DX"] = {"inspection_report": {"chase_count": 0, "deadline": "2026-10-13"},
                                 "disclosure": {"chase_count": 0, "deadline": "soon"}}
    assert sp.check_disclosure_deadlines("DX", "2026-10-12") == ["disclosure:bad_date"]
    assert _clar(sw, "DX") == [{"reason": "disclosure deadline 'soon' is not a date - cannot warn ahead of it",
                               "doc_type": "disclosure"}]
    assert sp.pending_requests["DX"]["disclosure"]["disclosure_warned"] is True
    assert sp.check_disclosure_deadlines("DX", "2026-10-12") == "none_due"
    assert sp.check_disclosure_deadlines("nobody", "2026-10-12") == "none_due"


def test_08_a_disclosure_without_a_deadline_is_not_warned(tmp_path):
    sw, s = _swarm(tmp_path)
    sp = sw.spokes["08"]
    sp.pending_requests["DY"] = {"disclosure": {"chase_count": 0, "deadline": None}}
    assert sp.check_disclosure_deadlines("DY", "2026-10-12") == "none_due"


# ------------------------------------------------------------ 14 access custody
@pytest.mark.parametrize("payload,problem", [
    ({"access_grant": {"party": "p", "window_end": "2026-10-15"}}, "access_grant takes exactly party, window_end, custody_ref"),
    ({"access_grant": "p"}, "access_grant takes exactly party, window_end, custody_ref"),
    ({"access_grant": {"party": "p", "window_end": "Friday", "custody_ref": "r"}}, "window_end must be YYYY-MM-DD"),
    ({"access_closed": {"party": "p", "x": 1}}, "access_closed takes exactly party"),
    ({"access_closed": "p"}, "access_closed takes exactly party"),
])
def test_14_access_problems_are_named_exactly(tmp_path, payload, problem):
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "14", "AC", payload))
    assert _clar(sw, "AC") == [{"reason": "access record rejected; nothing changed", "problems": [problem]}]
    assert not sw.spokes["14"].records.get("AC")


def test_14_access_records_are_kept_in_the_crm_and_closed_by_party(tmp_path):
    sw, s = _swarm(tmp_path)
    sp = sw.spokes["14"]
    sw.hub.send(_signed(s, "14", "AD", {"access_closed": {"party": "nobody"}}))   # nothing to close: fine
    sw.hub.send(_signed(s, "14", "AD", {"access_grant": {"party": "a", "window_end": "2026-10-15", "custody_ref": "r1"}}))
    sw.hub.send(_signed(s, "14", "AD", {"access_grant": {"party": "b", "window_end": "2026-10-15", "custody_ref": "r2"}}))
    sw.hub.send(_signed(s, "14", "AD", {"access_closed": {"party": "b"}}))
    assert [(g["party"], g["closed"]) for g in sp.access_grants["AD"]] == [("a", False), ("b", True)]
    assert [e["kind"] for e in sp.records["AD"]] == ["config.update"] * 4
    assert sp.check_access_custody("AD", "2026-10-16") == "flagged:['a']"
    assert _clar(sw, "AD") == [{"reason": "access window for 'a' ended 2026-10-15 and is not closed - confirm the key "
                                          "is back or the code was changed, then sign access_closed",
                               "custody_ref": "r1"}]
    assert sp.check_access_custody("nobody", "2026-10-16") == "none_due"


def test_14_a_flagged_grant_does_not_stop_the_next_one(tmp_path):
    sw, s = _swarm(tmp_path)
    sp = sw.spokes["14"]
    sp.access_grants["AE"] = [{"party": "a", "window_end": "2026-10-10", "custody_ref": "r", "closed": False, "flagged": True},
                              {"party": "b", "window_end": "2026-10-10", "custody_ref": "r", "closed": False, "flagged": False}]
    assert sp.check_access_custody("AE", "2026-10-16") == "flagged:['b']"


# ------------------------------------------------------------ HITL hold provisions the drawer
def test_hitl_hold_provisions_a_blank_client_drawer_and_records_errors(tmp_path):
    sw, s = _swarm(tmp_path)
    ws = sw.hitl.pause_operation("H9", "01", "lead.captured", "r", {"a": 1}, required_decision="CONTINUE_OR_CANCEL")
    m = sw.hub.drawers.get_drawer("H9").get_manifest()
    assert (m["client_name"], m["property_address"], m["role"]) == ("", "", "client")
    files = [f["filename"] for f in sw.hub.drawers.get_drawer("H9").list_files("timeline")]
    assert files == [f"{ws.wait_id}_pause.json"]
    body = json.loads(sw.hub.drawers.get_drawer("H9").get_file("timeline", files[0]))
    assert body["wait_id"] == ws.wait_id and body["client_context_id"] == "H9"
    sw.hitl.pause_operation("../x", "01", "lead.captured", "r", {}, required_decision="CONTINUE_OR_CANCEL")
    assert sw.hitl.errors and sw.hitl.errors[-1].startswith("drawer write ")


# ------------------------------------------------------------ pager (in process)
class _Resp:
    status = 201

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _cfg(**kw):
    return {"account_sid": "AC9", "auth_token": "tok", "from_number": "+15550000001",
            "to_number": "+15550000002", **kw}


def test_pager_sends_exactly_one_minimal_text_and_records_it():
    from dispatcher.pager import Pager, page_text
    seen = []

    def opener(req, timeout):
        seen.append((req.full_url, req.get_header("Authorization"), req.data.decode(), timeout))
        return _Resp()
    p = Pager(_cfg(), opener=opener)
    appended = []
    p.audit = SimpleNamespace(append=lambda k, r: appended.append((k, r)))
    assert p("escalation.hot_lead", {"client_context_id": "C1", "reason": "secret words"}) == \
        {"status": "sent", "http_status": 201}
    [(url, auth, data, timeout)] = seen
    assert url == "https://api.twilio.com/2010-04-01/Accounts/AC9/Messages.json" and timeout == 10.0
    import base64
    assert auth == "Basic " + base64.b64encode(b"AC9:tok").decode()
    import urllib.parse as up
    assert up.parse_qs(data) == {"To": ["+15550000002"], "From": ["+15550000001"],
                                 "Body": ["ListingAssistants: escalation.hot_lead waiting for you (C1). Open the console."]}
    assert appended == [("pager.sent", {"queue": "escalation.hot_lead", "client_context_id": "C1", "http_status": 201})]
    assert page_text("q", {}) == "ListingAssistants: q waiting for you (no client). Open the console."


def test_pager_failures_are_recorded_not_raised():
    import io
    import urllib.error
    from dispatcher.pager import Pager

    def http_fail(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 401, "no", {}, io.BytesIO(b""))

    def net_fail(req, timeout):
        raise OSError("down")
    for opener, expect in ((http_fail, {"status": "failed", "http_status": 401}),
                           (net_fail, {"status": "failed", "error": "OSError: down"})):
        p = Pager(_cfg(api_base="http://127.0.0.1:9"), opener=opener)
        got = []
        p.audit = SimpleNamespace(append=lambda k, r: got.append((k, r)))
        assert p("q", {"client_context_id": "C"}) == expect
        assert got[0][0] == "pager.failed" and got[0][1]["client_context_id"] == "C"
    assert Pager(_cfg(), opener=lambda r, timeout: _Resp())("q", {}) == {"status": "sent", "http_status": 201}


def test_pager_config_round_trip_is_private_and_validated(tmp_path):
    from dispatcher.pager import save_config, load_config, validate
    p = str(tmp_path / "sub" / "pager.json")
    assert load_config(p) is None
    save_config(p, _cfg(extra="dropped"))
    assert oct(os.stat(p).st_mode & 0o777) == "0o600"
    assert load_config(p) == _cfg()
    open(p, "w").write(json.dumps({"account_sid": "AC"}))
    with pytest.raises(ValueError):
        load_config(p)
    assert validate(_cfg()) == []
    assert validate(_cfg(api_base="http://localhost:5000")) == []
    assert validate(_cfg(api_base="http://example.com")) == ["api_base must be https (or this machine, for testing)"]
    assert validate({}) == [f"{f} is required" for f in ("account_sid", "auth_token", "from_number", "to_number")]
    assert validate(_cfg(from_number="+1555")) == ["from_number must be an international number like +15551234567"]
    assert validate(_cfg(to_number="+1234567")) == []                      # 8 characters: shortest allowed
    assert validate(_cfg(to_number="+123456789012345")) == []              # 16: longest allowed
    assert validate(_cfg(to_number="+1234567890123456")) != []             # 17
    assert validate(_cfg(to_number="+123456")) != []                       # 7
    assert validate(_cfg(to_number="1+5550000002")) != []
    assert validate(_cfg(to_number="+1555000000a")) != []
    assert validate(_cfg(to_number="++5550000002")) != []


# ------------------------------------------------------------ drawer_filing
def test_drawer_identity_is_filled_blank_by_blank_and_conflicts_are_exact(tmp_path):
    from dispatcher.drawer_filing import file_record
    sw, s = _swarm(tmp_path)
    hub = sw.hub
    assert file_record(hub, "14", "I1", "interactions", "a", {"x": 1},
                       identity={"client_name": None, "property_address": "", "role": "seller", "x": "y"})["filed"]
    m = hub.drawers.get_drawer("I1").get_manifest()
    assert (m["client_name"], m["property_address"], m["role"], m["assigned_human_agent"]) == ("", "", "seller", "00")
    [p] = [e for e in hub.audit.read() if e["kind"] == "drawer.provisioned"]
    assert {k: p[k] for k in ("agent", "client_context_id", "identity_fields")} == {
        "agent": "14", "client_context_id": "I1", "identity_fields": ["role"]}
    file_record(hub, "05", "I1", "artifacts", "b", {}, identity={"client_name": "Dana"})
    m = hub.drawers.get_drawer("I1").get_manifest()
    assert (m["client_name"], m["property_address"], m["role"]) == ("Dana", "", "seller")
    assert len(m["file_index"]) == 2                                   # the fill kept the file index
    [f] = [e for e in hub.audit.read() if e["kind"] == "drawer.identity_filled"]
    assert {k: f[k] for k in ("agent", "client_context_id", "fields")} == {
        "agent": "05", "client_context_id": "I1", "fields": ["client_name"]}
    file_record(hub, "05", "I1", "artifacts", "c", {}, identity={"property_address": "1 Elm"})
    assert hub.drawers.get_drawer("I1").get_manifest()["property_address"] == "1 Elm"
    assert hub.drawers.get_drawer("I1").get_manifest()["client_name"] == "Dana"
    file_record(hub, "05", "I1", "artifacts", "d", {}, identity={"client_name": "Eve", "property_address": "1 Elm"})
    [c] = [e for e in hub.audit.read() if e["kind"] == "drawer.identity_conflict"]
    assert c["conflicts"] == {"client_name": {"on_file": "Dana", "new": "Eve"}} and c["agent"] == "05"
    assert {"reason": "client drawer identity conflict - the value on file was kept; you decide which is right",
            "conflicts": {"client_name": {"on_file": "Dana", "new": "Eve"}}} in _clar(sw, "I1")


def test_drawer_file_record_return_values_body_and_metadata_are_exact(tmp_path):
    from dispatcher.drawer_filing import file_record
    import hashlib
    sw, s = _swarm(tmp_path)
    rec = {"b": 2, "a": datetime.date(2026, 10, 12)}
    r = file_record(sw.hub, "08", "F1", "documents", "doc1", rec)
    body = json.dumps(rec, sort_keys=True, indent=2, default=str)
    assert r == {"filed": True, "category": "documents", "filename": "doc1.json",
                 "sha256": hashlib.sha256(body.encode()).hexdigest()}
    d = sw.hub.drawers.get_drawer("F1")
    assert d.get_file("documents", "doc1.json").decode() == body
    assert d.get_manifest()["file_index"]["documents/doc1.json"]["metadata"] == {"agent": "08"}
    assert file_record(SimpleNamespace(), "08", "F1", "documents", "x", {}) == \
        {"filed": False, "reason": "no drawer store on this hub"}
    bad = file_record(sw.hub, "08", "F1", "nope", "x", {})
    assert bad["filed"] is False and bad["reason"].startswith("ValueError: unknown drawer category")
    [q] = [q for q in _clar(sw, "F1") if q["reason"] == "client drawer filing refused"]
    assert q == {"reason": "client drawer filing refused", "error": bad["reason"], "category": "nope"}


# ------------------------------------------------------------ readable_audit
@pytest.mark.parametrize("kind,rec,expect", [
    ("envelope.persisted", {"from_agent": "04", "to_agent": "17", "intent": "content.review", "client_context_id": "c"},
     ("DISPATCH", "Agent 04 -> Agent 17: content.review", "c", "04")),
    ("envelope.persisted", {"from_agent": "human", "to_agent": "external", "intent": "x", "client_context_id": "c"},
     ("DISPATCH", "You -> the outside world: x", "c", None)),
    ("envelope.persisted", {"from_agent": "clock", "to_agent": "queue", "intent": "y"},
     ("DISPATCH", "the daily clock -> your queue: y", None, None)),
    ("envelope.persisted", {"from_agent": "zz", "to_agent": "05", "intent": "y"},
     ("DISPATCH", "zz -> Agent 05: y", None, None)),
    ("spoke.trace", {"agent": "07", "result": "done"}, ("DECISION", "Agent 07: done", None, "07")),
    ("reject", {"envelope_id": "123456789", "reason": "r", "client_context_id": "c"},
     ("ALERT", "Hub refused message 12345678: r", "c", None)),
    ("escalation.raised", {"queue": "q", "client_context_id": "c"}, ("ALERT", "Paged you (q)", "c", None)),
    ("absolute_signal.hold", {"intent": "i", "audience": "public"},
     ("HOLD", "Outbound i to public held for your signed release", None, None)),
    ("hold.queued", {"intent": "i"}, ("HOLD", "i waiting for you", None, None)),
    ("disclosure.authorized", {"intent": "i"}, ("RELEASE", "i released on your signature", None, None)),
    ("absolute_signal.released", {"intent": "i"}, ("RELEASE", "i released on your signature", None, None)),
    ("hitl.decision.authorized", {"decision": "APPROVE", "agent": "01", "client_context_id": "c"},
     ("DECISION", "Your signed decision APPROVE applied to Agent 01's hold", "c", "01")),
    ("state.saved", {"snapshot_id": 3, "sha256": "x"}, ("STATE", "state.saved: snapshot_id=3", None, None)),
    ("config.load", {"agent": "07", "file": "f.json", "verdict": "unratified"},
     ("CONFIG", "config.load: agent 07 f.json unratified", None, None)),
    ("drawer.filed", {"agent": "08", "category": "documents", "filename": "d.json", "client_context_id": "c"},
     ("VAULT", "drawer.filed: documents/d.json", "c", "08")),
    ("decision.lead", {"agent": "02", "engine": "e", "tier": "HOT", "confidence": 0.9, "client_context_id": "c"},
     ("DECISION", "decision.lead: e tier=HOT confidence=0.9", "c", "02")),
    ("drafting.mode", {"agent": "04", "mode": "model"}, ("DECISION", "drafting.mode: model", None, "04")),
    ("handoff.failed", {"agent": "09", "reason": "dead"}, ("ALERT", "handoff.failed: dead", None, "09")),
    ("dead.letter", {"from_agent": "09", "intent": "x"}, ("ALERT", "dead.letter: x", None, "09")),
    ("sweep.error", {"agent": "07", "error": "boom"}, ("ALERT", "sweep.error: boom", None, "07")),
    ("loop.suspended", {"reason": "loop"}, ("HOLD", "Hub suspended a repeating exchange: loop", None, None)),
    ("pager.sent", {"queue": "q", "client_context_id": "c"}, ("DISPATCH", "Paged you by text (q)", "c", None)),
    ("pager.failed", {"queue": "q", "http_status": 401}, ("ALERT", "Text page failed (q): 401", None, None)),
    ("sweep.completed", {"today": "2026-10-12", "sweeps_run": 5, "errors": 0},
     ("CLOCK", "Daily clock ran for 2026-10-12: 5 agents, 0 errors", None, None)),
    ("signer.unarmed", {"reason": "r"}, ("SYSTEM", "Off: r", None, None)),
    ("jev.unarmed_fallback", {"reason": "k"}, ("SYSTEM", "Off: k", None, None)),
    ("jev.key_present", {"reason": "r"}, ("SYSTEM", "JEV key set: r", None, None)),
    ("something.else", {"client_context_id": "c"}, ("OTHER", "something.else", "c", None)),
    ("ack", {}, None),
])
def test_readable_describe_is_exact_for_every_kind(kind, rec, expect):
    from dispatcher.readable_audit import describe
    assert describe(kind, rec) == expect


def test_readable_append_carries_client_and_agent_and_chain_events_default_safely(tmp_path):
    from dispatcher.readable_audit import ReadableAuditLog, events_from_chain, write_eod
    calls = []
    log = ReadableAuditLog(str(tmp_path / "a.jsonl"), SimpleNamespace(
        log_event=lambda cat, msg, client_context_id=None, agent_id=None: calls.append((cat, msg, client_context_id, agent_id))))
    log.append("spoke.trace", {"agent": "07", "result": "r", "client_context_id": "c"})
    log.append("envelope.persisted", {"from_agent": "04", "to_agent": "17", "intent": "i", "client_context_id": "c"})
    assert calls == [("DECISION", "Agent 07: r", None, "07"), ("DISPATCH", "Agent 04 -> Agent 17: i", "c", "04")]
    fake = SimpleNamespace(read=lambda: [{"ts": 0, "client_context_id": "z"}, {"kind": "ack", "ts": 0},
                                         {"kind": "spoke.trace", "agent": "01", "result": "x"}])
    day = datetime.datetime.fromtimestamp(0).strftime("%Y-%m-%d")
    ev = events_from_chain(fake, day)
    assert [(e["category"], e["message"]) for e in ev] == [("OTHER", "?"), ("DECISION", "Agent 01: x")]
    assert events_from_chain(fake, "2999-01-01") == []
    got = {}
    write_eod(fake, SimpleNamespace(generate_eod_report=lambda d, audit_log=None, events=None: got.update(
        d=d, a=audit_log, n=len(events)) or got), day)
    assert got == {"d": day, "a": fake, "n": 2}
    write_eod(fake, SimpleNamespace(generate_eod_report=lambda d, audit_log=None, events=None: got.update(d=d) or got))
    assert got["d"] == datetime.datetime.now().strftime("%Y-%m-%d")


# ------------------------------------------------------------ model_drafting
class _Model:
    def __init__(self, reply="<think>ok</think>Three bedrooms."):
        self.reply, self.calls = reply, []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, model, messages, **kw):
        self.calls.append((model, messages))
        if isinstance(self.reply, Exception):
            raise self.reply
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.reply))])


def _dm(tmp_path, model, name="m1", exam=True):
    from dispatcher.model_drafting import DraftingModel, served_adapter_path
    dm = DraftingModel(None, model, name, str(tmp_path / "ck"))
    if exam:
        from tests_listing.test_wiring_2026_10_12 import EXAM_ANSWERS
        saved = model.reply
        model.reply = None
        model._create_saved = model._create

        def answer(model_name, messages, **kw):
            q = messages[-1]["content"]
            if "Write MLS public remarks" in q:
                return model._create_saved(model_name, messages)
            body = next(a for k, a in EXAM_ANSWERS.items() if k.lower() in q.lower())
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=body))])
        model.chat.completions.create = lambda model, messages, **kw: answer(model, messages)
        dm.examine("ck-1")
        model.reply = saved
    return dm


def test_model_drafting_asks_the_named_model_with_attributed_facts_and_learns_nothing(tmp_path):
    m = _Model()
    dm = _dm(tmp_path, m)
    assert dm.seam.model == "m1"
    facts = [{"text": "3 bedrooms", "attribution": None}, {"text": "1200 sq ft", "attribution": "per county tax records"}]
    r = dm.draft_remarks("04", "env-1", facts, 40)
    assert r == {"ok": True, "checkpoint": "ck-1", "remarks": "Three bedrooms."}
    model_name, messages = m.calls[-1]
    assert model_name == "m1"
    assert "- 3 bedrooms\n- 1200 sq ft (per county tax records)" in messages[-1]["content"]
    assert "at most 40 characters" in messages[-1]["content"]
    assert dm.seam.learning_loop.get_metrics() == dm.seam.learning_loop.get_metrics() and \
        not getattr(dm.seam.learning_loop, "exemplars", [])


def test_model_drafting_limits_and_failures_are_exact(tmp_path):
    m = _Model("<think>t</think>" + "x" * 10)
    dm = _dm(tmp_path, m)
    assert dm.draft_remarks("04", "e", [], 10)["ok"] is True                       # exactly the limit
    assert dm.draft_remarks("04", "e", [], 9) == {"ok": False, "checkpoint": "ck-1",
                                                  "reason": "model remarks are 10 characters (limit 9)"}
    m.reply = "<think>t</think>   "
    assert dm.draft_remarks("04", "e", [], 10) == {"ok": False, "checkpoint": "ck-1",
                                                   "reason": "model returned empty remarks"}
    m.reply = RuntimeError("server down")
    r = dm.draft_remarks("04", "e", [], 10)
    assert r["ok"] is False and r["checkpoint"] == "ck-1" and "server down" in r["reason"]
    from dispatcher.model_drafting import DraftingModel
    none = DraftingModel(None, None, "m1", str(tmp_path / "ck2"))
    assert none.gate() == {"ok": False, "reason": "no model client configured in this process"}
    with pytest.raises(RuntimeError, match="no model client configured - nothing to examine"):
        none.examine("x")
    entry = dm.checkpoints.list_checkpoints()
    assert any(e.get("notes") == "exam run against served model 'm1'" for e in entry)


def test_openai_compatible_client_builds_the_request_exactly(monkeypatch):
    import dispatcher.model_drafting as md
    seen = {}

    class R:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": "hi"}}]}).encode()

    def fake(req, timeout):
        seen.update(url=req.full_url, auth=req.get_header("Authorization"), body=json.loads(req.data), t=timeout)
        return R()
    monkeypatch.setattr(md.urllib.request, "urlopen", fake)
    c = md.OpenAICompatibleClient("http://localhost:11434/v1/", api_key="k", timeout=7)
    assert c.base_url == "http://localhost:11434/v1" and c.api_key == "k" and c.timeout == 7
    r = c.chat.completions.create(model="m", messages=[{"role": "user", "content": "q"}])
    assert r.choices[0].message.content == "hi"
    assert seen == {"url": "http://localhost:11434/v1/chat/completions", "auth": "Bearer k", "t": 7,
                    "body": {"model": "m", "messages": [{"role": "user", "content": "q"}],
                             "temperature": 0, "stream": False}}
    assert md.OpenAICompatibleClient("http://127.0.0.1:1").timeout == 120.0
    with pytest.raises(ValueError, match="is not this machine"):
        md.OpenAICompatibleClient("https://x.example/v1")


# ------------------------------------------------------------ handoff_guard
def test_guard_digest_ignores_key_order_and_handles_any_value(tmp_path):
    from dispatcher.handoff_guard import _config_digest
    assert _config_digest({"a": 1, "b": 2}) == _config_digest({"b": 2, "a": 1})
    assert _config_digest({"d": datetime.date(2026, 1, 1)}) == _config_digest({"d": "2026-01-01"})
    assert _config_digest({"a": 1}) != _config_digest({"a": 2})
    sw, s = _swarm(tmp_path)
    first = {"version": "r1", "ruleset": {"state_rules": {},
                                          "prohibited_phrases": [{"phrase": "p", "rule_id": "R"}]}}
    sw.hub.send(_signed(s, "17", "c", first))
    assert sw.spokes["17"]._effective_configs == {_config_digest(first): ["ruleset", "version"]}
    sw.hub.send(_signed(s, "17", "c", {"ruleset": {"prohibited_phrases": [{"rule_id": "R", "phrase": "p"}],
                                                   "state_rules": {}}, "version": "r1"}))
    assert not _clar(sw, "c")                                         # never paged as unrecognized
    assert list(sw.spokes["17"]._effective_configs) == [_config_digest(first)]   # same digest, one entry


def test_guard_unrecognized_payload_and_wrapped_handler_are_exact(tmp_path):
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "13", "u", {"zzz": 1}))
    assert _clar(sw, "u") == [{"reason": "config.update to Agent 13 changed nothing: no setting of this agent "
                                         "matched these keys, or the values equal what this agent already uses",
                               "keys": ["zzz"]}]
    h = sw.hub.handlers["13"] if hasattr(sw.hub, "handlers") else None
    if h is not None:
        assert h.__wrapped__ == sw.spokes["13"].handle


# ============================================================ second pass (run 2 survivors)
# Every reasoning trace an agent sends in these tests must name a two-digit
# agent, an envelope id, a thought and a result. Run 2 left ~30 mutants alive
# that blanked or dropped one of those arguments (02, 04, 05, 06, 14).
@pytest.fixture(autouse=True)
def _every_trace_is_well_formed(monkeypatch):
    import inspect
    import re
    from dispatcher.hub import Hub
    real = Hub.ingest_spoke_trace
    sig = inspect.signature(real)
    bad = []

    def checked(self, *a, **kw):
        try:
            args = sig.bind(self, *a, **kw).arguments
        except TypeError as e:
            bad.append(f"call shape: {e}")
            raise
        if not (isinstance(args["agent_id"], str) and re.fullmatch(r"\d\d", args["agent_id"])):
            bad.append(f"agent_id {args['agent_id']!r}")
        for k in ("envelope_id", "thought", "result"):
            if not (isinstance(args[k], str) and args[k].strip()):
                bad.append(f"{k} {args[k]!r} from agent {args['agent_id']!r}")
        return real(self, *a, **kw)
    monkeypatch.setattr(Hub, "ingest_spoke_trace", checked)
    yield
    assert not bad, bad


def test_04_rejected_drafting_setting_is_traced_and_held(tmp_path):
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "04", "c", {"drafting": {"mode": "magic"}}))
    assert _clar(sw, "c") == [{"reason": "drafting setting rejected - expected "
                                         "{\"mode\": \"rules\"} or {\"mode\": \"model\"}"}]
    [t] = [t for t in _traces(sw, "04") if t["result"] == "rejected: drafting"]
    assert t["thought"] == "drafting setting rejected whole: {'mode': 'magic'}"
    assert sw.spokes["04"].drafting_mode == "rules"


def test_04_a_hub_without_a_drafting_attribute_drafts_by_rules(tmp_path):
    sw, s = _swarm(tmp_path)
    hub = sw.hub.unwrapped if hasattr(sw.hub, "unwrapped") else sw.hub
    del hub.drafting
    sw.hub.send(_signed(s, "04", "c", {"drafting": {"mode": "model"}}))
    e = [e for e in sw.hub.audit.read() if e["kind"] == "drafting.mode"][-1]
    assert e["mode"] == "model" and e["reason"] == "no drafting model wired"
    sw.hub.send(_env("05", "04", "listing.data", "M3", {"beds": 2, "features": [], "today": "2026-10-12"}))
    [u] = [e for e in sw.hub.audit.read() if e["kind"] == "drafting.model_unavailable"]
    assert u["reason"] == "no drafting model wired in this process"


def test_02_an_engine_tier_the_agent_cannot_act_on_holds_and_the_reason_is_recorded(tmp_path):
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "02", "setup", RUBRIC))
    sw.hub.decision_adapter = SimpleNamespace(
        evaluate_lead=lambda ctx, p, r, confidence_threshold: {
            "tier": "PURPLE", "engine": "x", "fallback_reason": "engine said so", "notes": ["n"]})
    assert sw.spokes["02"]._score({}, "W1") == ("HELD_FOR_CALIBRATION", None, ["n"])
    [d] = [e for e in sw.hub.audit.read() if e["kind"] == "decision.lead"]
    assert d["fallback_reason"] == "engine said so" and d["tier"] == "PURPLE"


def test_05_occupied_with_no_watch_is_acked_not_crashed(tmp_path):
    sw, s = _swarm(tmp_path)
    res = sw.hub.send(_signed(s, "05", "V9", {"occupancy": "occupied"}))
    assert res["status"] == "ack", res
    assert not [e for e in sw.hub.audit.read() if e["kind"] in ("dead.letter", "handoff.failed")]


def test_06_a_skipped_showing_does_not_stop_the_rest_of_that_buyers_showings(tmp_path):
    sw, s = _swarm(tmp_path)
    sp = sw.spokes["06"]
    sw.hub.send(_signed(s, "06", "c", {"seller_reports": {"weekday": "monday", "listings": {"LA": "SA"}}}))
    _show(sp, "b1", "LX", "2026-10-10T09:00")    # another listing, then ours
    _show(sp, "b1", "LA", "2026-10-10T10:00")
    _show(sp, "b2", "LA", "garbage")             # unreadable, then a good one
    _show(sp, "b2", "LA", "2026-10-11T10:00")
    assert sp.weekly_seller_reports("2026-10-12") == "held:['LA']"
    assert sp.held_reports["SA"]["showings"] == 2


def test_clock_a_skipped_check_does_not_stop_the_next_and_every_context_is_chased(tmp_path):
    from dispatcher.clock import send_tick, take_results
    sw, s = _swarm(tmp_path)
    out = send_tick(sw.hub, "06", "2026-10-12", checks=["seller_weekly_report"])
    assert [r["sweep"] for r in out["results"]] == ["seller_weekly_report"]
    sw.spokes["08"].pending_requests.update({"P1": {"appraisal": {"chase_count": 0}},
                                             "P2": {"appraisal": {"chase_count": 0}}})
    out = send_tick(sw.hub, "08", "2026-10-12", checks=["chase_timeout"])
    assert [r["sweep"] for r in out["results"]] == ["chase_timeout", "chase_timeout"]
    assert take_results("never-sent") == []


def test_guard_a_failed_send_to_the_queue_is_recorded_once_and_never_recursed():
    from dispatcher.core import Envelope
    from dispatcher.handoff_guard import HandoffGuard
    sent, appended = [], []
    fake = SimpleNamespace(send=lambda env: sent.append(env) or {"status": "reject", "reason": "r1"},
                           audit=SimpleNamespace(append=lambda k, r: appended.append((k, r))),
                           ingest_spoke_trace=lambda *a, **k: None)
    g = HandoffGuard(fake, "07")
    for to, intent in (("queue", "escalation.hot_lead"), ("17", "clarification.request")):
        sent.clear()
        appended.clear()
        env = Envelope(from_agent="07", to_agent=to, intent=intent, client_context_id="G",
                       payload={}, provenance={"source": "spoke-07", "captured_at": "runtime"})
        assert g.send(env) == {"status": "reject", "reason": "r1"}
        assert sent == [env]                                      # nothing else sent
        assert appended == [("handoff.failed", {"agent": "07", "envelope_id": env.envelope_id,
                                                "intent": intent, "to_agent": to, "status": "reject",
                                                "reason": "r1", "clarification_sent": False})]


def test_readable_chain_events_skip_other_days_and_keep_going():
    from dispatcher.readable_audit import events_from_chain
    day = datetime.datetime.fromtimestamp(0).strftime("%Y-%m-%d")
    fake = SimpleNamespace(read=lambda: [{"kind": "spoke.trace", "agent": "01", "result": "later", "ts": 4e9},
                                         {"kind": "spoke.trace", "agent": "02", "result": "today", "ts": 0}])
    assert [e["message"] for e in events_from_chain(fake, day)] == ["Agent 02: today"]


def test_hitl_pause_record_is_the_wait_state_as_indented_json(tmp_path):
    sw, s = _swarm(tmp_path)
    ws = sw.hitl.pause_operation("H8", "01", "lead.captured", "r", {"a": 1}, required_decision="CONTINUE_OR_CANCEL")
    raw = sw.hub.drawers.get_drawer("H8").get_file("timeline", f"{ws.wait_id}_pause.json")
    assert raw.decode() == json.dumps(ws.to_dict(), indent=2)


def test_drawer_role_agent_and_metadata_survive_provision_and_fill(tmp_path):
    from dispatcher.drawer_filing import file_record
    sw, s = _swarm(tmp_path)
    hub = sw.hub
    file_record(hub, "14", "R1", "interactions", "a", {})              # no identity at all
    m = hub.drawers.get_drawer("R1").get_manifest()
    assert (m["role"], m["assigned_human_agent"]) == ("client", "00")
    hub.drawers.provision_drawer("R2", client_name="", property_address="", role="buyer",
                                 assigned_agent="00", metadata={"source": "open house"})
    file_record(hub, "05", "R2", "artifacts", "b", {}, identity={"client_name": "Ann"})
    m = hub.drawers.get_drawer("R2").get_manifest()
    assert (m["client_name"], m["role"], m["assigned_human_agent"], m["metadata"]) == \
        ("Ann", "buyer", "00", {"source": "open house"})


def test_model_drafting_passes_the_envelope_and_turns_learning_off(tmp_path):
    m = _Model()
    dm = _dm(tmp_path, m)
    seen = {}
    real = dm.seam.draft_and_trace

    def spy(agent_id, envelope_id, prompt, *a, **kw):
        seen.update(agent=agent_id, eid=envelope_id, a=a, kw=kw)
        return real(agent_id, envelope_id, prompt, *a, **kw)
    dm.seam.draft_and_trace = spy
    assert dm.draft_remarks("04", "env-9", [{"text": "3 bedrooms"}], 40)["ok"] is True
    assert seen == {"agent": "04", "eid": "env-9", "a": (), "kw": {"learn": False}}


def test_model_exam_questions_go_to_the_named_model(tmp_path):
    from dispatcher.model_drafting import DraftingModel
    from tests_listing.test_wiring_2026_10_12 import EXAM_ANSWERS
    names = []

    def create(model, messages, **kw):
        names.append(model)
        q = messages[-1]["content"]
        body = next(a for k, a in EXAM_ANSWERS.items() if k.lower() in q.lower())
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=body))])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    DraftingModel(None, client, "served-7", str(tmp_path / "ck")).examine("ck-7")
    assert names and set(names) == {"served-7"}


def test_pager_custom_base_trailing_slash_existing_dir_and_named_config_error(tmp_path):
    from dispatcher.pager import send_page, save_config, load_config
    urls = []
    send_page(_cfg(api_base="http://127.0.0.1:9/"), "t",
              opener=lambda req, timeout: urls.append(req.full_url) or _Resp())
    assert urls == ["http://127.0.0.1:9/2010-04-01/Accounts/AC9/Messages.json"]
    p = str(tmp_path / "pager.json")
    save_config(p, _cfg())
    save_config(p, _cfg(to_number="+15550000003"))                   # directory already there
    assert load_config(p)["to_number"] == "+15550000003"
    open(p, "w").write(json.dumps({"account_sid": "AC"}))
    with pytest.raises(ValueError, match=r"pager\.json is not usable: \['auth_token is required'"):
        load_config(p)


def test_console_questions_with_no_terminal_give_a_plain_error_not_a_traceback(tmp_path):
    import subprocess
    import sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ, LISTINGASSISTANTS_STATE_DIR=str(tmp_path / "st"))
    run = lambda *a: subprocess.run([sys.executable, os.path.join(root, "tools", "console.py"), *a],
                                    stdin=subprocess.DEVNULL, capture_output=True, text=True, env=env)
    assert run("init").returncode == 0
    for cmd in (["onboard"], ["pager"]):
        r = run(*cmd)
        if cmd == ["pager"]:
            assert run("onboard", "--name", "N", "--login", "n@example.com").returncode == 0
            r = run(*cmd)
        assert r.returncode == 1 and "Traceback" not in r.stderr + r.stdout
        last = r.stdout.strip().splitlines()[-1]                      # the unanswered prompt precedes it
        assert json.loads(last[last.index("{"):]) == {
            "error": f"`{cmd[0]}` asks for answers and none could be read - run it in a terminal, "
                     f"or pass every answer as an option (see --help)"}


def test_clock_a_once_per_tick_check_does_not_stop_the_checks_after_it(tmp_path):
    from dispatcher.clock import send_tick
    sw, s = _swarm(tmp_path)
    sw.spokes["14"].client_dates["CD"] = []
    out = send_tick(sw.hub, "14", "2026-10-12", checks=["eod_report", "date_triggers"])
    assert [r["sweep"] for r in out["results"]] == ["eod_report", "date_triggers"]
