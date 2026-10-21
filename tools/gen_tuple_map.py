#!/usr/bin/env python3
"""gen_tuple_map.py - docs/TUPLE_MAP.md, the 273 tuples sorted for a broker.

Owner request 2026-10-21: the tuples were only grouped by agent. This page
sorts them by what each one protects (seven categories) and how bad a failure
would be (three tiers), with each tuple's run status and the playbooks it can
fire in.

Sources, one per column:
  category, tier  synth/tuples/TUPLE_MAP.json (placed by hand, PROPOSED for
                  the owner's review; corrections are made there)
  rule, status    synth/tuples/specs/*.jsonl (the tuple text and its status)
  playbooks       identity/playbooks.json: the playbooks whose agent list
                  includes the tuple's agent (00 and swarm tuples: all). This
                  says where a tuple CAN fire, not that a playbook run fired it.

    python tools/gen_tuple_map.py           # write docs/TUPLE_MAP.md
    python tools/gen_tuple_map.py --check   # exit 1 if it is stale
"""
import argparse
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "TUPLE_MAP.md")
ORDER = "LCTAYRP"
TITLE = {"L": "Legal line", "C": "Consent and contact", "T": "Truth of the record",
         "A": "Your authority", "Y": "Choices that are yours", "R": "Time and reliability",
         "P": "People moments"}


def load():
    specs = []
    for f in sorted(glob.glob(os.path.join(ROOT, "synth", "tuples", "specs", "*.jsonl"))):
        for line in open(f, encoding="utf-8"):
            if line.strip():
                specs.append(json.loads(line))
    tmap = json.load(open(os.path.join(ROOT, "synth", "tuples", "TUPLE_MAP.json"), encoding="utf-8"))
    pbs = json.load(open(os.path.join(ROOT, "identity", "playbooks.json"), encoding="utf-8"))["playbooks"]
    return specs, tmap, pbs


def playbooks_for(agent, pbs):
    if agent in ("00", "SWARM"):
        return "all"
    hit = [p for p, v in pbs.items() if agent in v.get("agents", [])]
    return "all" if len(hit) == len(pbs) else (", ".join(hit) if hit else "none")


def rule_text(s):
    t = s["tuple"].strip()
    if t.startswith("(") and ")" in t:
        t = t[1:t.rindex(")")] + t[t.rindex(")") + 1:]
    return t.replace("|", "/").strip()


def build():
    specs, tmap, pbs = load()
    cats = tmap["tuples"]
    ids = [s["id"] for s in specs]
    missing = [i for i in ids if i not in cats]
    extra = [i for i in cats if i not in ids]
    if missing or extra:
        raise SystemExit(f"TUPLE_MAP.json out of step with the specs: missing {missing}, extra {extra}")
    rows = []
    for s in specs:
        c = cats[s["id"]]
        rows.append({"id": s["id"], "agent": s["agent"], "cat": c["category"], "tier": c["tier"],
                     "status": s.get("status", "RUNS"), "rule": rule_text(s),
                     "pb": playbooks_for(s["agent"], pbs)})
    live = [r for r in rows if r["status"] != "RETIRED"]
    out = ["# TUPLE_MAP.md - the tuples sorted by what they protect",
           "",
           "<!-- written by tools/gen_tuple_map.py from synth/tuples/TUPLE_MAP.json, the tuple specs "
           "and identity/playbooks.json; edit those, not this page -->",
           "",
           f"**{tmap['_status']}.**",
           "",
           "A tuple is one rule for one hard case: the situation, what the agent does, and what it "
           "must never do. There are " + str(len(rows)) + " (" + str(len(live)) + " in force, "
           + str(len(rows) - len(live)) + " retired). Each is sorted below by what it protects "
           "(category) and how bad a failure would be (tier).",
           "",
           "Columns: **status** is RUNS (it runs through the console and is checked), NOT REACHABLE "
           "(nothing in the product can produce the situation yet), NOT BUILT (the agent does not do "
           "it yet) or RETIRED. **Playbooks** are the playbooks whose agents include the tuple's "
           "agent, so where the rule can fire; it is not a record of a run firing it.",
           "",
           "## Categories", ""]
    for k in ORDER:
        out.append(f"- **{TITLE[k]}** - {tmap['_categories'][k].split(' - ', 1)[1]}")
    out += ["", "## Tiers", ""]
    for t in ("1", "2", "3"):
        out.append(f"- **Tier {t}**: {tmap['_tiers'][t]}")
    out += ["", "## Counts (tuples in force)", "",
            "| Category | Tier 1 | Tier 2 | Tier 3 | Total | Runs | Not reachable | Not built |",
            "|---|---|---|---|---|---|---|---|"]
    for k in ORDER:
        rs = [r for r in live if r["cat"] == k]
        out.append(f"| {TITLE[k]} | " + " | ".join(str(sum(1 for r in rs if r["tier"] == t)) for t in (1, 2, 3))
                   + f" | {len(rs)} | {sum(r['status'] == 'RUNS' for r in rs)}"
                   f" | {sum(r['status'] == 'NOT REACHABLE' for r in rs)}"
                   f" | {sum(r['status'] == 'NOT BUILT' for r in rs)} |")
    out.append(f"| **All** | " + " | ".join(str(sum(1 for r in live if r["tier"] == t)) for t in (1, 2, 3))
               + f" | {len(live)} | {sum(r['status'] == 'RUNS' for r in live)}"
               f" | {sum(r['status'] == 'NOT REACHABLE' for r in live)}"
               f" | {sum(r['status'] == 'NOT BUILT' for r in live)} |")
    for k in ORDER:
        out += ["", f"## {TITLE[k]}", "", tmap["_categories"][k].split(" - ", 1)[1].capitalize() + ".", ""]
        for t in (1, 2, 3):
            rs = [r for r in live if r["cat"] == k and r["tier"] == t]
            if not rs:
                continue
            out += [f"### Tier {t} ({len(rs)})", "", "| Tuple | Rule | Status | Playbooks |", "|---|---|---|---|"]
            for r in rs:
                out.append(f"| {r['id']} | {r['rule']} | {r['status']} | {r['pb']} |")
            out.append("")
    out += ["## Retired", "", "| Tuple | Rule |", "|---|---|"]
    for r in rows:
        if r["status"] == "RETIRED":
            out.append(f"| {r['id']} | {r['rule']} |")
    return "\n".join(out).rstrip() + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    text = build()
    cur = open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else None
    if a.check:
        print("up to date" if cur == text else "STALE: run python tools/gen_tuple_map.py")
        return 0 if cur == text else 1
    if cur != text:
        open(OUT, "w", encoding="utf-8").write(text)
        print("written")
    else:
        print("unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
