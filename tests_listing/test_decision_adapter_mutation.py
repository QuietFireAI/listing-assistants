"""Kills logic mutants that survived in dispatcher/decision_adapter.py
(post-fix mutmut run, 2026-10-11)."""
import json

import pytest
from dispatcher.decision_adapter import JevDecisionAdapter, JevPythonDecisionEngine

R = {"budget_threshold": 500_000, "budget_weight": 40, "timeline_days_threshold": 30,
     "timeline_weight": 40, "financing_weight": 20, "hot_threshold": 70, "warm_threshold": 40}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ("JEV_API_KEY", "JEV_ENDPOINT_URL", "JEV_FORCE_PYTHON", "JEV_MODEL"):
        monkeypatch.delenv(k, raising=False)


@pytest.mark.parametrize("payload,expected", [
    ({"budget": 600_000, "timeline_days": 10, "financing_progress": "preapproved"}, 0.85),
    ({"budget": 600_000, "timeline_days": 10}, 0.70),
    ({"budget": 600_000}, 0.55),
    ({"stated_budget": 600_000, "timeline_days": 10}, 0.70),
    ({"preapproval_doc": {"amount": 600_000}, "timeline_days": 10}, 0.70),
    ({"preapproval_document": {"amount": 600_000}, "timeline_days": 10}, 0.70),
    ({"timeline_days": 10, "financing_progress": "preapproved"}, 0.70),
    ({"financing_progress": "preapproved"}, 0.55),
])
def test_local_confidence_counts_each_missing_input(payload, expected):
    res = JevPythonDecisionEngine().evaluate_lead_rubric("c", payload, R)
    assert res["confidence"] == expected


def test_placeholder_keys_are_not_keys(monkeypatch):
    assert JevDecisionAdapter(api_key="YOUR_JEV_KEY").api_key is None
    assert JevDecisionAdapter(api_key="PLACEHOLDER").api_key is None
    assert JevDecisionAdapter(api_key="real-key").api_key == "real-key"
    monkeypatch.setenv("JEV_API_KEY", "env-key")
    assert JevDecisionAdapter().api_key == "env-key"


def test_force_python_from_env_and_endpoint_override(monkeypatch):
    a = JevDecisionAdapter(api_key="k", allow_external=True)
    assert a.force_python is False and a._live_enabled() is True
    assert a.endpoint_url == "https://api.typesafe.ai/v1/decisions"
    monkeypatch.setenv("JEV_FORCE_PYTHON", "1")
    monkeypatch.setenv("JEV_ENDPOINT_URL", "https://jev.example.test/d")
    b = JevDecisionAdapter(api_key="k", allow_external=True)
    assert b.force_python is True and b._live_enabled() is False
    assert b.endpoint_url == "https://jev.example.test/d"
    assert b.get_coprocessor_status()["reason"] == "JEV_FORCE_PYTHON active"
    assert JevDecisionAdapter(force_python=True).force_python is True


def test_http_call_sends_key_threshold_and_timeout(monkeypatch):
    seen = {}

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps({"tier": "HOT", "confidence": 0.9}).encode()

    def fake_urlopen(req, timeout):
        seen["timeout"] = timeout
        seen["auth"] = req.get_header("Authorization")
        seen["body"] = json.loads(req.data.decode())
        seen["url"] = req.full_url
        return Resp()
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("JEV_MODEL", "jev-test")
    a = JevDecisionAdapter(api_key="k-1", allow_external=True, timeout=7.5, confidence_threshold=0.6)
    res = a.evaluate_lead("ctx-9", {"budget": 600_000}, R)
    assert res["engine"] == "jev_live_api" and res["tier"] == "HOT" and res["confidence"] == 0.9
    assert seen["timeout"] == 7.5 and seen["auth"] == "Bearer k-1"
    assert seen["url"] == "https://api.typesafe.ai/v1/decisions"
    assert seen["body"]["model"] == "jev-test" and seen["body"]["decision_type"] == "lead_qualification"
    assert seen["body"]["context_id"] == "ctx-9" and seen["body"]["confidence_threshold"] == 0.6
    assert seen["body"]["payload"]["rubric"] == R


def test_floor_is_inclusive_and_hold_names_the_context(monkeypatch):
    a = JevDecisionAdapter(api_key="k", allow_external=True)
    monkeypatch.setattr(a, "_call_http_decision", lambda *x: {"tier": "WARM", "confidence": 0.45})
    assert a.evaluate_lead("ctx-eq", {"budget": 1}, R).get("status") != "held_confidence_underflow"
    monkeypatch.setattr(a, "_call_http_decision", lambda *x: {"tier": "WARM", "confidence": "n/a"})
    held = a.evaluate_lead("ctx-low", {"budget": 1}, R)
    assert held["status"] == "held_confidence_underflow" and "'ctx-low'" in held["operator_notice"]
    assert "external result confidence 'n/a' unreadable - treated as 0.0" in held["notes"]


def test_adapter_threshold_reaches_the_local_engine():
    a = JevDecisionAdapter(confidence_threshold=0.9)
    assert a.python_engine.default_confidence_threshold == 0.9
    res = a.evaluate_lead("c", {"budget": 600_000, "timeline_days": 10, "financing_progress": "preapproved"}, R)
    assert res["status"] == "held_confidence_underflow" and res["confidence_threshold"] == 0.9
