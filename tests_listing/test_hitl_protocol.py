"""Tests for the Human-In-The-Loop (HITL) wait-state and resumption protocol.

Rewritten 2026-10-11 (audit HITL-2..7). The previous tests resumed waits with
no hub and no signature, and asserted "resumed" for a wait whose agent had no
handler - they encoded the defects. Every decision below is a signed
'hitl.decision.authority' envelope verified by the hub, and the negative
cases prove the unsigned / forged / cross-context / out-of-scope paths are
refused.
"""
import os
import subprocess
import sys
import tempfile

import pytest

from dispatcher.client_drawer import ClientDrawerManager
from dispatcher.core import Envelope, Routes, AuditLog
from dispatcher.hitl_protocol import HITLManager, HITLAuthorizationError, WaitState, DECISION_INTENT
from dispatcher.hub import Hub
from dispatcher.listing_spokes_18 import Spoke18CalendarTask
from dispatcher.signatures import Ed25519Signer, Ed25519Verifier

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDENTITY_ROUTES = os.path.join(ROOT, "identity", "routes.json")


def make_hub(tmp_path):
    signer = Ed25519Signer()
    hub = Hub(Routes(IDENTITY_ROUTES), AuditLog(os.path.join(tmp_path, "audit.jsonl")),
              signature_verifier=Ed25519Verifier(signer.public_key_bytes()).verifier())
    return hub, signer


def decision(signer, ws, decision_name, **extra):
    env = Envelope(from_agent="human", to_agent="hitl", intent=DECISION_INTENT,
                   client_context_id=ws.client_context_id,
                   payload={"wait_id": ws.wait_id, "decision": decision_name, **extra},
                   provenance={"source": "human", "captured_at": "runtime"})
    if signer is not None:
        signer.sign(env)
    return env


def test_pause_resume_lifecycle_with_signed_decision_and_handler(tmp_path):
    hub, signer = make_hub(str(tmp_path))
    spoke18 = Spoke18CalendarTask(hub)
    drawer_mgr = ClientDrawerManager(str(tmp_path / "drawers"))
    drawer = drawer_mgr.provision_drawer("ctx-escrow-100", "Bob Seller", "100 Oak Lane")
    hitl = HITLManager(hub=hub, drawer_manager=drawer_mgr)
    seen = {}

    def agent07_resume(ws: WaitState, human_payload: dict):
        seen["decision"] = ws.resolution["decision"]
        seen["credit"] = ws.original_payload["requested_credit"]
        return "agent_07_milestone_advanced"
    hitl.register_resumption_handler("07", agent07_resume)

    ws = hitl.pause_operation("ctx-escrow-100", "07", "milestone.advance",
                              "Buyer requested $5,000 repair credit. Human-only.",
                              {"milestone": "inspection", "requested_credit": 5000},
                              "APPROVE_REPAIR_CONCESSION")
    assert ws.status == "PENDING" and ws.notice_result["status"] == "ack"
    assert [w["wait_id"] for w in hitl.get_pending_waits()] == [ws.wait_id]
    assert len(spoke18.waiting) == 1
    assert [f["filename"] for f in drawer.list_files("timeline")] == [f"{ws.wait_id}_pause.json"]

    res = hitl.resume_operation(decision(signer, ws, "MODIFY",
                                         updated_fields={"requested_credit": 3000}))
    assert res["status"] == "resumed"
    assert res["handler_result"] == "agent_07_milestone_advanced"
    assert seen == {"decision": "MODIFY", "credit": 3000}
    # Agent 18's wait is actually cleared (was rejected as 00 -> agent.status before)
    assert res["agent18_clear"]["status"] == "ack"
    assert spoke18.waiting == {}
    assert hitl.get_pending_waits() == []
    kinds = [e["kind"] for e in hub.audit.read()]
    assert "hitl.decision.authorized" in kinds
    assert not [e for e in hub.audit.read() if e["kind"] == "reject"]
    # the pause record's status is updated, plus a resolution record
    import json
    pause = json.loads(drawer.get_file("timeline", f"{ws.wait_id}_pause.json"))
    assert pause["status"] == "RESOLVED"
    assert drawer.get_file("timeline", f"{ws.wait_id}_resolved.json") is not None


