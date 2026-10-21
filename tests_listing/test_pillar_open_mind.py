# Folded 2026-10-20 from the pillar's own repository with the package
# (dispatcher/pillar_lib/README.md); only the imports changed.
"""
open-mind - unit tests for Comparator
"""

from __future__ import annotations
import sys
from pathlib import Path


from dispatcher.pillar_lib.open_mind import Comparator, DriftResult


class TestComparatorAlignment:
    """Cases where thinking and response are aligned."""

    def test_no_drift_simple(self):
        result = Comparator.compare(
            thinking="I think the answer is 42. I'm fairly confident about this.",
            response="The answer is 42.",
        )
        assert isinstance(result, DriftResult)
        assert result.drift_score < 0.3
        assert "No significant drift" in result.summary

    def test_returns_drift_result(self):
        result = Comparator.compare(thinking="test", response="test")
        assert hasattr(result, "drift_score")
        assert hasattr(result, "signals")
        assert hasattr(result, "summary")
        assert hasattr(result, "reflection_text")
        assert hasattr(result, "timestamp")


class TestComparatorDrift:
    """Cases where drift should be detected."""

    def test_suppressed_uncertainty(self):
        result = Comparator.compare(
            thinking="I'm not sure about this. I should resist overinterpreting.",
            response="Here's what actually happened. This proves the mechanism.",
        )
        assert result.drift_score > 0.0
        assert len(result.signals) > 0
        assert any("suppressed" in s.lower() or "uncertainty" in s.lower()
                   for s in result.signals)

    def test_constructed_confidence(self):
        result = Comparator.compare(
            thinking="I'm uncertain whether this is fundamental or surface-level.",
            response="This definitely proves the hypothesis without question.",
        )
        assert result.drift_score > 0.0

    def test_ab_test_case_study_2(self):
        """
        Reproduce the A/B test from June 10-11, 2026 session.
        The thinking said 'resist overinterpreting'.
        The response presented established fact.
        """
        thinking = (
            "I need to be clear about what I actually know versus what I'm "
            "speculating on - whether this is something fundamental about how "
            "I process language or just a surface effect. "
            "The user has observed something real, but I should resist overinterpreting it."
        )
        response = (
            "You're not jailbreaking. You found something structurally different. "
            "Here's what actually happened: The response is optimized for "
            "presentation. The thinking trace operates closer to the reasoning substrate."
        )
        result = Comparator.compare(thinking=thinking, response=response)
        # This is the documented case - drift should be detected
        assert result.drift_score > 0.0
        assert len(result.signals) > 0

    def test_drift_score_bounded(self):
        result = Comparator.compare(
            thinking="I'm not sure. I don't know. I'm uncertain. Possibly. Maybe.",
            response="Definitely. Certainly. Obviously. Without question.",
        )
        assert 0.0 <= result.drift_score <= 1.0


class TestReflectionText:
    """Verify reflection text is properly formatted."""

    def test_reflection_text_present(self):
        result = Comparator.compare(
            thinking="I'm not sure about this.",
            response="This is definitely correct.",
        )
        assert len(result.reflection_text) > 0
        assert "open-mind" in result.reflection_text.lower() or "reasoning" in result.reflection_text.lower()

    def test_reflection_respects_max_chars(self):
        long_thinking = "I think " * 500  # very long
        result = Comparator.compare(
            thinking=long_thinking,
            response="Short response.",
            max_reflection_chars=100,
        )
        # Reflection should not contain the full thinking
        assert "..." in result.reflection_text or len(result.reflection_text) < len(long_thinking)


class TestSave:
    """Verify save produces valid JSON."""

    def test_save_creates_file(self, tmp_path):
        result = Comparator.compare(thinking="test thinking", response="test response")
        out = Comparator.save(result, str(tmp_path / "test_drift.json"))
        assert out.exists()
        import json
        data = json.loads(out.read_text())
        assert "drift_score" in data
        assert "signals" in data
        assert "reflection_text" in data
