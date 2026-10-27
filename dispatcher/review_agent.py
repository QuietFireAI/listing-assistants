"""review_agent - an observer that builds the case when an agent is stopped.

Owner decisions 2026-10-26: the review agent sits outside the group. It
reads, it reports, it never acts: it has no line to any agent, it is not on
the routes, it cannot restart anything and it writes nothing on the record.
In its container it has no network, the record and the state mounted
read-only, and one folder of its own for its case files, which the Desk
shows beside the stopped agent.

For each stop on the record (portal.agent_stopped) it writes one case file,
named by the stop's code, answering what Jeff asks first:

  1. The stop: when, what kind (a rule broken, or a crash), the code.
  2. What the agent was handling: the message delivered to it just before.
  3. What it tried: the message it attempted (route, intent, from), and
     whether that route is on identity/routes.json for this agent.
  4. Its normal behaviour: what it sent in the 30 days before, by route;
     whether it had ever used the attempted route.
  5. Its code: whether the agent's files match the attested install
     (boot-attestation.json, signed with the operator's key).
  6. A first reading: which of these points to a bug in the agent, a
     changed install, or something to investigate further.

It is a first reading for a person, not a verdict.

    python -m dispatcher.review_agent --state /state --out /reviews [--watch]
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import sys
import time
from typing import Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NORMAL_DAYS = 30
SHARED_FILES = ("dispatcher/portal.py", "dispatcher/portal_agent.py", "dispatcher/handoff_guard.py",
                "dispatcher/drawer_filing.py", "dispatcher/clock.py", "dispatcher/core.py")


def _record(state_dir: str, record_path: Optional[str] = None) -> list[dict]:
    from .core import AuditLog
    path = record_path or os.path.join(state_dir, "console-audit.jsonl")
    if not os.path.exists(path):
        return []
    return AuditLog.reader(path).read()


def agent_files(agent_id: str) -> list[str]:
    from .portal_agent import AGENT_CLASSES
    mod, _ = AGENT_CLASSES[agent_id]
    return [f"dispatcher/{mod}.py", *SHARED_FILES]


def code_check(state_dir: str, agent_id: str) -> dict:
    """The agent's files against the list of installed files the operator's
    key attested (boot-attestation.json in the state folder)."""
    path = os.path.join(state_dir, "boot-attestation.json")
    try:
        manifest = json.load(open(path, encoding="utf-8"))["manifest"]
    except (OSError, ValueError, KeyError):
        return {"checked": False, "reason": f"no readable attestation at {path}"}
    out = {"checked": True, "match": [], "differ": [], "not_attested": []}
    for rel in agent_files(agent_id):
        p = os.path.join(ROOT, rel)
        if rel not in manifest:
            out["not_attested"].append(rel)
            continue
        with open(p, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        (out["match"] if digest == manifest[rel] else out["differ"]).append(rel)
    out["ok"] = not out["differ"] and not out["not_attested"]
    return out


def _routes():
    from .core import Routes
    return Routes(os.path.join(ROOT, "identity", "routes.json"))


def allowed_routes(agent_id: str) -> list[dict]:
    data = json.load(open(os.path.join(ROOT, "identity", "routes.json"), encoding="utf-8"))
    return [{"intent": r["intent"], "to": r["receivers"]} for r in data["routes"]
            if agent_id in r["senders"] or "any" in r["senders"]]


def build_case(entries: list[dict], i: int, state_dir: str) -> dict:
    stop = entries[i]
    aid = str(stop.get("agent"))
    ts = float(stop.get("ts") or 0)
    case: dict = {
        "code": stop.get("code") or f"{'V' if stop.get('stopped_for') == 'violation' else 'C'}"
                                   f"{aid}-{str(stop.get('entry_hash'))[:6].upper()}",
        "agent": aid, "system_id": stop.get("system_id"),
        "stopped_at": datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).isoformat(timespec="seconds"),
        "stopped_for": stop.get("stopped_for"), "stop_entry": stop.get("entry_hash"),
    }
    before = entries[:i]
    viol = next((e for e in reversed(before) if e.get("kind") == "portal.violation"
                 and str(e.get("agent")) == aid), None)
    if stop.get("stopped_for") == "violation" and viol is not None:
        case["violation"] = viol.get("violation")
        case["detail"] = viol.get("detail")
        case["tried"] = {k: viol.get(k) for k in ("intent", "from_agent", "to_agent", "envelope_id")
                         if viol.get(k) is not None}
    else:
        case["reason"] = stop.get("reason")
    handling = next((e for e in reversed(before) if e.get("kind") == "envelope.persisted"
                     and str(e.get("to_agent")) == aid), None)
    if handling is not None:
        case["was_handling"] = {k: handling.get(k) for k in ("envelope_id", "from_agent", "intent",
                                                           "client_context_id")}
    routes = _routes()
    tried = case.get("tried") or {}
    if tried.get("intent"):
        case["tried_is_on_track"] = routes.tuple_legal(aid, tried["intent"], tried.get("to_agent", ""))
    case["allowed_routes"] = allowed_routes(aid)
    since = ts - NORMAL_DAYS * 86400
    sent: dict[str, int] = {}
    for e in before:
        if (e.get("kind") == "envelope.persisted" and str(e.get("from_agent")) == aid
                and float(e.get("ts") or 0) >= since):
            k = f"{e.get('intent')} -> {e.get('to_agent')}"
            sent[k] = sent.get(k, 0) + 1
    case["sent_in_last_30_days"] = dict(sorted(sent.items(), key=lambda kv: -kv[1]))
    if tried.get("intent"):
        case["tried_route_used_before"] = sent.get(f"{tried['intent']} -> {tried.get('to_agent')}", 0)
    case["code_check"] = code_check(state_dir, aid)
    case["first_reading"] = first_reading(case)
    return case


def first_reading(case: dict) -> list[str]:
    out = []
    cc = case.get("code_check") or {}
    if cc.get("checked") and not cc.get("ok"):
        out.append("The agent's files differ from the attested install "
                   f"({', '.join(cc.get('differ', []) + cc.get('not_attested', []))}). Treat it as "
                   "tampering until shown otherwise; do not restart it on these files.")
    elif cc.get("checked"):
        out.append("The agent's files match the attested install, so this is the code you signed.")
    v = case.get("violation")
    if v == "impersonation":
        out.append("It put another agent's number in the sender field. No agent's own code path "
                   "does that in the checked runs; look at the message it was handling and at its code.")
    elif v == "route_not_on_track":
        used = case.get("tried_route_used_before", 0)
        out.append("It tried a route it is not allowed to use"
                   + (", and has never used before: likely a rarely used path in its code, set off "
                      "by the message it was handling. Reproduce it with that message."
                      if not used else f" ({used} earlier time(s) in 30 days on the record)."))
    elif v in ("off_menu", "record_kind"):
        out.append("It asked for something it was never given. Its code should not contain that "
                   "request; find where it comes from before restarting it.")
    elif case.get("stopped_for") == "crash":
        out.append("It stopped answering; no rule was broken. Look at the message it was handling "
                   "for an input it cannot take (the reason is above).")
    out.append("This is a first reading for a person, not a verdict. Restart the agent on the Desk "
               "only after you are satisfied.")
    return out


def render(case: dict) -> str:
    lines = [f"# Case {case['code']}: agent {case['agent']} stopped",
             "", f"System {case.get('system_id')}, {case['stopped_at']}, for: {case.get('stopped_for')}"]
    if case.get("violation"):
        lines += [f"Rule broken: {case['violation']} - {case.get('detail')}"]
    if case.get("reason"):
        lines += [f"Reason: {case['reason']}"]
    if case.get("was_handling"):
        h = case["was_handling"]
        lines += ["", "## What it was handling",
                  f"{h.get('intent')} from {h.get('from_agent')}, client {h.get('client_context_id')} "
                  f"(message {h.get('envelope_id')})"]
    if case.get("tried"):
        t = case["tried"]
        lines += ["", "## What it tried",
                  f"{t.get('intent')} from '{t.get('from_agent')}' to {t.get('to_agent')}; "
                  f"on the track for this agent: {'yes' if case.get('tried_is_on_track') else 'no'}; "
                  f"times it sent this in 30 days: {case.get('tried_route_used_before', 0)}"]
    lines += ["", "## What it normally sends (30 days on the record)"]
    lines += [f"- {k}: {n}" for k, n in case["sent_in_last_30_days"].items()] or ["- nothing"]
    cc = case["code_check"]
    lines += ["", "## Its code",
              ("matches the attested install" if cc.get("ok") else
               f"DIFFERS: {cc.get('differ')} not attested: {cc.get('not_attested')}")
              if cc.get("checked") else f"not checked: {cc.get('reason')}"]
    lines += ["", "## First reading"] + [f"- {x}" for x in case["first_reading"]]
    return "\n".join(lines) + "\n"


def review(state_dir: str, out_dir: str, record_path: Optional[str] = None) -> list[str]:
    """Writes a case file for each stop on the record that has none yet;
    returns the codes written."""
    os.makedirs(out_dir, exist_ok=True)
    entries = _record(state_dir, record_path)
    written = []
    for i, e in enumerate(entries):
        if e.get("kind") != "portal.agent_stopped":
            continue
        case = build_case(entries, i, state_dir)
        path = os.path.join(out_dir, f"{case['code']}.json")
        if os.path.exists(path):
            continue
        from .private_file import write_private
        write_private(os.path.join(out_dir, f"{case['code']}.md"), render(case).encode("utf-8"))
        write_private(path, json.dumps(case, indent=1).encode("utf-8"))
        written.append(case["code"])
    return written


def read_case(out_dir: Optional[str], code: Optional[str]) -> Optional[str]:
    """The case file's text for the Desk, when there is one."""
    if not out_dir or not code:
        return None
    p = os.path.join(out_dir, f"{code}.md")
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def main(argv=None) -> int:
    import argparse
    if os.name != "nt":
        os.umask(0o077)
    ap = argparse.ArgumentParser(description="The review agent: builds the case for each stopped agent")
    ap.add_argument("--state", required=True, help="the dispatcher's state folder (read only)")
    ap.add_argument("--out", required=True, help="where case files go")
    ap.add_argument("--record", default=None, help="the record (default <state>/console-audit.jsonl)")
    ap.add_argument("--watch", action="store_true", help="keep looking, every 5 seconds")
    a = ap.parse_args(argv)
    while True:
        try:
            done = review(a.state, a.out, a.record)
            if done:
                print(json.dumps({"case_files": done}), flush=True)
        except Exception as e:          # a busy or half-written record: try again
            print(json.dumps({"review_error": f"{type(e).__name__}: {e}"}), flush=True)
            if not a.watch:
                return 1
        if not a.watch:
            return 0
        time.sleep(5)


if __name__ == "__main__":
    sys.exit(main())
