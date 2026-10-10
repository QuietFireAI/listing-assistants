"""Tests for JEV AI Decision Platform Adapter and Pure Python Fallback."""
import pytest
from dispatcher.decision_adapter import JevDecisionAdapter, JevPythonDecisionEngine


def test_jev_lead_rubric_scoring_hot():
    engine = JevPythonDecisionEngine()
    rubric = {
        "budget_threshold": 500_000,
        "budget_weight": 40,
        "timeline_days_threshold": 30,
        "timeline_weight": 40,
        "financing_weight": 20,
        "hot_threshold": 70,
        "warm_threshold": 40,
    }
    lead = {
        "stated_budget": 650_000,
        "timeline_days": 15,
        "financing_progress": "preapproved",
    }
    result = engine.evaluate_lead_rubric("ctx-01", lead, rubric)
    assert result["status"] == "ok"
    assert result["tier"] == "HOT"
    assert result["score"] == 100
    assert result["decision_provenance"] == "jev_engine_python_v1"


def test_jev_lead_rubric_boundary_score_assigns_lower_tier():
    engine = JevPythonDecisionEngine()
    rubric = {
        "budget_threshold": 500_000,
        "budget_weight": 40,
        "timeline_days_threshold": 30,
        "timeline_weight": 30,
        "financing_weight": 20,
        "hot_threshold": 70,
        "warm_threshold": 40,
    }
    lead = {
        "stated_budget": 550_000,   # +40
        "timeline_days": 20,        # +30 = 70 (exact boundary)
        "financing_progress": "none",
    }
    result = engine.evaluate_lead_rubric("ctx-02", lead, rubric)
    assert result["score"] == 70
    assert result["tier"] == "WARM", "Exact hot boundary must assign lower tier WARM"
    assert any("boundary" in n for n in result["notes"])


def test_jev_lead_preapproval_overrides_stated_budget():
    engine = JevPythonDecisionEngine()
    rubric = {
        "budget_threshold": 500_000,
        "budget_weight": 40,
        "timeline_days_threshold": 30,
        "timeline_weight": 40,
        "financing_weight": 20,
        "hot_threshold": 70,
        "warm_threshold": 40,
    }
    lead = {
        "stated_budget": 700_000,
        "preapproval_document": {"verified": True, "amount": 400_000},  # Under threshold
        "timeline_days": 10,
        "financing_progress": "preapproved",
    }
    result = engine.evaluate_lead_rubric("ctx-03", lead, rubric)
    # Budget fails threshold (400k < 500k), timeline (+40), financing (+20) = 60 -> WARM
    assert result["score"] == 60
    assert result["tier"] == "WARM"
    assert any("pre-approval doc amount" in n for n in result["notes"])


def test_jev_scheduling_protected_displaces_soft_booking():
    engine = JevPythonDecisionEngine()
    existing = [
        {"slot_id": "s-1", "time": "2026-10-15T14:00:00", "protected": False}
    ]
    # New request is protected (Agent 07 milestone)
    requested = {
        "slot_id": "s-2",
        "time": "2026-10-15T14:15:00",
        "protected": True
    }
    result = engine.resolve_scheduling_conflict("ctx-sched", requested, existing, buffer_minutes=30)
    assert result["status"] == "ok"
    assert result["action"] == "displace_existing"
    assert result["displaced_slot"]["slot_id"] == "s-1"


def test_jev_adapter_fallback():
    adapter = JevDecisionAdapter(force_python=True)
    rubric = {
        "budget_threshold": 500_000,
        "budget_weight": 40,
        "timeline_days_threshold": 30,
        "timeline_weight": 40,
        "financing_weight": 20,
        "hot_threshold": 70,
        "warm_threshold": 40,
    }
    res = adapter.evaluate_lead("ctx-fallback", {"stated_budget": 600_000}, rubric)
    assert res["status"] == "ok"
    assert res["engine"] == "python_fallback"


