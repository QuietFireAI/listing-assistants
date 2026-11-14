"""Every playbook, start to end, through the console (2026-10-20), and the
tuples built in the 2026-10-15 to 2026-10-20 round, kept running in CI.

1. synth/playbooks/specs/PLAYBOOKS.jsonl has one session per playbook,
   P01 to P24, from its start to its end, run through `tools/console.py
   session` the way `python synth/tuples/run_tuples.py --set playbooks`
   runs them: each must start its run, end it as completed, write its
   after-action report and show the playbook's own evidence.
2. The tuples this round built (the fault harness, the dispatcher checks,
   the run tracker) must PASS through the console as well.
"""
import json
import os
import shutil
import sys
import tempfile

import pytest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "synth", "tuples"))

import run_tuples  # noqa: E402

PLAYBOOKS = [f"P{i:02d}" for i in range(1, 25)]
ROUND = [
    # fault harness and the hub failing closed (2026-10-15)
    "00-04", "00-07", "00-13", "00-16", "00-17", "01-16", "SW-07",
    # dispatcher checks: re-alert, clock skew, identity reload, briefing gaps,
    # instruction against a deadline (2026-10-15)
    "00-10", "00-11", "00-14", "18-02", "18-03",
    # the playbook run tracker (2026-10-20)
    "00-06", "00-12", "00-15", "SW-02", "SW-03", "SW-04", "SW-12", "SW-14",
    # the owner's playbook walkthrough (2026-10-21)
    "09-12",
]


@pytest.fixture(scope="module")
def template():
    workdir = tempfile.mkdtemp(prefix="playbook-ci-")
    try:
        yield workdir, run_tuples.make_template(workdir)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_one_session_per_playbook():
    specs = run_tuples.load_specs(spec_set="playbooks")
    assert [s["id"] for s in specs] == PLAYBOOKS
    for s in specs:
        assert not s.get("status"), f"{s['id']} is {s.get('status')}: every playbook runs"
        kinds = [c["kind"] for c in s["expect"]]
        assert kinds[:3] == ["playbook.started", "playbook.completed", "after_action.written"]
        assert len(kinds) > 3, f"{s['id']} checks only the run, not the playbook's own evidence"


def test_every_playbook_line_says_which_part_of_success_it_checks():
    """2026-11-12: each evidence line names, in plain words, the part of the
    playbook's success statement (docs/WHAT_SUCCESS_MEANS.md) it checks, and
    each playbook lists what its run does not check, with the reason."""
    for s in run_tuples.load_specs(spec_set="playbooks"):
        for c in s["expect"][3:]:
            assert c.get("says", "").strip(), f"{s['id']}: a line without 'says': {c}"
        assert isinstance(s.get("not_verified"), list), f"{s['id']}: no not_verified list"
        for n in s["not_verified"]:
            assert n.get("kind") in run_tuples.NOT_VERIFIED_KINDS, f"{s['id']}: {n}"
            assert n.get("says", "").strip() and n.get("why", "").strip(), f"{s['id']}: {n}"


def test_the_success_criteria_document_matches_the_specs():
    """docs/PLAYBOOK_SUCCESS_CRITERIA.md is written by the runner. With every
    line holding (test_playbook_runs_start_to_end checks that), it is exactly
    what the specs produce; a spec edited without re-running the runner fails
    here."""
    specs = run_tuples.load_specs(spec_set="playbooks")
    with open(run_tuples.CRITERIA_DOC, encoding="utf-8") as f:
        assert f.read() == run_tuples.criteria_text(specs), \
            "run: python synth/tuples/run_tuples.py --set playbooks"


@pytest.mark.parametrize("spec_id", PLAYBOOKS)
def test_playbook_runs_start_to_end(template, spec_id):
    workdir, tpl = template
    [spec] = run_tuples.load_specs([spec_id], spec_set="playbooks")
    result = run_tuples.run_one(spec, tpl, workdir)
    assert result["result"] == "PASS", json.dumps(result, indent=1)[:3000]


@pytest.mark.parametrize("spec_id", ROUND)
def test_round_tuple_passes_through_the_console(template, spec_id):
    workdir, tpl = template
    [spec] = run_tuples.load_specs([spec_id])
    result = run_tuples.run_one(spec, tpl, workdir)
    assert result["result"] == "PASS", json.dumps(result, indent=1)[:3000]
