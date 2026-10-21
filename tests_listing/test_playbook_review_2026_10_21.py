"""The owner's playbook walkthrough (2026-10-21), one fix per playbook.

P01: a vendor's delivery for a booking that never reached the vendor (the
booking message still held for the broker's release, or declined) is held
for the broker, not accepted (Agent 09 tuple added 2026-10-21). Continue
accepts it, cancel refuses it; a booking that was released goes through
as before.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dispatcher.core import Envelope                                   # noqa: E402
from dispatcher.signatures import Ed25519Signer, Ed25519Verifier      # noqa: E402
from dispatcher.swarm import build_swarm                               # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "synth", "tuples", "config")   # a ratified synthetic vendor roster


def _env(frm, to, intent, ctx, payload):
    return Envelope(from_agent=frm, to_agent=to, intent=intent, client_context_id=ctx,
                    payload=payload, provenance={"source": frm, "captured_at": "runtime",
                                                 "verbatim_available": True})


def _setup(tmp_path):
    signer = Ed25519Signer()
    sw = build_swarm(os.path.join(str(tmp_path), "audit.jsonl"), config_dir=CONFIG,
                     verifier=Ed25519Verifier(signer.public_key_bytes()).verifier())
    assert sw.roster_info["vendors_loaded"], "the synthetic roster must load"

    def signed(to, intent, ctx, payload):
        e = _env("human", to, intent, ctx, payload)
        signer.sign(e)
        return sw.hub.send(e)

    signed("17", "config.update", "setup", {"ruleset": {"prohibited_phrases": [], "state_rules": {}},
                                            "version": "t"})
    signed("12", "config.update", "setup", {"brokerage_identification": "Synth Realty"})
    signed("05", "listing.change.authorized", "L1",
           {"new_listing": {"address": "1 Test Ln, Testville, OH", "beds": 3, "baths": 2,
                            "sqft_tax_record": 1800, "price": 450000},
            "authorize_go_live": True, "today": "2026-10-15"})
    return sw, signer


def _photos(sw):
    return sw.hub.send(_env("external", "09", "vendor.event", "L1",
                            {"kind": "photography", "event_kind": "deliverable_report",
                             "doc_type": "photo_package", "proof_artifact_present": True,
                             "content_hash": "h1"}))


def _releases(sw):
    return [e for e in sw.hub.audit.read() if e["kind"] == "envelope.persisted"
            and e["intent"] == "deliverable.release" and e["client_context_id"] == "L1"]


def _decide(sw, signer, decision):
    [w] = [w for w in sw.hitl.get_pending_waits("L1") if w["agent_id"] == "09"]
    auth = _env("human", "09", "hitl.decision.authority", "L1",
                {"wait_id": w["wait_id"],
                 "decision": "APPROVE" if decision == "continue" else "REJECT_AND_ABORT"})
    signer.sign(auth)
    return sw.hitl.resume_operation(auth)


def _held_booking(sw):
    [held] = [e for e in sw.hub._absolute_holds.values() if e.intent == "vendor.schedule"]
    return held


def test_a_delivery_before_the_booking_is_released_is_held(tmp_path):
    sw, signer = _setup(tmp_path)
    booking = _held_booking(sw)
    assert sw.hub.outbound_state(booking.envelope_id) == "held"
    _photos(sw)
    assert _releases(sw) == [] and sw.spokes["05"].mls_records["L1"]["status"] == "draft"
    assert sw.spokes["09"].held_deliveries["L1"]["photography"]["content_hash"] == "h1"
    out = _decide(sw, signer, "continue")
    assert out["handler_result"] == "photography delivery accepted on your decision"
    assert len(_releases(sw)) == 1


def test_cancel_refuses_the_delivery(tmp_path):
    sw, signer = _setup(tmp_path)
    _photos(sw)
    _decide(sw, signer, "cancel")
    assert _releases(sw) == []
    assert [e for e in sw.hub.audit.read() if e["kind"] == "envelope.persisted"
            and e["payload"].get("kind") == "delivery_not_accepted"]


def test_a_released_booking_takes_the_delivery_as_before(tmp_path):
    sw, signer = _setup(tmp_path)
    booking = _held_booking(sw)
    auth = _env("human", "hub", "disclosure.authority", "L1",
                {"held_envelope_id": booking.envelope_id})
    signer.sign(auth)
    assert sw.hub.release_disclosure(auth).get("status") == "ack"
    assert sw.hub.outbound_state(booking.envelope_id) == "sent"
    _photos(sw)
    assert len(_releases(sw)) == 1 and not sw.spokes["09"].held_deliveries


# ------------------------------------------------------------------- P02
def _buyer(sw, signer_fn, ctx, budget):
    signer_fn("14", "config.update", ctx, {"consent_record": {"email": "yes"}})
    signer_fn("14", "config.update", ctx, {"buyer_agreement_on_file": True})   # decision 4
    signer_fn("13", "config.update", ctx, {"buyer_criteria": [{"field": "budget", "value": budget}],
                                           "today": "2026-10-15"})


def _live_listing(tmp_path):
    signer = Ed25519Signer()
    sw = build_swarm(os.path.join(str(tmp_path), "audit.jsonl"), config_dir=CONFIG,
                     verifier=Ed25519Verifier(signer.public_key_bytes()).verifier())

    def signed(to, intent, ctx, payload):
        e = _env("human", to, intent, ctx, payload)
        signer.sign(e)
        return sw.hub.send(e)

    signed("17", "config.update", "setup", {"ruleset": {"prohibited_phrases": [], "state_rules": {}},
                                            "version": "t"})
    signed("12", "config.update", "setup", {"brokerage_identification": "Synth Realty"})
    _buyer(sw, signed, "B1", 445000)
    _buyer(sw, signed, "B2", 500000)
    signed("05", "listing.change.authorized", "L1",
           {"new_listing": {"address": "1 Test Ln, Testville, OH", "beds": 3, "baths": 2,
                            "sqft_tax_record": 1800, "price": 450000},
            "authorize_go_live": True, "today": "2026-10-15"})
    booking = _held_booking(sw)
    auth = _env("human", "hub", "disclosure.authority", "L1", {"held_envelope_id": booking.envelope_id})
    signer.sign(auth)
    sw.hub.release_disclosure(auth)
    _photos(sw)
    assert sw.spokes["05"].mls_records["L1"]["status"] == "active"
    signed.signer = signer
    return sw, signed


def _to(sw, ctx, template):
    return [e for e in sw.hub.audit.read() if e["kind"] == "envelope.persisted"
            and e["intent"] == "client.message.request" and e["client_context_id"] == ctx
            and e["payload"].get("template") == template]


def test_a_listing_over_a_buyers_budget_is_not_sent_as_a_match(tmp_path):
    sw, _ = _live_listing(tmp_path)
    assert _to(sw, "B1", "new_match") == [], "450,000 is over B1's 445,000"
    assert len(_to(sw, "B2", "new_match")) == 1


def test_a_price_change_reaches_buyer_matching_once_per_buyer(tmp_path):
    sw, signed = _live_listing(tmp_path)
    signed("05", "listing.change.authorized", "L1",
           {"field": "price", "value": 440000, "live_verified": True, "today": "2026-10-16"})
    assert len(_to(sw, "B1", "new_match")) == 1, "now within B1's budget"
    assert len(_to(sw, "B2", "new_match")) == 1, "B2 is not matched twice"
    [upd] = _to(sw, "B2", "listing_update")
    assert upd["payload"]["value"] == 440000 and upd["payload"]["prior_value"] == 450000
    assert not [e for e in sw.hub.audit.read() if e["kind"] == "envelope.persisted"
                and e["payload"].get("kind") == "marketing_halted"]


def test_an_ad_showing_the_old_price_is_flagged_with_where_it_is(tmp_path):
    sw, signed = _live_listing(tmp_path)
    spoke12 = sw.spokes["12"]
    spoke12.published["L1"]["content"] = {"headline": "Now $450,000"}
    signed("05", "listing.change.authorized", "L1",
           {"field": "price", "value": 440000, "live_verified": True, "today": "2026-10-16"})
    [q] = [e for e in sw.hub.audit.read() if e["kind"] == "envelope.persisted"
           and e["intent"] == "clarification.request" and "old price" in str(e["payload"])]
    assert "held for your release" in q["payload"]["reason"] and "450000" in q["payload"]["reason"]


# ------------------------------------------------- decision 7 (nurture day 0)
def _nurture(tmp_path, now_iso=None, consent=True):
    signer = Ed25519Signer()
    sw = build_swarm(os.path.join(str(tmp_path), "audit.jsonl"),
                     verifier=Ed25519Verifier(signer.public_key_bytes()).verifier())
    for to, payload in (("17", {"ruleset": {"prohibited_phrases": [], "state_rules": {}},
                                "version": "r1"}),
                        ("03", {"nurture_sequences": {"default_drip": {"touches": [
                            {"day": 0, "text": "hello"}, {"day": 3, "text": "listings"}]}}})):
        e = _env("human", to, "config.update", "x", payload)
        signer.sign(e)
        sw.hub.send(e)
    if consent:   # on record at 14, as Agent 01 logs it at capture
        sw.hub.send(_env("01", "14", "interaction.log", "W-1",
                         {"kind": "lead.captured", "consent": {"email": "yes"}}))
    start = {"tier": "WARM", "consent": {"email": "yes"}, "today": "2026-10-21"}
    if now_iso:
        start["now_iso"] = now_iso
    sw.hub.send(_env("02", "03", "lead.nurture", "W-1", start))
    return sw


def _touches(sw):
    return [e["payload"]["content"]["text"] for e in sw.hub.audit.read()
            if e["kind"] == "envelope.persisted" and e["intent"] == "client.message.request"
            and e["payload"].get("template") == "sequence_touch"]


def test_the_day_0_touch_goes_at_once_when_compliance_clears_it(tmp_path):
    sw = _nurture(tmp_path, "2026-10-21T10:15:00")
    assert sw.spokes["03"].active_sequences["W-1"]["compliance_status"] == "cleared"
    assert _touches(sw) == ["hello"], "day 0 at once, day 3 stays on the clock"
    assert sw.spokes["03"].send_due_touches("W-1", "2026-10-21", "2026-10-21T15:00:00") == "none_due"


def test_outside_contact_hours_the_day_0_touch_waits_for_the_next_window(tmp_path):
    sw = _nurture(tmp_path, "2026-10-21T22:30:00")
    assert _touches(sw) == []
    assert sw.spokes["03"].send_due_touches("W-1", "2026-10-22", "2026-10-22T09:00:00") == "sent:[0]"
    assert _touches(sw) == ["hello"]


def test_with_no_time_on_the_start_this_computers_clock_decides(tmp_path, monkeypatch):
    from dispatcher.listing_spokes_03 import Spoke03LeadNurture
    monkeypatch.setattr(Spoke03LeadNurture, "NOW", staticmethod(lambda: "2026-10-21T06:00:00"))
    assert _touches(_nurture(tmp_path / "early")) == []
    monkeypatch.setattr(Spoke03LeadNurture, "NOW", staticmethod(lambda: "2026-10-21T12:00:00"))
    assert _touches(_nurture(tmp_path / "noon")) == ["hello"]


# ------------------------------------- decisions 8 and 9 (morning brief, evening books)
def _desk(tmp_path):
    signer = Ed25519Signer()
    sw = build_swarm(os.path.join(str(tmp_path), "audit.jsonl"),
                     verifier=Ed25519Verifier(signer.public_key_bytes()).verifier())

    def signed(to, ctx, payload):
        e = _env("human", to, "config.update", ctx, payload)
        signer.sign(e)
        return sw.hub.send(e)
    return sw, signed


def _to_human(sw, ctx):
    return [e["payload"] for e in sw.hub.audit.read() if e["kind"] == "envelope.persisted"
            and e["intent"] == "report.package" and e["to_agent"] == "human"
            and e["client_context_id"] == ctx]


def test_the_morning_briefing_carries_all_four_sections_each_reported_once(tmp_path):
    from dispatcher.clock import send_tick
    sw, signed = _desk(tmp_path)
    sw.hub.send(_env("external", "01", "lead.inbound", "N1",
                     {"channel": "web_form", "today": "2026-10-20", "name": "N One",
                      "consent": {"email": "yes"}, "phone": "(216) 555-0111"}))
    sw.hub.send(_env("07", "15", "transaction.closed", "C1",
                     {"sale_price": 400000, "commission_amount": 12000, "signed_docs_only": True,
                      "close_date": "2026-10-20"}))
    signed("15", "C1", {"add_expense": {"amount": 250, "categories": ["marketing"],
                                        "receipt_on_file": True, "date": "2026-10-20"}})
    signed("15", "C1", {"add_expense": {"amount": 99, "categories": ["marketing"],
                                        "date": "2026-10-19"}})
    signed("19", "x", {"zip_codes": ["44811"]})
    sw.hub.send(_env("external", "19", "discovery.feed", "O1",
                     {"listing_id": "M-1", "zip_code": "44811", "source": "mls", "status": "new"}))
    sw.hub.send(_env("05", "10", "listing.data", "L1",
                     {"listing_id": "L1", "changed_field": "price", "price": 440000,
                      "prior_price": 450000, "today": "2026-10-20"}))

    send_tick(sw.hub, "18", "2026-10-21", checks=["morning_briefing"])
    [brief] = [p for p in _to_human(sw, "briefing") if p.get("briefing_type") == "morning"]
    s = brief["sections"]
    assert brief["sections_missing"] == []
    assert [x["context"] for x in s["overnight_leads"]["leads"]] == ["N1"]
    books = s["yesterdays_books"]
    assert books["date"] == "2026-10-20" and books["commission_total"] == 12000
    assert books["expense_total"] == 250, "the 2026-10-19 expense is not yesterday's"
    assert [p["listing_id"] for p in s["prospects_waiting"]["prospects"]] == ["M-1"]
    [chg] = s["market_changes"]["changes"]
    assert (chg["change"], chg["value"], chg["prior_value"]) == ("price", 440000, 450000)

    signed("19", "x", {"prospects_handled": ["M-1"]})
    send_tick(sw.hub, "18", "2026-10-22", checks=["morning_briefing"])
    second = [p for p in _to_human(sw, "briefing") if p.get("briefing_type") == "morning"][-1]["sections"]
    assert second["overnight_leads"]["count"] == 0, "a lead is reported once"
    assert second["market_changes"]["count"] == 0
    assert second["prospects_waiting"]["count"] == 0
    assert second["yesterdays_books"]["commission_total"] == 0


def test_a_section_nobody_answers_is_named_missing(tmp_path):
    from dispatcher.clock import send_tick
    sw, _ = _desk(tmp_path)
    sw.hub.handlers["19"] = lambda env: None      # 19 receives the ask and never answers
    send_tick(sw.hub, "18", "2026-10-21", checks=["morning_briefing"])
    [brief] = _to_human(sw, "briefing")
    assert brief["sections"]["prospects_waiting"] is None
    assert brief["sections_missing"] == [{"agent": "19", "section": "prospects_waiting",
                                          "missing_source": "no answer to the briefing request"}]


def test_a_section_sent_when_no_briefing_is_built_is_not_used(tmp_path):
    sw, _ = _desk(tmp_path)
    sw.hub.send(_env("19", "18", "report.package", "briefing",
                     {"section": "prospects_waiting", "data": {"count": 99}}))
    assert sw.spokes["18"]._sections is None
    assert not _to_human(sw, "briefing")


def test_the_evening_clock_sends_the_books_with_the_days_figures_once(tmp_path):
    from dispatcher.sweep_runner import run_evening_sweep
    sw, signed = _desk(tmp_path)
    sw.hub.send(_env("07", "15", "transaction.closed", "C1",
                     {"sale_price": 400000, "commission_amount": 12000, "signed_docs_only": True,
                      "close_date": "2026-10-21"}))
    signed("15", "C1", {"add_expense": {"amount": 250, "categories": ["marketing"],
                                        "date": "2026-10-21"}})
    out = run_evening_sweep(sw.hub, sw.spokes, today="2026-10-21")
    assert [r["sweep"] for r in out] == ["eod_report"] and not out[0].get("error")
    [books] = _to_human(sw, "eod-report")
    assert books["report_type"] == "eod_books" and books["crm"]["report_type"] == "eod"
    f = books["figures"]
    assert (f["date"], f["commission_total"], f["expense_total"], f["expenses_unverified"]) == \
        ("2026-10-21", 12000, 250, 1)
    to_15 = [e for e in sw.hub.audit.read() if e["kind"] == "envelope.persisted"
             and e["intent"] == "report.package" and e["from_agent"] == "14"]
    assert [e["to_agent"] for e in to_15] == ["15"], "14's books go to 15, not straight to you"


# ------------------------------------------- P20: the vacant check is daily
def test_the_vacant_check_is_daily_and_never_stacks(tmp_path):
    from dispatcher.sweep_runner import run_daily_sweeps
    sw, signed = _live_listing(tmp_path)
    signed("05", "config.update", "L1", {"occupancy": "vacant", "today": "2026-10-16"})
    assert sw.spokes["05"].vacant_watch["L1"]["interval_days"] == 1

    def checks_held():
        return [h for h in sw.hub._absolute_holds.values()
                if h.intent == "vendor.schedule" and h.payload.get("kind") == "property_check"]
    run_daily_sweeps(sw.hub, sw.spokes, today="2026-10-17")
    assert len(checks_held()) == 1
    run_daily_sweeps(sw.hub, sw.spokes, today="2026-10-18")
    run_daily_sweeps(sw.hub, sw.spokes, today="2026-10-19")
    assert len(checks_held()) == 1, "a check waiting for your release is not booked again"
    told = [q for q in sw.hub.queues["clarification.request"] if "vacant-property check" in str(q)]
    assert len(told) == 1, "told once per open check"

    [held] = checks_held()
    auth = _env("human", "hub", "disclosure.authority", "L1", {"held_envelope_id": held.envelope_id})
    signed.signer.sign(auth)
    assert sw.hub.release_disclosure(auth).get("status") == "ack"
    run_daily_sweeps(sw.hub, sw.spokes, today="2026-10-20")
    assert checks_held() == [], "sent and not delivered yet: still not booked again"
    sw.hub.send(_env("external", "09", "vendor.event", "L1",
                     {"kind": "property_check", "event_kind": "deliverable_report",
                      "doc_type": "property_check_report", "proof_artifact_present": True,
                      "content_hash": "pc1"}))
    run_daily_sweeps(sw.hub, sw.spokes, today="2026-10-21")
    assert len(checks_held()) == 1, "the day after a proven delivery, the next check is booked"


# ------------------------- P11 sign-off: a touch 11 did not send is retried
def test_a_touch_blocked_for_no_consent_is_not_counted_and_goes_once_consent_is_recorded(tmp_path):
    sw = _nurture(tmp_path, "2026-10-21T10:15:00", consent=False)     # no consent at 14
    n = sw.spokes["03"]
    sent_out = lambda: [e for e in sw.hub.audit.read() if e["kind"] == "envelope.persisted"   # noqa: E731
                        and e["intent"] == "client.message.send"
                        and e["payload"].get("template") == "sequence_touch"]
    assert _touches(sw) == ["hello"] and sent_out() == [], "11 blocked it: no consent at 14"
    assert n.active_sequences["W-1"]["sent"] == [], "a blocked touch is not counted as sent"
    assert [e for e in sw.hub.audit.read() if e["kind"] == "envelope.persisted"
            and e["intent"] == "client.message.not_sent" and e["payload"]["reason"] == "no_consent"]
    # the broker records the client's consent, then the clock runs
    sw.hub.send(_env("01", "14", "interaction.log", "W-1",
                     {"kind": "lead.captured", "consent": {"email": "yes"}}))
    assert n.send_due_touches("W-1", "2026-10-22", "2026-10-22T09:00:00") == "sent:[0]"
    assert len(sent_out()) == 1
    assert n.send_due_touches("W-1", "2026-10-22", "2026-10-22T10:00:00") == "none_due"


def test_an_opt_out_reported_by_11_stops_the_sequence(tmp_path):
    sw = _nurture(tmp_path, "2026-10-21T22:30:00", consent=False)   # day 0 waits: outside hours
    sw.hub.send(_env("01", "14", "interaction.log", "W-1",
                     {"kind": "lead.captured", "consent": {"email": "no"}}))
    n = sw.spokes["03"]
    assert n.send_due_touches("W-1", "2026-10-22", "2026-10-22T09:00:00").startswith("held")
    assert n.active_sequences["W-1"]["paused"] is True
    assert [e for e in sw.hub.audit.read() if e["kind"] == "envelope.persisted"
            and e["payload"].get("kind") == "sequence_stopped"]
