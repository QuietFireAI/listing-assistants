"""Pressure test for listing Agent 03 (Lead Nurture).

All tests go through the real hub (hub.send()), against real routes in
identity/routes.json. Note for future readers: this file used to split
tests into a "full hub" class and a "logic-only, spoke.handle() direct"
class, because lead.reply and behavioral.signal had no ratified route
into this agent yet. Both routes were added since (11->03/04/12/13/20
for lead.reply; 12,20->03 for behavioral.signal) - confirmed 2026-07-16,
zero remaining spoke.handle() calls in this file. Every test here is a
genuine end-to-end route test, not a logic-only stand-in.
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from nurture_fixture import with_sequences
from dispatcher.core import Envelope, Routes, AuditLog
from dispatcher.hub import Hub
from dispatcher.listing_spokes_03 import Spoke03LeadNurture

IDENTITY_ROUTES = os.path.join(os.path.dirname(__file__), "..", "identity",
                               "routes.json")


def make_hub(tmp_path, **kw):
    audit_path = os.path.join(tmp_path, f"audit-{uuid.uuid4().hex[:8]}.jsonl")
    return Hub(Routes(IDENTITY_ROUTES), AuditLog(audit_path), **kw)


def nurture_env(ctx, payload):
    return Envelope(from_agent="02", to_agent="03", intent="lead.nurture",
                    client_context_id=ctx, payload=payload,
                    provenance={"source": "spoke-02", "captured_at": "runtime",
                                "verbatim_available": True})


def persisted(hub, intent=None):
    events = [e for e in hub.audit.read() if e["kind"] == "envelope.persisted"]
    return [e for e in events if intent is None or e["intent"] == intent]


# ------------------------------------------------------------ full hub path
def test_no_consent_on_any_channel_escalates_no_send(tmp_path):
    hub = make_hub(str(tmp_path))
    with_sequences(Spoke03LeadNurture(hub))
    hub.on_turn_start()

    hub.send(nurture_env("n-001", {"consent": {"call": "no", "text": "no", "email": "no"}}))
    assert hub.queues["escalation.legal_line"]


def test_consent_present_starts_sequence(tmp_path):
    hub = make_hub(str(tmp_path))
    spoke = with_sequences(Spoke03LeadNurture(hub))
    hub.on_turn_start()

    hub.send(nurture_env("n-002", {"consent": {"email": "yes"}, "sequence_id": "market_drip"}))
    assert spoke.active_sequences["n-002"]["sequence_id"] == "market_drip"
    assert spoke.active_sequences["n-002"]["paused"] is False


def test_overlapping_sequence_runs_neither_until_human_picks(tmp_path):
    hub = make_hub(str(tmp_path))
    spoke = with_sequences(Spoke03LeadNurture(hub))
    hub.on_turn_start()

    hub.send(nurture_env("n-003", {"consent": {"email": "yes"}, "sequence_id": "seq_a"}))
    hub.send(nurture_env("n-003", {"consent": {"email": "yes"}, "sequence_id": "seq_b"}))

    clar = persisted(hub, "clarification.request")
    assert any(c["payload"]["reason"] == "overlapping sequences" for c in clar)
    assert spoke.active_sequences["n-003"]["paused"] is True


# ------------------------------------------- THE FIX: reassignment wins
def test_reassignment_supersedes_without_holding_for_human(tmp_path):
    """Tuple 10, confirmed distinct from tuple 4 (2026-07-16): a
    deliberate reassignment (Agent 02 re-evaluating after a rescore) is
    NOT the same as tuple 4's ambiguous simultaneous conflict - the
    newer signed instruction should supersede outright, logged, not held
    for a human who was never actually needed here."""
    hub = make_hub(str(tmp_path))
    spoke = with_sequences(Spoke03LeadNurture(hub))
    hub.on_turn_start()
    ctx = "n-003b"

    hub.send(nurture_env(ctx, {"consent": {"email": "yes"},
                               "sequence_id": "seq_a"}))
    assert spoke.active_sequences[ctx]["sequence_id"] == "seq_a"

    reassign = Envelope(from_agent="02", to_agent="03", intent="lead.nurture",
                       client_context_id=ctx,
                       payload={"consent": {"email": "yes"},
                               "sequence_id": "seq_b",
                               "reassignment": True},
                       provenance={"source": "spoke-02", "captured_at": "runtime",
                                   "verbatim_available": True})
    hub.send(reassign)

    assert spoke.active_sequences[ctx]["sequence_id"] == "seq_b"
    assert spoke.active_sequences[ctx]["paused"] is False
    clar = persisted(hub, "clarification.request")
    assert not any(c["payload"].get("reason") == "overlapping sequences"
                  for c in clar), "a reassignment must not hold for human"
    logs = persisted(hub, "interaction.log")
    assert any(l["payload"].get("kind") == "sequence_reassigned" for l in logs)


def test_ambiguous_overlap_without_reassignment_flag_still_holds(tmp_path):
    """Confirms the default (tuple 4) path is unchanged: absent the
    reassignment signal, an overlap still holds for a human exactly as
    before - this is the genuine simultaneous-eligibility conflict, not
    a deliberate supersession."""
    hub = make_hub(str(tmp_path))
    spoke = with_sequences(Spoke03LeadNurture(hub))
    hub.on_turn_start()
    ctx = "n-003c"

    hub.send(nurture_env(ctx, {"consent": {"email": "yes"},
                               "sequence_id": "seq_a"}))
    # no reassignment flag at all - the ambiguous-eligibility case
    hub.send(nurture_env(ctx, {"consent": {"email": "yes"},
                               "sequence_id": "seq_b"}))

    assert spoke.active_sequences[ctx]["sequence_id"] == "seq_a", \
        "without the reassignment signal, the original sequence must stay"
    assert spoke.active_sequences[ctx]["paused"] is True
    clar = persisted(hub, "clarification.request")
    assert any(c["payload"].get("reason") == "overlapping sequences" for c in clar)


def test_content_review_submitted_before_any_send(tmp_path):
    hub = make_hub(str(tmp_path))
    spoke = with_sequences(Spoke03LeadNurture(hub))
    hub.on_turn_start()
    hub.send(nurture_env("n-004", {"consent": {"email": "yes"}, "sequence_id": "seq_a"}))
    assert spoke.active_sequences["n-004"]["compliance_status"] == "pending"
    reviews = persisted(hub, "content.review")
    assert reviews and reviews[0]["to_agent"] == "17"


def test_content_verdict_flagged_holds_sequence(tmp_path):
    hub = make_hub(str(tmp_path))
    spoke = with_sequences(Spoke03LeadNurture(hub))
    hub.on_turn_start()
    hub.send(nurture_env("n-004b", {"consent": {"email": "yes"}, "sequence_id": "seq_a"}))
    env = Envelope(from_agent="17", to_agent="03", intent="content.verdict",
                  client_context_id="n-004b",
                  payload={"verdict": "flagged", "findings": [{"phrase": "guaranteed"}]},
                  provenance={"source": "spoke-17", "captured_at": "runtime",
                              "verbatim_available": True})
    hub.send(env)
    assert spoke.active_sequences["n-004b"]["compliance_status"] == "pending"
    assert spoke.active_sequences["n-004b"]["paused"] is True


def test_content_verdict_approved_clears_sequence(tmp_path):
    hub = make_hub(str(tmp_path))
    spoke = with_sequences(Spoke03LeadNurture(hub))
    hub.on_turn_start()
    hub.send(nurture_env("n-004c", {"consent": {"email": "yes"}, "sequence_id": "seq_a"}))
    env = Envelope(from_agent="17", to_agent="03", intent="content.verdict",
                  client_context_id="n-004c", payload={"verdict": "approved"},
                  provenance={"source": "spoke-17", "captured_at": "runtime",
                              "verbatim_available": True})
    hub.send(env)
    assert spoke.active_sequences["n-004c"]["compliance_status"] == "cleared"


def test_no_market_update_path_owner_decision_j5():
    """Owner decision J5 (2026-10-12): Lead Nurture no longer requests
    market data or builds market-update touches (pricing information to a
    nurtured lead; the request also named no data mode, so 10 refused it).
    The route lanes 03 -data.request-> 10 and 10 -data.package-> 03 are gone."""
    import json
    assert not hasattr(Spoke03LeadNurture, "request_market_update")
    routes = json.load(open(os.path.join(os.path.dirname(__file__), "..", "identity", "routes.json"), encoding="utf-8"))
    by = {r["intent"]: r for r in routes["routes"]}
    assert "03" not in by["data.request"]["senders"] and "03" not in by["data.package"]["receivers"]


# --------------------------------------------------- confirm the gap is closed
def test_lead_reply_now_reaches_agent03_through_the_real_hub(tmp_path):
    """Was: proved lead.reply held in clarification, unreachable. Now: the
    route exists (11 -> 03/04/12/13/20), so it reaches the handler for real."""
    hub = make_hub(str(tmp_path))
    spoke = with_sequences(Spoke03LeadNurture(hub))
    hub.on_turn_start()
    hub.send(nurture_env("n-007", {"consent": {"call": "yes", "text": "yes"},
                                   "sequence_id": "seq_a"}))

    env = Envelope(from_agent="11", to_agent="03", intent="lead.reply",
                  client_context_id="n-007", payload={"message": "stop"},
                  provenance={"source": "spoke-11", "captured_at": "runtime",
                              "verbatim_available": True})
    result = hub.send(env)
    assert result["status"] == "ack"
    events = hub.audit.read()
    assert [e for e in events if e["kind"] == "ack"
           and e["envelope_id"] == env.envelope_id]


def test_explicit_stop_suppresses_all_channels(tmp_path):
    hub = make_hub(str(tmp_path))
    spoke = with_sequences(Spoke03LeadNurture(hub))
    hub.on_turn_start()
    hub.send(nurture_env("n-008", {"consent": {"call": "yes", "text": "yes"},
                                   "sequence_id": "seq_a"}))

    env = Envelope(from_agent="11", to_agent="03", intent="lead.reply",
                  client_context_id="n-008", payload={"message": "STOP", "channel": "text"},
                  provenance={"source": "spoke-11", "captured_at": "runtime",
                              "verbatim_available": True})
    hub.send(env)
    assert spoke.active_sequences["n-008"]["consent"] == {"call": "no", "text": "no"}
    # THE FIX: tuple 6 requires an actual client-facing confirmation, not
    # just the internal interaction.log system-of-record entry.
    confirmations = persisted(hub, "client.message.request")
    assert any(c["payload"].get("template") == "opt_out_confirmed" for c in confirmations), \
        "STOP must send a real client-facing confirmation, not just log internally"
    # D-A8 (owner, 2026-10-28): only on the channel the STOP came in on
    assert [c["payload"].get("channel") for c in confirmations
            if c["payload"].get("template") == "opt_out_confirmed"] == ["text"]


def test_engagement_spike_pauses_and_rescores(tmp_path):
    hub = make_hub(str(tmp_path))
    spoke = with_sequences(Spoke03LeadNurture(hub))
    hub.on_turn_start()
    hub.send(nurture_env("n-009", {"consent": {"email": "yes"}, "sequence_id": "seq_a"}))

    env = Envelope(from_agent="12", to_agent="03", intent="behavioral.signal",
                  client_context_id="n-009",
                  payload={"engagement_score": 80, "spike_threshold": 50},
                  provenance={"source": "spoke-12", "captured_at": "runtime",
                              "verbatim_available": True})
    result = hub.send(env)
    assert result["status"] == "ack"
    assert spoke.active_sequences["n-009"]["paused"] is True
    assert persisted(hub, "lead.rescored")


def test_substantive_question_routes_to_11_for_gated_human_reply(tmp_path):
    hub = make_hub(str(tmp_path))
    spoke = with_sequences(Spoke03LeadNurture(hub))
    hub.on_turn_start()
    hub.send(nurture_env("n-010", {"consent": {"call": "yes"}, "sequence_id": "seq_a"}))

    env = Envelope(from_agent="11", to_agent="03", intent="lead.reply",
                  client_context_id="n-010",
                  payload={"message": "What's the square footage on the second unit?"},
                  provenance={"source": "spoke-11", "captured_at": "runtime",
                              "verbatim_available": True})
    result = hub.send(env)
    assert result["status"] == "ack"
    routed = persisted(hub, "client.message.request")
    assert routed and routed[0]["to_agent"] == "11"


def test_compliance_wait_status_pushed_and_cleared_on_approval(tmp_path):
    hub = make_hub(str(tmp_path))
    with_sequences(Spoke03LeadNurture(hub))
    hub.on_turn_start()
    hub.send(nurture_env("n-020", {"consent": {"email": "yes"}, "sequence_id": "seq_a"}))
    status = persisted(hub, "agent.status")
    assert status and status[0]["payload"]["waiting_on"] == "compliance_review"

    verdict = Envelope(from_agent="17", to_agent="03", intent="content.verdict",
                      client_context_id="n-020", payload={"verdict": "approved"},
                      provenance={"source": "spoke-17", "captured_at": "runtime",
                                  "verbatim_available": True})
    hub.send(verdict)
    statuses = persisted(hub, "agent.status")
    assert any(s["payload"].get("resolved") for s in statuses)


def test_REGRESSION_frequency_cap_actually_enforced_now(tmp_path):
    """touch_log was declared but never read or written anywhere -
    frequency_cap_per_week only ever decreased on complaint, nothing ever
    checked touches sent against it. Proves real enforcement now."""
    hub = make_hub(str(tmp_path))
    spoke = with_sequences(Spoke03LeadNurture(hub, frequency_cap_per_week=2))
    hub.on_turn_start()
    ctx = "touch-001"
    # started at 23:00, outside contact hours: the day-0 touch is held at
    # clearance (decision 7, 2026-10-21), so this test sees only its own sends
    hub.send(nurture_env(ctx, {"consent": {"email": "yes"}, "sequence_id": "seq_a",
                              "now_iso": "2026-08-05T23:00:00"}))
    verdict = Envelope(from_agent="17", to_agent="03", intent="content.verdict",
                      client_context_id=ctx, payload={"verdict": "approved"},
                      provenance={"source": "spoke-17", "captured_at": "runtime",
                                  "verbatim_available": True})
    hub.send(verdict)

    r1 = spoke.send_scheduled_touch(ctx, {"body": "touch 1"}, "2026-W32")
    r2 = spoke.send_scheduled_touch(ctx, {"body": "touch 2"}, "2026-W32")
    r3 = spoke.send_scheduled_touch(ctx, {"body": "touch 3"}, "2026-W32")
    assert [r1, r2, r3] == ["sent", "sent", "held_frequency_cap"]

    sends = persisted(hub, "client.message.request")
    touches = [s for s in sends if s["payload"].get("template") == "sequence_touch"]
    assert len(touches) == 2  # never a third in the same week


def test_REGRESSION_frequency_cap_resets_next_week(tmp_path):
    hub = make_hub(str(tmp_path))
    spoke = with_sequences(Spoke03LeadNurture(hub, frequency_cap_per_week=1))
    hub.on_turn_start()
    ctx = "touch-002"
    hub.send(nurture_env(ctx, {"consent": {"email": "yes"}, "sequence_id": "seq_a"}))
    verdict = Envelope(from_agent="17", to_agent="03", intent="content.verdict",
                      client_context_id=ctx, payload={"verdict": "approved"},
                      provenance={"source": "spoke-17", "captured_at": "runtime",
                                  "verbatim_available": True})
    hub.send(verdict)
    r1 = spoke.send_scheduled_touch(ctx, {"body": "w32"}, "2026-W32")
    r2 = spoke.send_scheduled_touch(ctx, {"body": "w33"}, "2026-W33")
    assert [r1, r2] == ["sent", "sent"]


def test_REGRESSION_touch_never_sent_for_uncleared_sequence(tmp_path):
    hub = make_hub(str(tmp_path))
    spoke = with_sequences(Spoke03LeadNurture(hub))
    hub.on_turn_start()
    ctx = "touch-003"
    hub.send(nurture_env(ctx, {"consent": {"email": "yes"}, "sequence_id": "seq_a"}))
    # never approved - still pending
    result = spoke.send_scheduled_touch(ctx, {"body": "x"}, "2026-W32")
    assert result == "not_eligible"
    assert not persisted(hub, "client.message.request")


# ------------------------------------------- THE FIX: frequency complaint
def test_frequency_complaint_reduces_cadence_but_does_not_kill_sequence(tmp_path):
    """Tuple 2: 'stop sending so many' -> reduce + confirm, NOT a full
    opt-out - the sequence continues, just slower. Was: the generic
    tuple-1 'any reply pauses' logic set paused=True unconditionally
    before this branch even ran, and nothing here ever undid it - a
    frequency complaint silently killed the entire sequence forever,
    identical in effect to an explicit opt-out it explicitly isn't."""
    hub = make_hub(str(tmp_path))
    spoke = with_sequences(Spoke03LeadNurture(hub, frequency_cap_per_week=3))
    hub.on_turn_start()
    ctx = "freq-001"
    hub.send(nurture_env(ctx, {"consent": {"email": "yes"}, "sequence_id": "seq_a"}))
    verdict = Envelope(from_agent="17", to_agent="03", intent="content.verdict",
                      client_context_id=ctx, payload={"verdict": "approved"},
                      provenance={"source": "spoke-17", "captured_at": "runtime",
                                  "verbatim_available": True})
    hub.send(verdict)

    complaint = Envelope(from_agent="11", to_agent="03", intent="lead.reply",
                        client_context_id=ctx,
                        payload={"message": "you're sending too many emails"},
                        provenance={"source": "spoke-11", "captured_at": "runtime",
                                    "verbatim_available": True})
    hub.send(complaint)

    assert spoke.lead_cap(ctx) == 2, "this lead's cadence must actually reduce"
    # finding R (2026-10-27): the reduction is this lead's only
    assert spoke.frequency_cap_per_week == 3, "the agent-wide cap must not change"
    assert spoke.lead_cap("someone-else") == 3
    assert spoke.active_sequences[ctx]["paused"] is False, \
        "sequence must resume after a frequency complaint, not stay paused forever"
    # THE FIX: "+ confirm" half of the tuple never sent anything before.
    confirmations = persisted(hub, "client.message.request")
    assert any(c["payload"].get("template") == "frequency_reduced_confirmed"
              for c in confirmations), \
        "reducing cadence must be confirmed to the client, not just done silently"

    result = spoke.send_scheduled_touch(ctx, {"body": "next touch"}, "2026-W32")
    assert result == "sent", \
        "a touch must actually be sendable after the complaint is handled"


