"""Unit tests for the 2026-10-11 repairs that the ten operator scenes do not
already pin down. Every test builds the swarm the way production does
(dispatcher/swarm.py), so the HITL manager and the state store are real."""
import json
import os
import sqlite3

import pytest

from dispatcher.core import Envelope
from dispatcher.signatures import Ed25519Signer, Ed25519Verifier
from dispatcher.swarm import build_swarm
from dispatcher.state_snapshot import StateIntegrityError, encode, decode


def _swarm(tmp_path, state=False, name="a"):
    signer = Ed25519Signer()
    sw = build_swarm(str(tmp_path / f"{name}.jsonl"),
                     state_db=str(tmp_path / f"{name}.sqlite") if state else None,
                     verifier=Ed25519Verifier(signer.public_key_bytes()).verifier())
    return sw, signer


def _env(frm, to, intent, ctx, payload):
    return Envelope(from_agent=frm, to_agent=to, intent=intent, client_context_id=ctx,
                    payload=payload, provenance={"source": "human" if frm == "human" else
                                                 ("external" if frm == "external" else f"spoke-{frm}"),
                                                 "captured_at": "runtime", "verbatim_available": True})


def _signed(signer, to, ctx, payload, intent="config.update"):
    e = _env("human", to, intent, ctx, payload)
    signer.sign(e)
    return e


def _decide(sw, signer, ctx, decision, **fields):
    [w] = sw.hitl.get_pending_waits(ctx)
    payload = {"wait_id": w["wait_id"], "decision": decision}
    if fields:
        payload["updated_fields"] = fields
    auth = _env("human", w["agent_id"], "hitl.decision.authority", ctx, payload)
    signer.sign(auth)
    return sw.hitl.resume_operation(auth)


def _persisted(sw, intent, ctx=None):
    return [e for e in sw.hub.audit.read() if e.get("kind") == "envelope.persisted"
            and e.get("intent") == intent and (ctx is None or e["client_context_id"] == ctx)]


def _lead(ctx, **kw):
    p = {"channel": "web_form", "name": "N", "budget": 900000, "timeline_days": 7,
         "financing_progress": "preapproved", "preapproval_status": "yes",
         "today": "2026-10-12", "consent": {"call": "yes", "text": "yes", "email": "yes"}}
    p.update(kw)
    return _env("external", "01", "lead.inbound", ctx, p)


RUBRIC = {"rubric": {"budget_threshold": 400000, "budget_weight": 40, "timeline_days_threshold": 30,
                     "timeline_weight": 40, "financing_weight": 20, "hot_threshold": 70,
                     "warm_threshold": 40}, "version": "v1"}


# ------------------------------------------------------------ holds (#3, #6)
def test_duplicate_person_continue_scores_it_as_a_separate_lead(tmp_path):
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "02", "setup", RUBRIC))
    sw.hub.send(_lead("D-1", phone="555-0199"))
    sw.hub.send(_lead("D-2", phone="555 0199"))
    assert not _persisted(sw, "lead.captured", "D-2")
    assert sw.hub.queues["escalation.hot_lead"] == [{"client_context_id": "D-1", "score": 100, "sla_s": 300}]
    r = _decide(sw, s, "D-2", "APPROVE")
    assert r["handler_result"] == "continued: scored as a separate person"
    assert _persisted(sw, "lead.captured", "D-2")
    assert [h["client_context_id"] for h in sw.hub.queues["escalation.hot_lead"]] == ["D-1", "D-2"]


def test_reply_with_no_owner_holds_then_continue_routes_and_bad_route_stays_held(tmp_path):
    sw, s = _swarm(tmp_path)
    sw.hub.send(_env("external", "11", "client.reply", "R-1", {"message": "ok thanks"}))
    assert not _persisted(sw, "lead.reply", "R-1")
    assert _decide(sw, s, "R-1", "APPROVE_WITH_OVERRIDE", route_to="07")["handler_result"] \
        == "still held: bad route_to"
    assert _decide(sw, s, "R-1", "APPROVE_WITH_OVERRIDE", route_to="16")["handler_result"] \
        == "delivered to 16"
    [lr] = _persisted(sw, "lead.reply", "R-1")
    assert lr["to_agent"] == "16" and lr["payload"] == {"message": "ok thanks"}


