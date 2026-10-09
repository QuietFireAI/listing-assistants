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