# ------------------------------------- THE FIX: tuple 7, legal hours/holiday
def test_touch_held_outside_legal_contact_hours(tmp_path):
    """Was: zero implementing code - send_scheduled_touch only ever
    checked compliance_status/paused/frequency_cap, despite the class
    docstring listing this tuple as done."""
    hub = make_hub(str(tmp_path))
    spoke = with_sequences(Spoke03LeadNurture(hub, legal_contact_hours=(8, 21)))
    hub.on_turn_start()
    ctx = "hours-001"
    # started at 23:00, outside contact hours: the day-0 touch is held at
    # clearance (decision 7, 2026-10-21), so this test sees only its own sends
    hub.send(nurture_env(ctx, {"consent": {"email": "yes"}, "sequence_id": "seq_a",
                              "now_iso": "2026-08-05T23:00:00"}))
    verdict = Envelope(from_agent="17", to_agent="03", intent="content.verdict",
                      client_context_id=ctx, payload={"verdict": "approved"},
                      provenance={"source": "spoke-17", "captured_at": "runtime",
                                  "verbatim_available": True})
    hub.send(verdict)

    result = spoke.send_scheduled_touch(ctx, {"body": "late touch"}, "2026-W32", hour=23)
    assert result == "held_outside_contact_hours"
    assert not persisted(hub, "client.message.request")


