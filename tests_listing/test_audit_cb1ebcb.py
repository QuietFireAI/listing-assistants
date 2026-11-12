"""Fixes for the outside audit of cb1ebcb (2026-11-03). Each test names the
audit item it covers and fails on the code before the fix."""
from tests_listing.test_repairs_2026_10_11 import _swarm, _env, _signed, _persisted
from tests_listing.test_agent06 import make_hub, showing_req, base_payload, persisted
from dispatcher.core import Envelope
from dispatcher.listing_spokes_06 import Spoke06ShowingScheduler


def _decide_wait(sw, signer, wait, decision):
    auth = _env("human", wait["agent_id"], "hitl.decision.authority",
                wait["client_context_id"], {"wait_id": wait["wait_id"], "decision": decision})
    signer.sign(auth)
    return sw.hitl.resume_operation(auth)


# ------------------------------------------------------------ audit 18
def test_audit18_a_decision_on_one_sellers_report_releases_only_that_report(tmp_path):
    """One seller with two listings gets two weekly reports, two waits. The
    decision on the first wait sends the first report, not whichever was
    held last; the second stays held for its own decision."""
    sw, s = _swarm(tmp_path)
    sp = sw.spokes["06"]
    sw.hub.send(_signed(s, "06", "c", {"seller_reports": {"weekday": "monday",
                                                          "listings": {"LA": "S", "LB": "S"}}}))
    sp.confirmed_showings["b1"] = [{"time": "2026-10-10T09:00", "confirmed": True, "listing_id": "LA"}]
    sp.confirmed_showings["b2"] = [{"time": "2026-10-11T09:00", "confirmed": True, "listing_id": "LB"},
                                   {"time": "2026-10-11T10:00", "confirmed": True, "listing_id": "LB"}]
    assert sp.weekly_seller_reports("2026-10-12") == "held:['LA', 'LB']"
    waits = sw.hitl.get_pending_waits("S")
    assert len(waits) == 2
    wait_la = next(w for w in waits if w["reason"].startswith("weekly seller report for LA"))

    res = _decide_wait(sw, s, wait_la, "APPROVE")
    assert res["handler_result"] == "continued: report sent to 11"
    sent = [e["payload"]["variables"] for e in _persisted(sw, "client.message.request", "S")
            if e["payload"].get("template") == "seller_weekly_report"]
    assert [(v["listing_id"], v["showings"]) for v in sent] == [("LA", 1)]
    assert list(sp.held_reports) == ["S|LB"]


# ------------------------------------------------------------ audit 31
def _two_held_bumps(tmp_path):
    hub, signer = make_hub(str(tmp_path))
    spoke = Spoke06ShowingScheduler(hub)
    hub.on_turn_start()
    ctx = "s-031"
    hub.send(showing_req(ctx, base_payload(requested_time="2026-08-01T10:00", listing_id="L1")))
    hub.send(showing_req(ctx, base_payload(requested_time="2026-08-01T15:00", listing_id="L2")))
    assert [x["time"] for x in spoke.confirmed_showings[ctx]] == ["2026-08-01T10:00", "2026-08-01T15:00"]
    hub.send(showing_req(ctx, base_payload(requested_time="2026-08-01T10:00", listing_id="L1",
                                           protected_deadline=True, lead_tier="HOT")))
    hub.send(showing_req(ctx, base_payload(requested_time="2026-08-01T15:00", listing_id="L2",
                                           protected_deadline=True, lead_tier="HOT")))
    return hub, signer, spoke, ctx


def _confirm(hub, signer, ctx, **payload):
    env = Envelope(from_agent="human", to_agent="06", intent="config.update",
                   client_context_id=ctx, payload={"confirm_protected_bump": True, **payload},
                   provenance={"source": "human", "captured_at": "runtime",
                               "verbatim_available": True})
    signer.sign(env)
    hub.send(env)


