#!/usr/bin/env python3
"""gen_diagrams.py - the pictures in the docs, generated so they cannot drift.

Two kinds of diagram, both drawn from the swarm itself rather than by hand:

1. One per agent: NN-*/README.md (GitHub shows it under the agent's folder).
   Who the agent hears from and who it talks to, read from
   identity/routes.json, in plain words, plus the playbooks it took part in.

2. One per playbook, inside docs/PLAY-BY-PLAY.md: the messages a real run
   of that playbook's end-to-end test sent through the hub, in order.
   The script runs each test function in-process with a spy on the audit
   log, so every arrow is a message the hub actually persisted. Holds,
   signed releases and questions to the broker are drawn as they happened
   in that run.

Usage:
    python tools/gen_diagrams.py           # write the files
    python tools/gen_diagrams.py --check   # exit 1 if any file differs

tests_listing/test_docs_diagrams.py runs --check, so a change to the routes
or to a playbook's behavior that is not reflected in the pictures fails CI.
"""
from __future__ import annotations

import argparse
import glob
import importlib
import json
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests_listing"))

PLAY_BY_PLAY = os.path.join(ROOT, "docs", "PLAY-BY-PLAY.md")

# Plain words for every intent on the track. A route added without a
# phrase here fails the generator (no silent fallback to the code name).
PHRASE = {
    "lead.captured": "hands over a new lead",
    "lead.nurture": "passes a not-ready-yet lead for follow-up",
    "lead.rescored": "sends back a lead whose interest changed",
    "content.review": "sends a draft for fair-housing review",
    "content.verdict": "returns the review: approved or flagged",
    "asset.release": "releases the approved listing copy",
    "listing.data": "shares the listing details",
    "listing.change.authorized": "your signed listing or price change",
    "showing.request": "asks for a showing",
    "doc.request": "asks for a document",
    "doc.status": "reports where a document stands",
    "vendor.request": "asks to book a vendor",
    "deliverable.release": "passes on the vendor's finished work",
    "data.request": "asks for market data",
    "data.package": "delivers the market data",
    "client.message.request": "asks for a message to the client",
    "client.message.send": "sends the client a message",
    "deadline.alert": "warns that a deadline is near",
    "calendar.event": "puts it on the calendar",
    "date.trigger": "flags a date to act on",
    "prospect.opportunity": "brings a possible prospect",
    "lead.signal": "passes on a lead spotted on social media",
    "lead.inbound": "a new inquiry comes in",
    "report.package": "delivers a report",
    "briefing.request": "asks for its part of the morning briefing",
    "client.message.not_sent": "reports a touch that did not go out",
    "interaction.log": "logs it in the CRM",
    "record.request": "looks up the CRM record",
    "record.response": "returns the CRM record",
    "status.update": "reports the listing's status",
    "transaction.closed": "reports the deal closed",
    "vendor.schedule": "books the vendor",
    "campaign.publish": "publishes the marketing",
    "escalation.*": "flags it for you",
    "clarification.request": "asks you",
    "integrity.violation": "reports an integrity problem",
    "config.update": "your signed settings",
    "lead.reply": "passes on the client's reply",
    "behavioral.signal": "reports how a lead engaged with marketing",
    "status.request": "asks for the listing's status",
    "status.response": "answers with the listing's status",
    "showing.no_show": "reports a no-show",
    "showing.feedback_response": "passes on showing feedback",
    "document.submission": "passes on a document the client sent",
    "vendor.event": "the vendor reports in",
    "vendor.cancellation_notice": "reports a vendor cancellation",
    "compliance.notice": "sends it for a compliance check",
    "client.reply": "the client replies",
    "agent.status": "reports what it is waiting on",
    "platform.metrics": "marketing platform numbers come in",
    "discovery.feed": "public records come in",
    "social.mention": "a social media mention comes in",
    "clock.tick": "the daily clock runs",
}

# Left off the playbook pictures (they happen at nearly every step and
# would bury the story); each picture says so underneath.
ROUTINE = {"interaction.log", "agent.status", "record.request",
           "record.response"}

