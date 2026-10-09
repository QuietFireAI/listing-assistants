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