def test_jev_confidence_underflow_triggers_deterministic_stop():
    engine = JevPythonDecisionEngine(confidence_threshold=0.45)
    rubric = {
        "budget_threshold": 500_000,
        "budget_weight": 40,
        "timeline_days_threshold": 30,
        "timeline_weight": 40,
        "financing_weight": 20,
        "hot_threshold": 70,
        "warm_threshold": 40,
    }
    # Lead with explicit low confidence rating (0.38 < 0.45)
    lead = {
        "stated_budget": 650_000,
        "timeline_days": 10,
        "confidence": 0.38,
    }
    res = engine.evaluate_lead_rubric("ctx-underflow-01", lead, rubric)
    assert res["status"] == "held_confidence_underflow"
    assert res["is_confidence_underflow"] is True
    assert res["confidence"] == 0.38
    assert res["confidence_threshold"] == 0.45
    assert res["tier"] == "HELD_FOR_CALIBRATION"
    assert res["escalation_required"] is True
    assert res["escalation_type"] == "escalation.confidence_underflow"
    assert "JEV Calibration Hold" in res["broker_notice"]
    assert "HIGH-PRIORITY CALIBRATION" in res["operator_notice"]
    assert any("below default floor" in note for note in res["notes"])


def test_jev_confidence_underflow_from_signal_conflicts():
    engine = JevPythonDecisionEngine()
    rubric = {
        "budget_threshold": 500_000,
        "budget_weight": 40,
        "timeline_days_threshold": 30,
        "timeline_weight": 40,
        "financing_weight": 20,
        "hot_threshold": 70,
        "warm_threshold": 40,
    }
    # 1 signal present (base 0.50), but 2 conflicts:
    # conflict 1: stated budget conflicts with preapproval doc
    # conflict 2: stated urgency 'high' conflicts with no financing
    # 0.50 - 2 * 0.15 = 0.20 < 0.45 floor
    lead = {
        "stated_budget": 600_000,
        "preapproval_document": {"verified": True, "amount": 350_000},
        "stated_urgency": "high",
        "financing_progress": "none",
    }
    res = engine.evaluate_lead_rubric("ctx-underflow-conflicts", lead, rubric)
    assert res["status"] == "held_confidence_underflow"
    assert res["is_confidence_underflow"] is True
    assert res["confidence"] < 0.45
    assert "JEV Calibration Hold" in res["broker_notice"]


def test_jev_confidence_underflow_all_unknown_inputs():
    engine = JevPythonDecisionEngine()
    rubric = {"budget_threshold": 500_000}
    res = engine.evaluate_lead_rubric("ctx-unknown", {}, rubric)
    assert res["status"] == "held_confidence_underflow"
    assert res["is_confidence_underflow"] is True
    assert res["tier"] == "UNKNOWN"
    assert res["confidence"] == 0.0


def test_jev_adapter_mcp_enforces_confidence_floor():
    class MockMcpClient:
        def call_tool(self, name, args):
            return {
                "status": "ok",
                "confidence": 0.32,  # Below 0.45 floor
                "tier": "WARM",
                "score": 50
            }

    adapter = JevDecisionAdapter(mcp_client=MockMcpClient(), force_python=False, confidence_threshold=0.45)
    rubric = {"budget_threshold": 500_000}
    res = adapter.evaluate_lead("ctx-mcp-floor", {"stated_budget": 500_000}, rubric)
    assert res["status"] == "held_confidence_underflow"
    assert res["is_confidence_underflow"] is True
    assert res["engine"] == "jev_mcp"
    assert res["confidence"] == 0.32
    assert res["tier"] == "HELD_FOR_CALIBRATION"
    assert "JEV Calibration Hold" in res["broker_notice"]


def test_jev_hitl_pause_confidence_underflow_dispatches_dual_notices():
    from dispatcher.hitl_protocol import HITLManager

    class MockHub:
        def __init__(self):
            self.escalations = []
            self.traces = []

        def escalate(self, queue, payload):
            self.escalations.append((queue, payload))
            return {"status": "escalated", "queue": queue}

        def ingest_spoke_trace(self, agent_id, wait_id, thought, result):
            self.traces.append((agent_id, wait_id, thought, result))

    mock_hub = MockHub()
    hitl = HITLManager(hub=mock_hub)

    decision_result = {
        "confidence": 0.39,
        "confidence_threshold": 0.45,
        "broker_notice": "JEV Calibration Hold: Data certainty scored at 0.39 (below 0.45 floor). Parked in siding for your quick review.",
        "operator_notice": "HIGH-PRIORITY CALIBRATION: JEV confidence underflow (0.39 < 0.45) for context 'client-999'."
    }

    ws = hitl.pause_confidence_underflow("client-999", "03", decision_result)
    assert ws.status == "PENDING"
    assert ws.paused_intent == "jev.confidence_underflow"
    assert ws.required_decision == "APPROVE_OR_RECALIBRATE"

    # Verify broker notification logged
    assert len(hitl.notification_log) == 1
    notice = hitl.notification_log[0]
    assert "[JEV CALIBRATION HOLD]" in notice["body"]
    assert "0.39" in notice["body"]

    # Verify operator escalation ping
    assert len(mock_hub.escalations) == 1
    queue, payload = mock_hub.escalations[0]
    assert queue == "escalation.confidence_underflow"
    assert payload["confidence"] == 0.39
    assert payload["confidence_threshold"] == 0.45
    assert "operator_fine_tuning_evaluation" in payload["action"]


