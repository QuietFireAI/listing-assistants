"""Tests for Nous Hermes Cognitive Seam and Broker Context Ingestor."""
import os
import tempfile
import pytest
from dispatcher.hermes_seam import HermesCognitiveSeam, BrokerContextIngestor


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

    # Export fine tuning pairs
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = os.path.join(tmpdir, "hermes_training.jsonl")
        ingestor.export_fine_tuning_pairs(out_path)
        assert os.path.exists(out_path)
        with open(out_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            assert len(lines) >= 5


def test_hermes_seam_draft_and_trace():
    seam = HermesCognitiveSeam()
    thinking, text = seam.draft_and_trace(
        agent_id="04",
        envelope_id="env-draft-01",
        prompt="Draft MLS remarks for 742 Evergreen Terrace"
    )
    assert thinking
    assert text
    assert seam.learning_loop.get_metrics()["total_assimilated"] == 1


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