# Playbook -> the end-to-end test whose run the picture shows.
PLAYBOOK_TESTS = {
    "P01": ("test_playbooks_e2e", "test_p01_new_listing_onboarding_all_three_phases"),
    "P02": ("test_playbooks_e2e_all", "test_p02_price_adjustment"),
    "P03": ("test_playbooks_e2e_all", "test_p03_under_contract_transition"),
    "P04": ("test_playbooks_e2e_all", "test_p04_open_house_cycle"),
    "P05": ("test_playbooks_e2e_all", "test_p05_expired_withdrawn_winddown"),
    "P06": ("test_playbooks_e2e_all", "test_p06_new_buyer_onboarding"),
    "P07": ("test_playbooks_e2e_all", "test_p07_tour_day_coordination"),
    "P08": ("test_playbooks_e2e_all", "test_p08_offer_to_acceptance"),
    "P09": ("test_playbooks_e2e_all", "test_p09_contract_to_close_deadline_engine"),
    "P10": ("test_playbooks_e2e_all", "test_p10_close_postclose_handoff"),
    "P11": ("test_playbooks_e2e_all", "test_p11_speed_to_lead_hot_path"),
    "P12": ("test_playbooks_e2e_all", "test_p12_geographic_farm_campaign"),
    "P13": ("test_playbooks_e2e_all", "test_p13_referral_anniversary_cycle"),
    "P14": ("test_playbooks_e2e_all", "test_p14_complaint_response"),
    "P15": ("test_playbooks_e2e_all", "test_p15_cma_prep"),
    "P16": ("test_playbooks_e2e_all", "test_p16_morning_operations"),
    "P17": ("test_playbooks_e2e_all", "test_p17_end_of_day_books"),
    "P18": ("test_playbooks_e2e_all", "test_p18_seller_weekly_report"),
    "P19": ("test_playbooks_e2e_all", "test_p19_property_access_custody"),
    "P20": ("test_playbooks_e2e_all", "test_p20_vacant_property_watch_cycle"),
    "P21": ("test_playbooks_e2e_all", "test_p21_lead_rescore_cycle"),
    "P22": ("test_playbooks_e2e_all", "test_p22_buyer_feedback_match_refresh"),
    "P23": ("test_playbooks_e2e_all", "test_p23_price_review_evidence"),
    "P24": ("test_playbooks_e2e_all", "test_p24_prospecting_outreach_probation"),
}

# What a held outbound message is called in the "Held" note.
HELD = {"vendor.schedule": "the vendor booking",
        "campaign.publish": "the marketing"}

BROKER = "You (broker)"
OUTSIDE = "Outside world"
CLOCK = "Daily clock"


def phrase(intent: str) -> str:
    if intent in PHRASE:
        return PHRASE[intent]
    if intent.startswith("escalation."):
        return f"flags it for you ({intent.split('.', 1)[1].replace('_', ' ')})"
    raise KeyError(f"no plain-words phrase for intent {intent!r}: add one to PHRASE")


def agent_dirs():
    out = {}
    for d in sorted(glob.glob(os.path.join(ROOT, "[0-2][0-9]-*"))):
        aid = os.path.basename(d)[:2]
        head = open(os.path.join(d, "SKILL.md"), encoding="utf-8").read()
        m = re.search(r"^# Agent \d\d - (.+?)(?: Agent)?\s*$", head, re.M)
        name = m.group(1) if m else os.path.basename(d)[3:].replace("-", " ").title()
        desc = re.search(r'^description:\s*"?(.+?)"?\s*$', head, re.M)
        first = desc.group(1) if desc else ""
        out[aid] = {"dir": d, "name": name, "summary": first}
    return out


def label(aid, agents):
    if aid == "human" or aid == "queue":
        return BROKER
    if aid == "external":
        return OUTSIDE
    if aid == "clock":
        return CLOCK
    return f"{aid} {agents[aid]['name']}"


def clean(text: str, n: int = 70) -> str:
    """Make free text safe inside a mermaid label, and short."""
    t = re.sub(r"\s+", " ", str(text)).strip()
    t = t.replace(";", ",").replace("#", "no.").replace('"', "'")
    t = t.replace("<", "(").replace(">", ")").replace(":", " -")
    t = t.replace("&", "and")
    return t if len(t) <= n else t[: n - 3].rstrip() + "..."


