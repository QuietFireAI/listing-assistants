#!/usr/bin/env python3
"""build_site - the tuple procedures, as one linked website and a PDF binder.

Owner decisions 2026-10-26: every tuple gets its own ISO-style procedure
page (plain-English title, then a document code, LA-T-<number>, Rev 1),
readable by a broker, with a flowchart and its proof; the playbook manuals
follow and link both ways.

Sources (nothing on a page is typed twice):
  synth/tuples/specs/*.jsonl       the tuples themselves, as tested
  synth/tuples/TUPLE_MAP.json      category (accepted 2026-10-21; its risk tiers are not shown, owner 2026-10-27)
  synth/procedures/pages/*.json    the plain-language procedure for each tuple
  synth/procedures/agents.json     the agent pages (job, steps, today, the authorized user's part)
  synth/procedures/playbook_pages.json  the playbook pages (predefined steps)
  synth/procedures/overview.json   the whole picture (lifecycle stages)
  synth/procedures/evidence_playbooks.json  each playbook's recorded run
  identity/routes.json             what each agent receives and sends
  synth/procedures/evidence.json   what each tuple's own run put on the record
                                   (collect_evidence.py): the flowchart and proof
  identity/playbooks.json          playbook names
  NN-*/SKILL.md                    agent names
  tools/gen_diagrams.py PHRASE     plain words for each kind of message

    python synth/procedures/build_site.py            # writes site/procedures.html
    python synth/procedures/build_site.py --pdf      # and site/procedures.pdf
"""
import datetime
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SITE = os.path.join(HERE, "site")
sys.path.insert(0, os.path.join(ROOT, "synth", "tuples"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

ROUTINE = {"agent.status", "interaction.log", "record.request", "record.response"}
KIND_WORDS = {
    "envelope.persisted": "a message", "spoke.trace": "a decision the agent records",
    "escalation.raised": "an alert for the authorized user", "hitl.decision.authorized": "a signed decision, applied",
    "absolute_signal.hold": "a message held for signed release",
    "absolute_signal.released": "a held message released on a signature",
    "hold.clarification": "a message held because it is on no route", "reject": "a message refused",
    "dead.letter": "a message that could not be delivered", "playbook.started": "a playbook started",
    "playbook.completed": "a playbook finished", "after_action.written": "an after-action report written",
    "hold.queued": "an item waiting for the authorized user", "loop.suspended": "a repeating exchange stopped",
    "drawer.filed": "a record filed in the client's drawer", "config.unrecognized": "a setting nobody used",
    "sweep.error": "a daily check that failed", "decision.lead": "a lead scored",
    "human.notified": "a notice to the authorized user", "human.notify_failed": "a notice to the authorized user that failed to send",
    "integrity.violation": "a tampered or unsigned message refused",
    "playbook.waiting_released": "waiting playbook starts let in, in order",
    "harness.end": "the test's closing note on what the dispatcher did",
    "harness.halted_result": "the dispatcher answering a new message with \"halted\"",
    "harness.dropped": "the test's note of a message it dropped on purpose",
    "siding.hold": "a playbook step held on the siding behind another playbook",
    "siding.resume": "a held playbook step resumed",
    "escalation.realerted": "an alert sent a second time",
    "escalation.owner_paged": "the owner paged about an alert nobody marked done",
    "identity.reload_refused": "a settings reload refused while work is open",
    "identity.reloaded": "a settings reload carried out",
    "drawer.refused": "a filing refused by the client's drawer",
    "ack": "a message accepted",
    "desk.acknowledged": "an alert marked done",
    "playbook.start_waiting": "a playbook start held back",
    "clock.skew_hold": "time-driven work held because the clocks disagree",
    "playbook.conflict": "two playbooks in conflict on one client, held",
    "playbook.entry_waiting": "a playbook step waiting its turn",
    "playbook.sequenced": "playbook steps put in order",
    "playbook.entries_dropped": "playbook steps dropped",
    "drafting.mode": "the drafting mode in use",
    "playbook.integrity_violation": "a playbook table that failed its integrity check",
    "dedupe.hit": "a duplicate message caught and not delivered again",
    "manners.reinjection": "the conduct rules handed to an agent again",
}


# The manual speaks of "the authorized user", not "you" (owner 2026-10-27);
# these replace the repository diagrams' second-person phrases.
MANUAL_PHRASE = {
    "listing.change.authorized": "signed listing or price change",
    "clarification.request": "asks the authorized user",
    "config.update": "signed settings",
}
OUTCOME_WORDS = {
    "held for your signed release": "held for signed release",
    "sent after your release": "sent after release",
    "waiting for you": "waiting for the authorized user",
    "alert for you": "alert",
    "waiting for your decision": "waiting for a decision",
}


def build_ref() -> str:
    """The repository commit the manual was built from; "+changes" when the
    working tree differs from it."""
    import subprocess
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                             text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", ".", ":!synth/procedures/site"],
                               cwd=ROOT, capture_output=True, text=True).stdout.strip()
        return sha + ("+changes" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def code_for(tid: str) -> str:
    return f"LA-T-{tid}"


def agent_names() -> dict:
    out = {"00": "Dispatcher", "SWARM": "The whole team", "external": "The outside world",
           "human": "The authorized user", "clock": "The daily clock", "queue": "The queue"}
    for d in sorted(glob.glob(os.path.join(ROOT, "[0-2][0-9]-*"))):
        p = os.path.join(d, "SKILL.md")
        if os.path.isfile(p):
            m = re.search(r"^# Agent \d\d - (.+?)(?: Agent)?\s*$", open(p, encoding="utf-8").read(), re.M)
            out[os.path.basename(d)[:2]] = m.group(1) if m else os.path.basename(d)[3:]
    return out


def phrases() -> dict:
    from gen_diagrams import PHRASE
    return dict(PHRASE)


def describe_check(c: dict, names: dict, phrase: dict) -> str:
    kind = c.get("kind")
    what = KIND_WORDS.get(kind, kind)
    if kind == "envelope.persisted" and c.get("intent"):
        p = MANUAL_PHRASE.get(c["intent"]) or phrase.get(c["intent"])
        what = f"a message “{p}” ({c['intent']})" if p else f"a “{c['intent']}” message"
    elif kind == "spoke.trace" and c.get("agent"):
        what = f"a decision Agent {c['agent']} ({names.get(str(c['agent']), '')}) records"
    elif c.get("intent"):
        what += f" ({c['intent']})"
    if c.get("agent") and kind != "spoke.trace":
        what += f" by Agent {c['agent']}"
    if c.get("ctx"):
        what += f" for client {c['ctx']}"
    if c.get("contains"):
        what += f" that says “{c['contains']}”"
    if c.get("contains_all"):
        what += " that says " + " and ".join(f"“{x}”" for x in c["contains_all"])
    if c.get("absent"):
        return f"None: there must be no {what.removeprefix('a ').removeprefix('an ')}"
    if "count" in c:
        return f"Exactly {c['count']}: {what}"
    return f"At least one: {what}"


def chart_messages(flow: list, owner: str) -> list:
    """The messages a flowchart shows: the tuple's own clients only. Left
    out: routine bookkeeping (status, record keeping), the morning briefing,
    and the daily clock's tick to agents that play no part in this case.
    One clock run (every tick of one day) shows as one arrow, where the first tick was, to the
    owner agent when it was woken, else to the first agent in the case that
    was. Everything left out is still counted on the page."""
    def background(m):
        c = str(m.get("client") or "")
        return m["intent"] in ROUTINE or c.startswith("briefing") or c == "setup"
    own = [m for m in flow if not background(m) and m["intent"] != "clock.tick"]
    involved = {m["from"] for m in own} | {m["to"] for m in own}
    out, days = [], {}
    for m in flow:
        if background(m):
            continue
        if m["intent"] == "clock.tick":
            if m["to"] not in involved:
                continue
            day = re.search(r"\d{4}-\d\d-\d\d", str(m.get("client") or ""))
            day = day.group(0) if day else ""
            if day in days:
                if m["to"] == owner:
                    days[day]["to"] = owner
                continue
            m = {**m, "_day": day}
            days[day] = m
        out.append(m)
    return out


def fold_repeats(msgs: list) -> list:
    """A block of 1-3 messages repeated three or more times in a row, the
    same except for the client (25 settings, 25 questions), shows once with
    the count."""
    key = lambda m: (m["from"], m["to"], m["intent"], m.get("outcome"))
    out, i = [], 0
    while i < len(msgs):
        best = None
        for k in (1, 2, 3):
            n = 1
            while (i + (n + 1) * k <= len(msgs)
                   and [key(m) for m in msgs[i + n * k:i + (n + 1) * k]] == [key(m) for m in msgs[i:i + k]]):
                n += 1
            if n >= 3 and (best is None or n * k > best[0] * best[1]):
                best = (n, k)
        if best:
            n, k = best
            clients = [msgs[i + j * k].get("client") for j in range(n)]
            for j, m in enumerate(msgs[i:i + k]):
                out.append({**m, "times": n, "clients": f"{clients[0]} to {clients[-1]}"})
            i += n * k
        else:
            out.append(msgs[i])
            i += 1
    return out


def words_for(m: dict, phrase: dict) -> str:
    if m["intent"] in ("release.signed", "release.declined"):
        what = phrase.get(m.get("held_intent") or "", "the held message")
        return ("signed release of the held message: " if m["intent"] == "release.signed"
                else "signed decline of the held message: ") + what
    if m["intent"] == "decision.signed":
        d = str(m.get("decision") or "").lower()
        return "signed decision" + (f" ({d})" if d else "")
    if m["intent"] == "decision.required":
        return "holds it: continue or cancel"
    if m["intent"].startswith("alert:"):
        q = m["intent"][6:].removeprefix("escalation.").replace("_", " ")
        return f"raises an alert ({q})"
    if m["intent"] == "clock.tick":
        day = re.search(r"\d{4}-\d\d-\d\d", str(m.get("client") or ""))
        return "the daily clock runs" + (f" ({day.group(0)})" if day else "")
    if m.get("template") == "complaint_hold":
        return "holds every message to this client (complaint); sends nothing"
    words = MANUAL_PHRASE.get(m["intent"]) or phrase.get(m["intent"], m["intent"].replace(".", " "))
    if m.get("template"):
        words += f": {m['template'].replace('_', ' ')}"
    return words


def load_pages() -> dict:
    out = {}
    for p in sorted(glob.glob(os.path.join(HERE, "pages", "*.json"))):
        for page in json.load(open(p, encoding="utf-8")):
            if page["id"] in out:
                raise SystemExit(f"{page['id']} is written twice ({p})")
            out[page["id"]] = page
    return out


def build_data() -> dict:
    import run_tuples
    names, phrase = agent_names(), phrases()
    tmap = json.load(open(os.path.join(ROOT, "synth", "tuples", "TUPLE_MAP.json"), encoding="utf-8"))
    ev = json.load(open(os.path.join(HERE, "evidence.json"), encoding="utf-8"))
    pages = load_pages()
    pbs = json.load(open(os.path.join(ROOT, "identity", "playbooks.json"), encoding="utf-8"))["playbooks"]
    tuples = []
    for s in run_tuples.load_specs():
        tid = s["id"]
        status = s.get("status") or "IN FORCE"
        e = ev["tuples"].get(tid, {})
        page = pages.get(tid)
        flow = e.get("flow", [])
        shown = chart_messages(flow, s["agent"])
        main = fold_repeats(shown)
        tuples.append({
            "id": tid, "code": code_for(tid), "rev": (page or {}).get("rev", 1),
            "agent": s["agent"], "agent_name": names.get(s["agent"], s["agent"]),
            "status": status, "status_why": s.get("why", ""),
            "rule": s["tuple"], "category": tmap["tuples"].get(tid, {}).get("category"),
            "stand_in": s.get("route") == "stand-in", "route": s.get("route"),
            "spec": s.get("_file"), "page": page,
            "result": e.get("result"), "result_why": (e.get("why") or "")[:600],
            "checks": [{"text": describe_check(c, names, phrase), "ok": c.get("ok"), "found": c.get("found")}
                       for c in e.get("checks", [])],
            "flow": _flow_words(main, phrase, 40),
            "flow_more": max(0, len(main) - 40), "routine": len(flow) - len(shown),
            "queues": e.get("queues", []),
            "playbooks": [{"id": p, "name": pbs.get(p, {}).get("name", p)} for p in e.get("playbooks", [])],
        })
    agents = build_agents(tuples, pbs, names, phrase)
    playbooks = build_playbooks(tuples, pbs, names, phrase)
    return {
        "built": datetime.date.today().isoformat(), "evidence_date": ev.get("ran_on"),
        "build_ref": build_ref(),
        "categories": tmap["_categories"], "names": names,
        "tuples": tuples, "agents": agents, "playbooks": playbooks,
        "overview": build_overview(pbs),
        "routes_total": len(json.load(open(os.path.join(ROOT, "identity", "routes.json"), encoding="utf-8"))["routes"]),
    }


def _flow_words(main: list, phrase: dict, limit: int) -> list:
    return [{"from": m["from"], "to": m["to"], "intent": m["intent"],
             "words": words_for(m, phrase) + (f" (×{m['times']}, clients {m['clients']})" if m.get("times") else ""),
             "outcome": OUTCOME_WORDS.get(m.get("outcome"), m.get("outcome"))} for m in main[:limit]]


def build_agents(tuples: list, pbs: dict, names: dict, phrase: dict) -> list:
    """One page per agent (00-20): its job and steps from agents.json; what it
    receives and sends, from the closed track; its playbooks and procedures,
    computed."""
    src = json.load(open(os.path.join(HERE, "agents.json"), encoding="utf-8"))["agents"]
    routes = json.load(open(os.path.join(ROOT, "identity", "routes.json"), encoding="utf-8"))["routes"]
    word = lambda i: MANUAL_PHRASE.get(i) or phrase.get(i) or i.replace(".", " ")
    out = []
    for a in src:
        aid = a["id"]
        rin = [{"intent": r["intent"], "words": word(r["intent"]), "who": [x for x in r["senders"]]}
               for r in routes if aid in r["receivers"]]
        rout = [{"intent": r["intent"], "words": word(r["intent"]), "who": [x for x in r["receivers"]]}
                for r in routes if aid in r["senders"]]
        out.append({**a, "code": f"LA-A-{aid}", "rev": a.get("rev", 1),
                    "receives": sorted(rin, key=lambda r: r["intent"]),
                    "sends": sorted(rout, key=lambda r: r["intent"]),
                    "playbooks": [{"id": k, "name": v["name"]} for k, v in pbs.items() if aid in v.get("agents", [])],
                    "tuples": [t["id"] for t in tuples if t["agent"] == aid]})
    return out


def build_playbooks(tuples: list, pbs: dict, names: dict, phrase: dict) -> list:
    """One page per playbook: its predefined steps (playbook_pages.json), its
    recorded start-to-end run (evidence_playbooks.json, collect_evidence.py
    --set playbooks) and the procedures whose runs passed through it."""
    pages_path = os.path.join(HERE, "playbook_pages.json")
    pages = {p["id"]: p for p in json.load(open(pages_path, encoding="utf-8"))} if os.path.isfile(pages_path) else {}
    ev_path = os.path.join(HERE, "evidence_playbooks.json")
    ev = json.load(open(ev_path, encoding="utf-8"))["tuples"] if os.path.isfile(ev_path) else {}
    out = []
    for pid, pb in pbs.items():
        e = ev.get(pid, {})
        flow = e.get("flow", [])
        shown = chart_messages(flow, "")
        main = fold_repeats(shown)
        page = pages.get(pid)
        out.append({
            "id": pid, "code": f"LA-P-{pid[1:]}", "name": pb["name"], "rev": (page or {}).get("rev", 1),
            "page": page, "agents": pb.get("agents", []),
            "conflicts_with": pb.get("conflicts_with") or [],
            "ratified": pb.get("ratified", ""),
            "result": e.get("result"), "result_why": (e.get("why") or "")[:600],
            "checks": [{"text": describe_check(c, names, phrase), "ok": c.get("ok"), "found": c.get("found")}
                       for c in e.get("checks", [])],
            "flow": _flow_words(main, phrase, 60), "flow_more": max(0, len(main) - 60),
            "routine": len(flow) - len(shown),
            "ended": e.get("ended", []), "after_action": e.get("after_action", []),
            "tuples": [t["id"] for t in tuples if any(b["id"] == pid for b in t["playbooks"])],
        })
    return out


def build_overview(pbs: dict) -> dict:
    ov = json.load(open(os.path.join(HERE, "overview.json"), encoding="utf-8"))
    for st in ov["stages"]:
        seen = []
        for pid in st["playbooks"]:
            for a in pbs[pid].get("agents", []):
                if a not in seen and a != "00":
                    seen.append(a)
        st["agents"] = sorted(seen)
    ov.pop("_what", None)
    return ov


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    data = build_data()
    os.makedirs(SITE, exist_ok=True)
    tpl = open(os.path.join(HERE, "site_template.html"), encoding="utf-8").read()
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = tpl.replace("/*__DATA__*/null", payload)
    out = os.path.join(SITE, "procedures.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    written = sum(1 for t in data["tuples"] if t["page"])
    print(json.dumps({"site": out, "tuples": len(data["tuples"]), "procedures_written": written,
                      "bytes": len(html)}))
    if "--pdf" in argv:
        sys.path.insert(0, HERE)
        from build_pdf import build_pdf
        print(json.dumps({"pdf": build_pdf(out, os.path.join(SITE, "procedures.pdf"))}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
