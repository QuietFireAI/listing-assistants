#!/usr/bin/env python3
"""Run every pre-decided tuple through the product the way a broker would.

Each spec in synth/tuples/specs/*.jsonl is one tuple from an agent's
DECISIONS.md (or SWARM.md): the console session lines that reach it through
the entries the product actually takes, and what the audit log must show
afterwards. Every spec runs in its own fresh state folder, through
`python tools/console.py session`, with synth/tuples/setup.jsonl played first.

    python synth/tuples/run_tuples.py                 # every spec, writes synth/tuples/REPORT.md
    python synth/tuples/run_tuples.py 01-02 02-07     # just these tuples
    python synth/tuples/run_tuples.py --agent 01      # one agent's tuples
    python synth/tuples/run_tuples.py --show 01-02    # print the session file for one tuple, to run it yourself

A spec line:
  {"id": "01-02", "agent": "01", "tuple": "(prospect refuses consent, ...)",
   "route": "intake" | "stand-in" | "none",
   "lines": [<console session actions>], "expect": [<checks>],
   "status": optional "NOT BUILT" | "NOT REACHABLE" (with "why"), "note": "..."}

route "intake": every line is an entry the product takes from outside (an
inquiry, a vendor event, a client reply, a mention, a feed, a broker
authorization or setting, the daily clock, the broker's release / decline /
decide). route "stand-in": at least one line sends as an agent to stand in
for an upstream agent the product has no outside entry for; the report says
so. A check:
  {"kind": "escalation.raised", "ctx": "T1", "contains": "legal_line"}
  {"kind": "envelope.persisted", "intent": "clarification.request", "ctx": "T1", "contains": "..."}
  {"kind": "spoke.trace", "agent": "01", "ctx": "T1", "contains": "..."}
  ... any audit kind; "absent": true inverts it; "count": n requires exactly n.
"contains" (one string) and "contains_all" (a list) are matched
case-insensitively against the whole entry as JSON.

Results: PASS (every check held), VARIANCE (a check failed: the product does
something other than the tuple says), ERROR (the session itself failed), and
the spec's own status for tuples with no code path (NOT BUILT) or no outside
entry (NOT REACHABLE).
"""
from __future__ import annotations

import argparse
import concurrent.futures
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CONSOLE = os.path.join(ROOT, "tools", "console.py")
CONFIG = os.path.join(HERE, "config")
SETUP = os.path.join(HERE, "setup.jsonl")


def load_specs(selected=None, agent=None):
    specs = []
    for path in sorted(glob.glob(os.path.join(HERE, "specs", "*.jsonl"))):
        for n, line in enumerate(open(path, encoding="utf-8"), 1):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            s = json.loads(line)
            s["_file"] = f"{os.path.relpath(path, ROOT)}:{n}"
            if selected and s["id"] not in selected:
                continue
            if agent and s["agent"] != agent:
                continue
            specs.append(s)
    ids = [s["id"] for s in specs]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise SystemExit(f"duplicate spec ids: {sorted(dup)}")
    return specs


def session_lines(spec):
    """setup.jsonl first (all of it; "setup": false for none; "setup_skip":
    ["02"] leaves out the setup lines addressed to those agents), then the
    spec's own lines."""
    lines = []
    if spec.get("setup") is not False:
        skip = set(spec.get("setup_skip", []))
        for ln in open(SETUP, encoding="utf-8").read().splitlines():
            if ln.strip() and json.loads(ln).get("to") not in skip:
                lines.append(ln)
    return lines + [json.dumps(a) for a in spec.get("lines", [])]


def _env():
    env = dict(os.environ)
    env.pop("LISTINGASSISTANTS_STATE_DIR", None)
    return env


