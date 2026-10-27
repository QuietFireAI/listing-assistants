#!/usr/bin/env python3
"""collect_evidence - runs every tuple once and keeps what the record shows,
for the tuple procedure pages (owner decision 2026-10-26: every tuple gets
its own ISO-style page, with its proof).

For each tuple that runs, from that run's own record (after the starting
settings in synth/tuples/setup.jsonl):
  - the result (PASS / VARIANCE / ERROR) and the date it ran
  - each check the tuple makes, with what was found
  - the messages, in order: who sent what to whom, and what became of each
    (delivered, held for you, refused, could not be delivered)
  - what landed in your queues, and which playbooks started or ended

    python synth/procedures/collect_evidence.py           # writes synth/procedures/evidence.json
    python synth/procedures/collect_evidence.py 03-01 05-02
"""
import datetime
import json
import os
import re
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "synth", "tuples"))
import run_tuples  # noqa: E402

OUT = os.path.join(HERE, "evidence.json")
# raised by the dispatcher itself (run tracker, hub, HITL protocol), not by an agent
DISPATCHER_RAISED = {"escalation.queue_full", "escalation.system_error", "escalation.confidence_underflow"}
OUTCOME_KINDS = {
    "ack": "delivered", "reject": "refused", "dead.letter": "could not be delivered",
    "absolute_signal.hold": "held for your signed release", "hold.queued": "waiting for you",
    "hold.clarification": "held: not on any route", "loop.suspended": "stopped: repeating",
    "dedupe.hit": "duplicate, not delivered again", "absolute_signal.released": "released on your signature",
}


def own_part(entries):
    """The entries after the starting settings: the setup lines are signed
    settings with client 'setup'; the tuple's own part starts after the last
    entry that names one of them."""
    setup_ids = {e["envelope_id"] for e in entries
                 if e.get("kind") == "envelope.persisted" and e.get("client_context_id") == "setup"
                 and e.get("from_agent") == "human"}
    last = -1
    for i, e in enumerate(entries):
        if e.get("envelope_id") in setup_ids:
            last = i
    return entries[last + 1:]


def _template(e):
    """The message's template name, when it carries one (which client
    message, which vendor order): the flowchart shows it in plain words."""
    p = e.get("payload")
    t = p.get("template") if isinstance(p, dict) else None
    if t == "__p14_complaint_hold__":
        return "complaint_hold"
    return t if isinstance(t, str) and not t.startswith("__") and "." not in t else None


