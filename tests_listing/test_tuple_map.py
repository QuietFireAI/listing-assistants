"""docs/TUPLE_MAP.md (owner request 2026-10-21): every tuple sorted by what it
protects and how bad a failure would be. A new tuple without a place, a place
for a tuple that no longer exists, or a stale page fails CI."""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import gen_tuple_map  # noqa: E402


def test_every_tuple_has_one_place_and_nothing_else_does():
    specs, tmap, _ = gen_tuple_map.load()
    ids = [s["id"] for s in specs]
    assert len(ids) == len(set(ids))
    assert sorted(tmap["tuples"]) == sorted(ids)
    for i, c in tmap["tuples"].items():
        assert c["category"] in gen_tuple_map.ORDER, i
        assert c["tier"] in (1, 2, 3), i
    assert set(tmap["_categories"]) == set(gen_tuple_map.ORDER)


def test_the_page_is_current():
    p = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "gen_tuple_map.py"), "--check"],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stdout


def test_the_counts_on_the_page_add_up():
    text = open(gen_tuple_map.OUT, encoding="utf-8").read()
    specs, tmap, _ = gen_tuple_map.load()
    live = [s for s in specs if s.get("status") != "RETIRED"]
    total_row = next(line for line in text.splitlines() if line.startswith("| **All** |"))
    cells = [c.strip() for c in total_row.strip("|").split("|")]
    t1, t2, t3, total, runs = (int(x) for x in cells[1:6])
    assert t1 + t2 + t3 == total == len(live)
    assert runs == sum(1 for s in live if s.get("status", "RUNS") == "RUNS")