def test_unsigned_decision_is_refused(tmp_path):
    from dispatcher.hitl_protocol import HITLAuthorizationError
    sw, s = _swarm(tmp_path)
    sw.hub.send(_env("external", "11", "client.reply", "R-2", {"message": "hi"}))
    [w] = sw.hitl.get_pending_waits("R-2")
    auth = _env("human", "11", "hitl.decision.authority", "R-2",
                {"wait_id": w["wait_id"], "decision": "REJECT_AND_ABORT"})
    with pytest.raises(HITLAuthorizationError):
        sw.hitl.resume_operation(auth)
    assert sw.hitl.get_pending_waits("R-2")


# ------------------------------------------------------------ restart (#12)
def test_state_round_trips_and_refusals_change_nothing(tmp_path):
    sw, s = _swarm(tmp_path, state=True)
    sw.hub.send(_env("external", "11", "client.reply", "R-3", {"message": "hold me"}))
    saved = sw.save_state()
    sw.close()
    sw2, _ = _swarm(tmp_path, state=True)
    assert sw2.restored is not None and sw2.hitl.get_pending_waits("R-3")
    assert sw2.spokes["11"].held_replies["R-3"] == {"message": "hold me"}
    sw2.save_state()
    sw2.close()
    # altered body
    db = tmp_path / "a.sqlite"
    c = sqlite3.connect(db)
    c.execute("DROP TRIGGER state_snapshots_no_update")
    c.execute("UPDATE state_snapshots SET body=replace(body,'hold me','HOLD ME')")
    c.commit()
    c.close()
    before = (tmp_path / "a.jsonl").read_bytes()
    with pytest.raises(StateIntegrityError, match="altered"):
        _swarm(tmp_path, state=True)
    assert (tmp_path / "a.jsonl").read_bytes() == before
    assert saved["snapshot_id"] == 1


def test_state_from_another_log_is_refused(tmp_path):
    sw, _ = _swarm(tmp_path, state=True)
    sw.save_state()
    sw.close()
    os.replace(tmp_path / "a.sqlite", tmp_path / "b.sqlite")
    sw_b, _ = _swarm(tmp_path, state=False, name="b")     # a different log
    sw_b.close()
    with pytest.raises(StateIntegrityError, match="no state.saved"):
        _swarm(tmp_path, state=True, name="b")


def test_snapshot_codec_round_trips_and_refuses_unknown_types():
    v = {"s": {1, 2}, "t": (1, "x"), (1, 2): "tuple key", "__x__": 1,
         "e": Envelope(from_agent="09", to_agent="external", intent="vendor.schedule",
                       client_context_id="c", payload={"a": 1}, provenance={"source": "x"},
                       signature="sig")}
    out = decode(json.loads(json.dumps(encode(v))))
    assert out["s"] == {1, 2} and out["t"] == (1, "x") and out[(1, 2)] == "tuple key"
    assert out["e"] == v["e"] and out["e"].signature == "sig"
    with pytest.raises(TypeError):
        encode({"f": lambda: 1})


# ------------------------------------------------------------ config paths
def test_unrecognized_signed_config_is_held_not_silently_acked(tmp_path):
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "07", "c-1", {"timline_init": {"closing": "2026-11-01"}}))
    held = [q for q in sw.hub.queues["clarification.request"] if q["client_context_id"] == "c-1"]
    assert held and held[0]["payload"]["keys"] == ["timline_init"]
    assert [e for e in sw.hub.audit.read() if e["kind"] == "config.unrecognized"][0]["agent"] == "07"


