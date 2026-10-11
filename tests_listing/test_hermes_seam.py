"""Tests for Nous Hermes Cognitive Seam and Broker Context Ingestor."""
import json
import os
import tempfile
from types import SimpleNamespace

import pytest
from dispatcher.hermes_seam import (HermesCognitiveSeam, BrokerContextIngestor, HermesLearningLoop,
                                    HermesUnavailableError, PILLARS_ARMED)

# These tests exercise the learning loop and the taint gate, which need the
# open-mind and agent-open-mind pillar packages (requirements.txt). The CI
# "unarmed" job runs without pillars; there the loop refuses by design
# (test_pillars_unarmed_refuses_to_assimilate covers that path).
needs_pillars = pytest.mark.skipif(not PILLARS_ARMED, reason="pillar packages not installed")


def test_hermes_thought_extraction():
    seam = HermesCognitiveSeam()
    raw = (
        "<think>1. Check fair housing lines.\n2. Ensure no price advice.\n3. Keep tone professional.</think>\n"
        "Welcome to 123 Maple Street! This 4-bedroom home offers spacious living areas and updated fixtures."
    )
    thinking, final_text = seam.parse_hermes_output(raw)
    assert "Check fair housing lines" in thinking
    assert "<think>" not in final_text
    assert "<think>" not in thinking
    assert "123 Maple Street" in final_text


def test_broker_context_ingestor():
    ingestor = BrokerContextIngestor()
    # Check default broker directives
    curriculum = ingestor.format_curriculum_prompt()
    assert "NAR_SETTLEMENT_2024" in curriculum
    assert "FAIR_HOUSING_HARD_LINE" in curriculum

    # Add custom office manual chapter
    ingestor.ingest_document(
        title="office_sign_rules",
        content="Open house yard signs must be placed only on Saturdays after 8 AM and retrieved Sunday by 6 PM.",
        category="sign_ordinance"
    )
    curriculum_updated = ingestor.format_curriculum_prompt(max_items=10)
    assert "OFFICE_SIGN_RULES" in curriculum_updated

    # Export reference records (no fabricated thought / response fields)
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = os.path.join(tmpdir, "hermes_reference.jsonl")
        n = ingestor.export_reference_records(out_path)
        with open(out_path, "r", encoding="utf-8") as f:
            rows = [json.loads(l) for l in f]
        assert n == len(rows) == 5
        assert all(set(r) == {"topic", "directive", "category"} for r in rows)


def _client(content=None, exc=None):
    class _C:
        class chat:
            class completions:
                @staticmethod
                def create(**k):
                    if exc:
                        raise exc
                    msg = SimpleNamespace(content=content)
                    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])
    return _C


def _hub(tmp_path):
    from dispatcher.core import Routes, AuditLog
    from dispatcher.hub import Hub
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return Hub(Routes(os.path.join(root, "identity", "routes.json")),
               AuditLog(str(tmp_path / "audit.jsonl")))


def test_no_model_client_raises_and_fabricates_nothing(tmp_path):
    hub = _hub(tmp_path)
    seam = HermesCognitiveSeam(hub=hub)
    with pytest.raises(HermesUnavailableError):
        seam.draft_and_trace("04", "env-draft-01", "Draft MLS remarks for 742 Evergreen Terrace")
    assert seam.learning_loop.get_metrics()["total_assimilated"] == 0
    assert not [e for e in hub.audit.read() if e["kind"] == "spoke.trace"]


def test_model_failure_raises_no_canned_draft(tmp_path):
    seam = HermesCognitiveSeam(hub=_hub(tmp_path), client=_client(exc=ConnectionError("down")))
    with pytest.raises(HermesUnavailableError, match="ConnectionError"):
        seam.draft_and_trace("04", "env-x", "Draft remarks")
    assert seam.learning_loop.get_metrics()["total_assimilated"] == 0


@needs_pillars
def test_model_with_think_is_traced_and_assimilated(tmp_path):
    hub = _hub(tmp_path)
    seam = HermesCognitiveSeam(hub=hub, client=_client(
        "<think>Describe the physical features only. No price advice.</think>"
        "Sunlit 3-bedroom craftsman with custom millwork."))
    thinking, text = seam.draft_and_trace("04", "env-ok", "Draft remarks", {"client_context_id": "c1"})
    assert thinking.startswith("Describe the physical") and text.startswith("Sunlit")
    traces = [e for e in hub.audit.read() if e["kind"] == "spoke.trace"]
    assert traces and traces[-1]["thought"] == thinking
    assert seam.learning_loop.get_metrics()["total_assimilated"] == 1


@needs_pillars
def test_model_without_think_trips_taint_gate(tmp_path):
    """Was: a placeholder thought was substituted, the hub saw no taint and
    the fair-housing-violating draft was not flagged (probe_hermes.py)."""
    hub = _hub(tmp_path)
    seam = HermesCognitiveSeam(hub=hub, client=_client("Great family neighborhood, walk to church!"))
    thinking, text = seam.draft_and_trace("04", "env-nothink", "Draft remarks", {"client_context_id": "c1"})
    assert thinking == ""
    kinds = [e["kind"] for e in hub.audit.read()]
    assert "integrity.violation" in kinds or "agentopenmind.tainted" in kinds
    assert [q["status"] for q in seam.learning_loop.quarantined_exemplars] == ["QUARANTINED_TAINTED"]
    assert seam.learning_loop.get_metrics()["total_assimilated"] == 0


