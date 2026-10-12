"""Kills logic mutants that survived in dispatcher/hitl_protocol.py
(post-fix mutmut run, 2026-10-11): the armed-registry path, sender/intent
checks, decision validation messages, and support escalation details."""
import json
import os

import pytest

from dispatcher.core import Envelope, Routes, AuditLog
from dispatcher.hub import Hub
from dispatcher.client_drawer import ClientDrawerManager
from dispatcher.hitl_protocol import HITLManager, HITLAuthorizationError, DECISION_INTENT
from dispatcher.signatures import Ed25519Signer, Ed25519Verifier

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROUTES = os.path.join(ROOT, "identity", "routes.json")


def hub_with(tmp_path, arm=False):
    signer = Ed25519Signer()
    hub = Hub(Routes(ROUTES), AuditLog(str(tmp_path / "audit.jsonl")),
              signature_verifier=Ed25519Verifier(signer.public_key_bytes()).verifier())
    if arm:
        root = tmp_path / "idroot"
        (root / "config").mkdir(parents=True)
        (root / "config" / "authority_signers.json").write_text(json.dumps({
            "_status": "RATIFIED (test fixture only)",
            "entries": [{"intent": DECISION_INTENT, "signer_login": "broker@example.test",
                         "idp": "test-idp", "mfa_required": True, "effective": "2026-01-01",
                         "revoked": None}]}), encoding="utf-8")
        hub.arm_signer_registry(str(root))
    return hub, signer


def decision(signer, ws, name="APPROVE", login=None, frm="human", intent=DECISION_INTENT, **extra):
    prov = {"source": "human", "captured_at": "runtime"}
    if login:
        prov["signer"] = {"signer_login": login, "mfa": True, "idp_session_ref": "sess-1"}
    env = Envelope(from_agent=frm, to_agent="hitl", intent=intent, client_context_id=ws.client_context_id,
                   payload={"wait_id": ws.wait_id, "decision": name, **extra}, provenance=prov)
    signer.sign(env)
    return env


def test_armed_registry_accepts_a_ratified_signer_and_refuses_others(tmp_path):
    hub, signer = hub_with(tmp_path, arm=True)
    hitl = HITLManager(hub=hub)
    ws = hitl.pause_operation("ctx-1", "07", "x", "r", {"x": 1})
    with pytest.raises(HITLAuthorizationError, match="^signer registry: "):
        hitl.resume_operation(decision(signer, ws, login="intruder@example.test"))
    bad = [e for e in hub.audit.read() if e["kind"] == "integrity.violation"][-1]
    assert bad["reason"].startswith("signer registry: ") and bad["envelope_id"]
    assert ws.status == "PENDING"
    ok = decision(signer, ws, login="broker@example.test")
    assert hitl.resume_operation(ok)["status"] == "decision_recorded_no_handler"
    assert not [e for e in hub.audit.read() if e["kind"] == "signer.unarmed"]


def test_unarmed_registry_is_declared(tmp_path):
    hub, signer = hub_with(tmp_path)
    hitl = HITLManager(hub=hub)
    ws = hitl.pause_operation("ctx-1", "07", "x", "r", {"x": 1})
    hitl.resume_operation(decision(signer, ws))
    assert [e for e in hub.audit.read() if e["kind"] == "signer.unarmed"]


def test_hub_without_verify_sig_refuses(tmp_path):
    class NoVerify:
        audit = AuditLog(str(tmp_path / "a.jsonl"))
    hitl = HITLManager(hub=NoVerify())
    from dispatcher.hitl_protocol import WaitState
    ws = WaitState("w1", "ctx-1", "07", "x", "r", {"x": 1}, "APPROVE")
    hitl.active_waits["w1"] = ws
    with pytest.raises(HITLAuthorizationError):
        hitl.resume_operation(decision(Ed25519Signer(), ws))


def test_wrong_intent_and_sender_messages(tmp_path):
    hub, signer = hub_with(tmp_path)
    hitl = HITLManager(hub=hub)
    ws = hitl.pause_operation("ctx-1", "07", "x", "r", {"x": 1})
    with pytest.raises(HITLAuthorizationError, match="decision must be intent 'hitl.decision.authority'"):
        hitl.resume_operation(decision(signer, ws, intent="config.update"))
    with pytest.raises(HITLAuthorizationError, match="decision sender must be 'human'"):
        hitl.resume_operation(decision(signer, ws, frm="07"))
    with pytest.raises(HITLAuthorizationError, match="unverified signature on HITL decision"):
        hitl.resume_operation(decision(Ed25519Signer(), ws))
    other = decision(signer, ws)
    other.client_context_id = "ctx-2"
    signer.sign(other)
    with pytest.raises(HITLAuthorizationError, match="decision signed for context 'ctx-2' cannot resolve a wait on 'ctx-1'"):
        hitl.resume_operation(other)