# --------------------------------------------------------------- capture
def capture(module: str, test: str) -> list[dict]:
    """Run one test function in-process; return what the hub recorded."""
    from dispatcher import core
    events: list[dict] = []
    orig = core.AuditLog.append

    def spy(self, kind, record, *a, **k):
        if isinstance(record, dict):
            events.append({"kind": kind,
                           "from": record.get("from_agent"),
                           "to": record.get("to_agent"),
                           "intent": record.get("intent"),
                           "payload": record.get("payload") or {}})
        return orig(self, kind, record, *a, **k)

    core.AuditLog.append = spy
    try:
        fn = getattr(importlib.import_module(module), test)
        with tempfile.TemporaryDirectory() as tmp:
            fn(tmp)
    finally:
        core.AuditLog.append = orig
    return events


def sender_of(intent: str, routes) -> str:
    """The one sender of an outbound intent (holds record no sender)."""
    s = {x for r in routes if r["intent"] == intent for x in r["senders"]}
    assert len(s) == 1, (intent, s)
    return s.pop()


def playbook_steps(events, routes):
    """Turn a run into ordered steps: ('msg', frm, to, text) or
    ('note', who, text). Routine traffic is dropped; repeats folded."""
    steps = []
    for e in events:
        k, intent = e["kind"], e["intent"]
        if k == "envelope.persisted":
            if intent in ROUTINE:
                continue
            frm, to = e["from"], e["to"]
            if to == "queue" and intent == "clarification.request":
                why = e["payload"].get("reason")
                text = "asks you" + (f" - {clean(why, 60)}" if why else "")
            elif to == "queue":
                text = phrase(intent)
            else:
                text = phrase(intent)
            steps.append(["msg", frm, to, text, 1])
        elif k == "absolute_signal.hold":
            who = sender_of(intent, routes)
            steps.append(["note", who, f"Held: {HELD.get(intent, phrase(intent))} waits for your signed release"])
        elif k == "disclosure.authorized":
            steps.append(["msg", "human", sender_of(intent, routes),
                          "you sign the release", 1])
    folded = []
    for s in steps:
        if folded and s[0] == "msg" and folded[-1][0] == "msg" \
                and folded[-1][1:4] == s[1:4]:
            folded[-1][4] += 1
        else:
            folded.append(s)
    return folded


def sequence_diagram(steps, agents) -> str:
    order = []
    for s in steps:
        for who in ((s[1], s[2]) if s[0] == "msg" else (s[1],)):
            key = "human" if who in ("human", "queue") else who
            if key not in order:
                order.append(key)
    # broker first, outside world last, agents in order of appearance
    order = ([o for o in order if o == "human"]
             + [o for o in order if o not in ("human", "external")]
             + [o for o in order if o == "external"])
    alias = {o: ("B" if o == "human" else "X" if o == "external"
                 else "K" if o == "clock" else f"A{o}") for o in order}
    lines = ["```mermaid", "sequenceDiagram", "    autonumber"]
    for o in order:
        kw = "actor" if o == "human" else "participant"
        lines.append(f"    {kw} {alias[o]} as {clean(label(o, agents))}")
    for s in steps:
        if s[0] == "msg":
            _, frm, to, text, n = s
            frm = "human" if frm == "queue" else frm
            to = "human" if to == "queue" else to
            times = f" (x{n})" if n > 1 else ""
            lines.append(f"    {alias[frm]}->>{alias[to]}: {clean(text, 90)}{times}")
        else:
            _, who, text = s
            lines.append(f"    Note over {alias[who]}: {clean(text, 90)}")
    lines.append("```")
    return "\n".join(lines)