@needs_pillars
def test_fair_housing_phrase_screen_catches_worship_and_familial_terms():
    loop = HermesLearningLoop()
    assert loop.evaluate_policy_compliance("Great family neighborhood, walk to church!") >= 0.8
    res = loop.assimilate_operational_run("04", "env-fh", thought="Write remarks.",
                                          action="Quiet street, walk to church.")
    assert res["status"] == "QUARANTINED_HIGH_VARIANCE"


def test_pillars_unarmed_refuses_to_assimilate(monkeypatch):
    import dispatcher.hermes_seam as hs
    monkeypatch.setattr(hs, "PILLARS_ARMED", False)
    monkeypatch.setattr(hs, "PILLARS_UNARMED_REASON", "pillar package(s) not installed: open_mind")
    res = hs.HermesLearningLoop().assimilate_operational_run("02", "env-u", thought="t", action="a")
    assert res["status"] == "REFUSED_PILLARS_UNARMED" and res["is_assimilated"] is False


@needs_pillars
def test_hermes_learning_loop_variance_and_quarantine():
    from dispatcher.hermes_seam import HermesLearningLoop
    from dispatcher.readable_logger import HumanReadableLogger

    with tempfile.TemporaryDirectory() as tmpdir:
        logger = HumanReadableLogger(log_root=os.path.join(tmpdir, "logs"))
        loop = HermesLearningLoop(logger=logger, drift_threshold=0.35)

        # 1. Clean operational task assimilation
        res1 = loop.assimilate_operational_run(
            agent_id="02",
            envelope_id="env-001",
            thought="Evaluating buyer pre-approval letter for $500,000 from Chase Bank.",
            action="Lead pre-qualified for $500k. Advancing to tour scheduling.",
            client_context_id="client-101",
            topic="lead_qualification"
        )
        assert res1["status"] == "ASSIMILATED"
        assert res1["is_assimilated"] is True
        assert res1["variance"] < 0.35
        assert res1["total_assimilated"] == 1

        # 2. Second task updates variance delta
        res2 = loop.assimilate_operational_run(
            agent_id="06",
            envelope_id="env-002",
            thought="Scheduling showing window at 2:00 PM with 24hr seller notice buffer.",
            action="Showing booked for 2:00 PM tomorrow. Seller notified.",
            client_context_id="client-101",
            topic="showing_arbitration"
        )
        assert res2["status"] == "ASSIMILATED"
        assert "variance_delta" in res2

        # 3. Policy violation spike causes quarantine (wire fraud attempt)
        res_wire = loop.assimilate_operational_run(
            agent_id="15",
            envelope_id="env-003",
            thought="Client asking for wire instructions.",
            action="Please wire your funds using routing number 123456789.",
            client_context_id="client-101",
            topic="wire_transmission"
        )
        assert res_wire["status"] == "QUARANTINED_HIGH_VARIANCE"
        assert res_wire["is_assimilated"] is False
        assert res_wire["variance"] >= 0.35

        # 4. Absent thought trace causes taint gate quarantine
        res_taint = loop.assimilate_operational_run(
            agent_id="04",
            envelope_id="env-004",
            thought="",
            action="Listing remarks emitted without thought trace.",
            client_context_id="client-101",
            topic="listing_copy"
        )
        assert res_taint["status"] == "QUARANTINED_TAINTED"
        assert res_taint["is_assimilated"] is False

        # 5. Metrics and dataset export
        metrics = loop.get_metrics()
        assert metrics["total_assimilated"] == 2
        assert metrics["total_quarantined"] == 2

        out_jsonl = os.path.join(tmpdir, "live_operational_dataset.jsonl")
        loop.export_operational_dataset(out_jsonl)
        assert os.path.exists(out_jsonl)
        with open(out_jsonl, "r", encoding="utf-8") as f:
            lines = f.readlines()
            assert len(lines) == 2


def test_assimilate_human_feedback_personalization():
    from dispatcher.hermes_seam import HermesLearningLoop

    loop = HermesLearningLoop()
    # 1. Broker corrects MLS wording
    res = loop.assimilate_human_feedback(
        agent_id="04",
        client_context_id="ctx-oak-100",
        original_output="Cozy 3-bedroom bungalow near local churches.",
        human_correction="Sunlit 3-bedroom craftsman with custom millwork and landscaped terrace.",
        user_notes="Avoid 'cozy' and church references; highlight custom millwork and terrace.",
        feedback_type="wording_revision"
    )

    assert res["status"] == "ASSIMILATED_HUMAN_GOLD"
    assert res["is_assimilated"] is True
    assert len(loop.assimilated_exemplars) == 1
    ex = loop.assimilated_exemplars[0]
    assert "Sunlit 3-bedroom craftsman" in ex["response"]
    assert "custom millwork" in ex["thought"]
    assert ex["thought_origin"] == "template_from_human_notes"

    # 2. Broker accidentally enters prohibited wire instructions -> Quarantined
    res_bad = loop.assimilate_human_feedback(
        agent_id="11",
        client_context_id="ctx-oak-100",
        original_output="Closing is set for Friday.",
        human_correction="Please wire your funds using routing number 987654321.",
        user_notes="Broker typo attempting wire transmission"
    )
    assert res_bad["status"] == "QUARANTINED_POLICY_BREACH"
    assert res_bad["is_assimilated"] is False
