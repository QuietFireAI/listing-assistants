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
