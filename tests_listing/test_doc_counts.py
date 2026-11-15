"""The test counts the docs state match the suite (2026-10-14). The counts
went stale more than once; now a wrong number fails CI instead of shipping.

One test runs on Windows only and one on Linux / macOS only (2026-10-14:
the state-folder permission check), so every system reports
(collected - 1) passed and 1 skipped."""
import importlib.util
import json
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

UNIX = ["README.md", "RELEASE_NOTES.md", "OPERATOR_TESTING_GUIDE.md", "docs/OPERATOR_TUNING_GUIDE.md",
        "docs/OPERATOR_TESTING_MANUAL.md", "docs/START_HERE.md", "docs/BROKER_DESK_TESTING_GUIDE.md"]


def collected():
    out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p",
                          "no:cacheprovider", "tests_listing/"], cwd=ROOT,
                         capture_output=True, text=True).stdout
    m = re.search(r"(\d+) tests? collected", out)
    assert m, out[-500:]
    return int(m.group(1))


def text(name):
    return open(os.path.join(ROOT, name), encoding="utf-8").read()


# the docs give the counts for the documented install (requirements.txt); some
# test modules skip themselves without these, so the count differs there (the
# pillars are part of the code since 2026-10-20, so they are not listed)
INSTALL = ["mcp", "cryptography"]


def test_the_documented_test_counts_match_the_suite():
    missing = [m for m in INSTALL if importlib.util.find_spec(m) is None]
    if missing:
        pytest.skip(f"counts are documented for the full install; missing {missing}")
    n = collected()
    found = {}
    for name in UNIX:
        found[name] = [int(x) for x in re.findall(r"(\d{3,}) passed, 1 skipped", text(name))]
        assert found[name], f"{name}: no 'N passed, 1 skipped' line"
    windows = {
        "QUICKSTART_WINDOWS.md": re.findall(r"Expected: `(\d+) passed, 1 skipped`",
                                            text("QUICKSTART_WINDOWS.md")),
        "docs/BROKER_DESK_TESTING_GUIDE.md": re.findall(r"`(\d+) passed, 1 skipped` on Windows",
                                                        text("docs/BROKER_DESK_TESTING_GUIDE.md")),
    }
    totals = {
        "SKILL.md": re.findall(r"a test suite \((\d+) tests", text("SKILL.md")),
        "docs/TUNING_MANUAL.md": re.findall(r"20 spokes, (\d+) tests", text("docs/TUNING_MANUAL.md")),
    }
    wrong = {k: v for k, v in found.items() if any(x != n - 1 for x in v)}
    wrong.update({k: v for k, v in windows.items() if not v or any(int(x) != n - 1 for x in v)})
    wrong.update({k: v for k, v in totals.items() if not v or any(int(x) != n for x in v)})
    assert not wrong, f"collected {n}: expected {n - 1} passed + 1 skipped on every system; found {wrong}"


def test_the_documented_route_counts_match_the_closed_track():
    """README.md said 52 routes and 146 lanes, and SKILL.md 52 routes, long after
    identity/routes.json held 56 (found 2026-11-15). A wrong number now fails."""
    routes = json.load(open(os.path.join(ROOT, "identity", "routes.json"), encoding="utf-8"))["routes"]
    intents = len({r["intent"] for r in routes})
    lanes = sum(len(r["senders"]) * len(r["receivers"]) for r in routes)
    readme = " ".join(text("README.md").split())
    assert (f"Only the {len(routes)} routes in `identity/routes.json` ({intents} intents, {lanes} "
            f"sender-intent-receiver lanes)") in readme
    assert f"{len(routes)} legal routes" in " ".join(text("SKILL.md").split())