def test_unsigned_and_forged_decisions_are_refused(tmp_path):
    hub, signer = make_hub(str(tmp_path))
    hitl = HITLManager(hub=hub)
    ws = hitl.pause_operation("ctx-1", "07", "milestone.advance", "r", {"x": 1})
    with pytest.raises(HITLAuthorizationError):
        hitl.resume_operation(decision(None, ws, "APPROVE"))           # unsigned
    with pytest.raises(HITLAuthorizationError):
        hitl.resume_operation(decision(Ed25519Signer(), ws, "APPROVE"))  # wrong key
    tampered = decision(signer, ws, "APPROVE")
    tampered.payload["decision"] = "REJECT"                              # altered after signing
    with pytest.raises(HITLAuthorizationError):
        hitl.resume_operation(tampered)
    assert ws.status == "PENDING"
    assert sum(1 for e in hub.audit.read() if e["kind"] == "integrity.violation") == 3


def test_no_hub_means_no_decision_accepted():
    hitl = HITLManager()
    ws = hitl.pause_operation("ctx-1", "07", "x", "r", {"x": 1})
    with pytest.raises(HITLAuthorizationError):
        hitl.resume_operation(decision(Ed25519Signer(), ws, "APPROVE"))
    assert ws.status == "PENDING"


def test_cross_context_wrong_sender_and_replay_refused(tmp_path):
    hub, signer = make_hub(str(tmp_path))
    hitl = HITLManager(hub=hub)
    ws = hitl.pause_operation("ctx-a", "07", "x", "r", {"x": 1})
    other = decision(signer, ws, "APPROVE")
    other.client_context_id = "ctx-b"
    signer.sign(other)
    with pytest.raises(HITLAuthorizationError):
        hitl.resume_operation(other)
    spoofed = decision(None, ws, "APPROVE")
    spoofed.from_agent = "07"
    signer.sign(spoofed)
    with pytest.raises(HITLAuthorizationError):
        hitl.resume_operation(spoofed)
    ok = decision(signer, ws, "APPROVE")
    assert hitl.resume_operation(ok)["status"] == "decision_recorded_no_handler"
    with pytest.raises(ValueError):
        hitl.resume_operation(ok)                                        # replay


def test_modify_cannot_inject_new_fields(tmp_path):
    hub, signer = make_hub(str(tmp_path))
    hitl = HITLManager(hub=hub)
    ws = hitl.pause_operation("ctx-1", "09", "vendor.request", "vendor unverified", {"vendor_id": "v1"})
    with pytest.raises(ValueError):
        hitl.resume_operation(decision(signer, ws, "MODIFY",
                                       updated_fields={"vendor_id": "v2", "wire_to": "acct-999"}))
    with pytest.raises(ValueError):
        hitl.resume_operation(decision(signer, ws, "APPROVE", updated_fields={"vendor_id": "v2"}))
    assert ws.original_payload == {"vendor_id": "v1"} and ws.status == "PENDING"


def test_no_handler_is_reported_honestly(tmp_path):
    hub, signer = make_hub(str(tmp_path))
    hitl = HITLManager(hub=hub)
    ws = hitl.pause_operation("ctx-1", "04", "marketing.copy", "bed count conflict", {"beds": 3})
    res = hitl.resume_operation(decision(signer, ws, "APPROVE_WITH_OVERRIDE", updated_fields={"beds": 4}))
    assert res["status"] == "decision_recorded_no_handler"
    assert ws.status == "RESOLVED_NO_HANDLER" and ws.original_payload["beds"] == 4


def test_hold_and_close_semantics(tmp_path):
    hub, signer = make_hub(str(tmp_path))
    hitl = HITLManager(hub=hub)
    ws = hitl.pause_operation("ctx-1", "07", "x", "r", {"x": 1})
    assert hitl.resume_operation(decision(signer, ws, "HOLD"))["status"] == "held"
    assert ws.status == "HELD"
    ws2 = hitl.pause_operation("ctx-1", "15", "x", "Suspected wire fraud spoofing.", {"x": 1})
    res = hitl.resume_operation(decision(signer, ws2, "CLOSE_SYSTEM"))
    assert res["status"] == "wait_closed" and ws2.status == "CLOSED"


