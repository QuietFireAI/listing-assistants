"""Tests for Human-In-The-Loop (HITL) Pause, Real-Time Alert, Wait-State, and Resumption Protocol."""
import os
import tempfile
import pytest
from dispatcher.client_drawer import ClientDrawerManager
from dispatcher.hitl_protocol import HITLManager, WaitState
from dispatcher.listing_spokes_18 import Spoke18CalendarTask
from dispatcher.core import Envelope, Routes, AuditLog
from dispatcher.hub import Hub
from dispatcher.signatures import Ed25519Signer, Ed25519Verifier

IDENTITY_ROUTES = os.path.join(os.path.dirname(__file__), "..", "identity", "routes.json")


def make_test_hub(tmp_path):
    signer = Ed25519Signer()
    verifier = Ed25519Verifier(signer.public_key_bytes())
    return Hub(Routes(IDENTITY_ROUTES),
               AuditLog(os.path.join(tmp_path, "audit.jsonl")),
               signature_verifier=verifier.verifier())


def test_hitl_pause_and_resumption_lifecycle():
    with tempfile.TemporaryDirectory() as tmpdir:
        drawer_mgr = ClientDrawerManager(tmpdir)
        drawer = drawer_mgr.provision_drawer("ctx-escrow-100", "Bob Seller", "100 Oak Lane")

        hitl = HITLManager(drawer_manager=drawer_mgr)

        # 1. Agent 07 (Transaction Coordinator) encounters conflicting repair request -> PAUSE
        resumed_spoke_payload = {}
        def mock_agent_07_resume(wait_state: WaitState, human_payload: dict):
            resumed_spoke_payload["resumed"] = True
            resumed_spoke_payload["decision"] = wait_state.resolution["decision"]
            resumed_spoke_payload["repair_credit"] = human_payload.get("repair_credit")
            return "agent_07_milestone_advanced"

        hitl.register_resumption_handler("07", mock_agent_07_resume)

        ws = hitl.pause_operation(
            client_context_id="ctx-escrow-100",
            agent_id="07",
            paused_intent="milestone.advance",
            reason="Buyer requested $5,000 repair credit. Concession negotiation is human-only.",
            original_payload={"milestone": "inspection", "requested_credit": 5000},
            required_decision="APPROVE_REPAIR_CONCESSION"
        )

        assert ws.status == "PENDING"
        assert "ctx-escrow-100" in ws.wait_id

        # Verify wait is listed in pending queue
        pending = hitl.get_pending_waits()
        assert len(pending) == 1
        assert pending[0]["wait_id"] == ws.wait_id
        assert pending[0]["agent_id"] == "07"

        # Verify pause record exists in Client Drawer timeline
        timeline_files = drawer.list_files("timeline")
        assert len(timeline_files) == 1
        assert "_pause.json" in timeline_files[0]["filename"]

        # 2. Human makes decision: Broker approves a $3,000 counter-credit -> RESUME
        resume_res = hitl.resume_operation(
            wait_id=ws.wait_id,
            human_decision="MODIFY",
            human_payload={"repair_credit": 3000, "broker_notes": "Offer $3,000 credit in lieu of repairs"},
            human_agent_id="00"
        )

        assert resume_res["status"] == "resumed"
        assert resume_res["decision"] == "MODIFY"
        assert resume_res["handler_result"] == "agent_07_milestone_advanced"

        # Verify spoke resume callback was executed with human payload
        assert resumed_spoke_payload["resumed"] is True
        assert resumed_spoke_payload["repair_credit"] == 3000

        # Verify pending queue is now empty
        assert len(hitl.get_pending_waits()) == 0

        # Verify resolution record exists in Client Drawer timeline
        timeline_files_after = drawer.list_files("timeline")
        assert len(timeline_files_after) == 2
        assert any("_resumed.json" in f["filename"] for f in timeline_files_after)


def test_hitl_realtime_notification_and_am_recap():
    with tempfile.TemporaryDirectory() as tmpdir:
        hub = make_test_hub(tmpdir)
        spoke18 = Spoke18CalendarTask(hub)
        hub.on_turn_start()

        dispatched_alerts = []
        def test_alert_sink(alert: dict):
            dispatched_alerts.append(alert)
            return {"sent": True}

        hitl = HITLManager(hub=hub, real_time_notifier=test_alert_sink)

        # 1. Agent 02 halts lead qualification -> immediate notification fired!
        ws = hitl.pause_operation(
            client_context_id="ctx-lead-999",
            agent_id="02",
            paused_intent="lead.tier",
            reason="Lead score 70 on exact HOT/WARM boundary. Human review required.",
            original_payload={"score": 70},
            required_decision="TIER_OVERRIDE"
        )

        # Check real-time alert was received immediately
        assert len(dispatched_alerts) == 1
        alert = dispatched_alerts[0]
        assert alert["type"] == "decision_required"
        assert alert["client_context_id"] == "ctx-lead-999"
        assert alert["agent_id"] == "02"
        assert "DECISION REQUIRED" in alert["body"]
        assert ws.wait_id in alert["body"]

        # 2. Check Agent 18 Morning Briefing recaps the unresolved decision
        briefing = spoke18.generate_briefing(briefing_type="morning")
        recap = briefing.get("unresolved_decisions_recap", [])
        assert len(recap) == 1
        assert recap[0]["context"] == "ctx-lead-999"
        assert recap[0]["agent"] == "02"
        assert recap[0]["wait_id"] == ws.wait_id
        assert "HOT/WARM boundary" in recap[0]["reason"]


