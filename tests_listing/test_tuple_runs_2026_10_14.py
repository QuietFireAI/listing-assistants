"""The tuple runs of 2026-10-14 (synth/tuples), kept running in CI.

1. Every tuple in agents 00-20 DECISIONS.md and in SWARM.md has exactly one
   spec, in order, with the same text. A tuple added, removed or reworded
   without its spec fails here.
2. The specs whose code was fixed during the runs are run through the real
   console session, the same way `python synth/tuples/run_tuples.py` runs
   them, and must PASS.

The full run (all 273 since 2026-10-21) is `python synth/tuples/run_tuples.py`; it writes
synth/tuples/REPORT.md. Two tuples there are VARIANCE on purpose until the
owner decides them (01-01, 04-03), so the full run is not a CI gate.
"""
import glob
import json
import os
import shutil
import sys
import tempfile

import pytest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "synth", "tuples"))

import run_tuples  # noqa: E402


def _tuples(path):
    text = open(path, encoding="utf-8").read()
    return [line[2:].strip() for line in text.splitlines() if line.startswith("- (")]


def test_every_tuple_has_one_spec_in_order():
    specs = run_tuples.load_specs()
    by_agent = {}
    for s in specs:
        by_agent.setdefault(s["agent"], []).append(s)
    expected = {}
    for d in sorted(glob.glob(os.path.join(ROOT, "[0-2][0-9]-*", "DECISIONS.md"))):
        expected[os.path.basename(os.path.dirname(d))[:2]] = _tuples(d)
    expected["SWARM"] = _tuples(os.path.join(ROOT, "SWARM.md"))
    assert sorted(by_agent) == sorted(expected)
    for agent, tuples in expected.items():
        got = [s["tuple"] for s in by_agent[agent]]
        assert got == tuples, f"agent {agent}: specs do not match its tuples"
    assert sum(len(t) for t in expected.values()) == len(specs) == 273


def test_every_spec_without_a_run_says_why():
    for s in run_tuples.load_specs():
        if s.get("status") in ("NOT BUILT", "NOT REACHABLE", "RETIRED"):
            assert s.get("why"), f"{s['id']} has status {s['status']} and no why"
        else:
            assert s.get("lines") and s.get("expect"), f"{s['id']} has nothing to run"


# the specs whose code changed during the 2026-10-14 runs (the last three
# by the plumbing pass the same day)
FIXED = ["03-05", "03-08", "05-10", "06-03", "06-06", "06-10", "07-11", "09-02",
         # 14-03 left: NOT REACHABLE since owner decision D-A6 (2026-10-28)
         "10-04", "12-09", "14-01", "15-06", "15-10", "17-03", "19-08",
         "07-03", "14-04", "18-06",
         # wired by the owner's decisions of 2026-10-14
         "06-05", "06-07", "06-11", "11-14", "13-01", "16-08", "16-10",
         "17-01", "17-04", "17-05", "17-07", "17-09", "20-01"]


@pytest.fixture(scope="module")
def template():
    workdir = tempfile.mkdtemp(prefix="tuple-ci-")
    try:
        yield workdir, run_tuples.make_template(workdir)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


@pytest.mark.parametrize("spec_id", FIXED)
def test_fixed_tuple_passes_through_the_console(template, spec_id):
    workdir, tpl = template
    spec = run_tuples.load_specs([spec_id])
    assert len(spec) == 1
    result = run_tuples.run_one(spec[0], tpl, workdir)
    assert result["result"] == "PASS", json.dumps(result, indent=1)[:3000]
