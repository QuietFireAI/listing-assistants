"""The agents' SKILL.md route tables against identity/routes.json, the file
the hub actually loads (2026-10-12 freshness review: Agent 10's table still
named Agent 03 as a requester after J5 removed that route; most tables were
missing clock.tick and config.update)."""
import glob
import json
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROUTES = json.load(open(os.path.join(ROOT, "identity", "routes.json"), encoding="utf-8"))["routes"]
WILDCARD = {"clarification.request", "integrity.violation"}   # any -> queue


def _table(text, start, end):
    sec = text[text.index(start):text.index(end)]
    return [[c.strip() for c in l.strip().strip("|").split("|")]
            for l in sec.splitlines() if l.startswith("|") and not l.startswith("|---")][1:]


def _names(cell):
    return sorted(cell.replace(" - SIGNED", "").split(" (audience")[0].split(", "))


def test_dispatcher_routing_table_is_routes_json():
    text = open(os.path.join(ROOT, "00-dispatcher", "SKILL.md"), encoding="utf-8").read()
    rows = _table(text, "### 4.2", "\n\nThis table is `identity/routes.json`")
    label = {"human": "human (broker)", "queue": "queues (section 2)"}
    want = [[f"`{r['intent']}`", sorted(label.get(x, x) for x in r["senders"]),
             sorted(label.get(x, x) for x in r["receivers"])] for r in ROUTES]
    got = [[r[0], _names(r[1]), _names(r[2])] for r in rows]
    assert got == want


@pytest.mark.parametrize("folder", sorted(os.path.basename(os.path.dirname(p)) for p in
                                          glob.glob(os.path.join(ROOT, "[01][0-9]-*", "SKILL.md"))
                                          + glob.glob(os.path.join(ROOT, "20-*", "SKILL.md"))
                                          if not p.split(os.sep)[-2].startswith("00")))
def test_agent_table_names_every_routed_intent_and_no_unrouted_one(folder):
    aid = folder[:2]
    text = open(os.path.join(ROOT, folder, "SKILL.md"), encoding="utf-8").read()
    rows = _table(text, "### 4.2", "### 4.3")
    doc_out = {i for r in rows if r[0] == "OUT" for i in re.findall(r"`([a-z_.*]+)`", r[-1])}
    doc_in = {i for r in rows if r[0] == "IN" for i in re.findall(r"`([a-z_.*]+)`", r[-1])}
    sends = {r["intent"] for r in ROUTES if aid in r["senders"] or "any" in r["senders"]}
    recvs = {r["intent"] for r in ROUTES if aid in r["receivers"] or "any" in r["receivers"]}
    escal = {i for i in doc_out if i.startswith("escalation.")}
    assert sends - WILDCARD - {"escalation.*"} <= doc_out, \
        f"routed sends missing from {folder} table: {sorted(sends - WILDCARD - {'escalation.*'} - doc_out)}"
    assert recvs <= doc_in, f"routed receives missing from {folder} table: {sorted(recvs - doc_in)}"
    assert doc_out - escal - {"in_reply_to"} <= sends, \
        f"{folder} table sends what no route allows: {sorted(doc_out - escal - sends)}"
    assert doc_in - {"in_reply_to"} <= recvs, \
        f"{folder} table receives what no route delivers: {sorted(doc_in - recvs)}"