def test_hitl_resume_fails_on_unknown_wait_id():
    hitl = HITLManager()
    with pytest.raises(ValueError) as exc_info:
        hitl.resume_operation(
            wait_id="wait-fake-id",
            human_decision="APPROVE",
            human_payload={}
        )
    assert "not found" in str(exc_info.value)


def test_hitl_standardized_decisions_and_forensic_snapshot():
    with tempfile.TemporaryDirectory() as tmpdir:
        drawer_mgr = ClientDrawerManager(tmpdir)
        drawer = drawer_mgr.provision_drawer("ctx-snap-777", "Alice Test", "777 Elm St")
        hitl = HITLManager(drawer_manager=drawer_mgr)

        # 1. Pause operation
        ws = hitl.pause_operation(
            client_context_id="ctx-snap-777",
            agent_id="04",
            paused_intent="marketing.copy",
            reason="Contradiction in property bed count. Stoppage requires operator value update.",
            original_payload={"beds": 3, "listing_price": 500000},
            required_decision="CORRECT_BED_COUNT"
        )

        # 2. Test create_forensic_snapshot
        snapshot = hitl.create_forensic_snapshot(
            client_context_id="ctx-snap-777",
            wait_id=ws.wait_id,
            notes="Client confirmed 4 bedrooms, not 3."
        )
        assert snapshot["snapshot_id"].startswith("snap_ctx-snap-777_")
        assert snapshot["json_path"] is not None
        assert snapshot["markdown_path"] is not None
        assert "Alice Test" in snapshot["markdown_content"] or "ctx-snap-777" in snapshot["markdown_content"]
        assert "CORRECT_BED_COUNT" in snapshot["markdown_content"]

        # 3. Resume with APPROVE_WITH_OVERRIDE / CONTINUE_WITH_UPDATE
        res = hitl.resume_operation(
            wait_id=ws.wait_id,
            human_decision="APPROVE_WITH_OVERRIDE",
            human_payload={"updated_fields": {"beds": 4}}
        )
        assert res["status"] == "resumed"
        assert res["decision"] == "APPROVE_WITH_OVERRIDE"
        assert ws.original_payload["beds"] == 4  # Overridden value merged cleanly

        # 4. Test CLOSE_SYSTEM emergency shutdown
        ws2 = hitl.pause_operation(
            client_context_id="ctx-snap-777",
            agent_id="15",
            paused_intent="wire.instruction",
            reason="Suspected wire fraud spoofing.",
            original_payload={"wire_requested": True},
            required_decision="EMERGENCY_GATE"
        )
        close_res = hitl.resume_operation(
            wait_id=ws2.wait_id,
            human_decision="CLOSE_SYSTEM",
            human_payload={"reason": "Compromised title email"}
        )
        assert close_res["status"] == "system_closed"
        assert ws2.status == "SYSTEM_CLOSED"


def test_hitl_escalate_to_support():
    with tempfile.TemporaryDirectory() as tmpdir:
        hub = make_test_hub(tmpdir)
        drawer_mgr = ClientDrawerManager(tmpdir)
        drawer_mgr.provision_drawer("ctx-support-101", "Charlie Test", "101 Maple Way")
        hitl = HITLManager(hub=hub, drawer_manager=drawer_mgr)

        ws = hitl.pause_operation(
            client_context_id="ctx-support-101",
            agent_id="07",
            paused_intent="closing.concession",
            reason="Ambiguous addendum clause regarding buyer repair allowance.",
            original_payload={"clause": "Seller credits buyer $4,500 pending HVAC check"},
            required_decision="APPROVE_CREDIT"
        )

        res = hitl.resume_operation(
            wait_id=ws.wait_id,
            human_decision="ESCALATE_TO_SUPPORT",
            human_payload={"user_notes": "Unclear if HVAC check passed; need QuietFire assistance."}
        )

        assert res["status"] == "escalated_to_support"
        assert res["decision"] == "ESCALATE_TO_SUPPORT"
        assert res["ticket_id"].startswith("TICKET-")
        assert "Diagnostic package packaged" in res["message"]
        assert ws.status == "ESCALATED_TO_SUPPORT"
        assert ws.resolution["ticket_id"] == res["ticket_id"]
        assert ws.resolution["snapshot_id"] is not None

