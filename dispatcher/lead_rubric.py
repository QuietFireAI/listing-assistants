"""lead_rubric - the ONE lead-scoring implementation.

Extracted 2026-10-11 (audit JEV-3) from Spoke02LeadQualification._score,
whose behavior is unchanged. The JEV fallback engine previously carried its
own divergent copy: different input keys (stated_budget /
preapproval_document vs budget / preapproval_doc), no expired-letter tuple,
and no unwrapping of Agent 01's {"value", "source"} capture schema, so the
same lead scored differently (WARM 60 vs HOT 100) and a real 01-shaped lead
raised TypeError. Both now call score_lead().

Accepted input keys (either spelling): budget | stated_budget,
preapproval_doc | preapproval_document ({amount, expired?, verified?}),
timeline_days, stated_urgency, financing_progress. A pre-approval document
counts unless it is expired or explicitly verified=False.
"""
from __future__ import annotations

# Every key score_lead() reads off a rubric. Agent 02 rejects a rubric missing
# any of them (doctrine root rule: no tuple covers a partial rubric -> STOP);
# the JEV fallback engine holds instead of filling defaults.
REQUIRED_RUBRIC_KEYS = frozenset({"budget_threshold", "budget_weight",
                                  "timeline_days_threshold", "timeline_weight",
                                  "financing_weight", "hot_threshold", "warm_threshold"})


def _unwrap(v):
    """Agent 01's capture schema wraps stated fields as
    {"value": ..., "source": "stated_by_party"} - its documented
    source-attribution format. Unwrapping a documented schema is reading,
    not interpreting (found by the first e2e run, 2026-07-18)."""
    if isinstance(v, dict) and "value" in v and "source" in v:
        return v["value"]
    return v


def score_lead(payload: dict, rubric: dict) -> tuple[str, int | None, list[str], list[str]]:
    """Returns (tier, score_or_None, notes, conflicts). tier is UNKNOWN when
    all scoring inputs are unknown (tuple #12: unknown is absent data, not a
    low score). conflicts lists the data conflicts that were logged."""
    notes: list[str] = []
    conflicts: list[str] = []
    budget = _unwrap(payload.get("budget", payload.get("stated_budget")))
    preapproval_doc = payload.get("preapproval_doc", payload.get("preapproval_document"))
    timeline_days = _unwrap(payload.get("timeline_days"))
    stated_urgency = _unwrap(payload.get("stated_urgency"))
    financing_progress = _unwrap(payload.get("financing_progress"))

    if isinstance(preapproval_doc, dict) and preapproval_doc.get("verified") is False:
        notes.append("pre-approval document marked unverified - not used for scoring")
        preapproval_doc = None

    # tuple: financing letter present but expired -> treat as no verification
    if preapproval_doc and preapproval_doc.get("expired"):
        notes.append("pre-approval letter expired - treated as no "
                     "financing verification")
        financing_progress = financing_progress or "none"
        preapproval_doc = None

    # tuple: budget vs pre-approval doc conflict -> doc wins
    if preapproval_doc and budget and preapproval_doc.get("amount"):
        if abs(preapproval_doc["amount"] - budget) > 0:
            msg = (f"stated budget {budget} conflicts with pre-approval "
                   f"doc amount {preapproval_doc['amount']} - doc wins for "
                   f"scoring, conflict logged verbatim")
            notes.append(msg)
            conflicts.append(msg)
            budget = preapproval_doc["amount"]

    # tuple: stated urgency vs financing signal conflict -> financing wins
    if stated_urgency == "high" and financing_progress in (None, "none"):
        msg = ("stated urgency 'high' conflicts with no financing "
               "progress - weighting verifiable financing over stated "
               "urgency, conflict logged")
        notes.append(msg)
        conflicts.append(msg)

    inputs = {"budget": budget, "timeline_days": timeline_days,
              "financing_progress": financing_progress}
    if all(v is None for v in inputs.values()):
        return "UNKNOWN", None, notes + ["all rubric inputs unknown - "
                                         "tier is UNKNOWN, not COLD"], conflicts

    r = rubric
    score = 0
    if budget is not None and budget >= r.get("budget_threshold", 500_000):
        score += r.get("budget_weight", 40)
    if timeline_days is not None and timeline_days <= r.get("timeline_days_threshold", 30):
        score += r.get("timeline_weight", 40)
    if financing_progress == "preapproved":
        score += r.get("financing_weight", 20)

    hot = r.get("hot_threshold", 70)
    warm = r.get("warm_threshold", 40)

    # tuple: boundary score -> lower tier + flag for human. Checked FIRST.
    if score == hot:
        tier = "WARM"
        notes.append(f"score {score} sits exactly on a tier boundary "
                     f"(HOT/WARM) - assigned the lower tier (WARM), "
                     f"flagged for human")
    elif score == warm:
        tier = "COLD"
        notes.append(f"score {score} sits exactly on a tier boundary "
                     f"(WARM/COLD) - assigned the lower tier (COLD), "
                     f"flagged for human")
    elif score > hot:
        tier = "HOT"
    elif score > warm:
        tier = "WARM"
    else:
        tier = "COLD"
    return tier, score, notes, conflicts