def make_template(workdir):
    tpl = os.path.join(workdir, "template")
    env = _env()
    env["LISTINGASSISTANTS_STATE_DIR"] = tpl
    r = subprocess.run([sys.executable, CONSOLE, "init"], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise SystemExit(f"console init failed:\n{r.stdout}\n{r.stderr}")
    return tpl


def ctx_index(entries):
    """envelope_id -> client_context_id, so a trace can be matched by ctx."""
    idx = {}
    for e in entries:
        if e.get("kind") == "envelope.persisted" and e.get("envelope_id"):
            idx[e["envelope_id"]] = e.get("client_context_id")
    return idx


def entry_ctx(e, idx):
    for key in ("client_context_id",):
        if e.get(key):
            return e[key]
    for key in ("envelope_id", "held_envelope_id"):
        if e.get(key) in idx:
            return idx[e[key]]
    return None


def check(entries, idx, c):
    hits = []
    for e in entries:
        if e.get("kind") != c["kind"]:
            continue
        if "intent" in c and e.get("intent") != c["intent"]:
            continue
        if "agent" in c and str(e.get("agent")) != str(c["agent"]):
            continue
        if "ctx" in c and entry_ctx(e, idx) != c["ctx"]:
            continue
        text = json.dumps(e).lower()
        if "contains" in c and c["contains"].lower() not in text:
            continue
        if "contains_all" in c and not all(x.lower() in text for x in c["contains_all"]):
            continue
        hits.append(e)
    if c.get("absent"):
        return not hits, len(hits)
    if "count" in c:
        return len(hits) == c["count"], len(hits)
    return bool(hits), len(hits)


def run_one(spec, template, workdir):
    if spec.get("status") in ("NOT BUILT", "NOT REACHABLE") and not spec.get("lines"):
        return {"id": spec["id"], "result": spec["status"], "why": spec.get("why", "")}
    state = os.path.join(workdir, spec["id"])
    shutil.copytree(template, state)
    script = os.path.join(workdir, spec["id"] + ".jsonl")
    with open(script, "w", encoding="utf-8") as f:
        f.write("\n".join(session_lines(spec)) + "\n")
    env = _env()
    env["LISTINGASSISTANTS_STATE_DIR"] = state
    r = subprocess.run([sys.executable, CONSOLE, "session", script, "--config-dir", CONFIG],
                       cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
    last = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
    try:
        summary = json.loads(last)
    except ValueError:
        summary = {}
    if r.returncode != 0 or not summary.get("session_complete"):
        return {"id": spec["id"], "result": "ERROR",
                "why": (r.stdout[-1500:] + r.stderr[-1500:]).strip()}
    entries = [json.loads(ln) for ln in open(os.path.join(state, "console-audit.jsonl"), encoding="utf-8")]
    idx = ctx_index(entries)
    failed = []
    for c in spec.get("expect", []):
        ok, n = check(entries, idx, c)
        if not ok:
            failed.append({"check": c, "found": n})
    errors = summary.get("errors", 0)
    if failed:
        return {"id": spec["id"], "result": "VARIANCE", "failed": failed, "errors": errors}
    return {"id": spec["id"], "result": spec.get("status") or "PASS", "errors": errors,
            "why": spec.get("why", "")}


def write_report(specs, results, path):
    by = {r["id"]: r for r in results}
    order = ["PASS", "VARIANCE", "ERROR", "NOT REACHABLE", "NOT BUILT"]
    counts = {k: sum(1 for r in results if r["result"] == k) for k in order}
    out = ["# Tuple runs", "",
           "Written by `python synth/tuples/run_tuples.py`. Each tuple ran in its own fresh",
           "state through `tools/console.py session`, after `synth/tuples/setup.jsonl`.", "",
           "| Result | Tuples |", "|---|---|"]
    out += [f"| {k} | {counts[k]} |" for k in order if counts[k]]
    out += ["", "| Tuple | Agent | Route | Result | Tuple text | Detail |", "|---|---|---|---|---|---|"]
    for s in specs:
        r = by[s["id"]]
        detail = r.get("why") or s.get("note", "")
        if r["result"] == "VARIANCE":
            detail = "; ".join(f"expected {json.dumps(f['check'])} (found {f['found']})" for f in r["failed"])
            if s.get("note"):
                detail += f" | {s['note']}"
        if r["result"] == "ERROR":
            detail = "session failed: " + r["why"].replace("\n", " ")[-300:]
        text = s["tuple"].replace("|", "/")
        out.append(f"| {s['id']} | {s['agent']} | {s.get('route', '-')} | {r['result']} | {text} | "
                   f"{detail.replace('|', '/')} |")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    return counts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--agent", default=None)
    ap.add_argument("--show", default=None, metavar="ID")
    ap.add_argument("--jobs", type=int, default=max(1, min(4, os.cpu_count() or 1)))
    ap.add_argument("--report", default=os.path.join(HERE, "REPORT.md"))
    args = ap.parse_args(argv)
    if args.show:
        spec = load_specs([args.show])
        if not spec:
            raise SystemExit(f"no spec {args.show}")
        print("\n".join(session_lines(spec[0])))
        return 0
    specs = load_specs(args.ids or None, args.agent)
    if not specs:
        raise SystemExit("no specs selected")
    workdir = tempfile.mkdtemp(prefix="tuple-runs-")
    try:
        template = make_template(workdir)
        with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
            results = list(pool.map(lambda s: run_one(s, template, workdir), specs))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    for r in results:
        line = f"{r['id']:8} {r['result']}"
        if r["result"] == "VARIANCE":
            line += "  " + "; ".join(json.dumps(f["check"]) + f" found {f['found']}" for f in r["failed"])
        if r["result"] == "ERROR":
            line += "  " + r["why"].replace("\n", " ")[-400:]
        print(line)
    report = args.report if not (args.ids or args.agent) else None
    if report:
        counts = write_report(specs, results, report)
        print(json.dumps({"report": os.path.relpath(report, ROOT), **counts}))
    bad = [r for r in results if r["result"] in ("VARIANCE", "ERROR")]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