# --------------------------------------------------------------- agents
def agent_diagram(aid, agents, routes) -> str:
    ins, outs = {}, {}

    def add(table, who, intent):
        table.setdefault(who, [])
        p = phrase(intent)
        if p not in table[who]:
            table[who].append(p)

    for r in routes:
        intent = r["intent"]
        if intent == "config.update":
            if aid != "00":
                add(ins, "human", intent)
            continue
        senders = [s for s in r["senders"]]
        receivers = r["receivers"]
        if aid in senders or ("any" in senders and aid != "00"):
            for rc in receivers:
                if rc != aid:
                    add(outs, rc, intent)
        if aid in receivers:
            many = [s for s in senders if s.isdigit()]
            if len(many) >= 8:
                add(ins, "many", intent)
                for s in senders:
                    if not s.isdigit():
                        add(ins, s, intent)
            else:
                for s in senders:
                    add(ins, s, intent)
    me = f"A{aid}"

    def node(who, side):
        """Senders sit on the left, receivers on the right: the same agent
        can appear on both sides, so no arrow has to double back."""
        if who in ("human", "queue"):
            return f"{side}B", f'{side}B(["{BROKER}"])', "you"
        if who == "external":
            return f"{side}X", f'{side}X[/"{OUTSIDE}"/]', "out"
        if who == "clock":
            return f"{side}K", f'{side}K(["{CLOCK}"])', "out"
        if who == "many":
            return f"{side}M", f'{side}M["Most of the other agents"]', None
        return f"{side}{who}", f'{side}{who}["{clean(label(who, agents))}"]', None

    lines = ["```mermaid", "flowchart LR"]
    styled = {"you": [], "out": []}
    if ins:
        lines.append('    subgraph IN["Hears from"]')
        lines.append("        direction TB")
        for who in ins:
            nid, decl, cls = node(who, "I")
            lines.append(f"        {decl}")
            if cls:
                styled[cls].append(nid)
        lines.append("    end")
    lines.append(f'    {me}(("{clean(label(aid, agents))}"))')
    if outs:
        lines.append('    subgraph OUT["Talks to"]')
        lines.append("        direction TB")
        for who in outs:
            nid, decl, cls = node(who, "O")
            lines.append(f"        {decl}")
            if cls:
                styled[cls].append(nid)
        lines.append("    end")
    for who, ps in ins.items():
        nid = node(who, "I")[0]
        lines.append(f'    {nid} -- "{"<br/>".join(clean(x) for x in ps)}" --> {me}')
    for who, ps in outs.items():
        nid = node(who, "O")[0]
        lines.append(f'    {me} -- "{"<br/>".join(clean(x) for x in ps)}" --> {nid}')
    lines += ["    classDef me fill:#1f6feb,stroke:#1f6feb,color:#ffffff",
              "    classDef you fill:#f2cc60,stroke:#9a6700,color:#1f2328",
              "    classDef out fill:#d0d7de,stroke:#57606a,color:#1f2328",
              f"    class {me} me"]
    for cls, ids in styled.items():
        if ids:
            lines.append(f"    class {','.join(ids)} {cls}")
    lines.append("```")
    return "\n".join(lines)


from doc_diagrams import BLOCKS, HUB_FLOW  # noqa: E402



def slug(heading: str) -> str:
    s = heading.strip().lower()
    s = re.sub(r"[^\w\- ]", "", s)
    return s.replace(" ", "-")


def agent_readme(aid, agents, routes, appears, headings) -> str:
    a = agents[aid]
    folder = os.path.basename(a["dir"])
    parts = [f"# Agent {aid} - {a['name']}", "",
             a["summary"], "",
             "> **Words used here.** Lane, closed track, playbook, tuple and the "
             "other technical words are explained in plain language in "
             "[GLOSSARY.md](../docs/GLOSSARY.md).", "",
             "## Who it works with", "",
             "Left: who sends this agent messages. Right: who it sends messages "
             "to. The blue circle is the agent; the yellow box is you. Every "
             "arrow is a lane on the closed track (`identity/routes.json`): "
             "the hub refuses any message that is not on one.", "",
             agent_diagram(aid, agents, routes), ""]
    if aid == "00":
        parts = parts[:6] + [
            "## What it does with every message", "",
            "The hub has no lanes of its own: every message between agents, "
            "and every message to you or to the outside world, passes through "
            "it. These are its checks, in the order `dispatcher/hub.py` runs "
            "them. Yellow: waits for you. Red: stopped. Green: done.", "",
            HUB_FLOW, ""]
    pbs = appears.get(aid, [])
    parts += ["## Where it shows up", ""]
    if pbs:
        parts.append("Playbooks whose test run includes this agent "
                     "(pictures in [PLAY-BY-PLAY](../docs/PLAY-BY-PLAY.md)):")
        parts.append("")
        for pb in pbs:
            h = headings.get(pb)
            parts.append(f"- [{h}](../docs/PLAY-BY-PLAY.md#{slug(h)})" if h else f"- {pb}")
    else:
        parts.append("None of the playbook test runs pictured in "
                     "[PLAY-BY-PLAY](../docs/PLAY-BY-PLAY.md) include this agent "
                     "outside routine logging.")
    parts += ["", "## The rules it follows", "",
              f"- [SKILL.md](SKILL.md) - its job, its limits, and when it stops and asks you",
              f"- [DECISIONS.md](DECISIONS.md) - the decisions made ahead of time for it", "",
              "*Generated by `tools/gen_diagrams.py` from `identity/routes.json` and the "
              "playbook test runs; edit the generator, not this file.*", ""]
    return "\n".join(parts)


