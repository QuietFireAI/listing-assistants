#!/usr/bin/env python3
"""desk.py - the Broker Desk: one page that shows the broker what the swarm
is doing and lets them act on what is waiting for them.

    python tools/desk.py                 # your desk (console-state/), http://127.0.0.1:8765
    python tools/desk.py --showcase      # a separate showcase desk that replays the
                                         # ten operator scenes on synthetic data
    python tools/desk.py --lan           # reachable from a tablet on your network;
                                         # prints a link with an access code

What the page shows (every number is read from the swarm itself: the hub's
holds and queues, the HITL manager's paused threads, and the audit log):
  - Needs you: messages held for your release (the exact content and who
    it goes to), paused threads waiting for continue or cancel, and the
    items in your queues (legal line, hot leads, complaints, questions,
    integrity violations, undeliverable messages).
  - Listings: one card per listing, with the steps the record shows done.
  - Leads: each captured lead; a hot lead with its five-minute clock.
  - Team: the twenty agents - working, waiting on you, idle, or a problem.
  - Proof: the audit chain check, how many outbound messages went to a
    vendor or the public and how many of those carried your signed
    release, and which outside connections exist.

What a button does:
  - Send: signs one disclosure.authority for that held message with your
    key - the same call `console.py session` makes for {"do": "release"}.
  - Continue / Cancel: signs one hitl.decision.authority - the same call as
    {"do": "decide"}.
  - Done (on a queue item): records `desk.acknowledged` on the audit log
    with your login. It changes nothing in the swarm; it only takes the
    item off your list.
  - Run today's checks: the daily clock, through the hub, as run_sweeps.py.
There is no "don't send" that discards a held message: the hub has no such
path. A held message stays held until you send it.

One process at a time: the desk holds the swarm open and saves its state
after every action. While it runs it writes desk.lock in the state folder,
and console.py and run_sweeps.py refuse to start against that folder.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import http.server
import json
import os
import secrets
import shutil
import sys
import threading
import time
import urllib.parse

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, ROOT)
sys.path.insert(0, TOOLS)

import console  # noqa: E402
from gen_diagrams import PHRASE, phrase  # noqa: E402

PAGE = os.path.join(TOOLS, "desk.html")
GATED = {"counterparty", "public"}
QUEUE_TITLE = {
    "escalation.legal_line": "Legal line - yours to answer",
    "escalation.hot_lead": "Hot lead - call now",
    "escalation.complaint": "Upset client - nothing was sent back",
    "clarification.request": "A question for you",
    "integrity.violation": "Refused: unsigned or tampered",
    "dead.letter": "Could not be delivered",
}
REPLY_AGENTS = ["03", "04", "12", "13", "16", "20"]   # agents with a reply handler (Agent 11)


def now():
    return time.time()


def agent_names():
    import re
    out = {"00": "Dispatcher"}
    for d in sorted(os.listdir(ROOT)):
        if d[:2].isdigit() and d[2:3] == "-" and os.path.isfile(os.path.join(ROOT, d, "SKILL.md")):
            m = re.search(r"^# Agent \d\d - (.+?)(?: Agent)?\s*$",
                          open(os.path.join(ROOT, d, "SKILL.md")).read(), re.M)
            out[d[:2]] = m.group(1) if m else d[3:]
    return out


NAMES = agent_names()


def words(intent):
    try:
        return phrase(intent)
    except KeyError:
        return intent


def short(value, n=160):
    s = value if isinstance(value, str) else json.dumps(value, default=str)
    return s if len(s) <= n else s[: n - 1] + "…"


def key_of(queue, record):
    body = json.dumps(record, sort_keys=True, default=str)
    return hashlib.sha256(f"{queue}|{body}".encode()).hexdigest()[:16]


def held_content(intent, ctx, payload):
    """What a held message would say, in plain fields."""
    p = payload if isinstance(payload, dict) else {}
    if intent == "vendor.schedule":
        return {"Vendor": p.get("vendor_id"), "Job": p.get("kind"),
                "For listing": ctx}
    if intent == "campaign.publish":
        c = p.get("content") if isinstance(p.get("content"), dict) else {}
        facts = [f.get("text") for f in c.get("facts", []) if isinstance(f, dict) and f.get("text")]
        out = {"For listing": c.get("ctx") or ctx}
        if facts:
            out["The ad says"] = " · ".join(facts)
        if p.get("action"):
            out["Action"] = p["action"]
        if c.get("notes"):
            out["Notes"] = "; ".join(map(str, c["notes"]))
        if p.get("source"):
            out["Copy"] = "approved description from 04" if p["source"] == "04_asset" else p["source"]
        return out
    return p


def queue_said(q, rec):
    """The words to show for a queue item."""
    payload = rec.get("payload") if isinstance(rec.get("payload"), dict) else {}
    if q == "integrity.violation":
        who = "you" if rec.get("from_agent") == "human" else rec.get("from_agent")
        return (f"A message claiming to be {who} was sent to "
                f"{rec.get('to_agent')} {NAMES.get(rec.get('to_agent'), '')} without a valid "
                f"signature ({rec.get('intent')}: {short(payload, 120)}). The hub refused it.")
    if q == "dead.letter":
        return f"{rec.get('intent')} to {rec.get('to_agent')} could not be delivered"
    return (rec.get("trigger") or rec.get("verbatim") or payload.get("verbatim")
            or payload.get("reason") or rec.get("reason"))


# ----------------------------------------------------------------- read model
class ReadModel:
    """Everything the page shows, computed from the live swarm and its log."""

    def __init__(self, desk):
        self.d = desk

    def build(self):
        sw = self.d.sw
        hub = sw.hub
        log = hub.audit.read()
        routes = json.load(open(os.path.join(ROOT, "identity", "routes.json")))["routes"]
        audience = {r["intent"]: r.get("audience") for r in routes
                    if "external" in r["receivers"]}
        acked = {e.get("item") for e in log if e.get("kind") == "desk.acknowledged"}
        return {
            "operator": self.d.operator,
            "mode": "showcase" if self.d.showcase else "live",
            "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "needs_you": self.needs_you(hub, sw, acked),
            "listings": self.listings(log, hub),
            "leads": self.leads(log, hub, acked),
            "team": self.team(log, hub, sw),
            "proof": self.proof(log, hub, sw, audience),
            "activity": self.activity(log),
            "showcase": self.d.show.status() if self.d.showcase else None,
            "last_action": self.d.last_action,
        }

    # ---- needs you
    def needs_you(self, hub, sw, acked):
        items = []
        for hid, e in hub._absolute_holds.items():
            items.append({
                "type": "held", "id": hid, "ctx": e.client_context_id,
                "intent": e.intent, "from": e.from_agent,
                "from_name": NAMES.get(e.from_agent, e.from_agent),
                "title": {"vendor.schedule": "Book a vendor",
                          "campaign.publish": "Publish marketing"}.get(e.intent, words(e.intent)),
                "to": "a vendor (the other side)" if e.intent == "vendor.schedule"
                      else "the public" if e.intent == "campaign.publish" else "outside",
                "content": held_content(e.intent, e.client_context_id, e.payload),
                "why": "It leaves the swarm for someone other than your client, "
                       "so it waits for your signed release."})
        for w in sw.hitl.get_pending_waits():
            items.append({
                "type": "wait", "id": w["wait_id"], "ctx": w["client_context_id"],
                "from": w["agent_id"], "from_name": NAMES.get(w["agent_id"], w["agent_id"]),
                "title": "Paused - your decision", "why": w.get("reason"),
                "needs_route": w["agent_id"] == "11",
                "route_choices": [{"id": a, "name": NAMES.get(a, a)} for a in REPLY_AGENTS],
                "paused": words(w.get("paused_intent") or "") if w.get("paused_intent") else None,
                "content": w.get("original_payload")})
        holds = set(hub._absolute_holds)
        for q, records in hub.queues.items():
            if q not in QUEUE_TITLE or q == "escalation.hot_lead":
                continue          # hot leads are shown on the lead cards, with their clock
            for rec in records:
                if not isinstance(rec, dict):
                    continue
                if rec.get("absolute_signal") and rec.get("envelope_id") in holds:
                    continue      # already shown above as a held message
                if rec.get("absolute_signal"):
                    continue      # a hold that has since been released
                k = key_of(q, rec)
                if k in acked:
                    continue
                agent = rec.get("agent") or rec.get("from_agent")
                if agent == "human":
                    agent = None          # an unsigned "human" sender is not you
                said = queue_said(q, rec)
                items.append({
                    "type": "queue", "id": k, "queue": q, "title": QUEUE_TITLE[q],
                    "ctx": rec.get("client_context_id"), "from": agent,
                    "from_name": NAMES.get(agent, agent) if agent else None,
                    "said": short(str(said), 400) if said else None,
                    "content": rec})
        order = {"held": 0, "wait": 1, "queue": 2}
        prio = {"escalation.legal_line": 0, "escalation.complaint": 1,
                "integrity.violation": 2, "dead.letter": 3, "clarification.request": 4}
        items.sort(key=lambda i: (order[i["type"]], prio.get(i.get("queue"), 9)))
        return items

    # ---- listings
    STEPS = [("signed", "Signed"), ("booked", "Booked"),
             ("photos", "Photos"), ("copy", "Copy OK"),
             ("live", "Live"), ("marketing", "Marketed"),
             ("contract", "Contract"), ("closed", "Closed")]
    LONG = {"signed": "signed by you", "booked": "photographer booked",
            "photos": "photos verified", "copy": "copy approved by compliance",
            "live": "live", "marketing": "marketing out",
            "contract": "under contract", "closed": "closed"}

    def listings(self, log, hub):
        cards = {}
        held_by_ctx = {}
        for hid, e in hub._absolute_holds.items():
            held_by_ctx.setdefault(e.client_context_id, []).append(e.intent)
        for e in log:
            if e.get("kind") != "envelope.persisted":
                continue
            ctx, intent = e.get("client_context_id"), e.get("intent")
            if intent == "listing.change.authorized" and e.get("from_agent") == "human":
                c = cards.setdefault(ctx, {"ctx": ctx, "done": {}, "flags": [],
                                           "facts": {}})
                nl = (e.get("payload") or {}).get("new_listing") or {}
                if nl:
                    c["facts"] = {k: nl[k] for k in ("beds", "price", "address") if k in nl}
                c["done"]["signed"] = e.get("ts")
            c = cards.get(ctx)
            if c is None:
                continue
            p = e.get("payload") if isinstance(e.get("payload"), dict) else {}
            if intent == "vendor.schedule" and e.get("to_agent") == "external":
                c["done"].setdefault("booked", e.get("ts"))
            elif intent == "deliverable.release":
                c["done"].setdefault("photos", e.get("ts"))
            elif intent == "content.verdict":
                if p.get("verdict") == "approved":
                    c["done"].setdefault("copy", e.get("ts"))
                elif p.get("verdict") == "flagged":
                    c["flags"].append("Copy flagged by compliance - fix it before it markets")
            elif intent == "status.update" and p.get("status") == "active":
                c["done"].setdefault("live", e.get("ts"))
            elif intent == "status.update" and p.get("status") == "pending":
                c["done"].setdefault("contract", e.get("ts"))
            elif intent == "campaign.publish" and e.get("to_agent") == "external":
                c["done"].setdefault("marketing", e.get("ts"))
            elif intent == "transaction.closed":
                c["done"].setdefault("closed", e.get("ts"))
            elif intent == "clarification.request" and e.get("from_agent") in ("04", "05", "09"):
                c["flags"].append(short(p.get("reason") or "a question for you", 140))
        out = []
        for ctx, c in cards.items():
            waiting = []
            held_steps = set()
            for intent in held_by_ctx.get(ctx, []):
                step = {"vendor.schedule": "booked", "campaign.publish": "marketing"}.get(intent)
                if step:
                    held_steps.add(step)
                waiting.append({"vendor.schedule": "the vendor booking",
                                "campaign.publish": "the marketing"}.get(intent, intent))
            steps = []
            for key, label in self.STEPS:
                state = "done" if key in c["done"] else \
                    "you" if key in held_steps else "todo"
                steps.append({"key": key, "label": label, "state": state, "long": self.LONG[key]})
            reached = [s for s in steps if s["state"] == "done"]
            out.append({"ctx": ctx, "facts": c["facts"], "steps": steps,
                        "now": reached[-1]["long"].capitalize() if reached else "Not started",
                        "waiting_on_you": waiting, "flags": c["flags"][-3:],
                        "last_ts": max(c["done"].values()) if c["done"] else 0})
        out.sort(key=lambda c: -c["last_ts"])
        return out

    # ---- leads
    def leads(self, log, hub, acked):
        leads = {}
        for e in log:
            k = e.get("kind")
            if k == "envelope.persisted" and e.get("intent") == "lead.inbound":
                p = e.get("payload") or {}
                leads.setdefault(e["client_context_id"], {
                    "ctx": e["client_context_id"], "name": p.get("name"),
                    "channel": p.get("channel"), "at": e.get("ts"),
                    "tier": None, "hot_since": None, "sla_s": None, "captured": False})
            elif k == "envelope.persisted" and e.get("intent") == "lead.captured":
                if e["client_context_id"] in leads:
                    leads[e["client_context_id"]]["captured"] = True
            elif k == "escalation.raised" and e.get("queue") == "escalation.hot_lead":
                ld = leads.get(e.get("client_context_id"))
                if ld:
                    ld["tier"] = "HOT"
                    ld["hot_since"] = e.get("ts")
                    ld["sla_s"] = e.get("sla_s")
            elif k == "hitl.decision.authorized":
                ld = leads.get(e.get("client_context_id"))
                if ld:
                    ld["decided"] = e.get("decision")
            elif k == "decision.lead":
                ld = leads.get(e.get("client_context_id"))
                if ld and e.get("tier"):
                    ld["tier"] = ld["tier"] or e.get("tier")
        hot_records = {r.get("client_context_id"): r for r in hub.queues.get("escalation.hot_lead", [])
                       if isinstance(r, dict)}
        out = []
        for ld in leads.values():
            rec = hot_records.get(ld["ctx"])
            ld["hot_open"] = bool(rec) and key_of("escalation.hot_lead", rec) not in acked
            ld["ack_id"] = key_of("escalation.hot_lead", rec) if rec else None
            pending = bool(self.d.sw.hitl.get_pending_waits(ld["ctx"]))
            decided = ld.get("decided")
            ld["status"] = ("Hot - call now" if ld["hot_open"] else
                            "Hot - handled" if ld["tier"] == "HOT" else
                            "Waiting for your decision" if pending else
                            "Closed by your decision" if decided == "REJECT_AND_ABORT" else
                            "Captured" if ld["captured"] else "Not captured")
            out.append(ld)
        out.sort(key=lambda l: (not l["hot_open"], -(l["at"] or 0)))
        return out

    # ---- team
    def team(self, log, hub, sw):
        last, waiting, problem = {}, {}, {}
        for e in log:
            k = e.get("kind")
            if k == "envelope.persisted":
                a = e.get("from_agent")
                if a and a[:1].isdigit():
                    if e.get("intent") not in ("interaction.log", "agent.status"):
                        last[a] = (e.get("intent"), e.get("client_context_id"), e.get("ts"))
                        problem.pop(a, None)
            elif k == "handoff.failed":
                a = e.get("agent")
                if a:
                    problem[a] = short(e.get("reason") or e.get("status") or "a handoff failed", 120)
        # what each agent is waiting on, as Agent 18 tracks it now (its live
        # wait list: an agent.status that was cleared is gone from it)
        for w in getattr(sw.spokes.get("18"), "waiting", {}).values():
            what = str(w.get("waiting_on")).replace("_", " ").replace(":", ": ")
            lst = waiting.setdefault(w.get("agent"), [])
            if what not in lst:
                lst.append(what)
        you = {}
        for hid, e in hub._absolute_holds.items():
            you[e.from_agent] = you.get(e.from_agent, 0) + 1
        for w in sw.hitl.get_pending_waits():
            you[w["agent_id"]] = you.get(w["agent_id"], 0) + 1
        tiles = []
        for aid in sorted(NAMES):
            if aid == "00":
                continue
            if aid in problem:
                state, note = "problem", problem[aid]
            elif you.get(aid):
                state, note = "you", f"{you[aid]} waiting for you"
            elif waiting.get(aid):
                state, note = "waiting", "waiting on " + short(", ".join(waiting[aid]), 70)
            elif aid in last:
                state, note = "working", "last: " + words(last[aid][0])
            else:
                state, note = "idle", "nothing yet"
            tiles.append({"id": aid, "name": NAMES[aid], "state": state, "note": note,
                          "ctx": last.get(aid, (None, None, None))[1]})
        return tiles

    # ---- proof
    def proof(self, log, hub, sw, audience):
        chain = hub.audit.verify_chain()
        released = {e.get("envelope_id") for e in log if e.get("kind") == "absolute_signal.released"}
        gated_out = [e for e in log if e.get("kind") == "envelope.persisted"
                     and e.get("to_agent") == "external"
                     and audience.get(e.get("intent")) in GATED]
        signed_out = sum(1 for e in gated_out if e.get("envelope_id") in released)
        client_msgs = sum(1 for e in log if e.get("kind") == "envelope.persisted"
                          and e.get("intent") == "client.message.send")
        pager = os.path.exists(os.path.join(self.d.state_dir, "pager.json"))
        return {
            "chain_ok": bool(chain.get("ok")), "entries": len(log),
            "chain_detail": chain,
            "gated_out": len(gated_out), "gated_out_signed": signed_out,
            "held_now": len(hub._absolute_holds),
            "client_messages": client_msgs,
            "connections": [
                {"name": "MLS", "state": "not connected",
                 "note": "go-live is recorded here; confirming it on the MLS is yours"},
                {"name": "Email / SMS to clients", "state": "not connected",
                 "note": "a client message is released and recorded, not delivered to a phone"},
                {"name": "Text pager to you", "state": "on" if pager else "off",
                 "note": "pages carry the queue and client id only"},
                {"name": "Vendor roster", "state": sw.roster_info["verdict"],
                 "note": f"{len(sw.roster_info['vendors_loaded'])} vendors loaded"},
                {"name": "Identity provider (login + MFA)", "state": "not armed",
                 "note": "the hub checks your key's signature"},
                {"name": "Model-written remarks", "state": "on" if sw.hub.drafting.gate()["ok"] else "off",
                 "note": sw.hub.drafting.gate().get("reason") or ""},
            ]}

    # ---- activity
    def activity(self, log, n=25):
        out = []
        for e in reversed(log):
            k = e.get("kind")
            if k == "envelope.persisted" and e.get("intent") not in ("interaction.log", "agent.status",
                                                                     "record.request", "record.response",
                                                                     "clock.tick"):
                frm, to = e.get("from_agent"), e.get("to_agent")
                who = "You" if frm == "human" else "Outside" if frm == "external" \
                    else f"{frm} {NAMES.get(frm, '')}".strip()
                dest = "you" if to in ("human", "queue") else "outside" if to == "external" \
                    else f"{to} {NAMES.get(to, '')}".strip()
                out.append({"ts": e.get("ts"), "ctx": e.get("client_context_id"),
                            "text": f"{who} → {dest}: {words(e.get('intent'))}"})
            elif k == "absolute_signal.hold":
                out.append({"ts": e.get("ts"), "ctx": None, "kind": "hold",
                            "text": f"Held for your release: {words(e.get('intent'))}"})
            elif k == "disclosure.authorized":
                out.append({"ts": e.get("ts"), "ctx": None, "kind": "you",
                            "text": f"You signed the release: {words(e.get('intent'))}"})
            elif k == "desk.acknowledged":
                out.append({"ts": e.get("ts"), "ctx": e.get("client_context_id"), "kind": "you",
                            "text": f"You marked done: {e.get('title')}"})
            if len(out) >= n:
                break
        return out


# ----------------------------------------------------------------- showcase
class Showcase:
    """Replays the ten operator scenes into the desk, one line per step.
    Lines that are yours (release, decide) are not run for you: the step
    waits until you press the button on the held message or the paused
    thread, exactly as you would in real use."""

    def __init__(self, desk):
        self.d = desk
        self.lines = []
        manual = open(os.path.join(ROOT, "docs", "OPERATOR_TESTING_MANUAL.md")).read()
        import re
        titles = {int(m.group(1)): m.group(2) for m in
                  re.finditer(r"^## Scene (\d+) - (.+?) \(`scene\d+_[a-z_]+\.jsonl`\)$", manual, re.M)}
        for f in sorted(x for x in os.listdir(os.path.join(ROOT, "scenes")) if x.endswith(".jsonl")):
            n = int(f[5:7])
            for line in open(os.path.join(ROOT, "scenes", f)):
                line = line.strip()
                if line and not line.startswith("#"):
                    self.lines.append({"scene": n, "title": titles.get(n, f), "a": json.loads(line)})
        self.pos = 0
        self.log = []
        self.reached = set()      # your lines the showcase has shown you

    def caption(self, a):
        do = a.get("do")
        if do == "config":
            keys = ", ".join(sorted((a.get("payload") or {}).keys()))
            return f"You sign settings for {a['to']} {NAMES.get(a['to'], '')}: {keys}"
        if do == "authorize":
            p = a.get("payload") or {}
            what = "a new listing" if "new_listing" in p else "a listing change"
            return f"You sign {what} for {a.get('ctx')}"
        if do == "send":
            frm = a.get("from")
            if frm == "human":
                return (f"An unsigned message claiming to be you arrives for "
                        f"{a['to']} {NAMES.get(a['to'], '')} ({a.get('intent')}, {a.get('ctx')})")
            who = "From outside" if frm == "external" else f"{frm} {NAMES.get(frm, '')}"
            return f"{who}: {words(a.get('intent'))} ({a.get('ctx')})"
        if do == "sweep":
            return f"The daily clock runs for {a.get('today')}"
        if do == "show" and a.get("what") == "briefing":
            return "Agent 18 builds the morning briefing"
        if do == "show" and a.get("what") == "eod":
            return "Agent 14 runs the end-of-day books"
        if do == "release":
            noun = {"vendor.schedule": "vendor booking", "campaign.publish": "marketing"}.get(
                a.get("intent"), "message")
            return f"Your move: press Send on the held {noun} for {a.get('ctx')}"
        if do == "decide":
            return (f"Your move: press {a.get('decision', '').title()} on the paused "
                    f"thread for {a.get('ctx')}")
        return f"{do}"

    def _pending(self, a):
        """For a line that is yours: is it still waiting for your press?"""
        sw = self.d.sw
        if a.get("do") == "release":
            return any(e.client_context_id == a.get("ctx") and
                       (not a.get("intent") or e.intent == a.get("intent"))
                       for e in sw.hub._absolute_holds.values())
        if a.get("do") == "decide":
            return bool(sw.hitl.get_pending_waits(a.get("ctx")))
        return False

    def skip_noise(self):
        """Moves past lines with nothing to do: console 'show' lines (the desk
        already shows everything), and a line of yours you have already done
        on the desk (pressed Send or Continue/Cancel)."""
        while self.pos < len(self.lines):
            cur = self.lines[self.pos]
            a = cur["a"]
            if a.get("do") == "show" and a.get("what") not in ("briefing", "eod"):
                self.pos += 1
                continue
            if a.get("do") in ("release", "decide") and self.pos in self.reached \
                    and not self._pending(a):
                self.log.append({"scene": cur["scene"],
                                 "text": self.caption(a).replace("Your move: press", "You pressed")})
                self.pos += 1
                continue
            break

    def status(self):
        self.skip_noise()
        if self.pos >= len(self.lines):
            return {"done": True, "pos": self.pos, "total": len(self.lines), "log": self.log[-8:]}
        cur = self.lines[self.pos]
        a = cur["a"]
        yours = a.get("do") in ("release", "decide")
        if yours:
            self.reached.add(self.pos)
        return {"done": False, "pos": self.pos, "total": len(self.lines),
                "scene": cur["scene"], "title": cur["title"],
                "next": self.caption(a), "yours": yours, "line": a if yours else None,
                "waiting_for_you": yours and self._pending(a),
                "log": self.log[-8:]}

    def step(self):
        self.skip_noise()
        if self.pos >= len(self.lines):
            return {"done": True}
        cur = self.lines[self.pos]
        a = cur["a"]
        if a.get("do") in ("release", "decide"):
            self.reached.add(self.pos)
            if self._pending(a):
                return {"waiting_for_you": True, "next": self.caption(a)}
            self.skip_noise()      # you already pressed it on the desk
            return {"stepped": True}
        r, err = console.apply_action(self.d.sw, self.d.signer, self.d.operator, a)
        self.pos += 1
        self.log.append({"scene": cur["scene"], "text": self.caption(a),
                         "result": short(r, 200), "error": err})
        return {"stepped": True, "result": r, "error": err}


# ----------------------------------------------------------------- the desk
class Desk:
    def __init__(self, state_dir, config_dir=None, showcase=False):
        from dispatcher.state_snapshot import StateIntegrityError  # noqa: F401
        self.state_dir = state_dir
        self.showcase = showcase
        self.lock = threading.RLock()
        self.last_action = None
        os.makedirs(state_dir, exist_ok=True)
        key = os.path.join(state_dir, "operator-key.bin")
        if showcase and not os.path.exists(key):
            from dispatcher.signatures import Ed25519Signer
            with open(key, "wb") as f:
                f.write(Ed25519Signer().private_key_bytes())
            json.dump({"name": "Showcase Broker", "login": "showcase@example.test",
                       "note": "showcase desk - synthetic data, not your records"},
                      open(os.path.join(state_dir, "operator.json"), "w"), indent=1)
        if showcase:
            config_dir = os.path.join(state_dir, "config")
            os.makedirs(config_dir, exist_ok=True)
            roster = json.load(open(os.path.join(ROOT, "scenes", "config", "vendor_panel.json")))
            roster["_status"] = (f"RATIFIED {datetime.date.today().isoformat()} showcase copy of "
                                 f"scenes/config/vendor_panel.json - synthetic vendors")
            json.dump(roster, open(os.path.join(config_dir, "vendor_panel.json"), "w"), indent=1)
        if not os.path.exists(key):
            raise SystemExit(f"no key in {state_dir}: run `python tools/console.py init` and "
                             f"`python tools/console.py onboard` first")
        console.STATE_DIR = state_dir
        console.KEY_PATH = key
        console.OPERATOR_PATH = os.path.join(state_dir, "operator.json")
        self.lockfile = os.path.join(state_dir, "desk.lock")
        other = console.desk_running(state_dir)
        if other:
            raise SystemExit(f"a desk is already running on {state_dir} (pid {other})")
        with open(self.lockfile, "w") as f:
            f.write(str(os.getpid()))
        self.operator = console._operator()
        self.sw, self.signer = console.build(
            os.path.join(state_dir, "console-audit.jsonl"), config_dir,
            os.path.join(state_dir, "swarm-state.sqlite"))
        self.show = Showcase(self) if showcase else None
        self.model = ReadModel(self)

    def close(self):
        try:
            self.sw.save_state()
        finally:
            if os.path.exists(self.lockfile):
                os.remove(self.lockfile)

    def state(self):
        with self.lock:
            return self.model.build()

    def _done(self, what, result):
        self.sw.save_state()
        self.last_action = {"what": what, "result": short(result, 300), "at": now()}
        return result

    def act(self, body):
        with self.lock:
            kind = body.get("action")
            if kind == "send":
                hid = body.get("id")
                held = self.sw.hub._absolute_holds.get(hid)
                if held is None:
                    return {"error": "that message is no longer held"}
                from dispatcher.core import Envelope
                auth = Envelope(from_agent="human", to_agent=held.from_agent,
                                intent="disclosure.authority",
                                client_context_id=held.client_context_id,
                                payload={"held_envelope_id": hid},
                                provenance={"source": "human", "captured_at": "runtime",
                                            "verbatim_available": True})
                if self.operator:
                    auth.provenance["operator"] = self.operator["login"]
                self.signer.sign(auth)
                return self._done(f"Sent: {words(held.intent)} ({held.client_context_id})",
                                  self.sw.hub.release_disclosure(auth))
            if kind == "decide":
                w = next((w for w in self.sw.hitl.get_pending_waits()
                          if w["wait_id"] == body.get("id")), None)
                if w is None:
                    return {"error": "that thread is no longer paused"}
                a = {"ctx": w["client_context_id"], "agent": w["agent_id"],
                     "decision": body.get("decision")}
                if body.get("route_to"):
                    a["route_to"] = body["route_to"]
                return self._done(f"{str(body.get('decision')).title()}: {w['client_context_id']}",
                                  console.decide(self.sw, self.signer, a))
            if kind == "ack":
                item = body.get("id")
                self.sw.hub.audit.append("desk.acknowledged", {
                    "item": item, "title": body.get("title"),
                    "client_context_id": body.get("ctx"),
                    "by": (self.operator or {}).get("login")})
                return self._done(f"Marked done: {body.get('title')}", {"acknowledged": item})
            if kind == "sweep":
                day = body.get("today") or datetime.date.today().isoformat()
                r, _ = console.apply_action(self.sw, self.signer, self.operator,
                                            {"do": "sweep", "today": day})
                return self._done(f"Ran today's checks ({day})", r)
            if kind == "verify":
                r = self.sw.hub.audit.verify_chain()
                self.last_action = {"what": "Checked the record", "result": short(r, 300), "at": now()}
                return r
            if kind == "showcase.step" and self.show:
                r = self.show.step()
                if r.get("stepped"):
                    self.sw.save_state()
                return r
            return {"error": f"unknown action {kind!r}"}


# ----------------------------------------------------------------- http
def make_handler(desk, token):
    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _authorized(self):
            if token is None:
                return True
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            return self.headers.get("X-Desk-Token") == token or q.get("t", [None])[0] == token

        def _send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body, default=str).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if not self._authorized():
                return self._send(403, {"error": "access code required"})
            path = urllib.parse.urlparse(self.path).path
            if path == "/":
                return self._send(200, open(PAGE, "rb").read(), "text/html; charset=utf-8")
            if path == "/api/state":
                return self._send(200, desk.state())
            return self._send(404, {"error": "not found"})

        def do_POST(self):
            if not self._authorized():
                return self._send(403, {"error": "access code required"})
            if urllib.parse.urlparse(self.path).path != "/api/act":
                return self._send(404, {"error": "not found"})
            n = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._send(400, {"error": "bad JSON"})
            try:
                return self._send(200, desk.act(body))
            except Exception as e:    # raw reason, never softened
                return self._send(500, {"error": repr(e)})
    return H


def main(argv=None):
    ap = argparse.ArgumentParser(description="The Broker Desk")
    ap.add_argument("--showcase", action="store_true",
                    help="a separate desk that replays the ten operator scenes on synthetic data")
    ap.add_argument("--state-dir", default=None,
                    help="state folder (default: console-state/, or showcase-state/ with --showcase)")
    ap.add_argument("--config-dir", default=None)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--lan", action="store_true",
                    help="listen on the network (for a tablet); prints a link with an access code")
    ap.add_argument("--fresh", action="store_true",
                    help="with --showcase: start the showcase from scene 1 on empty state")
    args = ap.parse_args(argv)
    state_dir = args.state_dir or (os.path.join(ROOT, "showcase-state") if args.showcase
                                   else console.STATE_DIR)
    if args.showcase and args.fresh and os.path.isdir(state_dir):
        shutil.rmtree(state_dir)
    desk = Desk(state_dir, args.config_dir, showcase=args.showcase)
    host = "0.0.0.0" if args.lan else "127.0.0.1"
    token = secrets.token_urlsafe(9) if args.lan else None
    # one thread: the swarm's SQLite store may only be used from the thread
    # that opened it, and one broker's page does not need more
    srv = http.server.HTTPServer((host, args.port), make_handler(desk, token))
    url = f"http://{'<this-computer>' if args.lan else '127.0.0.1'}:{args.port}/" + \
        (f"?t={token}" if token else "")
    print(json.dumps({"desk": url, "mode": "showcase" if args.showcase else "live",
                      "state_dir": state_dir,
                      "note": "Ctrl+C to stop; state is saved after every action"}))
    import signal

    def _stop(*_a):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, _stop)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
        desk.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
