"""Owner decisions D-A1 to D-A21 and the plain bugs found by the procedures
audit and its independent re-check (2026-10-27/28).

Each test fails on the code before the change (checked against the
commit before it: c89406a).
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dispatcher.core import Envelope, Routes, AuditLog
from dispatcher.hub import Hub
from dispatcher.clock import send_tick
from dispatcher.signatures import Ed25519Signer, Ed25519Verifier
from dispatcher.listing_spokes import Spoke14CRMPipeline, Spoke01LeadCapture
from dispatcher.listing_spokes_02 import Spoke02LeadQualification
from dispatcher.listing_spokes_03 import Spoke03LeadNurture
from dispatcher.listing_spokes_11 import Spoke11ClientCommunication
from tests_listing.consent_fixture import give_consent
from tests_listing.nurture_fixture import with_sequences

IDENTITY_ROUTES = os.path.join(os.path.dirname(__file__), "..", "identity", "routes.json")


def make_hub(tmp_path, **kw):
    audit_path = os.path.join(str(tmp_path), f"audit-{uuid.uuid4().hex[:8]}.jsonl")
    signer = Ed25519Signer()
    hub = Hub(Routes(IDENTITY_ROUTES), AuditLog(audit_path),
              signature_verifier=Ed25519Verifier(signer.public_key_bytes()).verifier(), **kw)
    hub._test_signer = signer
    return hub


def signed(hub, to, ctx, payload, intent="config.update"):
    e = Envelope(from_agent="human", to_agent=to, intent=intent, client_context_id=ctx,
                 payload=payload, provenance={"source": "human", "captured_at": "runtime",
                                              "verbatim_available": True})
    hub._test_signer.sign(e)
    return e


def env(frm, to, intent, ctx, payload):
    return Envelope(from_agent=frm, to_agent=to, intent=intent, client_context_id=ctx,
                    payload=payload, provenance={"source": f"spoke-{frm}",
                                                 "captured_at": "runtime",
                                                 "verbatim_available": True})


def persisted(hub, intent=None, ctx=None):
    return [e for e in hub.audit.read() if e["kind"] == "envelope.persisted"
            and (intent is None or e["intent"] == intent)
            and (ctx is None or e.get("client_context_id") == ctx)]


def queue_reasons(hub, ctx=None):
    return [e["payload"].get("reason", "") for e in persisted(hub, "clarification.request", ctx)]


def _started_sequence(hub, spoke, ctx, today="2026-10-15"):
    hub.send(env("02", "03", "lead.nurture", ctx,
                 {"consent": {"email": "yes"}, "sequence_id": "seq_a", "today": today,
                  "now_iso": f"{today}T10:00:00"}))
    hub.send(env("17", "03", "content.verdict", ctx, {"verdict": "approved"}))
    return spoke.active_sequences[ctx]


# ------------------------------------------------------------- D-A7 (P)
def test_spike_pause_lifts_when_rescore_comes_back_warm(tmp_path):
    hub = make_hub(tmp_path)
    spoke = with_sequences(Spoke03LeadNurture(hub))
    hub.on_turn_start()
    seq = _started_sequence(hub, spoke, "p-1")
    assert seq["sent"] == [0]                       # day-0 touch went
    hub.send(env("12", "03", "behavioral.signal", "p-1", {"engagement_score": 80}))
    assert seq["paused"] is True
    # Agent 02's answer: still WARM, same sequence (no sequence named)
    hub.send(env("02", "03", "lead.nurture", "p-1",
                 {"consent": {"email": "yes"}, "reassignment": True, "today": "2026-10-16"}))
    assert seq["paused"] is False
    logs = [e["payload"] for e in persisted(hub, "interaction.log", "p-1")]
    assert any(p.get("reason") == "resumed after spike re-score: WARM" for p in logs)
    # the next touch (day 7) goes on its own day, not before
    assert spoke.send_due_touches("p-1", "2026-10-21", "2026-10-21T10:00:00") == "none_due"
    assert spoke.send_due_touches("p-1", "2026-10-22", "2026-10-22T10:00:00") == "sent:[1]"


def test_touches_missed_during_a_spike_pause_are_skipped_not_burst(tmp_path):
    hub = make_hub(tmp_path)
    spoke = with_sequences(Spoke03LeadNurture(hub))
    hub.on_turn_start()
    seq = _started_sequence(hub, spoke, "p-2")
    hub.send(env("12", "03", "behavioral.signal", "p-2", {"engagement_score": 80}))
    # the WARM answer arrives on day 9: the day-7 touch passed while paused
    hub.send(env("02", "03", "lead.nurture", "p-2",
                 {"consent": {"email": "yes"}, "reassignment": True, "today": "2026-10-24"}))
    assert seq["skipped"] == [1]
    assert spoke.send_due_touches("p-2", "2026-10-24", "2026-10-24T10:00:00") == "none_due"


def test_a_reply_pause_is_not_lifted_by_a_warm_rescore(tmp_path):
    hub = make_hub(tmp_path)
    spoke = with_sequences(Spoke03LeadNurture(hub))
    hub.on_turn_start()
    seq = _started_sequence(hub, spoke, "p-3")
    hub.send(env("12", "03", "behavioral.signal", "p-3", {"engagement_score": 80}))
    hub.send(env("11", "03", "lead.reply", "p-3", {"message": "is the house on elm still open?"}))
    hub.send(env("02", "03", "lead.nurture", "p-3",
                 {"consent": {"email": "yes"}, "reassignment": True, "today": "2026-10-16"}))
    assert seq["paused"] is True and seq["paused_for"] == "reply"


# ------------------------------------------------------------- D-A8 (S)
def test_stop_confirmation_goes_only_on_the_stop_channel(tmp_path):
    hub = make_hub(tmp_path)
    spoke = with_sequences(Spoke03LeadNurture(hub))
    hub.on_turn_start()
    _started_sequence(hub, spoke, "s-1")
    hub.send(env("11", "03", "lead.reply", "s-1", {"message": "STOP", "channel": "text"}))
    reqs = [e["payload"] for e in persisted(hub, "client.message.request", "s-1")
            if e["payload"].get("template") == "opt_out_confirmed"]
    assert reqs == [{"template": "opt_out_confirmed", "channel": "text"}]


def test_stop_with_no_channel_gets_no_confirmation_and_asks_the_owner(tmp_path):
    hub = make_hub(tmp_path)
    spoke = with_sequences(Spoke03LeadNurture(hub))
    hub.on_turn_start()
    _started_sequence(hub, spoke, "s-2")
    hub.send(env("11", "03", "lead.reply", "s-2", {"message": "STOP"}))
    assert not [e for e in persisted(hub, "client.message.request", "s-2")
                if e["payload"].get("template") == "opt_out_confirmed"]
    assert any("no confirmation was sent" in r for r in queue_reasons(hub, "s-2"))
    assert spoke.active_sequences["s-2"]["consent"] == {"call": "no", "text": "no", "email": "no"}


def test_agent_11_sends_the_stop_confirmation_on_the_named_channel(tmp_path):
    hub = make_hub(tmp_path)
    Spoke11ClientCommunication(hub)
    hub.on_turn_start()
    hub.send(env("03", "11", "client.message.request", "s-3",
                 {"template": "opt_out_confirmed", "channel": "email", "hour": 14}))
    sends = [e["payload"] for e in persisted(hub, "client.message.send", "s-3")]
    assert sends == [{"template": "opt_out_confirmed", "variables": {}, "channel": "email"}]


def test_a_client_reply_carries_its_channel_to_the_owning_agent(tmp_path):
    hub = make_hub(tmp_path)
    Spoke11ClientCommunication(hub)
    spoke = with_sequences(Spoke03LeadNurture(hub))
    hub.on_turn_start()
    _started_sequence(hub, spoke, "s-4")
    hub.send(env("external", "11", "client.reply", "s-4",
                 {"message": "STOP", "owning_agent": "03", "channel": "text", "hour": 14}))
    reqs = [e["payload"] for e in persisted(hub, "client.message.request", "s-4")
            if e["payload"].get("template") == "opt_out_confirmed"]
    assert reqs == [{"template": "opt_out_confirmed", "channel": "text"}]


def test_intake_opt_out_from_a_web_form_asks_the_owner_instead_of_confirming(tmp_path):
    hub = make_hub(tmp_path)
    Spoke01LeadCapture(hub)
    hub.on_turn_start()
    hub.send(env("external", "01", "lead.inbound", "s-5",
                 {"channel": "web_form", "today": "2026-10-15", "name": "Noel",
                  "phone": "(216) 555-0115", "revoke_all_contact": True,
                  "consent": {"call": "yes", "text": "yes", "email": "yes"}}))
    assert not persisted(hub, "client.message.request", "s-5")
    assert any("no message can go back on that channel" in r for r in queue_reasons(hub, "s-5"))


# ------------------------------------------------------------- CA
def test_opt_out_confirmation_still_goes_while_a_complaint_hold_is_open(tmp_path):
    hub = make_hub(tmp_path)
    spoke = Spoke11ClientCommunication(hub)
    hub.on_turn_start()
    spoke.complaint_hold.add("ca-1")
    hub.send(env("03", "11", "client.message.request", "ca-1",
                 {"template": "opt_out_confirmed", "channel": "text", "hour": 14}))
    assert [e["payload"]["template"] for e in persisted(hub, "client.message.send", "ca-1")] \
        == ["opt_out_confirmed"]


# ------------------------------------------------------------- AH
def test_agent_11_catches_the_same_wire_phrases_as_07_and_08(tmp_path):
    hub = make_hub(tmp_path)
    Spoke11ClientCommunication(hub)
    hub.on_turn_start()
    hub.send(env("external", "11", "client.reply", "ah-1",
                 {"message": "what is the account number for closing?", "hour": 14}))
    assert hub.queues["escalation.legal_line"]


# ------------------------------------------------------------- D-A4 (AI, M)
def test_quiet_hours_hold_is_sent_on_the_next_daily_run_after_8(tmp_path):
    hub = make_hub(tmp_path)
    spoke = Spoke11ClientCommunication(hub)
    Spoke14CRMPipeline(hub)
    hub.on_turn_start()
    give_consent(hub, "q-1")
    hub.send(env("05", "11", "status.update", "q-1",
                 {"template": "milestone_update", "variables": {}, "hour": 23}))
    assert not persisted(hub, "client.message.send", "q-1")
    assert any("held until 08:00" in r for r in queue_reasons(hub, "q-1"))
    assert spoke.quiet_held["q-1"][0]["template"] == "milestone_update"
    send_tick(hub, "11", "2026-10-16", "2026-10-16T06:30:00")      # still quiet
    assert not persisted(hub, "client.message.send", "q-1")
    send_tick(hub, "11", "2026-10-16", "2026-10-16T08:05:00")
    assert [e["payload"]["template"] for e in persisted(hub, "client.message.send", "q-1")] \
        == ["milestone_update"]
    assert "q-1" not in spoke.quiet_held



def test_the_watch_and_evening_runs_release_quiet_hours_holds(tmp_path):
    """Found 2026-10-28 re-checking the manual: the documented daily run is at
    07:00, inside quiet hours, so held messages never went out."""
    from dispatcher.sweep_runner import run_quiet_hours_release
    hub = make_hub(tmp_path)
    s11 = Spoke11ClientCommunication(hub)
    Spoke14CRMPipeline(hub)
    hub.on_turn_start()
    give_consent(hub, "q-3")
    assert run_quiet_hours_release(hub, {"11": s11}, "2026-10-16", "2026-10-16T09:00:00") == []
    hub.send(env("05", "11", "status.update", "q-3",
                 {"template": "milestone_update", "variables": {}, "hour": 23}))
    run_quiet_hours_release(hub, {"11": s11}, "2026-10-16", "2026-10-16T07:00:00")
    assert not persisted(hub, "client.message.send", "q-3")
    run_quiet_hours_release(hub, {"11": s11}, "2026-10-16", "2026-10-16T08:05:00")
    assert [e["payload"]["template"] for e in persisted(hub, "client.message.send", "q-3")] \
        == ["milestone_update"]

def test_a_held_message_is_not_released_into_a_complaint_hold(tmp_path):
    hub = make_hub(tmp_path)
    spoke = Spoke11ClientCommunication(hub)
    Spoke14CRMPipeline(hub)
    hub.on_turn_start()
    give_consent(hub, "q-2")
    hub.send(env("05", "11", "status.update", "q-2",
                 {"template": "milestone_update", "variables": {}, "hour": 22}))
    spoke.complaint_hold.add("q-2")
    send_tick(hub, "11", "2026-10-16", "2026-10-16T09:00:00")
    assert not persisted(hub, "client.message.send", "q-2")


def test_a_message_with_no_hour_uses_the_computer_clock(tmp_path, monkeypatch):
    monkeypatch.setenv("LISTING_CLOCK_NOW", "2026-10-15T23:30:00")
    hub = make_hub(tmp_path)
    Spoke11ClientCommunication(hub)
    Spoke14CRMPipeline(hub)
    hub.on_turn_start()
    give_consent(hub, "q-3")
    hub.send(env("05", "11", "status.update", "q-3",
                 {"template": "milestone_update", "variables": {}}))
    assert not persisted(hub, "client.message.send", "q-3")       # was taken as noon
    assert any("held until 08:00" in r for r in queue_reasons(hub, "q-3"))
    monkeypatch.setenv("LISTING_CLOCK_NOW", "2026-10-15T12:00:00")
    hub.send(env("05", "11", "status.update", "q-3",
                 {"template": "milestone_update", "variables": {}}))
    assert persisted(hub, "client.message.send", "q-3")


# ------------------------------------------------------------- template gate
def test_a_template_without_signed_wording_is_not_sent_until_signed(tmp_path):
    hub = make_hub(tmp_path)
    Spoke11ClientCommunication(hub)
    Spoke14CRMPipeline(hub)
    hub.on_turn_start()
    give_consent(hub, "t-1")
    hub.send(env("08", "11", "client.message.request", "t-1",
                 {"template": "doc_unsigned_resend", "doc_type": "purchase_agreement",
                  "hour": 14}))
    assert not persisted(hub, "client.message.send", "t-1")
    hub.send(signed(hub, "11", "t-1", {"template_signed": "doc_unsigned_resend"}))
    hub.send(env("08", "11", "client.message.request", "t-1",
                 {"template": "doc_unsigned_resend", "doc_type": "purchase_agreement",
                  "hour": 14}))
    assert [e["payload"]["template"] for e in persisted(hub, "client.message.send", "t-1")] \
        == ["doc_unsigned_resend"]


# ------------------------------------------------------------- D-A10 (E)
def _intake(hub, ctx, **extra):
    payload = {"channel": "call", "today": "2026-10-15", "name": "Pat",
               "phone": "(216) 555-0142", "message": "can I talk to a real person please",
               "consent": {"call": "yes", "text": "yes", "email": "yes"}}
    payload.update(extra)
    hub.send(env("external", "01", "lead.inbound", ctx, payload))


def _owner_items(hub, ctx):
    return {q: [r for r in recs if isinstance(r, dict) and r.get("client_context_id") == ctx]
            for q, recs in hub.queues.items()}


def test_a_caller_demanding_a_human_lands_in_the_hot_lead_queue_once(tmp_path):
    hub = make_hub(tmp_path)
    Spoke01LeadCapture(hub)
    Spoke14CRMPipeline(hub)
    Spoke02LeadQualification(hub)
    hub.on_turn_start()
    _intake(hub, "e-1")
    items = _owner_items(hub, "e-1")
    assert not items.get("escalation.legal_line")
    hot = items.get("escalation.hot_lead")
    assert len(hot) == 1 and hot[0]["reason"] == "demands_human" and hot[0]["sla_s"]
    assert "real person" in hot[0]["demands_human"]


def test_a_caller_demanding_a_human_on_dnc_is_marked_do_not_contact(tmp_path):
    hub = make_hub(tmp_path)
    s01 = Spoke01LeadCapture(hub)
    s01.dnc_list = {"(216) 555-0142"}
    Spoke14CRMPipeline(hub)
    Spoke02LeadQualification(hub)
    hub.on_turn_start()
    _intake(hub, "e-2")
    hot = _owner_items(hub, "e-2").get("escalation.hot_lead")
    assert len(hot) == 1 and hot[0]["do_not_contact"] is True and "sla_s" not in hot[0]
    assert "real person" in hot[0]["demands_human"]
    # 01's own DNC legal-line item still stands; no second item for the demand
    assert not [r for r in _owner_items(hub, "e-2").get("escalation.legal_line", [])
                if "demands a human" in r.get("trigger", "")]


# ------------------------------------------------------------- D-A9 (J)
def _listing_change(hub, ctx, change):
    e = Envelope(from_agent="human", to_agent="05", intent="listing.change.authorized",
                 client_context_id=ctx, payload=change,
                 provenance={"source": "human", "captured_at": "runtime",
                             "verbatim_available": True})
    hub._test_signer.sign(e)
    return e


def test_an_expired_listing_ends_like_a_withdrawn_one(tmp_path):
    from dispatcher.listing_spokes_05 import Spoke05MLSListingManagement
    hub = make_hub(tmp_path)
    spoke = Spoke05MLSListingManagement(hub)
    hub.on_turn_start()
    hub.send(_listing_change(hub, "j-1", {"field": "status", "value": "expired"}))
    assert spoke.mls_records["j-1"]["status"] == "expired"
    told = sorted(e["to_agent"] for e in persisted(hub, "status.update", "j-1"))
    assert told == ["11", "12", "14"]
    assert not any("invalid status" in r for r in queue_reasons(hub, "j-1"))


def test_expiry_while_under_contract_is_refused_like_withdrawal(tmp_path):
    from dispatcher.listing_spokes_05 import Spoke05MLSListingManagement
    hub = make_hub(tmp_path)
    spoke = Spoke05MLSListingManagement(hub)
    hub.on_turn_start()
    hub.send(_listing_change(hub, "j-2", {"field": "status", "value": "pending",
                                          "signed_contract_artifact": "contract-1"}))
    hub.send(_listing_change(hub, "j-2", {"field": "status", "value": "expired"}))
    assert spoke.mls_records["j-2"]["status"] == "pending"
    assert any("expiry requested while under contract" in r["trigger"]
               for r in hub.queues["escalation.legal_line"])


# ------------------------------------------------------------- D-A3 (Y)
def test_no_show_is_never_marked_on_the_day_of_the_showing(tmp_path):
    from dispatcher.listing_spokes_18 import Spoke18CalendarTask
    hub = make_hub(tmp_path)
    s18 = Spoke18CalendarTask(hub)
    hub.on_turn_start()
    s18.showings["y-1"] = {"time": "2026-10-17T10:00:00", "day": "2026-10-17"}
    assert s18.check_showing_no_show("y-1", "2026-10-17T23:59:59") == "same_day_waits"
    assert not persisted(hub, "showing.no_show", "y-1")
    assert s18.check_showing_no_show("y-1", "2026-10-18T09:00:00") == "reported"


# ------------------------------------------------------------- D-A2 (V)
def test_unverified_requester_cancel_tells_owner_and_buyer(tmp_path):
    from dispatcher.listing_spokes_06 import Spoke06ShowingScheduler
    hub = make_hub(tmp_path)
    Spoke06ShowingScheduler(hub)
    hub.on_turn_start()
    hub.send(env("11", "06", "showing.request", "v-1",
                 {"requested_time": "2026-10-20T10:00:00", "listing_id": "L1",
                  "buyer_agreement_on_file": True, "requester_identity_verified": False}))
    assert any("identity is not verified - verify it and rebook" in r
               for r in queue_reasons(hub, "v-1"))
    assert [e["payload"]["template"] for e in persisted(hub, "client.message.request", "v-1")] \
        == ["identity_verification_needed"]


# ------------------------------------------------------------- Z
def test_feedback_is_asked_per_showing_and_once_a_day(tmp_path):
    from dispatcher.listing_spokes_06 import Spoke06ShowingScheduler
    hub = make_hub(tmp_path)
    s06 = Spoke06ShowingScheduler(hub)
    hub.on_turn_start()
    s06.confirmed_showings["z-1"] = [{"time": "2026-10-16T10:00:00", "listing_id": "L1",
                                       "confirmed": True}]
    assert s06.clock_showing_feedback("z-1", "2026-10-17") == "asked"
    assert s06.clock_showing_feedback("z-1", "2026-10-17") == "already_asked_today"
    assert s06.clock_showing_feedback("z-1", "2026-10-18") == "asked"
    assert s06.clock_showing_feedback("z-1", "2026-10-19") == "stopped"
    # a second showing for the same buyer is asked about on its own count
    s06.confirmed_showings["z-1"].append({"time": "2026-10-20T10:00:00", "listing_id": "L2",
                                           "confirmed": True})
    assert s06.clock_showing_feedback("z-1", "2026-10-21") == ["stopped", "asked"]


# ------------------------------------------------------------- D-A14 / D-A15 (AD, AG)
def _inspection(hub, ctx, **extra):
    hub.send(env("11", "08", "document.submission", ctx,
                 {"doc_type": "inspection_report", "opens_correctly": True,
                  "content_hash": f"insp-{ctx}", "today": "2026-10-20", **extra}))


def _tx_hub(tmp_path):
    from dispatcher.listing_spokes_07 import Spoke07TransactionCoordinator
    from dispatcher.listing_spokes_08 import Spoke08DocumentCollection
    hub = make_hub(tmp_path)
    s07 = Spoke07TransactionCoordinator(hub)
    s08 = Spoke08DocumentCollection(hub)
    hub.on_turn_start()
    return hub, s07, s08


def test_inspection_report_without_repair_flag_gives_one_legal_line_item(tmp_path):
    hub, s07, _ = _tx_hub(tmp_path)
    s07.timelines["ad-1"] = {"inspection": {"deadline": "2026-10-25", "satisfied": False,
                                            "artifact": None}}
    _inspection(hub, "ad-1")
    items = _owner_items(hub, "ad-1")
    legal = items.get("escalation.legal_line", [])
    assert len(legal) == 1
    assert "repair requests not stated" in legal[0]["trigger"]
    assert "send the report to the contract parties" in legal[0]["trigger"]
    assert not [r for r in queue_reasons(hub, "ad-1") if "contract parties" in r]


def test_inspection_report_stating_no_repairs_gives_one_queue_item(tmp_path):
    hub, s07, _ = _tx_hub(tmp_path)
    s07.timelines["ad-2"] = {"inspection": {"deadline": "2026-10-25", "satisfied": False,
                                            "artifact": None}}
    _inspection(hub, "ad-2", repair_requests_present=False)
    assert not _owner_items(hub, "ad-2").get("escalation.legal_line")
    assert [r for r in queue_reasons(hub, "ad-2") if "send the report to the contract parties" in r] \
        == ["Inspection report received (2026-10-20): no repair requests stated - "
            "send the report to the contract parties"]


# ------------------------------------------------------------- D-A11 (AF)
def test_unsigned_document_asks_owner_and_pauses_the_chase_until_done(tmp_path):
    from dispatcher.escalation_watch import acknowledge
    hub, _, s08 = _tx_hub(tmp_path)
    hub.send(env("07", "08", "doc.request", "af-1",
                 {"milestone": "contract", "doc_type": "purchase_agreement",
                  "today": "2026-10-15"}))
    s08.pending_requests.setdefault("af-1", {}).setdefault(
        "purchase_agreement", {"chase_count": 0})
    hub.send(env("11", "08", "document.submission", "af-1",
                 {"doc_type": "purchase_agreement", "opens_correctly": True,
                  "signature_expected": True, "signed": False, "content_hash": "pa-1"}))
    assert any("purchase_agreement arrived UNSIGNED" in r for r in queue_reasons(hub, "af-1"))
    assert [e["payload"]["template"] for e in persisted(hub, "client.message.request", "af-1")
            if e["from_agent"] == "08"][-1] == "doc_unsigned_resend"
    assert s08.check_chase_timeout("af-1", "purchase_agreement") \
        == "paused: unsigned copy question open"
    acknowledge(hub, "clarification.request", "af-1", by="owner")
    assert s08.check_chase_timeout("af-1", "purchase_agreement") != \
        "paused: unsigned copy question open"


# ------------------------------------------------------------- D-A5 (AB, AE)
def test_signed_amendment_changes_one_date_and_keeps_the_rest(tmp_path):
    from dispatcher.listing_spokes_18 import Spoke18CalendarTask
    hub, s07, _ = _tx_hub(tmp_path)
    s18 = Spoke18CalendarTask(hub)
    hub.send(signed(hub, "07", "ab-1", {"timeline_init": {"inspection": "2026-10-20",
                                                           "closing": "2026-11-15"}}))
    s07.timelines["ab-1"]["inspection"]["satisfied"] = True
    requests_before = len(persisted(hub, "doc.request", "ab-1"))
    hub.send(signed(hub, "07", "ab-1", {"milestone_amendment": {
        "milestone": "closing", "new_date": "2026-11-22", "amendment_ref": "amend-1"}}))
    t = s07.timelines["ab-1"]
    assert t["closing"]["deadline"] == "2026-11-22"
    assert t["inspection"]["satisfied"] is True                 # untouched
    assert len(persisted(hub, "doc.request", "ab-1")) == requests_before   # nothing re-sent
    logs = [e["payload"] for e in persisted(hub, "interaction.log", "ab-1")]
    assert {"kind": "milestone_amended", "milestone": "closing", "old_date": "2026-11-15",
            "new_date": "2026-11-22", "amendment_ref": "amend-1"} in logs
    assert "deadline-ab-1-closing" in [e["event_id"] for e in s18.calendar["2026-11-22"]]
    assert "deadline-ab-1-closing" not in [e["event_id"]
                                           for e in s18.calendar.get("2026-11-15", [])]


def test_amendment_without_a_reference_is_refused(tmp_path):
    hub, s07, _ = _tx_hub(tmp_path)
    hub.send(signed(hub, "07", "ab-2", {"timeline_init": {"closing": "2026-11-15"}}))
    hub.send(signed(hub, "07", "ab-2", {"milestone_amendment": {
        "milestone": "closing", "new_date": "2026-11-22"}}))
    assert s07.timelines["ab-2"]["closing"]["deadline"] == "2026-11-15"
    assert any("milestone amendment refused" in r for r in queue_reasons(hub, "ab-2"))


def test_a_verbal_closing_move_asks_the_owner(tmp_path):
    hub, s07, _ = _tx_hub(tmp_path)
    hub.send(signed(hub, "07", "ae-1", {"timeline_init": {"closing": "2026-11-15"}}))
    hub.send(signed(hub, "07", "ae-1", {"closing_date_moved_verbally": {
        "new_date": "2026-11-29"}}))
    assert s07.timelines["ae-1"]["closing"]["deadline"] == "2026-11-15"
    assert any("closing date reportedly moved verbally" in r for r in queue_reasons(hub, "ae-1"))


# ------------------------------------------------------------- AM, AN (Agent 12)
def _s12(hub):
    from dispatcher.listing_spokes_12 import Spoke12MarketingCampaign
    return Spoke12MarketingCampaign(hub, brokerage_identification="Synth Realty, Testville OH")


def test_no_retraction_for_an_ad_still_held_for_release(tmp_path):
    hub = make_hub(tmp_path)
    s12 = _s12(hub)
    hub.on_turn_start()
    hub.send(env("05", "12", "status.update", "am-1", {"status": "active"}))
    hub.send(signed(hub, "12", "am-1", {"new_campaign": {"body": "x"}}))
    hub.send(env("17", "12", "content.verdict", "am-1", {"verdict": "approved"}))
    hub.send(env("external", "12", "platform.metrics", "am-1",
                 {"event_kind": "stale_detected", "delta": "price", "retract_requested": True}))
    assert not [e for e in persisted(hub, "campaign.publish", "am-1")
                if e["payload"].get("action") == "retract"]
    assert any("still held for your release - decline it" in r for r in queue_reasons(hub, "am-1"))


def test_no_retraction_for_an_ad_never_published(tmp_path):
    hub = make_hub(tmp_path)
    _s12(hub)
    hub.on_turn_start()
    hub.send(env("external", "12", "platform.metrics", "am-2",
                 {"event_kind": "stale_detected", "delta": "price", "retract_requested": True}))
    assert not persisted(hub, "campaign.publish", "am-2")
    assert any("was ever published - nothing to retract" in r for r in queue_reasons(hub, "am-2"))


def test_an_asset_from_04_waiting_on_the_mls_gate_is_tracked(tmp_path):
    hub = make_hub(tmp_path)
    _s12(hub)
    hub.on_turn_start()
    hub.send(env("04", "12", "asset.release", "an-1",
                 {"draft": {"facts": [], "body": "x"}, "approved_by_verdict": "v1"}))
    waits = [e["payload"] for e in persisted(hub, "agent.status", "an-1")]
    assert {"waiting_on": "ccp_gate", "since": None} in waits


# ------------------------------------------------------------- D-A12 (AS), D-A20
def _s13(hub):
    from dispatcher.listing_spokes_13 import Spoke13BuyerSearchMatch
    from tests_listing.test_agent13 import answering_14
    s13 = Spoke13BuyerSearchMatch(hub)
    answering_14(hub, on_file=True)
    return s13


def _listing(hub, ctx, payload):
    hub.send(env("05", "13", "listing.data", ctx, payload))


def test_missing_must_have_keeps_the_match_and_asks_the_buyer(tmp_path):
    hub = make_hub(tmp_path)
    s13 = _s13(hub)
    hub.on_turn_start()
    hub.send(signed(hub, "13", "as-1", {"buyer_criteria": [
        {"field": "budget", "value": 500000}, {"field": "pool", "value": True, "hard": True}]}))
    _listing(hub, "as-1", {"listing_id": "L1", "price": 450000})
    asks = [e["payload"] for e in persisted(hub, "client.message.request", "as-1")]
    assert asks == [{"template": "unknown_criterion_ask", "field": "pool", "listing_id": "L1"}]
    assert "L1" in s13.unknown_kept["as-1"]
    _listing(hub, "as-1", {"listing_id": "L1", "price": 450000})     # same listing again
    assert len(persisted(hub, "client.message.request", "as-1")) == 1  # asked once
    # the owner records the buyer's yes: the kept match goes out, flagged unknown
    hub.send(signed(hub, "13", "as-1", {"deliver_unknown_standing_preference": True}))
    assert [m["listing_id"] for m in s13.match_history.get("as-1", [])] == ["L1"]
    assert s13.match_history["as-1"][0]["unknown_fields"] == ["pool"]


def test_signed_replace_drops_a_criterion_and_rechecks_kept_matches(tmp_path):
    hub = make_hub(tmp_path)
    s13 = _s13(hub)
    hub.on_turn_start()
    hub.send(signed(hub, "13", "as-2", {"buyer_criteria": [
        {"field": "budget", "value": 500000}, {"field": "pool", "value": True, "hard": True}]}))
    _listing(hub, "as-2", {"listing_id": "L2", "price": 450000})
    assert "L2" in s13.unknown_kept["as-2"]
    hub.send(signed(hub, "13", "as-2", {"buyer_criteria_replace": [
        {"field": "budget", "value": 500000}]}))
    assert [c["field"] for c in s13.buyer_criteria["as-2"]] == ["budget"]
    logs = [e["payload"] for e in persisted(hub, "interaction.log", "as-2")
            if e["payload"].get("kind") == "buyer_criteria_replaced"]
    assert [c["field"] for c in logs[0]["old"]] == ["budget", "pool"]
    assert [m["listing_id"] for m in s13.match_history.get("as-2", [])] == ["L2"]


# ------------------------------------------------------------- D-A6 (6, AP)
def test_frozen_record_takes_an_opt_out_and_holds_an_opt_in(tmp_path):
    hub = make_hub(tmp_path)
    s14 = Spoke14CRMPipeline(hub)
    hub.on_turn_start()
    give_consent(hub, "fz-1")                     # email yes on record
    hub.send(signed(hub, "14", "fz-1", {"action": "delete_record"}))
    hub.send(env("11", "14", "interaction.log", "fz-1",
                 {"kind": "channel_change", "consent": {"text": "yes"}}))
    assert s14.consent["fz-1"].get("text") != "yes"           # opt-in waits
    assert any("WAITS" in r for r in queue_reasons(hub, "fz-1"))
    hub.send(env("03", "14", "interaction.log", "fz-1",
                 {"kind": "opt_out", "consent": {"email": "no"}}))
    assert s14.consent["fz-1"]["email"] == "no"               # opt-out applies
    assert s14.records["fz-1"][-1]["recorded_while_frozen"] == "opt-out"
    hub.send(signed(hub, "14", "fz-1", {"action": "release_record_freeze"}))
    assert s14.consent["fz-1"]["text"] == "yes"               # applied on release


def test_frozen_record_flags_do_not_change_on_a_refused_write(tmp_path):
    hub = make_hub(tmp_path)
    s14 = Spoke14CRMPipeline(hub)
    hub.on_turn_start()
    hub.send(signed(hub, "14", "fz-2", {"action": "delete_record"}))
    hub.send(env("13", "14", "interaction.log", "fz-2",
                 {"kind": "agreement", "buyer_agreement_on_file": True}))
    assert s14.buyer_agreement.get("fz-2") is not True


def test_channel_change_on_a_frozen_record_is_not_confirmed_to_the_client(tmp_path):
    hub = make_hub(tmp_path)
    Spoke14CRMPipeline(hub)
    Spoke11ClientCommunication(hub)
    hub.on_turn_start()
    give_consent(hub, "fz-3")
    hub.send(signed(hub, "14", "fz-3", {"action": "delete_record"}))
    hub.send(env("external", "11", "client.reply", "fz-3",
                 {"message": "please text me instead", "requests_channel_change": True,
                  "new_channel": "text", "hour": 14}))
    assert not [e for e in persisted(hub, "client.message.send", "fz-3")
                if e["payload"]["template"] == "channel_change_confirmed"]
    reasons = queue_reasons(hub, "fz-3")
    assert any("WAITS" in r for r in reasons)                       # Agent 14 asks, once
    assert not any("opted out of earlier" in r for r in reasons)


def test_channel_change_to_a_consented_channel_is_not_confirmed_while_frozen(tmp_path):
    """The client already consented to text; asking to be texted changes the
    record, which is frozen, so nothing is confirmed (D-A6)."""
    hub = make_hub(tmp_path)
    Spoke14CRMPipeline(hub)
    Spoke11ClientCommunication(hub)
    hub.on_turn_start()
    hub.send(signed(hub, "14", "fz-4", {"consent_record": {"email": "yes", "text": "yes"}}))
    hub.send(signed(hub, "14", "fz-4", {"action": "delete_record"}))
    hub.send(env("external", "11", "client.reply", "fz-4",
                 {"message": "please text me instead", "requests_channel_change": True,
                  "new_channel": "text", "hour": 14}))
    assert not persisted(hub, "client.message.send", "fz-4")
    assert len([r for r in queue_reasons(hub, "fz-4") if "WAITS" in r]) == 1



def test_access_grant_on_a_frozen_record_waits_for_the_freeze_to_lift(tmp_path):
    """Found writing the manual (2026-10-28): the grant list changed while the
    log entry was refused. Now it waits like every other change (D-A6)."""
    hub = make_hub(tmp_path)
    s14 = Spoke14CRMPipeline(hub)
    hub.on_turn_start()
    hub.send(signed(hub, "14", "fz-5", {"action": "delete_record"}))
    hub.send(signed(hub, "14", "fz-5", {"access_grant": {
        "party": "inspector", "window_end": "2026-10-30", "custody_ref": "lockbox log 7"}}))
    assert not s14.access_grants.get("fz-5")
    assert any("access_grant" in r and "WAITS" in r for r in queue_reasons(hub, "fz-5"))
    hub.send(signed(hub, "14", "fz-5", {"action": "release_record_freeze"}))
    assert s14.access_grants["fz-5"][0]["party"] == "inspector"


def test_an_escrow_mention_inside_an_expense_is_caught(tmp_path):
    """Found writing the manual (2026-10-28): only top-level text was checked,
    so a disbursement inside add_expense was recorded as an expense."""
    from dispatcher.listing_spokes_15 import Spoke15FinancialTracking
    hub = make_hub(tmp_path)
    s15 = Spoke15FinancialTracking(hub)
    hub.on_turn_start()
    hub.send(signed(hub, "15", "es-1", {"add_expense": {
        "amount": 500, "description": "disbursement to the seller per their email"}}))
    assert not s15.expenses.get("es-1")
    assert any("disbursement" in str(r) for r in hub.queues["escalation.legal_line"])


def test_the_day_figures_keep_estimates_apart_from_recorded_commissions(tmp_path):
    """Found writing the manual (2026-10-28): one total added a commission
    computed at the default rate to a signed one."""
    from dispatcher.listing_spokes_15 import Spoke15FinancialTracking
    hub = make_hub(tmp_path)
    s15 = Spoke15FinancialTracking(hub)
    hub.on_turn_start()
    hub.send(env("07", "15", "transaction.closed", "cm-1",
                 {"closed": True, "close_date": "2026-10-27", "commission_amount": 9000,
                  "signed_docs_only": True}))
    hub.send(env("07", "15", "transaction.closed", "cm-2",
                 {"closed": True, "close_date": "2026-10-27", "sale_price": 100000,
                  "signed_docs_only": True}))
    f = s15.day_figures("2026-10-27")
    assert f["commission_total_recorded"] == 9000
    assert f["commission_total_estimated"] == 100000 * s15.commission_rate

# ------------------------------------------------------------- D-A18, D-A19 (AQ, AV)
def test_morning_briefing_lists_record_conflicts_and_compliance_notices_once(tmp_path):
    from dispatcher.listing_spokes_17 import Spoke17ComplianceFairHousing
    from dispatcher.listing_spokes_18 import Spoke18CalendarTask
    hub = make_hub(tmp_path)
    Spoke14CRMPipeline(hub)
    Spoke17ComplianceFairHousing(hub)
    s18 = Spoke18CalendarTask(hub)
    hub.on_turn_start()
    hub.send(env("06", "14", "interaction.log", "aq-1", {"kind": "showing_feedback", "rating": 4}))
    hub.send(env("06", "14", "interaction.log", "aq-1", {"kind": "showing_feedback", "rating": 2}))
    hub.send(env("10", "17", "compliance.notice", "av-1",
                 {"trigger": "data request smelled like appraisal substitution",
                  "agent": "10", "requested_by": "human", "today": "2026-10-27"}))
    b = s18.generate_briefing("morning", "2026-10-28")
    rc = b["sections"]["record_conflicts"]
    assert rc["count"] == 1 and rc["conflicts"][0]["field"] == "rating"
    assert (rc["conflicts"][0]["old"], rc["conflicts"][0]["new"]) == (4, 2)
    cn = b["sections"]["compliance_notices"]
    assert cn["count"] == 1 and cn["notices"][0]["requested_by"] == "human"
    b2 = s18.generate_briefing("morning", "2026-10-29")
    assert b2["sections"]["record_conflicts"]["count"] == 0
    assert b2["sections"]["compliance_notices"]["count"] == 0


def test_sla_breach_note_is_sent_once_per_waiting_review(tmp_path):
    from dispatcher.listing_spokes_17 import Spoke17ComplianceFairHousing
    hub = make_hub(tmp_path)
    s17 = Spoke17ComplianceFairHousing(hub)
    hub.on_turn_start()
    s17.pending_reviews["au-1"] = {"submitted_at": "2026-10-20", "agent": "04"}
    assert s17.check_sla("au-1", "2026-10-25") == "breached"
    assert s17.check_sla("au-1", "2026-10-26") == "breached_already_alerted"
    assert len([r for r in queue_reasons(hub, "au-1") if "SLA breach" in r]) == 1


# ------------------------------------------------------------- D-A16 (AW)
def test_agent_19_no_longer_talks_to_agent_10(tmp_path):
    import json
    routes = json.load(open(IDENTITY_ROUTES))["routes"]
    by = {r["intent"]: r for r in routes}
    assert "19" not in by["data.request"]["senders"]
    assert "19" not in by["data.package"]["receivers"]
    from dispatcher.listing_spokes_19 import Spoke19Prospecting
    hub = make_hub(tmp_path)
    s19 = Spoke19Prospecting(hub)
    hub.on_turn_start()
    hub.send(signed(hub, "19", "setup", {"zip_codes": ["44811"]}))
    hub.send(env("external", "19", "discovery.feed", "aw-1",
                 {"listing_id": "LW", "zip_code": "44811", "status": "new", "source": "mls"}))
    assert not persisted(hub, "data.request")
    assert not [e for e in persisted(hub, "agent.status")
                if e["payload"].get("waiting_on") == "market_context_enrichment"]
    assert s19.opportunities["LW"]["market_context"] == "none - no comp source connected"


# ------------------------------------------------- found re-checking the manual
def _held_ad(hub, ctx):
    hub.send(env("05", "12", "status.update", ctx, {"status": "active"}))
    hub.send(signed(hub, "12", ctx, {"new_campaign": {"body": "x"}}))
    hub.send(env("17", "12", "content.verdict", ctx, {"verdict": "approved"}))
    (held_id,) = list(hub._absolute_holds)
    auth = Envelope(from_agent="human", to_agent="12", intent="disclosure.authority",
                    client_context_id=ctx,
                    payload={"held_envelope_id": held_id, "decision": "decline"},
                    provenance={"source": "human", "captured_at": "runtime",
                                "verbatim_available": True})
    hub._test_signer.sign(auth)
    assert hub.decline_disclosure(auth)["status"] == "declined"


def test_a_declined_ad_is_never_retracted_or_halted(tmp_path):
    hub = make_hub(tmp_path)
    _s12(hub)
    hub.on_turn_start()
    _held_ad(hub, "rc-2")
    hub.send(env("external", "12", "platform.metrics", "rc-2",
                 {"event_kind": "stale_detected", "delta": "price", "retract_requested": True}))
    hub.send(env("05", "12", "status.update", "rc-2", {"status": "withdrawn"}))
    sent = [e["payload"] for e in persisted(hub, "campaign.publish", "rc-2")]
    held = [e.payload for e in hub._absolute_holds.values()]
    assert not [p for p in sent + held if p.get("action") in ("retract", "halt")]


def test_the_duplicate_check_retry_carries_the_contact_and_asks_you_once(tmp_path):
    hub = make_hub(tmp_path)
    s01 = Spoke01LeadCapture(hub, record_response_timeout_days=1)
    hub.register("14", lambda e: None)          # Agent 14 never answers
    hub.on_turn_start()
    hub.send(env("external", "01", "lead.inbound", "rc-3",
                 {"channel": "web_form", "name": "Waiting", "phone": "(330) 555-0111",
                  "today": "2026-07-01", "consent": {"email": "yes"}}))
    assert s01.check_record_response_timeout("rc-3", "2026-07-03") == "retried"
    retry = persisted(hub, "record.request", "rc-3")[-1]["payload"]
    assert retry["identifiers"]
    assert s01.check_record_response_timeout("rc-3", "2026-07-05") == "handoff.failed"
    assert s01.check_record_response_timeout("rc-3", "2026-07-06") == "already_failed"
    assert len([r for r in queue_reasons(hub, "rc-3") if "lead held undeduped" in r]) == 1


def test_stop_with_no_running_sequence_opts_out_every_channel(tmp_path):
    hub = make_hub(tmp_path)
    Spoke03LeadNurture(hub)
    hub.on_turn_start()
    hub.send(env("11", "03", "lead.reply", "rc-4", {"message": "STOP", "channel": "text"}))
    logs = [e["payload"] for e in persisted(hub, "interaction.log", "rc-4")
            if e["payload"].get("kind") == "opt_out"]
    assert logs and logs[0]["consent"] == {"call": "no", "text": "no", "email": "no"}


def test_a_channel_change_naming_no_channel_is_not_confirmed(tmp_path):
    hub = make_hub(tmp_path)
    Spoke14CRMPipeline(hub)
    Spoke11ClientCommunication(hub)
    hub.on_turn_start()
    give_consent(hub, "rc-5")
    hub.send(env("external", "11", "client.reply", "rc-5",
                 {"message": "reach me some other way", "requests_channel_change": True,
                  "hour": 14}))
    assert not persisted(hub, "client.message.send", "rc-5")
    assert any("named no channel" in r for r in queue_reasons(hub, "rc-5"))


def test_a_day_s_digest_is_sent_before_the_next_day_starts(tmp_path):
    hub = make_hub(tmp_path)
    s13 = _s13(hub)
    hub.on_turn_start()
    hub.send(signed(hub, "13", "rc-6", {"buyer_criteria": [{"field": "beds", "value": 2}]}))
    for i in range(7):
        _listing(hub, "rc-6", {"listing_id": f"D{i}", "beds": 3, "today": "2026-10-16"})
    assert len(s13.matches_today["rc-6"]["overflow"]) == 2
    _listing(hub, "rc-6", {"listing_id": "N1", "beds": 3, "today": "2026-10-17"})
    digests = [e["payload"] for e in persisted(hub, "client.message.request", "rc-6")
               if e["payload"].get("template") == "match_digest"]
    assert digests and digests[0]["count"] == 2


def test_feedback_does_not_mark_a_showing_not_yet_held(tmp_path, monkeypatch):
    from dispatcher.listing_spokes_06 import Spoke06ShowingScheduler
    monkeypatch.setenv("LISTING_CLOCK_NOW", "2026-10-17T12:00:00")
    hub = make_hub(tmp_path)
    s06 = Spoke06ShowingScheduler(hub)
    hub.on_turn_start()
    s06.confirmed_showings["rc-7"] = [
        {"time": "2026-10-16T10:00:00", "listing_id": "L1", "confirmed": True},
        {"time": "2026-10-25T10:00:00", "listing_id": "L2", "confirmed": True}]
    assert s06.clock_showing_feedback("rc-7", "2026-10-17") == "asked"
    hub.send(env("11", "06", "showing.feedback_response", "rc-7", {"message": "liked it"}))
    assert s06.confirmed_showings["rc-7"][0].get("feedback_received") is True
    assert not s06.confirmed_showings["rc-7"][1].get("feedback_received")


def test_a_criterion_from_buyer_feedback_is_checked_for_protected_class(tmp_path):
    hub = make_hub(tmp_path)
    s13 = _s13(hub)
    hub.on_turn_start()
    hub.send(env("11", "13", "lead.reply", "rc-8",
                 {"message": "more of these please", "explicit_feedback_field": "school rating",
                  "explicit_feedback_value": "high"}))
    assert not s13.buyer_criteria.get("rc-8")
    assert hub.queues["escalation.legal_line"]


def test_the_buyer_s_answer_to_a_criteria_question_reaches_you(tmp_path):
    hub = make_hub(tmp_path)
    _s13(hub)
    hub.on_turn_start()
    for msg in ("forget the 3 bedrooms", "yes, forget the 3 bedrooms"):
        hub.send(env("11", "13", "lead.reply", "rc-9",
                     {"message": msg, "contradicts_stated_criteria": True}))
    asks = [e for e in persisted(hub, "client.message.request", "rc-9")
            if e["payload"].get("template") == "confirm_criteria_update"]
    assert len(asks) == 1
    assert any("buyer answered the criteria question" in r for r in queue_reasons(hub, "rc-9"))