def test_touch_held_on_legal_holiday(tmp_path):
    hub = make_hub(str(tmp_path))
    spoke = with_sequences(Spoke03LeadNurture(hub))
    hub.on_turn_start()
    ctx = "hours-002"
    # started at 23:00, outside contact hours: the day-0 touch is held at
    # clearance (decision 7, 2026-10-21), so this test sees only its own sends
    hub.send(nurture_env(ctx, {"consent": {"email": "yes"}, "sequence_id": "seq_a",
                              "now_iso": "2026-08-05T23:00:00"}))
    verdict = Envelope(from_agent="17", to_agent="03", intent="content.verdict",
                      client_context_id=ctx, payload={"verdict": "approved"},
                      provenance={"source": "spoke-17", "captured_at": "runtime",
                                  "verbatim_available": True})
    hub.send(verdict)

    result = spoke.send_scheduled_touch(ctx, {"body": "holiday touch"}, "2026-W32",
                                        hour=10, is_legal_holiday=True)
    assert result == "held_legal_holiday"
    assert not persisted(hub, "client.message.request")


def test_touch_sends_normally_inside_legal_contact_hours(tmp_path):
    hub = make_hub(str(tmp_path))
    spoke = with_sequences(Spoke03LeadNurture(hub, legal_contact_hours=(8, 21)))
    hub.on_turn_start()
    ctx = "hours-003"
    hub.send(nurture_env(ctx, {"consent": {"email": "yes"}, "sequence_id": "seq_a"}))
    verdict = Envelope(from_agent="17", to_agent="03", intent="content.verdict",
                      client_context_id=ctx, payload={"verdict": "approved"},
                      provenance={"source": "spoke-17", "captured_at": "runtime",
                                  "verbatim_available": True})
    hub.send(verdict)

    result = spoke.send_scheduled_touch(ctx, {"body": "daytime touch"}, "2026-W32", hour=14)
    assert result == "sent"