def test_decision_validation_messages(tmp_path):
    hub, signer = hub_with(tmp_path)
    hitl = HITLManager(hub=hub)
    ws = hitl.pause_operation("ctx-1", "07", "x", "r", {"x": 1})
    with pytest.raises(ValueError, match="unknown decision 'MAYBE'"):
        hitl.resume_operation(decision(signer, ws, "maybe"))
    with pytest.raises(ValueError, match="unknown decision ''"):
        hitl.resume_operation(decision(signer, ws, ""))
    with pytest.raises(ValueError, match="MODIFY requires a non-empty updated_fields dict"):
        hitl.resume_operation(decision(signer, ws, "MODIFY", updated_fields=["x"]))
    with pytest.raises(ValueError, match="MODIFY requires a non-empty updated_fields dict"):
        hitl.resume_operation(decision(signer, ws, "MODIFY", updated_fields={}))
    with pytest.raises(ValueError, match=r"not in the paused payload: \['y'\]"):
        hitl.resume_operation(decision(signer, ws, "MODIFY", updated_fields={"y": 1}))
    with pytest.raises(ValueError, match="APPROVE does not take updated_fields"):
        hitl.resume_operation(decision(signer, ws, "APPROVE", updated_fields={"x": 2}))


def test_handler_receives_the_payload_and_trace_names_the_decision(tmp_path):
    hub, signer = hub_with(tmp_path)
    hitl = HITLManager(hub=hub)
    got = {}
    hitl.register_resumption_handler("07", lambda ws, payload: got.update(payload) or "done")
    ws = hitl.pause_operation("ctx-1", "07", "x", "r", {"x": 1})
    auth = decision(signer, ws, "APPROVE", note="ok")
    hitl.resume_operation(auth)
    assert got["note"] == "ok" and got["decision"] == "APPROVE"
    t = [t for t in hub.spoke_traces if t.get("result") == "decision: APPROVE"][-1]
    assert t["agent"] == "07" and t["envelope_id"] == ws.wait_id and auth.envelope_id in t["thought"]


def test_support_escalation_carries_ticket_wait_and_snapshot(tmp_path):
    hub, signer = hub_with(tmp_path)
    drawers = ClientDrawerManager(str(tmp_path / "drawers"))
    drawers.provision_drawer("ctx-1", "Alice", "1 Oak")
    hitl = HITLManager(hub=hub, drawer_manager=drawers)
    ws = hitl.pause_operation("ctx-1", "07", "closing.concession", "Ambiguous clause.", {"x": 1})
    res = hitl.resume_operation(decision(signer, ws, "ESCALATE_TO_SUPPORT", user_notes="need help"))
    [item] = hub.queues["escalation.support"]
    assert item["ticket_id"] == res["ticket_id"] and item["wait_id"] == ws.wait_id
    assert item["agent_id"] == "07" and item["client_context_id"] == "ctx-1"
    assert item["snapshot_id"] and item["snapshot_id"] == ws.resolution["snapshot_id"]
    pause = json.loads(drawers.get_drawer("ctx-1").get_file("timeline", f"{ws.wait_id}_pause.json"))
    assert pause["status"] == "ESCALATED_TO_SUPPORT"
    files = drawers.get_drawer("ctx-1").get_manifest()["file_index"]
    assert files[f"timeline/{ws.wait_id}_pause.json"]["agent_id"] == "07"


def test_resolution_records_are_attributed(tmp_path):
    hub, signer = hub_with(tmp_path)
    drawers = ClientDrawerManager(str(tmp_path / "drawers"))
    drawers.provision_drawer("ctx-1", "Alice", "1 Oak")
    hitl = HITLManager(hub=hub, drawer_manager=drawers)
    ws = hitl.pause_operation("ctx-1", "07", "x", "r", {"x": 1})
    hitl.resume_operation(decision(signer, ws))
    files = drawers.get_drawer("ctx-1").get_manifest()["file_index"]
    assert files[f"timeline/{ws.wait_id}_pause.json"]["agent_id"] == "07"
    assert files[f"timeline/{ws.wait_id}_resolved.json"]["agent_id"] == "00"