def test_jev_adapter_live_api_success(monkeypatch):
    adapter = JevDecisionAdapter(api_key="jev_test_key_live_123")
    assert adapter.api_key == "jev_test_key_live_123"

    mock_response = {
        "status": "ok",
        "confidence": 0.88,
        "tier": "HOT",
        "score": 95,
        "notes": ["Evaluated by live JEV AI platform"]
    }

    # Mock _call_http_decision
    monkeypatch.setattr(adapter, "_call_http_decision", lambda decision_type, context_id, payload: mock_response)

    rubric = {"budget_threshold": 500_000}
    res = adapter.evaluate_lead("ctx-live-01", {"stated_budget": 600_000}, rubric)
    assert res["status"] == "ok"
    assert res["engine"] == "jev_live_api"
    assert res["confidence"] == 0.88
    assert res["tier"] == "HOT"


def test_jev_adapter_live_api_confidence_underflow_enforced(monkeypatch):
    adapter = JevDecisionAdapter(api_key="jev_test_key_live_123", confidence_threshold=0.45)

    mock_response = {
        "status": "ok",
        "confidence": 0.35,  # Below 0.45 floor
        "tier": "WARM",
        "score": 50
    }

    monkeypatch.setattr(adapter, "_call_http_decision", lambda decision_type, context_id, payload: mock_response)

    rubric = {"budget_threshold": 500_000}
    res = adapter.evaluate_lead("ctx-live-underflow", {"stated_budget": 500_000}, rubric)
    assert res["status"] == "held_confidence_underflow"
    assert res["is_confidence_underflow"] is True
    assert res["engine"] == "jev_live_api"
    assert res["confidence"] == 0.35
    assert res["tier"] == "HELD_FOR_CALIBRATION"
    assert "JEV Calibration Hold" in res["broker_notice"]


def test_jev_adapter_live_api_network_failure_falls_back(monkeypatch):
    adapter = JevDecisionAdapter(api_key="jev_test_key_live_123")

    def failing_http(*args, **kwargs):
        raise ConnectionResetError("Connection refused by remote host")

    monkeypatch.setattr(adapter, "_call_http_decision", failing_http)

    rubric = {
        "budget_threshold": 500_000,
        "budget_weight": 40,
        "timeline_days_threshold": 30,
        "timeline_weight": 40,
        "financing_weight": 20,
        "hot_threshold": 70,
        "warm_threshold": 40,
    }
    lead = {
        "stated_budget": 650_000,
        "timeline_days": 15,
        "financing_progress": "preapproved",
    }
    # Must seamlessly fall back to local pure-Python engine rather than crashing
    res = adapter.evaluate_lead("ctx-failover", lead, rubric)
    assert res["status"] == "ok"
    assert res["engine"] == "python_fallback"
    assert res["tier"] == "HOT"
    assert res["score"] == 100


def test_jev_adapter_showing_conflict_live_api(monkeypatch):
    adapter = JevDecisionAdapter(api_key="jev_test_key_live_123")

    mock_response = {
        "status": "ok",
        "action": "displace_existing",
        "displaced_slot": {"slot_id": "s-1"},
        "reason": "protected_outranks_soft"
    }

    monkeypatch.setattr(adapter, "_call_http_decision", lambda decision_type, context_id, payload: mock_response)

    res = adapter.resolve_showing_conflict("ctx-sched", {"time": "2026-10-15T14:00:00"}, [])
    assert res["status"] == "ok"
    assert res["engine"] == "jev_live_api"
    assert res["action"] == "displace_existing"