def test_rescore_without_a_sequence_keeps_the_running_one(tmp_path):
    """Finding Q (procedures audit, 2026-10-27): Agent 02's re-score sends
    lead.nurture with reassignment=True and no sequence_id. That read as
    default_drip, so a lead on any other sequence was moved to default_drip
    and restarted at day 0. No sequence named keeps the current one."""
    hub = make_hub(str(tmp_path))
    spoke = with_sequences(Spoke03LeadNurture(hub))
    spoke.sequences["spring_buyers"] = {"touches": [{"day": 0, "text": "Spring touch"}]}
    hub.on_turn_start()
    ctx = "q-001"
    hub.send(nurture_env(ctx, {"consent": {"email": "yes"}, "sequence_id": "spring_buyers"}))
    assert spoke.active_sequences[ctx]["sequence_id"] == "spring_buyers"
    hub.send(nurture_env(ctx, {"consent": {"email": "yes"}, "reassignment": True}))
    assert spoke.active_sequences[ctx]["sequence_id"] == "spring_buyers"
    logs = persisted(hub, "interaction.log")
    assert not any(l["payload"].get("kind") == "sequence_reassigned" for l in logs), \
        "a re-score naming no sequence must not reassign"


def test_reassignment_naming_another_sequence_still_supersedes(tmp_path):
    """The other half stays as it was: a reassignment that names a new
    sequence replaces the running one (tuple 10)."""
    hub = make_hub(str(tmp_path))
    spoke = with_sequences(Spoke03LeadNurture(hub))
    spoke.sequences["spring_buyers"] = {"touches": [{"day": 0, "text": "Spring touch"}]}
    hub.on_turn_start()
    ctx = "q-002"
    hub.send(nurture_env(ctx, {"consent": {"email": "yes"}, "sequence_id": "spring_buyers"}))
    hub.send(nurture_env(ctx, {"consent": {"email": "yes"}, "reassignment": True,
                               "sequence_id": "seq_a"}))
    assert spoke.active_sequences[ctx]["sequence_id"] == "seq_a"


