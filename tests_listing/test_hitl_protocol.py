"""Tests for Human-In-The-Loop (HITL) Pause, Wait-State, and Resumption Protocol."""
import os
import tempfile
import pytest
from dispatcher.client_drawer import ClientDrawerManager
from dispatcher.hitl_protocol import HITLManager, WaitState


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


def test_hitl_resume_fails_on_unknown_wait_id():
    hitl = HITLManager()
    with pytest.raises(ValueError) as exc_info:
        hitl.resume_operation(
            wait_id="wait-fake-id",
            human_decision="APPROVE",
            human_payload={}
        )
    assert "not found" in str(exc_info.value)