def test_realtime_notification_and_am_recap(tmp_path):
    hub, signer = make_hub(str(tmp_path))
    spoke18 = Spoke18CalendarTask(hub)
    hub.on_turn_start()
    alerts = []
    hitl = HITLManager(hub=hub, real_time_notifier=lambda a: alerts.append(a) or {"sent": True})
    ws = hitl.pause_operation("ctx-lead-999", "02", "lead.tier",
                              "Lead score 70 on exact HOT/WARM boundary. Human review required.",
                              {"score": 70}, "TIER_OVERRIDE")
    assert len(alerts) == 1 and "DECISION REQUIRED" in alerts[0]["body"] and ws.wait_id in alerts[0]["body"]
    recap = spoke18.generate_briefing(briefing_type="morning")["unresolved_decisions_recap"]
    assert [(r["context"], r["agent"], r["wait_id"]) for r in recap] == [("ctx-lead-999", "02", ws.wait_id)]
    hitl.resume_operation(decision(signer, ws, "APPROVE"))
    assert spoke18.generate_briefing(briefing_type="morning")["unresolved_decisions_recap"] == []


def test_unknown_wait_id_fails(tmp_path):
    hub, signer = make_hub(str(tmp_path))
    hitl = HITLManager(hub=hub)
    fake = WaitState("wait-fake-id", "ctx-1", "07", "x", "r", {}, "APPROVE")
    with pytest.raises(ValueError, match="not found"):
        hitl.resume_operation(decision(signer, fake, "APPROVE"))


def test_escalate_to_support_files_support_queue_with_snapshot(tmp_path):
    hub, signer = make_hub(str(tmp_path))
    drawer_mgr = ClientDrawerManager(str(tmp_path / "drawers"))
    drawer_mgr.provision_drawer("ctx-support-101", "Charlie Test", "101 Maple Way")
    hitl = HITLManager(hub=hub, drawer_manager=drawer_mgr)
    ws = hitl.pause_operation("ctx-support-101", "07", "closing.concession",
                              "Ambiguous addendum clause.", {"clause": "credit pending HVAC"},
                              "APPROVE_CREDIT")
    res = hitl.resume_operation(decision(signer, ws, "ESCALATE_TO_SUPPORT", user_notes="need help"))
    assert res["status"] == "escalated_to_support" and res["ticket_id"].startswith("TICKET-")
    assert ws.status == "ESCALATED_TO_SUPPORT" and ws.resolution["snapshot_id"]
    assert len(hub.queues["escalation.support"]) == 1
    assert hub.queues["escalation.complaint"] == []     # no longer pollutes P14's queue
    assert "escalation.support" in res["message"]


def test_forensic_snapshot_written_to_drawer(tmp_path):
    hub, _ = make_hub(str(tmp_path))
    drawer_mgr = ClientDrawerManager(str(tmp_path / "drawers"))
    drawer_mgr.provision_drawer("ctx-snap-777", "Alice Test", "777 Elm St")
    hitl = HITLManager(hub=hub, drawer_manager=drawer_mgr)
    ws = hitl.pause_operation("ctx-snap-777", "04", "marketing.copy", "bed count", {"beds": 3}, "CORRECT_BED_COUNT")
    snap = hitl.create_forensic_snapshot("ctx-snap-777", wait_id=ws.wait_id, notes="4 bedrooms")
    assert snap["snapshot_id"].startswith("snap_ctx-snap-777_")
    assert snap["json_path"] and snap["markdown_path"] and "CORRECT_BED_COUNT" in snap["markdown_content"]
    assert hitl.errors == []


def test_cli_decide_no_longer_fakes_success(tmp_path):
    out = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "manage_hitl_queue.py"),
                          "--decide", "wait-does-not-exist", "--decision", "APPROVE"],
                         capture_output=True, text=True, cwd=str(tmp_path))
    assert out.returncode != 0
    assert "SUCCESS" not in out.stdout and "Agent resumed" not in out.stdout