def flow(part):
    """Messages in order, with what became of each. Also drawn as messages:
    an alert raised for the broker (escalation.raised), a hold that waits
    for the broker's continue or cancel (human.notified on decision_required)
    and the broker's signed decision on it (hitl.decision.authorized).
    An alert entry does not always name its agent; then it is the agent
    handling a message at that moment: the newest recorded message to an
    agent that the dispatcher has not yet reported delivered (hub.reflection
    "persisted seq=N ..." comes after the handler returns), else the agent
    whose decision record (spoke.trace) came last, leaving out the record
    keepers 14 and 18. Alerts the dispatcher itself raises are drawn from 00."""
    msgs, by_id, last_actor, released, handling = [], {}, "00", [], []
    for e in part:
        k = e.get("kind")
        if k == "spoke.trace":
            if e.get("agent") not in ("14", "18"):
                last_actor = e.get("agent") or last_actor
            continue
        if k == "hub.reflection":
            mt = re.search(r"seq=(\d+)", str(e.get("thought", "")))
            if mt:
                handling[:] = [h for h in handling if h[0] != int(mt.group(1))]
            continue
        if k == "escalation.raised":
            agents = [h[1] for h in handling if re.fullmatch(r"\d\d", str(h[1]))]
            frm = e.get("agent") or (agents[-1] if agents else last_actor)
            if e.get("queue") in DISPATCHER_RAISED:
                frm = "00"
            msgs.append({"from": frm, "to": "queue", "intent": "alert:" + str(e.get("queue", "")),
                         "client": e.get("client_context_id"), "outcome": "alert for you"})
            continue
        if k == "human.notified" and e.get("queue") == "decision_required":
            msgs.append({"from": e.get("agent") or "00", "to": "queue", "intent": "decision.required",
                         "client": e.get("client_context_id"), "outcome": "waiting for your decision"})
            continue
        if k == "human.notified" and isinstance(e.get("absolute_signal"), dict):
            # an outbound message held at the gate for your signed release;
            # the gate holds it before it is recorded as sent, so this
            # notice is where it shows
            msgs.append({"from": e.get("from_agent"), "to": e.get("to_agent"), "intent": e.get("intent"),
                         "client": e.get("client_context_id"), "outcome": "held for your signed release",
                         "template": _template(e)})
            continue
        if k in ("disclosure.authorized", "disclosure.declined"):
            ok = k == "disclosure.authorized"
            msgs.append({"from": "human", "to": "00", "intent": "release.signed" if ok else "release.declined",
                         "client": e.get("client_context_id"), "outcome": None,
                         "held_intent": e.get("intent")})
            if ok:
                released.append(e.get("intent"))
            continue
        if k == "hitl.decision.authorized":
            msgs.append({"from": "human", "to": e.get("agent") or "00", "intent": "decision.signed",
                         "client": e.get("client_context_id"), "outcome": None,
                         "decision": e.get("decision")})
            continue
        if k == "envelope.persisted":
            m = {"from": e.get("from_agent"), "to": e.get("to_agent"), "intent": e.get("intent"),
                 "client": e.get("client_context_id"), "outcome": None, "template": _template(e)}
            if isinstance(e.get("sequence"), int):
                handling.append((e["sequence"], e.get("to_agent")))
            if e.get("intent") in released:
                released.remove(e.get("intent"))
                m["outcome"] = "sent after your release"
            msgs.append(m)
            by_id[e.get("envelope_id")] = m
        elif k in OUTCOME_KINDS and e.get("envelope_id") in by_id:
            m = by_id[e["envelope_id"]]
            if m["outcome"] is None:
                m["outcome"] = OUTCOME_KINDS[k]
        elif k == "reject" and not e.get("from_agent"):
            # a refused message is never recorded as sent; the refusal names
            # the route ("tuple illegal: 06 -> record.request -> 14")
            mt = re.search(r"(\w+) -> ([\w.]+) -> (\w+)", str(e.get("reason", "")))
            if mt:
                msgs.append({"from": mt.group(1), "to": mt.group(3), "intent": mt.group(2),
                             "client": e.get("client_context_id"), "outcome": "refused"})
        elif k in ("reject", "hold.clarification") and e.get("from_agent"):
            msgs.append({"from": e.get("from_agent"), "to": e.get("to_agent"), "intent": e.get("intent"),
                         "client": e.get("client_context_id"), "outcome": OUTCOME_KINDS[k]})
    return msgs


def evidence(spec, result, entries):
    part = own_part(entries) if entries else []
    idx = run_tuples.ctx_index(entries)
    checks = []
    for c in spec.get("expect", []):
        ok, n = run_tuples.check(entries, idx, c) if entries else (False, 0)
        checks.append({**c, "ok": ok, "found": n})
    queues = [{"queue": e.get("queue"), "client": e.get("client_context_id")}
              for e in part if e.get("kind") == "escalation.raised"]
    playbooks = sorted({e.get("playbook") for e in entries
                        if e.get("kind") in ("playbook.started", "playbook.completed") and e.get("playbook")})
    return {"result": result.get("result"), "why": result.get("why", ""),
            "checks": checks, "flow": flow(part), "queues": queues, "playbooks": playbooks,
            "entries": len(part)}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    specs = run_tuples.load_specs(argv or None)
    wd = tempfile.mkdtemp(prefix="proc-evidence-")
    tpl = run_tuples.make_template(wd)
    today = datetime.date.today().isoformat()

    def one(spec):
        if spec.get("status") in ("NOT BUILT", "NOT REACHABLE", "RETIRED") and not spec.get("lines"):
            return spec["id"], {"result": spec["status"], "why": spec.get("why", ""), "checks": [],
                                "flow": [], "queues": [], "playbooks": [], "entries": 0}
        r = run_tuples.run_one(spec, tpl, wd)
        path = os.path.join(wd, spec["id"], "console-audit.jsonl")
        entries = [json.loads(ln) for ln in open(path, encoding="utf-8")] if os.path.exists(path) else []
        hpath = os.path.join(wd, spec["id"], "harness.jsonl")
        if os.path.exists(hpath):   # the fault harness's own observations, as run_tuples reads them
            entries += [json.loads(ln) for ln in open(hpath, encoding="utf-8")]
        return spec["id"], evidence(spec, r, entries)

    with ThreadPoolExecutor(8) as ex:
        results = dict(ex.map(one, specs))
    old = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) and argv else {"tuples": {}}
    old["tuples"].update(results)
    doc = {"_what": "what each tuple's own run put on the record; written by collect_evidence.py",
           "ran_on": today, "tuples": dict(sorted(old["tuples"].items()))}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
    from collections import Counter
    print(json.dumps({"written": OUT, "tuples": len(results),
                      "results": Counter(v["result"] for v in results.values())}))


if __name__ == "__main__":
    main()