@pytest.mark.parametrize("agent,payload", [
    ("01", {"brokerage_scope": "L1"}), ("01", {"dnc_add": [""]}),
    ("08", {"expected_senders": {"closing_settlement_statement": []}}),
    ("14", {"buyer_agreement_on_file": "yes"}),
    ("03", {"nurture_sequences": {"s": {"touches": [{"day": 7, "text": "a"}, {"day": 0, "text": "b"}]}}}),
    ("20", {"reply_templates": {"complaint": "sorry"}}),
])
def test_bad_new_configs_are_rejected_whole(tmp_path, agent, payload):
    sw, s = _swarm(tmp_path)
    before = encode({k: v for k, v in vars(sw.spokes[agent]).items() if k != "hub"})
    sw.hub.send(_signed(s, agent, "c-2", payload))
    assert encode({k: v for k, v in vars(sw.spokes[agent]).items() if k != "hub"}) == before
    assert any("rejected" in q["payload"].get("reason", "") for q in sw.hub.queues["clarification.request"])


def test_scope_replaces_and_dnc_only_adds(tmp_path):
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "01", "c", {"brokerage_scope": ["L1", "L2"], "dnc_add": ["555-0000"]}))
    sw.hub.send(_signed(s, "01", "c", {"brokerage_scope": ["L3"], "dnc_add": ["555-1111"]}))
    assert sw.spokes["01"].brokerage_scope == {"L3"}
    assert sw.spokes["01"].dnc_list == {"555-0000", "555-1111"}


# ------------------------------------------------------------ real-traffic fixes
def test_new_listing_is_matched_against_every_buyer(tmp_path):
    sw, s = _swarm(tmp_path)
    for b in ("B-1", "B-2"):
        sw.hub.send(_signed(s, "13", b, {"buyer_criteria": [{"field": "budget", "value": 500000}]}))
    sw.hub.send(_env("05", "13", "listing.data", "L-9", {"price": 450000, "today": "2026-10-12"}))
    m = [e for e in _persisted(sw, "client.message.request") if e["payload"].get("template") == "new_match"]
    assert sorted(e["client_context_id"] for e in m) == ["B-1", "B-2"]
    assert all(e["payload"]["match"]["listing_id"] == "L-9" for e in m)


def test_reply_no_rule_covers_is_held_with_the_clients_words(tmp_path):
    sw, _ = _swarm(tmp_path)
    for owner in ("13", "16", "20"):
        sw.hub.send(_env("external", "11", "client.reply", f"Q-{owner}",
                         {"message": "see you then", "owning_agent": owner}))
        held = [q for q in sw.hub.queues["clarification.request"]
                if q["client_context_id"] == f"Q-{owner}"]
        assert held and held[0]["payload"]["verbatim"] == "see you then", owner


def test_calendar_event_without_a_day_is_refused(tmp_path):
    sw, _ = _swarm(tmp_path)
    sw.hub.send(_env("06", "18", "calendar.event", "K-1", {"event": "showing", "timezone_confirmed": True}))
    assert None not in sw.spokes["18"].calendar
    assert any("no day" in q["payload"].get("reason", "") for q in sw.hub.queues["clarification.request"])


def test_document_request_by_milestone_accepts_the_real_document(tmp_path):
    sw, _ = _swarm(tmp_path)
    sw.hub.send(_env("07", "08", "doc.request", "T-1", {"milestone": "inspection", "today": "2026-10-12"}))
    assert set(sw.spokes["08"].pending_requests["T-1"]) == {"inspection_report"}
    sw.hub.send(_env("11", "08", "document.submission", "T-1",
                     {"doc_type": "inspection_report", "opens_correctly": True, "content_hash": "h"}))
    assert [d["doc_type"] for d in sw.spokes["08"].filed_documents["T-1"]] == ["inspection_report"]
    sw.hub.send(_env("07", "08", "doc.request", "T-2", {"milestone": "no_such_step"}))
    assert any("no document type on record" in q["payload"].get("reason", "")
               for q in sw.hub.queues["clarification.request"])


def test_exhausted_chase_escalates_once(tmp_path):
    sw, _ = _swarm(tmp_path)
    sw.hub.send(_env("07", "08", "doc.request", "T-3", {"milestone": "appraisal", "today": "2026-10-12"}))
    results = [sw.spokes["08"].check_chase_timeout("T-3", "appraisal_report") for _ in range(5)]
    assert results == ["chased", "chased", "escalated", "already_escalated", "already_escalated"]


