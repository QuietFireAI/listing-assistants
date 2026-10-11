"""Kills the logic mutants that survived in dispatcher/lead_rubric.py
(mutmut run on the fixed code, 2026-10-11)."""
import pytest
from dispatcher.lead_rubric import score_lead, REQUIRED_RUBRIC_KEYS

R = {"budget_threshold": 500_000, "budget_weight": 40, "timeline_days_threshold": 30,
     "timeline_weight": 40, "financing_weight": 20, "hot_threshold": 70, "warm_threshold": 40}
# distinct weights, so each component's contribution is identifiable
W = {"budget_threshold": 500_000, "budget_weight": 11, "timeline_days_threshold": 30,
     "timeline_weight": 23, "financing_weight": 5, "hot_threshold": 90, "warm_threshold": 2}


def test_each_weight_counts_once_and_exactly():
    assert score_lead({"budget": 600_000}, W)[1] == 11
    assert score_lead({"timeline_days": 10}, W)[1] == 23
    assert score_lead({"financing_progress": "preapproved"}, W)[1] == 5
    assert score_lead({"budget": 600_000, "timeline_days": 10, "financing_progress": "preapproved"}, W)[1] == 39


def test_thresholds_are_inclusive():
    assert score_lead({"budget": 500_000}, W)[1] == 11          # >= not >
    assert score_lead({"budget": 499_999}, W)[1] == 0
    assert score_lead({"timeline_days": 30}, W)[1] == 23        # <= not <
    assert score_lead({"timeline_days": 31}, W)[1] == 0


def test_thresholds_come_from_the_rubric_and_missing_keys_fail():
    tight = dict(W, budget_threshold=700_000, timeline_days_threshold=5)
    assert score_lead({"budget": 600_000, "timeline_days": 10}, tight)[1] == 0
    for key in REQUIRED_RUBRIC_KEYS:
        partial = {k: v for k, v in R.items() if k != key}
        with pytest.raises(KeyError):
            score_lead({"budget": 600_000, "timeline_days": 10, "financing_progress": "preapproved"}, partial)


def test_tier_bands_from_rubric():
    assert score_lead({"budget": 600_000, "timeline_days": 10, "financing_progress": "preapproved"}, R)[0] == "HOT"
    assert score_lead({"budget": 600_000, "timeline_days": 10}, R)[0] == "HOT"       # 80 > 70
    assert score_lead({"budget": 600_000}, R)[0] == "COLD"                          # 40 == warm -> lower
    assert score_lead({"budget": 600_000, "financing_progress": "preapproved"}, R)[0] == "WARM"  # 60
    assert score_lead({"financing_progress": "preapproved"}, R)[0] == "COLD"        # 20
    assert score_lead({"budget": 600_000, "timeline_days": 40}, dict(R, hot_threshold=41))[0] == "COLD"


def test_unverified_document_is_ignored_with_its_note():
    tier, score, notes, conflicts = score_lead(
        {"budget": 100_000, "preapproval_doc": {"amount": 900_000, "verified": False}}, R)
    assert score == 0 and conflicts == []
    assert "pre-approval document marked unverified - not used for scoring" in notes
    tier, score, _, conflicts = score_lead(
        {"budget": 100_000, "preapproval_doc": {"amount": 900_000, "verified": True}}, R)
    assert score == 40 and len(conflicts) == 1


def test_expired_letter_alone_scores_zero_not_unknown():
    tier, score, notes, _ = score_lead({"preapproval_doc": {"amount": 600_000, "expired": True}}, R)
    assert (tier, score) == ("COLD", 0)


def test_budget_conflict_only_when_amounts_differ():
    _, _, notes, conflicts = score_lead({"budget": 300_000, "preapproval_doc": {"amount": 300_000}}, R)
    assert conflicts == []
    _, _, _, conflicts = score_lead({"budget": 300_000, "preapproval_doc": {"amount": 300_001}}, R)
    assert len(conflicts) == 1 and "conflicts with pre-approval" in conflicts[0]


def test_urgency_conflict_is_recorded_as_text():
    _, _, _, conflicts = score_lead({"budget": 600_000, "stated_urgency": "high"}, R)
    assert len(conflicts) == 1 and isinstance(conflicts[0], str) and "urgency" in conflicts[0]
