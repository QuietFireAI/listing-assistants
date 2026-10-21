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
    "00-05", "00-06", "00-12", "00-15", "SW-01", "SW-02", "SW-03", "SW-04", "SW-12", "SW-14",
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