def test_vendor_holdup_escalates_once(tmp_path):
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "07", "T-4", {"timeline_init": {"inspection": "2026-11-01"}, "today": "2026-10-01"}))
    a = sw.spokes["07"].check_vendor_holdups("T-4", "2026-10-09")
    b = sw.spokes["07"].check_vendor_holdups("T-4", "2026-10-10")
    assert a == ["inspection"] and b == []


def test_nurture_sends_due_touches_once_each_after_clearance(tmp_path):
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "17", "x", {"ruleset": {"prohibited_phrases": [], "state_rules": {}},
                                         "version": "r1"}))
    sw.hub.send(_signed(s, "03", "x", {"nurture_sequences": {"default_drip": {"touches": [
        {"day": 0, "text": "hello"}, {"day": 3, "text": "listings"}]}}}))
    sw.hub.send(_env("02", "03", "lead.nurture", "W-1",
                     {"tier": "WARM", "consent": {"email": "yes"}, "today": "2026-10-12"}))
    n = sw.spokes["03"]
    assert n.active_sequences["W-1"]["compliance_status"] == "cleared"
    assert n.send_due_touches("W-1", "2026-10-12", "2026-10-12T10:00:00") == "sent:[0]"
    assert n.send_due_touches("W-1", "2026-10-13", "2026-10-13T10:00:00") == "none_due"
    assert n.send_due_touches("W-1", "2026-10-15", "2026-10-15T23:00:00").startswith("held:")
    assert n.send_due_touches("W-1", "2026-10-16", "2026-10-16T10:00:00") == "sent:[1]"
    review = _persisted(sw, "content.review", "W-1")[0]["payload"]
    assert review["draft"]["touches"] == ["hello", "listings"]


def test_nurture_without_a_definition_sends_nothing(tmp_path):
    sw, _ = _swarm(tmp_path)
    sw.hub.send(_env("02", "03", "lead.nurture", "W-2", {"consent": {"email": "yes"}}))
    assert "W-2" not in sw.spokes["03"].active_sequences
    assert any("is not defined" in q["payload"].get("reason", "") for q in sw.hub.queues["clarification.request"])


def test_social_draft_flagged_is_discarded_approved_holds_for_the_broker(tmp_path):
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "17", "x", {"ruleset": {"prohibited_phrases": [
        {"phrase": "best schools", "rule_id": "FH-2"}], "state_rules": {}}, "version": "r1"}))
    sw.hub.send(_signed(s, "20", "x", {"monitored_channels": ["fb"],
                                         "reply_templates": {"praise": "Thank you!",
                                                             "question": "Near the best schools!"}}))
    sw.hub.send(_env("external", "20", "social.mention", "P-1", {"channel": "fb", "sentiment": "praise", "text": "great"}))
    sw.hub.send(_env("external", "20", "social.mention", "P-2", {"channel": "fb", "sentiment": "question", "text": "where?"}))
    assert [w["client_context_id"] for w in sw.hitl.get_pending_waits()] == ["P-1"]
    assert any("flagged by compliance" in q["payload"].get("reason", "")
               for q in sw.hub.queues["clarification.request"] if q["client_context_id"] == "P-2")
    assert _decide(sw, s, "P-1", "REJECT_AND_ABORT")["handler_result"] == "draft_discarded_by_broker"
    assert not [e for e in sw.external if e["ctx"] in ("P-1", "P-2") and "post" in e["intent"]]


def test_opportunity_comps_reach_the_broker(tmp_path):
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "19", "x", {"zip_codes": ["44811"]}))
    sw.hub.send(_env("external", "19", "discovery.feed", "O-1",
                     {"listing_id": "M-1", "zip_code": "44811", "source": "mls", "status": "new"}))
    ups = [e for e in _persisted(sw, "prospect.opportunity") if e["payload"].get("update") == "market_context"]
    assert ups and ups[0]["payload"]["market_context"]["package_type"] == "comp"
