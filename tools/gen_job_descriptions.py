#!/usr/bin/env python3
"""gen_job_descriptions.py - rebuilds the agent entries of
docs/JOB_DESCRIPTIONS.md from the sources in THIS repository.

Owner decision 2026-10-11: listing-assistants is the single source of truth
(the listing-agents-blueprint generator is no longer used). Each entry is
built from:
  - the agent's SKILL.md: title, **Type:**, description, section 1 (role)
    and section 2 (job components)
  - identity/routes.json: the intents it sends and receives
  - the agent's DECISIONS.md: the number of predeliberated tuples
    (lines beginning "- (")

Everything above the first "## Agent 00" heading (header, notice, roster)
is kept as written.

  python tools/gen_job_descriptions.py           # rewrite the file
  python tools/gen_job_descriptions.py --check   # exit 1 if it is stale
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(ROOT, "docs", "JOB_DESCRIPTIONS.md")


def _section(text, number):
    m = re.search(rf"^## {number}\.[^\n]*\n(.*?)(?=^## \d+\.|\Z)", text, re.S | re.M)
    return m.group(1).strip() if m else ""


def entry(folder, routes):
    aid = folder[:2]
    skill = open(os.path.join(ROOT, folder, "SKILL.md"), encoding="utf-8").read()
    title = re.search(r"^# Agent \d\d - (.+)$", skill, re.M).group(1).strip()
    typ = re.search(r"^\*\*Type:\*\* (.+)$", skill, re.M).group(1).strip()
    desc = re.search(r'^description: "(.*)"$', skill, re.M).group(1)
    role = _section(skill, 1)
    jobs = _section(skill, 2)
    sends = sorted({r["intent"] for r in routes if aid in r["senders"]})
    recvs = sorted({r["intent"] for r in routes if aid in r["receivers"]})
    tuples = sum(1 for l in open(os.path.join(ROOT, folder, "DECISIONS.md"), encoding="utf-8")
                 if l.startswith("- ("))
    return (f"## Agent {aid} - {title}\n\n"
            f"**Type:** {typ}\n"
            f"**Summary:** {desc}\n"
            f"**Sends:** {', '.join(sends) or '(none routed)'}\n"
            f"**Receives:** {', '.join(recvs) or '(none routed)'}\n"
            f"**Predeliberated tuples:** {tuples} (see {folder}/DECISIONS.md)\n\n"
            f"{role}\n\n### Job components\n{jobs}\n")


def build():
    routes = json.load(open(os.path.join(ROOT, "identity", "routes.json")))["routes"]
    folders = sorted(d for d in os.listdir(ROOT) if re.match(r"^\d\d-", d)
                     and os.path.isfile(os.path.join(ROOT, d, "SKILL.md")))
    current = open(DOC, encoding="utf-8").read()
    head = current[:current.index("## Agent 00")]
    return head + "\n".join(entry(f, routes) for f in folders)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    new = build()
    old = open(DOC, encoding="utf-8").read()
    if a.check:
        print("up to date" if new == old else "STALE: run python tools/gen_job_descriptions.py")
        return 0 if new == old else 1
    open(DOC, "w", encoding="utf-8").write(new)
    print("written" if new != old else "unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