def test_frequency_complaint_lowers_only_that_leads_cap(tmp_path):
    """Finding R (procedures audit, 2026-10-27): 'too many' from one lead
    lowered frequency_cap_per_week for every lead. Now only that lead's."""
    hub = make_hub(str(tmp_path))
    spoke = with_sequences(Spoke03LeadNurture(hub, frequency_cap_per_week=2))
    hub.on_turn_start()
    for ctx in ("r-a", "r-b"):
        hub.send(nurture_env(ctx, {"consent": {"email": "yes"}, "sequence_id": "seq_a"}))
        hub.send(Envelope(from_agent="17", to_agent="03", intent="content.verdict",
                          client_context_id=ctx, payload={"verdict": "approved"},
                          provenance={"source": "spoke-17", "captured_at": "runtime",
                                      "verbatim_available": True}))
    hub.send(Envelope(from_agent="11", to_agent="03", intent="lead.reply",
                      client_context_id="r-a", payload={"message": "too many emails"},
                      provenance={"source": "spoke-11", "captured_at": "runtime",
                                  "verbatim_available": True}))
    assert spoke.lead_cap("r-a") == 1
    assert spoke.lead_cap("r-b") == 2
    week = "2026-W43"
    assert spoke.send_scheduled_touch("r-a", {"touch": 1}, week) == "sent"
    assert spoke.send_scheduled_touch("r-a", {"touch": 2}, week) == "held_frequency_cap"
    assert spoke.send_scheduled_touch("r-b", {"touch": 1}, week) == "sent"
    assert spoke.send_scheduled_touch("r-b", {"touch": 2}, week) == "sent"