def test_audit31_a_bump_confirmation_acts_on_the_bump_it_names(tmp_path):
    hub, signer, spoke, ctx = _two_held_bumps(tmp_path)
    _confirm(hub, signer, ctx, bump_id="L1@2026-08-01T10:00")
    bumped = [e["payload"]["original_time"] for e in persisted(hub, "client.message.request")
              if e["payload"].get("template") == "showing_bumped_notice"]
    assert bumped == ["2026-08-01T10:00"]
    assert list(spoke.pending_bumps[ctx]) == ["L2@2026-08-01T15:00"]


def test_audit31_a_confirmation_that_names_no_held_bump_moves_nothing(tmp_path):
    hub, signer, spoke, ctx = _two_held_bumps(tmp_path)
    _confirm(hub, signer, ctx)                      # a bare yes
    _confirm(hub, signer, ctx, bump_id="L9@2026-08-01T10:00")
    assert not [e for e in persisted(hub, "client.message.request")
                if e["payload"].get("template") == "showing_bumped_notice"]
    assert sorted(spoke.pending_bumps[ctx]) == ["L1@2026-08-01T10:00", "L2@2026-08-01T15:00"]
    refusals = [q["payload"] for q in hub.queues["clarification.request"]
                if q["payload"]["reason"].startswith("bump confirmation refused")]
    assert len(refusals) == 2
    assert refusals[0]["held_bump_ids"] == ["L1@2026-08-01T10:00", "L2@2026-08-01T15:00"]


# ------------------------------------------------------------ audit 19
def _held_and_key(tmp_path):
    from dispatcher.signatures import Ed25519Signer
    from dispatcher.swarm import build_swarm
    s = Ed25519Signer()
    sw = build_swarm(str(tmp_path / "a.jsonl"), verifier=s.verifier())
    held = Envelope(from_agent="09", to_agent="external", intent="vendor.schedule",
                    client_context_id="c1", payload={"vendor_id": "v1", "when": "Tue 10:00"},
                    provenance={"source": "spoke-09", "captured_at": "runtime",
                                "verbatim_available": True})
    sw.hub.send(held)
    assert held.envelope_id in sw.hub._absolute_holds

    def key(**extra):
        auth = Envelope(from_agent="human", to_agent="09", intent="disclosure.authority",
                        client_context_id="c1",
                        payload={"held_envelope_id": held.envelope_id, **extra},
                        provenance={"source": "human", "captured_at": "runtime",
                                    "verbatim_available": True})
        s.sign(auth)
        return auth
    return sw, held, key


def _went_out(sw):
    return [e["payload"] for e in sw.hub.audit.read()
            if e["kind"] == "envelope.persisted" and e["intent"] == "vendor.schedule"]


def test_audit19_the_sender_changing_its_message_after_the_hold_changes_nothing(tmp_path):
    sw, held, key = _held_and_key(tmp_path)
    held.payload["when"] = "Tue 23:00"                 # the sender still has its object
    assert sw.hub.release_disclosure(key())["status"] != "reject"
    assert _went_out(sw) == [{"vendor_id": "v1", "when": "Tue 10:00"}]


def test_audit19_a_held_copy_changed_in_the_hub_is_not_released(tmp_path):
    sw, held, key = _held_and_key(tmp_path)
    sw.hub._absolute_holds[held.envelope_id].payload["when"] = "Tue 23:00"
    res = sw.hub.release_disclosure(key())
    assert res["status"] == "reject" and "changed after it was held" in res["reason"]
    assert held.envelope_id in sw.hub._absolute_holds and _went_out(sw) == []
    assert [e for e in sw.hub.audit.read() if e["kind"] == "integrity.violation"
            and "disclosure release refused" in e["reason"]]


def test_audit19_a_key_that_names_other_content_releases_nothing(tmp_path):
    from dispatcher.hub import held_content_sha256
    sw, held, key = _held_and_key(tmp_path)
    [hold] = [e for e in sw.hub.audit.read() if e["kind"] == "absolute_signal.hold"]
    assert hold["content_sha256"] == held_content_sha256(sw.hub._absolute_holds[held.envelope_id])
    res = sw.hub.release_disclosure(key(content_sha256="0" * 64))
    assert res["status"] == "reject" and _went_out(sw) == []
    assert sw.hub.release_disclosure(key(content_sha256=hold["content_sha256"]))["status"] != "reject"
    assert _went_out(sw) == [{"vendor_id": "v1", "when": "Tue 10:00"}]


