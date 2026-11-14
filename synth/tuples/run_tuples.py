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
    python synth/tuples/run_tuples.py --set playbooks # every playbook, start to end, writes synth/playbooks/REPORT.md

A spec line:
  {"id": "01-02", "agent": "01", "tuple": "(prospect refuses consent, ...)",
   "route": "intake" | "stand-in" | "none",
   "lines": [<console session actions>], "expect": [<checks>],
   "status": optional "NOT BUILT" | "NOT REACHABLE" (with "why"), "note": "..."}

route "fault": a {"do": "fault"} line injects one failure no product entry
can produce (synth/tuples/fault_harness.py; the harness's own observations
are read as entries of kind "harness.*"). route "intake": every line is an
entry the product takes from outside (an
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
the spec's own status for tuples with no code path (NOT BUILT), no outside
entry (NOT REACHABLE), or retired by the owner (RETIRED).

A rejected envelope is never persisted, so a "reject" entry carries no
context: match it with "contains", not "ctx".
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
HARNESS = os.path.join(HERE, "fault_harness.py")
CONFIG = os.path.join(HERE, "config")
SETUP = os.path.join(HERE, "setup.jsonl")


# the playbook runs (2026-10-20): one session per playbook, from its start to
# its end, in synth/playbooks/specs/, reported to synth/playbooks/REPORT.md
SPEC_SETS = {"tuples": (os.path.join(HERE, "specs"), os.path.join(HERE, "REPORT.md")),
             "playbooks": (os.path.join(ROOT, "synth", "playbooks", "specs"),
                           os.path.join(ROOT, "synth", "playbooks", "REPORT.md"))}


def load_specs(selected=None, agent=None, spec_set="tuples"):
    specs = []
    for path in sorted(glob.glob(os.path.join(SPEC_SETS[spec_set][0], "*.jsonl"))):
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


# The agents' clock for a synthetic run (owner decision D-A4, 2026-10-28;
# finding T): Agents 03 and 11 use this computer's clock when a message
# carries no time of day, so an unpinned run gave different flows, and since
# D-A4 different results, depending on when it ran. Every run is pinned to
# noon on the specs' day unless LISTING_CLOCK_NOW is already set.
CLOCK_NOW = "2026-10-15T12:00:00"


def _env():
    env = dict(os.environ)
    env.pop("LISTINGASSISTANTS_STATE_DIR", None)
    env.setdefault("LISTING_CLOCK_NOW", CLOCK_NOW)
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
    if spec.get("status") in ("NOT BUILT", "NOT REACHABLE", "RETIRED") and not spec.get("lines"):
        return {"id": spec["id"], "result": spec["status"], "why": spec.get("why", "")}
    state = os.path.join(workdir, spec["id"])
    shutil.copytree(template, state)
    script = os.path.join(workdir, spec["id"] + ".jsonl")
    with open(script, "w", encoding="utf-8") as f:
        f.write("\n".join(session_lines(spec)) + "\n")
    env = _env()
    env["LISTINGASSISTANTS_STATE_DIR"] = state
    # a spec with a fault line runs through the fault harness (same build,
    # same apply_action, one injected failure); every other spec through the
    # console, exactly as a broker runs it
    faulted = any(a.get("do") == "fault" for a in spec.get("lines", []))
    cmd = ([sys.executable, HARNESS, script, "--config-dir", CONFIG] if faulted else
           [sys.executable, CONSOLE, "session", script, "--config-dir", CONFIG])
    r = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
    last = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
    try:
        summary = json.loads(last)
    except ValueError:
        summary = {}
    if r.returncode != 0 or not summary.get("session_complete"):
        return {"id": spec["id"], "result": "ERROR",
                "why": (r.stdout[-1500:] + r.stderr[-1500:]).strip()}
    entries = [json.loads(ln) for ln in open(os.path.join(state, "console-audit.jsonl"), encoding="utf-8")]
    hpath = os.path.join(state, "harness.jsonl")
    if os.path.exists(hpath):   # the harness's own observations, kind "harness.*"
        entries += [json.loads(ln) for ln in open(hpath, encoding="utf-8")]
    idx = ctx_index(entries)
    failed, checks = [], []
    for c in spec.get("expect", []):
        ok, n = check(entries, idx, c)
        checks.append({"check": c, "ok": ok, "found": n})
        if not ok:
            failed.append({"check": c, "found": n})
    errors = summary.get("errors", 0)
    if failed:
        return {"id": spec["id"], "result": "VARIANCE", "failed": failed, "errors": errors,
                "checks": checks}
    return {"id": spec["id"], "result": spec.get("status") or "PASS", "errors": errors,
            "why": spec.get("why", ""), "checks": checks}


def write_report(specs, results, path):
    by = {r["id"]: r for r in results}
    order = ["PASS", "VARIANCE", "ERROR", "NOT REACHABLE", "NOT BUILT", "RETIRED"]
    counts = {k: sum(1 for r in results if r["result"] == k) for k in order}
    if os.path.abspath(path) == os.path.abspath(SPEC_SETS["playbooks"][1]):
        out = ["# Playbook runs", "",
               "Written by `python synth/tuples/run_tuples.py --set playbooks`. Each playbook ran from its",
               "start to its end in its own fresh state through `tools/console.py session`, after",
               "`synth/tuples/setup.jsonl`; each must start its run, end it as completed, write its",
               "after-action report and show the playbook's own evidence. The table is",
               "`identity/playbooks.json` (PROPOSED until the owner ratifies it).", "",
               "| Result | Playbooks |", "|---|---|"]
    else:
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


# --- playbook success criteria (2026-11-12) --------------------------------
# Every evidence line of a playbook spec carries "says": the part of that
# playbook's success statement (docs/WHAT_SUCCESS_MEANS.md) the line checks,
# in plain words. "not_verified" lists what the run does not check, each with
# its reason and a kind:
#   outside    it needs a system that is not connected (an MLS, an ad platform)
#   not_shown  the success statement says it and this run does not show it
#   gate       a human gate from docs/PLAYBOOKS.md this run does not reach
# docs/PLAYBOOK_SUCCESS_CRITERIA.md is written from the specs and the run.
CRITERIA_DOC = os.path.join(ROOT, "docs", "PLAYBOOK_SUCCESS_CRITERIA.md")
NOT_VERIFIED_KINDS = ("outside", "not_shown", "gate")
RUN_SAYS = {"playbook.started": "The run starts on the playbook's trigger",
            "playbook.completed": "The run ends as completed",
            "after_action.written": "An after-action report is written for the run"}


def says_of(c):
    return c.get("says") or RUN_SAYS.get(c.get("kind"), "")


def how_of(c):
    """One evidence line in words: what must (or must not) be on the record."""
    what = c["kind"] if c["kind"] != "envelope.persisted" else f"a {c.get('intent', 'message')} message"
    bits = []
    if c.get("ctx"):
        bits.append(f"for {c['ctx']}")
    need = ([c["contains"]] if "contains" in c else []) + list(c.get("contains_all", []))
    if need:
        bits.append("containing " + " and ".join(f"`{x}`" for x in need))
    tail = (" " + ", ".join(bits)) if bits else ""
    if c.get("absent"):
        return f"no {what[2:] if what.startswith('a ') else what}{tail}"
    if "count" in c:
        return f"exactly {c['count']} x {what}{tail}"
    return f"{what}{tail}"


def playbook_status(spec, result=None):
    """VERIFIED: every line holds and nothing in the success statement is left
    unshown (parts that need an unconnected outside system are named).
    PARTLY VERIFIED: every line holds; parts of the statement are not shown.
    FAILED: a line does not hold."""
    if result is not None and result.get("result") != "PASS":
        return "FAILED"
    unshown = [n for n in spec.get("not_verified", []) if n.get("kind") == "not_shown"]
    return "PARTLY VERIFIED" if unshown else "VERIFIED"


def criteria_text(specs, results=None):
    by = {r["id"]: r for r in (results or [])}
    try:
        table = json.load(open(os.path.join(ROOT, "identity", "playbooks.json"), encoding="utf-8"))["playbooks"]
    except (OSError, ValueError, KeyError):
        table = {}
    out = ["# Playbook success criteria: what each run checks, and what it does not", "",
           "Written by `python synth/tuples/run_tuples.py --set playbooks`; do not edit by hand.",
           "Edit `synth/playbooks/specs/PLAYBOOKS.jsonl` and run it again.", "",
           "Each playbook runs once, from its trigger to its end, in a fresh state, through",
           "`tools/console.py session` with synthetic data. Every line under \"Checked\" is a",
           "part of that playbook's success statement in [WHAT_SUCCESS_MEANS.md](WHAT_SUCCESS_MEANS.md),",
           "tied to what must be on the audit record afterwards. The same lines run in the test",
           "suite (`tests_listing/test_playbook_runs.py`), so a line that stops holding fails CI.", "",
           "- **VERIFIED**: every checked line holds, and every part of the success statement is",
           "  either checked or needs an outside system that is not connected (named below).",
           "- **PARTLY VERIFIED**: every checked line holds; parts of the success statement are",
           "  not shown by this run (named below).",
           "- **FAILED**: a checked line does not hold.", "",
           "One run is one path. Human gates this run does not reach are listed; the tuple runs",
           "([synth/tuples/REPORT.md](../synth/tuples/REPORT.md)) exercise the gates one at a time.",
           "Nothing here was run against a live MLS, a live ad platform or real clients.", "",
           "| Playbook | Owner's sign-off of the run table | Status | Lines checked | Not shown | Needs an outside system | Gates not reached |",
           "|---|---|---|---|---|---|---|"]
    body = []
    for s in specs:
        r = by.get(s["id"])
        nv = s.get("not_verified", [])
        n = {k: sum(1 for x in nv if x.get("kind") == k) for k in NOT_VERIFIED_KINDS}
        rat = "RATIFIED" if str((table.get(s["id"]) or {}).get("ratified", "")).startswith("RATIFIED") else "PROPOSED"
        status = playbook_status(s, r)
        name = s["tuple"].split(":")[0]
        out.append(f"| {name} | {rat} | {status} | {len(s.get('expect', []))} | {n['not_shown']} | "
                   f"{n['outside']} | {n['gate']} |")
        body += ["", f"## {name}", "", f"**{status}.**" + (f" {s['note'][0].upper() + s['note'][1:]}." if s.get("note") else ""), "",
                 "### Checked", "", "| What success means | What must be on the record | Result |", "|---|---|---|"]
        checks = (r or {}).get("checks") or [{"check": c, "ok": True} for c in s.get("expect", [])]
        for ch in checks:
            c = ch["check"]
            res = "holds" if ch["ok"] else f"DOES NOT HOLD (found {ch.get('found')})"
            body.append(f"| {says_of(c)} | {how_of(c).replace('|', '/')} | {res} |")
        for kind, title in (("not_shown", "Not shown by this run"),
                            ("outside", "Needs an outside system that is not connected"),
                            ("gate", "Human gates this run does not reach")):
            items = [x for x in nv if x.get("kind") == kind]
            if items:
                body += ["", f"### {title}", ""]
                body += [f"- {x['says']}. {x['why']}" for x in items]
    return "\n".join(out + body) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--agent", default=None)
    ap.add_argument("--show", default=None, metavar="ID")
    ap.add_argument("--jobs", type=int, default=max(1, min(4, os.cpu_count() or 1)))
    ap.add_argument("--set", dest="spec_set", choices=sorted(SPEC_SETS), default="tuples",
                    help="tuples (default) or playbooks: one session per playbook, start to end")
    ap.add_argument("--report", default=None)
    args = ap.parse_args(argv)
    if args.report is None:
        args.report = SPEC_SETS[args.spec_set][1]
    if args.show:
        spec = load_specs([args.show], spec_set=args.spec_set)
        if not spec:
            raise SystemExit(f"no spec {args.show}")
        print("\n".join(session_lines(spec[0])))
        return 0
    specs = load_specs(args.ids or None, args.agent, args.spec_set)
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
        if args.spec_set == "playbooks":
            with open(CRITERIA_DOC, "w", encoding="utf-8") as f:
                f.write(criteria_text(specs, results))
            st = [playbook_status(sp, r) for sp, r in zip(specs, results)]
            print(json.dumps({"criteria": os.path.relpath(CRITERIA_DOC, ROOT),
                              **{k: st.count(k) for k in ("VERIFIED", "PARTLY VERIFIED", "FAILED")}}))
    bad = [r for r in results if r["result"] in ("VARIANCE", "ERROR")]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