# --------------------------------------------------------------- main
def build():
    routes = json.load(open(os.path.join(ROOT, "identity", "routes.json"), encoding="utf-8"))["routes"]
    for r in routes:
        phrase(r["intent"])                      # every intent has words
    agents = agent_dirs()

    text = open(PLAY_BY_PLAY, encoding="utf-8").read()
    headings = {}
    for m in re.finditer(r"^### (P\d\d) (.+)$", text, re.M):
        headings[m.group(1)] = f"{m.group(1)} {m.group(2)}"

    appears: dict[str, list[str]] = {}
    blocks = {}
    for pb, (mod, test) in PLAYBOOK_TESTS.items():
        steps = playbook_steps(capture(mod, test), routes)
        for s in steps:
            for who in ((s[1], s[2]) if s[0] == "msg" else (s[1],)):
                if who and who.isdigit():
                    appears.setdefault(who, [])
                    if pb not in appears[who]:
                        appears[who].append(pb)
        blocks[pb] = "\n".join([
            f"<!-- diagram:{pb} - generated by tools/gen_diagrams.py from `{test}`; edit the generator, not this block -->",
            sequence_diagram(steps, agents),
            "",
            f"*One recorded run of this playbook's test (`{test}`), read top to "
            "bottom. Left out to keep it readable: each agent logging the step "
            "in the CRM (14), telling the calendar (18) what it is waiting on, "
            "and CRM look-ups.*",
            f"<!-- /diagram:{pb} -->"])

    files = {}
    for aid in agents:
        files[os.path.join(agents[aid]["dir"], "README.md")] = \
            agent_readme(aid, agents, routes, appears, headings)

    new = re.sub(r"<!-- diagram:P\d\d .*?<!-- /diagram:P\d\d -->\n\n", "",
                 text, flags=re.S)
    for pb, block in blocks.items():
        h = re.search(rf"^### {pb} .+$\n", new, re.M)
        assert h, f"PLAY-BY-PLAY has no heading for {pb}"
        new = new[:h.end()] + block + "\n\n" + new[h.end():]
    files[PLAY_BY_PLAY] = new

    # hand-drawn pictures (tools/doc_diagrams.py), placed after an anchor line
    by_file: dict[str, list] = {}
    for name, (rel, anchor, mermaid, caption) in BLOCKS.items():
        by_file.setdefault(os.path.join(ROOT, rel), []).append((name, anchor, mermaid, caption))
    for path, blocks_here in by_file.items():
        body = files.get(path) or open(path, encoding="utf-8").read()
        body = re.sub(r"\n<!-- diagram:([a-z0-9-]+) - drawn[^\n]*-->\n.*?<!-- /diagram:\1 -->\n",
                      "", body, flags=re.S)
        for name, anchor, mermaid, caption in blocks_here:
            m = re.search(anchor + r"\n", body, re.M)
            assert m, f"{os.path.relpath(path, ROOT)}: no line matches {anchor!r} for {name}"
            block = (f"<!-- diagram:{name} - drawn in tools/doc_diagrams.py; edit it there, not here -->\n"
                     f"{mermaid}\n" + (f"\n{caption}\n" if caption else "")
                     + f"<!-- /diagram:{name} -->\n")
            body = body[:m.end()] + "\n" + block + body[m.end():]
        files[path] = body
    return files


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    files = build()
    stale = [p for p, body in files.items()
             if not os.path.exists(p) or open(p, encoding="utf-8").read() != body]
    if args.check:
        for p in stale:
            print(f"stale diagram: {os.path.relpath(p, ROOT)}")
        print(f"gen_diagrams --check: {len(files)} files, {len(stale)} stale")
        return 1 if stale else 0
    for p in stale:
        open(p, "w", encoding="utf-8").write(files[p])
        print(f"wrote {os.path.relpath(p, ROOT)}")
    print(f"gen_diagrams: {len(files)} files, {len(stale)} written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
