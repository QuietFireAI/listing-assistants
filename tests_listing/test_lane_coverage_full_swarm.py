"""Every declared lane exercised end to end in the FULL swarm.

Audit LC-1 (2026-10-11): 28 of 142 declared (sender, intent, receiver)
lanes were never delivered (ack/held) by any test. Most had an emitter that
unit tests called against a partial hub, where the send dead-lettered for
want of a receiver. Each test below drives the emitter's real code path
inside full_swarm() (all 20 agents + human/external sinks) and asserts the
lane is delivered with no handoff.failed.

Lanes with no emitter in the code are listed in NO_EMITTER and checked to
stay that way, so adding one later surfaces here:
  20 -behavioral.signal-> 03   declared route, Agent 20 never sends it
(11 -lead.reply-> 04 / 12 is covered in test_agent11.py since 04 and 12 got
handlers, owner decision 2026-10-11.)
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from test_playbooks_e2e import spoke_env                                    # noqa: E402
from test_playbooks_e2e_all import full_swarm                              # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def delivered(hub, frm, intent, to):
    """ids of envelopes on this lane that were persisted AND acked/queued."""
    audit = hub.audit.read()
    ids = {e["envelope_id"] for e in audit if e["kind"] == "envelope.persisted"
           and (e["from_agent"], e["intent"], e["to_agent"]) == (frm, intent, to)}
    ok = {e["envelope_id"] for e in audit if e["kind"] in ("ack", "hold.queued")}
    return ids & ok


def no_handoff_failures(hub):
    return [e for e in hub.audit.read() if e["kind"] == "handoff.failed"] == []


@pytest.fixture
def swarm(tmp_path):
    hub, signer, spokes, external = full_swarm(str(tmp_path))
    hub.on_turn_start()
    return hub, signer, spokes


def test_01_opt_out_confirmation_to_11(swarm):
    hub, _, _ = swarm
    from test_agent01_agent14 import signal
    hub.send(signal("lead-025", {"channel": "call", "name": "Done With This", "revoke_all_contact": True}))
    assert delivered(hub, "01", "client.message.request", "11") and no_handoff_failures(hub)


def test_03_touch_review_status_and_log(swarm):
    hub, _, spokes = swarm
    from test_agent03 import nurture_env
    from dispatcher.core import Envelope
    ctx = "touch-001"
    hub.send(nurture_env(ctx, {"consent": {"email": "yes"}, "sequence_id": "seq_a"}))
    assert delivered(hub, "03", "content.review", "17")
    assert delivered(hub, "03", "agent.status", "18")
    hub.send(Envelope(from_agent="11", to_agent="03", intent="lead.reply", client_context_id=ctx,
                      payload={"message": "STOP"},
                      provenance={"source": "spoke-11", "captured_at": "runtime"}))
    assert delivered(hub, "03", "interaction.log", "14") and no_handoff_failures(hub)


def test_05_withdrawal_under_contract_notifies_17(swarm):
    hub, signer, _ = swarm
    from test_agent05 import authorized_change
    hub.send(authorized_change(signer, "p-004", {"field": "status", "value": "pending",
                                                 "signed_contract_artifact": "contract-1"}))
    hub.send(authorized_change(signer, "p-004", {"field": "status", "value": "withdrawn"}))
    assert delivered(hub, "05", "compliance.notice", "17") and no_handoff_failures(hub)


def test_06_open_house_orders_signage_from_09(swarm):
    hub, _, _ = swarm
    from test_agent06 import showing_req, base_payload
    hub.send(showing_req("s-011", base_payload(is_open_house=True)))
    assert delivered(hub, "06", "vendor.request", "09") and no_handoff_failures(hub)


def test_09_no_show_logged_to_14(swarm):
    hub, _, _ = swarm
    from test_agent09 import vendor_event
    hub.send(vendor_event("v-015", {"event_kind": "no_show", "deadline_critical": False}))
    assert delivered(hub, "09", "interaction.log", "14") and no_handoff_failures(hub)


def test_10_external_scope_package_to_human(swarm):
    hub, _, _ = swarm
    from test_agent10 import data_req
    hub.send(data_req("m-007", {"mode": "comp", "license_scope": "external",
                                "comps": [], "today": "2026-07-15"}, frm="19"))
    assert delivered(hub, "10", "data.package", "human") and no_handoff_failures(hub)


def test_11_advice_wait_status_to_18(swarm):
    hub, _, _ = swarm
    from test_agent11 import client_reply
    hub.send(client_reply("c-007", {"message": "what's it worth to you, negotiate"}))
    assert delivered(hub, "11", "agent.status", "18") and no_handoff_failures(hub)


def test_11_showing_request_to_06(swarm):
    hub, _, spokes = swarm
    from test_agent11 import client_reply
    spokes["14"].buyer_agreement["c-015"] = True
    spokes["14"].identity_verified["c-015"] = True
    hub.send(client_reply("c-015", {"message": "can I see it Saturday", "requests_showing": True,
                                    "requested_time": "2026-08-15T10:00"}))
    assert delivered(hub, "11", "showing.request", "06")


def test_13_sensitive_criterion_review_status(swarm):
    hub, signer, spokes = swarm
    from test_agent13 import config_update
    hub.send(config_update(signer, "b-003", {"buyer_criteria": [
        {"field": "walkability", "value": "high", "fair_housing_sensitive": True}]}))
    assert delivered(hub, "13", "content.review", "17")
    assert delivered(hub, "13", "agent.status", "18")


def test_15_roi_report_to_human(swarm):
    hub, _, _ = swarm
    hub.send(spoke_env("14", "15", "report.package", "f-015",
                       {"marketing_spend": 1000,
                        "referral_attribution": {"attributed_value": 4000, "source": "facebook_ads"}}))
    assert delivered(hub, "15", "report.package", "human") and no_handoff_failures(hub)


def test_16_new_business_lead_to_02(swarm):
    hub, _, _ = swarm
    hub.send(spoke_env("11", "16", "lead.reply", "n-005",
                       {"message": "we're thinking of selling again", "new_lead_context_id": "n-005-new"}))
    assert delivered(hub, "16", "lead.captured", "02")


def test_17_near_miss_pattern_to_human(swarm):
    hub, signer, _ = swarm
    from test_agent17 import sign_ruleset, review
    hub.send(sign_ruleset(signer))
    for i in range(3):
        hub.send(review(f"c-010-{i}", {"draft": {"facts": ["adults only"]}, "content_hash": f"hash-{i}"}, frm="04"))
    assert delivered(hub, "17", "report.package", "human")


def test_19_market_context_request_and_status(swarm):
    hub, signer, spokes = swarm
    from test_agent19 import _setup_zip, discovery
    hub.send(_setup_zip(signer))
    hub.send(discovery("d-014", {"listing_id": "L14", "zip_code": "44811", "status": "new", "source": "mls_feed"}))
    spokes["19"].request_market_context("L14")
    assert delivered(hub, "19", "data.request", "10")
    assert delivered(hub, "19", "agent.status", "18")


def test_20_draft_review_and_status(swarm):
    hub, _, spokes = swarm
    assert spokes["20"].draft_response("m-011", "thanks for reaching out!", "mention-2") == "submitted_for_review"
    assert delivered(hub, "20", "content.review", "17")
    assert delivered(hub, "20", "agent.status", "18")


def test_human_data_request_to_10(swarm):
    hub, _, _ = swarm
    hub.send(spoke_env("human", "10", "data.request", "m-h1",
                       {"mode": "comp", "license_scope": "internal", "comps": [], "today": "2026-07-15"}))
    assert delivered(hub, "human", "data.request", "10")


def test_queue_lanes_via_send(swarm):
    hub, _, _ = swarm
    hub.send(spoke_env("11", "queue", "escalation.complaint", "q-1", {"trigger": "t"}))
    hub.send(spoke_env("11", "queue", "integrity.violation", "q-2", {"reason": "r"}))
    assert delivered(hub, "11", "escalation.complaint", "queue")
    assert delivered(hub, "11", "integrity.violation", "queue")


NO_EMITTER = [("20", "behavioral.signal", "03")]


@pytest.mark.parametrize("frm,intent,to", NO_EMITTER)
def test_lanes_without_an_emitter_stay_documented(frm, intent, to):
    path = os.path.join(ROOT, "dispatcher", f"listing_spokes_{frm}.py")
    src = open(path).read()
    pattern = re.compile(r'_env\("%s",\s*"%s",\s*"%s"' % (frm, to, re.escape(intent)))
    assert not pattern.search(src), f"{frm} now emits {intent}->{to}: add a full-swarm test and update NO_EMITTER"
