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


def flow(part):
    """Messages in order, with what became of each. An alert raised for the
    broker (escalation.raised) is drawn as a message from the agent handling
    a message at that moment to your queue: the entry does not name its
    agent, so the handler is the newest persisted message the dispatcher has
    not yet reported on (hub.reflection "persisted seq=N ...")."""
    msgs, by_id, open_seq = [], {}, []
    for e in part:
        k = e.get("kind")
        if k == "hub.reflection":
            mt = re.search(r"seq=(\d+)", str(e.get("thought", "")))
            if mt:
                open_seq[:] = [x for x in open_seq if x[0] != int(mt.group(1))]
            continue
        if k == "escalation.raised":
            frm = e.get("agent") or (open_seq[-1][1] if open_seq else "00")
            msgs.append({"from": frm, "to": "queue", "intent": "alert:" + str(e.get("queue", "")),
                         "client": e.get("client_context_id"), "outcome": "alert for you"})
            continue
        if k == "envelope.persisted":
            m = {"from": e.get("from_agent"), "to": e.get("to_agent"), "intent": e.get("intent"),
                 "client": e.get("client_context_id"), "outcome": None}
            msgs.append(m)
            by_id[e.get("envelope_id")] = m
            if isinstance(e.get("sequence"), int):
                open_seq.append((e["sequence"], e.get("to_agent")))
        elif k in OUTCOME_KINDS and e.get("envelope_id") in by_id:
            m = by_id[e["envelope_id"]]
            if m["outcome"] is None or k == "absolute_signal.released":
                m["outcome"] = OUTCOME_KINDS[k]
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