# ------------------------------------------------------------ audit 69
def test_audit69_the_review_says_signed_only_when_the_signature_checks(tmp_path):
    import json
    import os
    from dispatcher import review_agent
    from dispatcher.boot_attest import canonical, current_manifest
    from dispatcher.signatures import Ed25519Signer
    state = str(tmp_path)
    op = Ed25519Signer()
    open(os.path.join(state, "operator-public.bin"), "wb").write(op.public_key_bytes())
    manifest = current_manifest()

    def write(sig):
        json.dump({"manifest": manifest, "signature": sig},
                  open(os.path.join(state, "boot-attestation.json"), "w"))

    def reading():
        cc = review_agent.code_check(state, "05")
        return cc, review_agent.first_reading({"code_check": cc})[0]

    write(op.sign_bytes(canonical(manifest)))
    cc, first = reading()
    assert cc["ok"] and cc["signature"]["verified"] is True
    assert "this is the code you signed" in first

    write(Ed25519Signer().sign_bytes(canonical(manifest)))      # someone else's key
    cc, first = reading()
    assert cc["ok"] and cc["signature"]["verified"] is False
    assert "code you signed" not in first.replace("not proof that this is the code you signed", "")
    assert "unverified list" in first


# ------------------------------------------------------------ audit 12
def _settlement(sw, ctx):
    # a settlement statement is filed only from a sender you named
    sw.spokes["08"].expected_senders[ctx] = {"closing_settlement_statement": {"title_co"}}
    sw.hub.send(_env("11", "08", "document.submission", ctx,
                     {"doc_type": "closing_settlement_statement", "opens_correctly": True,
                      "submitting_party": "title_co",
                      "signature_expected": True, "signed": True, "content_hash": "cs-1",
                      "sale_price": 400000, "commission_amount": 10000,
                      "today": "2026-11-20"}))


def _closing_timeline(sw, s, ctx):
    sw.hub.send(_signed(s, "07", ctx, {"timeline_init": {"closing": "2026-11-20"},
                                       "today": "2026-11-01"}))
    return sw.spokes["07"].timelines[ctx]["closing"]


def test_audit12_a_document_the_drawer_refuses_is_not_reported_as_filed(tmp_path, monkeypatch):
    """Fixed 2026-11-12. Before: the drawer refused the settlement statement,
    Agent 08 still logged document_filed and told Agent 07 the artifact was
    on file, and 07 closed the deal."""
    sw, s = _swarm(tmp_path)
    closing = _closing_timeline(sw, s, "c12")

    def refuse(*a, **k):
        raise PermissionError("drawer is read-only")
    monkeypatch.setattr(sw.hub.drawers, "record_agent_artifact", refuse)
    _settlement(sw, "c12")

    kinds = [e["payload"].get("kind") for e in _persisted(sw, "interaction.log", "c12")]
    assert "document_filed" not in kinds and "document_not_filed" in kinds
    [status] = [e["payload"] for e in _persisted(sw, "doc.status", "c12")]
    assert status["status"] == "incomplete" and not status.get("artifact_on_file")
    assert "drawer is read-only" in status["filing_refused"]
    assert closing["satisfied"] is False                       # the deal is not closed
    assert not _persisted(sw, "transaction.closed", "c12")
    # the refusal is on the record and on the owner's list (raised by the filing itself)
    assert [e for e in sw.hub.audit.read() if e["kind"] == "drawer.refused"]
    assert any(q.get("client_context_id") == "c12"
               and q["payload"].get("reason") == "client drawer filing refused"
               for q in sw.hub.queues["clarification.request"])


def test_audit12_the_same_document_filed_normally_still_closes(tmp_path):
    sw, s = _swarm(tmp_path)
    closing = _closing_timeline(sw, s, "c13")
    _settlement(sw, "c13")
    kinds = [e["payload"].get("kind") for e in _persisted(sw, "interaction.log", "c13")]
    assert "document_filed" in kinds and "document_not_filed" not in kinds
    assert closing["satisfied"] is True
