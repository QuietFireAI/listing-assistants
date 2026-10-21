"""run_tracker - the dispatcher's playbook runs (owner decision 2026-10-15).

The agents do the work; nothing here tells an agent what to do. The tracker
watches every message on the hub, matches it against the playbook table
(identity/playbooks.json) and keeps one run per playbook and client:

  start    a message that matches one playbook's start opens a run of it
           (`playbook.started`); every later message on that client that
           involves one of the playbook's agents is a step of the run
           (`playbook.step`), and a message that matches an end closes it
           (`playbook.completed`) and writes its after-action report.

  two      a message that matches the start of two or more playbooks is
  matches  not delivered. It is held for you, naming every match (Agent 00
           tuple "two playbooks match a situation, deploy neither"). Continue
           with the playbook you choose (`set: {"playbook": "P15"}`) and it
           is delivered and that run starts; cancel drops it. A human
           message can name its playbook up front (payload.playbook).

  conflict a new run whose playbook conflicts with one already open on the
           same client (the table's conflicts_with, e.g. a wind-down while
           the listing is being marketed) holds both: the new message is
           not delivered and further entries for the open run on that
           client wait (tuple "same client_context in two live playbooks
           with conflicting next actions, hold both; human sequences
           them"). Continue with `set: {"first": "P05"}`: the new playbook
           first ends the open run by your decision and its waiting
           entries are dropped (on the log); the open playbook first lets
           it go on and the new message waits until that run ends. Cancel
           drops the new message.

  full     while CAP_OPEN_QUESTIONS (25) or more questions wait for you
  queue    (paused threads plus unanswered clarification requests), a
           message from outside the agents (you, an outside system, the
           clock) that would start a new run waits instead (tuple "a swarm
           that cannot get answers must not take on more"). You are told
           once, on escalation.queue_full. When the count drops, the waiting
           starts go in priority order.

  siding   work that waits in the tracker (full queue, a run you put
           second) is released by priority class (identity/priority.json:
           1 escalation, 2 time-critical, 3 scheduled, 4 background), the
           older first within a class. Two waiting messages for the same
           agent take turns through dispatcher/priority.py's
           SidingScheduler: the lower class is held live on the siding and
           resumes when the agent is free (`siding.hold`, `siding.resume`).
           Agents answer at once in this product, so nothing waits on an
           agent mid-delivery; work only waits here.

  legal    a message from an agent inside a run that the closed track
  line     refuses (`reject`) means the playbook asked for a step the track
           does not allow: the run halts and an integrity.violation names
           it as a defect in the playbook, not a judgment call (tuple SW-02).
           The table itself is checked against the closed track at start-up;
           a pattern the track cannot carry stops the tracker and says so.

The table is PROPOSED until the owner ratifies it (its _status line);
every run records which (`table`), and so does every report.

State (runs, held and waiting messages) is saved with the swarm's state
(dispatcher/state_snapshot.py). Runs started before a restart continue.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Optional

from .core import Envelope
from .human_holds import hold_for_human, decision_of, register_resumer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABLE_PATH = os.path.join(ROOT, "identity", "playbooks.json")
PRIORITY_PATH = os.path.join(ROOT, "identity", "priority.json")

# TUNABLE (owner decision 2026-10-15). See docs/TUNING_MANUAL.md.
CAP_OPEN_QUESTIONS = 25

_AGENT = "00"
_PSEUDO = ("human", "external", "clock", "queue")


# ------------------------------------------------------------------ patterns
def _get(data: dict, key: str):
    cur: Any = data
    for part in key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _tests_pass(p: dict, data: dict) -> bool:
    for k in p.get("has", []):
        if _get(data, k) is None:
            return False
    for k, v in p.get("eq", {}).items():
        if _get(data, k) != v:
            return False
    for k, v in p.get("ne", {}).items():
        if _get(data, k) == v:
            return False
    for k, vs in p.get("in", {}).items():
        if _get(data, k) not in vs:
            return False
    for k, v in p.get("prefix", {}).items():
        got = _get(data, k)
        if not isinstance(got, str) or not got.lower().startswith(str(v).lower()):
            return False
    return True


def _one_of(want, got) -> bool:
    if want is None:
        return True
    return got in (want if isinstance(want, list) else [want])


def env_matches(p: dict, env: Envelope) -> bool:
    if "intent" not in p or p["intent"] != env.intent:
        return False
    if not _one_of(p.get("from"), env.from_agent) or not _one_of(p.get("to"), env.to_agent):
        return False
    return _tests_pass(p, env.payload if isinstance(env.payload, dict) else {})


def audit_matches(p: dict, kind: str, rec: dict) -> bool:
    return p.get("audit") == kind and _tests_pass(p, rec)


class TableError(ValueError):
    """The playbook table cannot be used as written."""


class PlaybookTable:
    def __init__(self, path: str, routes, classes: dict):
        from .config_status import is_ratified
        raw = open(path, encoding="utf-8").read()
        data = json.loads(raw)
        self.path = path
        self.sha256 = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self.status_line = data.get("_status", "")
        self.ratified = is_ratified(self.status_line)
        self.status = "RATIFIED" if self.ratified else "PROPOSED"
        self.playbooks: dict = data.get("playbooks", {})
        self.problems = self._check(routes, classes)

    def _check(self, routes, classes) -> list[str]:
        """Every pattern must be a crossing the closed track can carry, and
        every playbook needs a priority class: a table that asks for a step
        the track refuses is a defect in the table (tuple SW-02)."""
        out = []
        for pid, pb in sorted(self.playbooks.items()):
            if pid not in classes:
                out.append(f"{pid}: no priority class in identity/priority.json")
            for which in ("starts", "ends"):
                if not pb.get(which):
                    out.append(f"{pid}: no {which}")
                for p in pb.get(which, []):
                    if "audit" in p:
                        continue
                    frms = p.get("from")
                    tos = p.get("to")
                    frms = frms if isinstance(frms, list) else [frms] if frms else []
                    tos = tos if isinstance(tos, list) else [tos] if tos else []
                    if not any(True for _ in routes.matches(p.get("intent", ""))):
                        out.append(f"{pid} {which}: intent {p.get('intent')!r} is not on the track")
                        continue
                    for f in frms:
                        for t in tos:
                            if not routes.tuple_legal(f, p["intent"], t):
                                out.append(f"{pid} {which}: {f} -> {t} {p['intent']} is not a "
                                           f"crossing the track allows")
            for other in pb.get("conflicts_with", []) + pb.get("supersedes", []):
                if other not in self.playbooks:
                    out.append(f"{pid}: names {other}, which is not in the table")
        return out

    def starts_for(self, env: Envelope) -> list[str]:
        return sorted(pid for pid, pb in self.playbooks.items()
                      if any(env_matches(p, env) for p in pb.get("starts", [])))

    def starts_for_audit(self, kind: str, rec: dict) -> list[str]:
        return sorted(pid for pid, pb in self.playbooks.items()
                      if any(audit_matches(p, kind, rec) for p in pb.get("starts", [])))

    def ends_on(self, pid: str, env: Envelope) -> bool:
        return any(env_matches(p, env) for p in self.playbooks[pid].get("ends", []))

    def ends_on_audit(self, pid: str, kind: str, rec: dict) -> bool:
        return any(audit_matches(p, kind, rec) for p in self.playbooks[pid].get("ends", []))

    def conflicts(self, a: str, b: str) -> bool:
        return (b in self.playbooks.get(a, {}).get("conflicts_with", [])
                or a in self.playbooks.get(b, {}).get("conflicts_with", []))


# ------------------------------------------------------------------- tracker
STATE_ATTRS = ("runs", "held", "waiting", "parked", "cap_alerted", "counter")


class RunTracker:
    def __init__(self, sw, table_path: str = TABLE_PATH, report_dir: Optional[str] = None):
        self.sw = sw
        self.hub = sw.hub
        self.classes = json.load(open(PRIORITY_PATH, encoding="utf-8"))["classes"]
        self.report_dir = report_dir or os.path.join(
            os.path.dirname(os.path.abspath(self.hub.audit.path)), "after_action")
        self.runs: dict[str, dict] = {}       # run_id -> run
        self.held: dict[str, dict] = {}       # wait_id -> held start (two matches / conflict)
        self.waiting: list[dict] = []         # starts waiting on a full queue or another run
        self.parked: dict[str, list] = {}     # run_id -> entries waiting while the run is held
        self.cap_alerted = False
        self.counter = 0
        self._depth = 0
        self._busy = False
        self._draining = False
        self._forced: dict[str, str] = {}     # envelope_id -> playbook, for a decided start
        self._pending: dict[str, list] = {}   # envelope_id -> [(run_id, step index)] in flight
        self.errors: list[str] = []
        try:
            self.table = PlaybookTable(table_path, self.hub.routes, self.classes)
        except (OSError, ValueError) as e:
            self.table = None
            self.hub.audit.append("playbook.table_refused", {"path": table_path,
                                                             "reason": f"{type(e).__name__}: {e}"})
            return
        if self.table.problems:
            self.hub.audit.append("playbook.table_refused", {
                "path": table_path, "problems": self.table.problems,
                "reason": "the playbook table asks for crossings the track does not allow - "
                          "no run is tracked until it is fixed"})
            self.hub.queue_and_notify("integrity.violation", {
                "client_context_id": "playbook-table", "kind": "playbook_table_defect",
                "problems": self.table.problems})
            self.table = None
            return
        self.hub.audit.append("playbook.table", {
            "path": os.path.relpath(table_path, ROOT), "status": self.table.status,
            "status_line": self.table.status_line, "sha256": self.table.sha256,
            "playbooks": len(self.table.playbooks)})
        self._install()

    # ------------------------------------------------------------ plumbing
    def _install(self):
        inner_send = self.hub.send
        inner_append = self.hub.audit.append

        def send(env):
            self._depth += 1
            try:
                try:
                    held = self._before(env)
                except Exception as e:
                    # the tracker never stands between a message and the hub's
                    # own checks: with the audit log unwritable, for one, the
                    # hub halts and alarms (fail closed); the tracker's failure
                    # is recorded when the log can take it
                    held = None
                    self._tracker_error("before", env, e)
                if held is not None:
                    return held
                res = inner_send(env)
                try:
                    self._after(env, res)
                except Exception as e:
                    self._tracker_error("after", env, e)
                return res
            finally:
                self._depth -= 1
                if self._depth == 0:
                    self._write_due_reports()
                    self._release_waiting()

        def append(kind, rec):
            out = inner_append(kind, rec)
            if not self._busy and isinstance(rec, dict) and self.table is not None:
                self._after_audit(kind, rec)
            return out

        self.hub.send = send
        self.hub.audit.append = append
        register_resumer(self.hub, _AGENT, self._resume)

    def _tracker_error(self, where: str, env, e: Exception):
        self.errors.append(f"{where} {getattr(env, 'envelope_id', None)}: {type(e).__name__}: {e}")
        try:
            self._log("playbook.tracker_error", {"where": where,
                                                 "envelope_id": getattr(env, "envelope_id", None),
                                                 "client_context_id": getattr(env, "client_context_id", None),
                                                 "error": f"{type(e).__name__}: {e}"[:300]})
        except Exception:
            pass   # the log itself is what failed; the hub has said so

    def state(self) -> dict:
        return {a: getattr(self, a) for a in STATE_ATTRS}

    def restore(self, saved: dict):
        for a in STATE_ATTRS:
            if a in saved:
                setattr(self, a, saved[a])

    def open_runs(self, ctx: Optional[str] = None) -> list[str]:
        return sorted(r for r, run in self.runs.items()
                      if run["status"] in ("open", "held") and (ctx is None or run["ctx"] == ctx))

    def _log(self, kind: str, rec: dict):
        self._busy = True
        try:
            self.hub.audit.append(kind, rec)
        finally:
            self._busy = False

    def _held_result(self, env, why: str, **extra) -> dict:
        return {"status": "held", "queue": "playbook", "envelope_id": env.envelope_id,
                "reason": why, **extra}

    @staticmethod
    def _keep(env: Envelope) -> dict:
        return {"record": env.to_record(), "signature": env.signature}

    @staticmethod
    def _rebuild(kept: dict) -> Envelope:
        return Envelope(**kept["record"], signature=kept.get("signature"))

    # -------------------------------------------------------------- counts
    def open_questions(self) -> int:
        """Questions waiting for you: paused threads, and clarification
        requests not yet marked done (the desk's Done, the console's ack)."""
        from .escalation_watch import key_of
        waits = len(self.sw.hitl.get_pending_waits()) if getattr(self.sw, "hitl", None) else 0
        items = [r for r in self.hub.queues.get("clarification.request", []) if isinstance(r, dict)]
        if not items:
            return waits
        acked = {e.get("item") for e in self.hub.audit.read() if e.get("kind") == "desk.acknowledged"}
        return waits + sum(1 for r in items if key_of("clarification.request", r) not in acked)

    # ------------------------------------------------------------- matching
    def _before(self, env: Envelope) -> Optional[dict]:
        if self.table is None or getattr(self.hub, "halted", None):
            return None
        # a message the hub will refuse (off the track, or an authority
        # without a verified signature) starts, holds and joins nothing:
        # the hub's own refusal is what happens to it
        from .hub import is_authority
        if not self.hub.routes.tuple_legal(env.from_agent, env.intent, env.to_agent):
            if env.from_agent not in _PSEUDO:
                # an agent inside a run attempting a crossing the track
                # refuses: a step of the run, so the refusal halts it (SW-02)
                self._attribute(env)
            return None
        if is_authority(env.intent, self.hub.routes.signed_intents) and not self.hub.verify_sig(env):
            return None
        ctx = env.client_context_id
        top = self._depth == 1
        # a run held for your sequencing: its further entries wait
        if top:
            for rid in self.open_runs(ctx):
                run = self.runs[rid]
                if run["status"] == "held" and self._involves(run, env) \
                        and env.envelope_id not in self._forced:
                    self.parked.setdefault(rid, []).append(self._keep(env))
                    self._log("playbook.entry_waiting", {
                        "run_id": rid, "playbook": run["playbook"], "client_context_id": ctx,
                        "envelope_id": env.envelope_id, "intent": env.intent,
                        "reason": "this run is held for your decision on a conflicting playbook"})
                    return self._held_result(env, f"{rid} is held for your decision")
        forced = self._forced.pop(env.envelope_id, None)
        starts = [forced] if forced else self.table.starts_for(env)
        named = env.payload.get("playbook") if isinstance(env.payload, dict) else None
        if not forced and env.from_agent == "human" and named in starts:
            starts = [named]
        open_here = {self.runs[r]["playbook"] for r in self.open_runs(ctx)}
        starts = [p for p in starts if p not in open_here]
        if not starts:
            self._attribute(env)
            return None
        if top and not forced:
            n = self.open_questions()
            if n >= CAP_OPEN_QUESTIONS:
                return self._wait_full_queue(env, starts, n)
        if len(starts) > 1:
            return self._hold_two_matches(env, starts)
        pid = starts[0]
        if not forced:
            for rid in self.open_runs(ctx):
                other = self.runs[rid]["playbook"]
                if self.table.conflicts(pid, other):
                    return self._hold_conflict(env, pid, rid)
        self._start(pid, env)
        self._attribute(env)
        return None

    def _attribute_one(self, rid: str, env: Envelope):
        run = self.runs[rid]
        n = len(run["steps"]) + 1
        run["steps"].append({"step": n, "agent": f"{env.from_agent}->{env.to_agent}",
                             "intent": env.intent, "envelope_id": env.envelope_id,
                             "status": "ends this run before delivery"})
        self._log("playbook.step", {"playbook": run["playbook"], "run_id": rid,
                                    "client_context_id": run["ctx"], "step": n,
                                    "envelope_id": env.envelope_id,
                                    "note": f"{env.from_agent}->{env.to_agent} {env.intent} (ends the run)"})

    def _attribute(self, env: Envelope):
        """Records the message as the next step of every open run on its
        client that it involves, in the order messages are sent."""
        ctx = env.client_context_id
        marks = []
        # a run that just ended on a message also records what that
        # message set off (its "tail"), until the message is finished
        tails = [r for r, run in self.runs.items() if run.get("tail") and run["ctx"] == ctx]
        for rid in self.open_runs(ctx) + tails:
            run = self.runs[rid]
            if run["status"] != "open" and not run.get("tail"):
                continue
            if env.envelope_id != run["start_envelope"] and not self._involves(run, env):
                continue
            n = len(run["steps"]) + 1
            run["steps"].append({"step": n, "agent": f"{env.from_agent}->{env.to_agent}",
                                 "intent": env.intent, "envelope_id": env.envelope_id,
                                 "status": None})
            self._log("playbook.step", {"playbook": run["playbook"], "run_id": rid,
                                        "client_context_id": ctx, "step": n,
                                        "envelope_id": env.envelope_id,
                                        "note": f"{env.from_agent}->{env.to_agent} {env.intent}"})
            marks.append((rid, n - 1))
        if marks:
            self._pending[env.envelope_id] = marks

    def _involves(self, run: dict, env: Envelope) -> bool:
        agents = set(self.table.playbooks[run["playbook"]].get("agents", []))
        return env.from_agent in agents or env.to_agent in agents

    def _start(self, pid: str, env: Envelope) -> str:
        ctx = env.client_context_id
        for rid in self.open_runs(ctx):
            old = self.runs[rid]["playbook"]
            if old in self.table.playbooks[pid].get("supersedes", []):
                # the message that starts the next playbook may also be the
                # one that ends this one (P03's timeline is P09's start)
                if self.table.ends_on(old, env):
                    self._attribute_one(rid, env)
                    self._end(rid, "completed", f"ended on {env.intent}; {pid} starts on it")
                else:
                    self._end(rid, "handed_on", f"{pid} started on {env.intent}")
        self.counter += 1
        rid = f"{pid}-{ctx}-{self.counter}"
        self.runs[rid] = {"run_id": rid, "playbook": pid, "ctx": ctx, "status": "open",
                          "class": self.classes[pid], "started_at": time.time(),
                          "start_envelope": env.envelope_id, "steps": []}
        self._log("playbook.started", {
            "playbook": pid, "name": self.table.playbooks[pid].get("name"), "run_id": rid,
            "client_context_id": ctx, "class": self.classes[pid],
            "start_envelope": env.envelope_id, "start_intent": env.intent,
            "table": self.table.status})
        return rid

    def _start_from_log(self, pid: str, kind: str, rec: dict) -> str:
        ctx = rec["client_context_id"]
        self.counter += 1
        rid = f"{pid}-{ctx}-{self.counter}"
        self.runs[rid] = {"run_id": rid, "playbook": pid, "ctx": ctx, "status": "open",
                          "class": self.classes[pid], "started_at": time.time(),
                          "start_envelope": None, "steps": [
                              {"step": 1, "agent": rec.get("agent") or "-", "intent": kind,
                               "envelope_id": None, "status": rec.get("queue")}]}
        self._log("playbook.started", {
            "playbook": pid, "name": self.table.playbooks[pid].get("name"), "run_id": rid,
            "client_context_id": ctx, "class": self.classes[pid], "start_envelope": None,
            "start_intent": kind, "table": self.table.status})
        return rid

    def _after(self, env: Envelope, res):
        if self.table is None:
            return
        status = res.get("status") if isinstance(res, dict) else None
        for rid, idx in self._pending.pop(env.envelope_id, []):
            run = self.runs[rid]
            run["steps"][idx]["status"] = status
            if run["status"] != "open":
                continue
            first = env.envelope_id == run["start_envelope"]
            if status == "reject" and env.from_agent not in _PSEUDO:
                self._halt_on_track(rid, env, res)
                continue
            single = self.table.playbooks[run["playbook"]].get("single_message")
            if (single and first) or (not first and self.table.ends_on(run["playbook"], env)):
                self._end(rid, "completed", None)

    def _after_audit(self, kind: str, rec: dict):
        if kind.startswith("playbook.") or kind in ("segment.grant", "segment.release",
                                                    "siding.hold", "siding.resume"):
            return
        ctx = rec.get("client_context_id")
        if ctx is None:
            return
        # a start seen on the log, not on a message (an escalation raised by
        # an agent, e.g. P14's complaint): it cannot be held, only tracked
        open_here = {self.runs[r]["playbook"] for r in self.open_runs(ctx)}
        for pid in self.table.starts_for_audit(kind, rec):
            if pid not in open_here:
                rid = self._start_from_log(pid, kind, rec)
                open_here.add(pid)
        for rid in self.open_runs(ctx):
            run = self.runs[rid]
            if run["status"] == "open" and self.table.ends_on_audit(run["playbook"], kind, rec):
                self._end(rid, "completed", None)

    def _halt_on_track(self, rid: str, env: Envelope, res: dict):
        run = self.runs[rid]
        why = (f"{run['playbook']} asked {env.from_agent} to send {env.intent} to "
               f"{env.to_agent}; the closed track refuses it ({res.get('reason')}). "
               f"A playbook step against an agent's legal line is a defect in the playbook, "
               f"not a judgment call.")
        flag = {"client_context_id": run["ctx"], "violation": "playbook_step_off_track",
                "run_id": rid, "playbook": run["playbook"], "envelope_id": env.envelope_id,
                "reason": why}
        # on the chain as well as on the integrity queue: a queue landing is
        # only recorded when a notifier is configured
        self._log("playbook.integrity_violation", flag)
        self._busy = True
        try:
            self.hub.queue_and_notify("integrity.violation", flag)
        finally:
            self._busy = False
        self._end(rid, "halted", why)

    # ------------------------------------------------------------ holding
    def _hold(self, env: Envelope, ctx: str, reason: str, fields: dict, kind: str) -> Optional[str]:
        self._busy = True
        try:
            out = hold_for_human(self.hub, _AGENT, ctx, "playbook.start", reason,
                                 {**fields, "envelope_id": env.envelope_id, "intent": env.intent})
        finally:
            self._busy = False
        wid = out.get("held")
        if wid:
            self.held[wid] = {"kind": kind, "env": self._keep(env), "ctx": ctx, **fields}
        return wid

    def _hold_two_matches(self, env: Envelope, starts: list[str]) -> dict:
        ctx = env.client_context_id
        names = ", ".join(f"{p} {self.table.playbooks[p].get('name')}" for p in starts)
        reason = (f"{env.intent} from {env.from_agent} starts more than one playbook ({names}). "
                  f"Neither is run. Continue with the one you mean (playbook: one of "
                  f"{', '.join(starts)}); cancel drops the message.")
        wid = self._hold(env, ctx, reason, {"playbook": None, "candidates": starts}, "two_matches")
        self._log("playbook.ambiguous", {"client_context_id": ctx, "envelope_id": env.envelope_id,
                                         "intent": env.intent, "candidates": starts,
                                         "wait_id": wid})
        return self._held_result(env, reason, wait_id=wid, candidates=starts)

    def _hold_conflict(self, env: Envelope, pid: str, rid: str) -> dict:
        ctx = env.client_context_id
        run = self.runs[rid]
        last = run["steps"][-1]["intent"] if run["steps"] else run["playbook"]
        reason = (f"{pid} {self.table.playbooks[pid].get('name')} would start on {env.intent} "
                  f"while {run['playbook']} {self.table.playbooks[run['playbook']].get('name')} "
                  f"is open for {ctx} (its last step: {last}). They conflict, so both are held. "
                  f"Continue with first: {pid} (ends {run['playbook']} by your decision) or "
                  f"first: {run['playbook']} (it goes on; {pid} waits until it ends); "
                  f"cancel drops the {env.intent}.")
        run["status"] = "held"
        wid = self._hold(env, ctx, reason, {"first": None, "new": pid, "open_run": rid,
                                            "open_playbook": run["playbook"]}, "conflict")
        self._log("playbook.conflict", {"client_context_id": ctx, "envelope_id": env.envelope_id,
                                        "new": pid, "open_run": rid,
                                        "open_playbook": run["playbook"], "wait_id": wid})
        return self._held_result(env, reason, wait_id=wid, held_runs=[rid])

    def _wait_full_queue(self, env: Envelope, starts: list[str], n: int) -> dict:
        self.counter += 1
        self.waiting.append({"env": self._keep(env), "playbook": starts[0] if len(starts) == 1 else None,
                             "candidates": starts, "why": "queue_full", "seq": self.counter,
                             "since": time.time()})
        self._log("playbook.start_waiting", {
            "client_context_id": env.client_context_id, "envelope_id": env.envelope_id,
            "intent": env.intent, "candidates": starts, "open_questions": n,
            "cap": CAP_OPEN_QUESTIONS,
            "reason": f"{n} questions wait for you (cap {CAP_OPEN_QUESTIONS}): no new run starts "
                      f"until some are answered"})
        if not self.cap_alerted:
            self.cap_alerted = True
            self._busy = True
            try:
                self.hub.escalate("escalation.queue_full", {
                    "client_context_id": env.client_context_id, "open_questions": n,
                    "cap": CAP_OPEN_QUESTIONS,
                    "reason": f"{n} questions are waiting for you. New playbook runs wait until "
                              f"fewer than {CAP_OPEN_QUESTIONS} are open; nothing is dropped."})
            finally:
                self._busy = False
        return self._held_result(env, f"queue full: {n} open questions", waiting=True)

    # ------------------------------------------------------------ waiting
    def release_waiting(self):
        """Releases what waits on a full question queue now that questions
        were answered (the console's ack and watch call this; any message
        through the hub does it too)."""
        if self._depth == 0:
            self._release_waiting()

    def _release_waiting(self):
        if self._busy or self._draining or self.table is None or not self.waiting:
            return
        self._draining = True
        try:
            self._release_now()
        finally:
            self._draining = False

    def _release_now(self):
        ready = [w for w in self.waiting if w["why"] == "ready"]
        if ready:
            self._drain(ready, "the run they waited for ended")
        full = [w for w in self.waiting if w["why"] == "queue_full"]
        if full and self.open_questions() < CAP_OPEN_QUESTIONS:
            self.cap_alerted = False
            self._drain(full, "fewer than the cap of open questions")

    def _drain(self, items: list[dict], why: str):
        """Releases waiting starts by priority class (oldest first within a
        class); two for the same agent take turns on the siding."""
        from .priority import SidingScheduler
        for it in items:
            self.waiting.remove(it)
        cls = lambda it: min(self.classes.get(p, 9) for p in it["candidates"])
        order = sorted(items, key=lambda it: (cls(it), it["seq"]))
        # the siding's name for each waiting start: playbook, client, place in line
        name = {it["seq"]: f"{it['playbook'] or '/'.join(it['candidates'])}:"
                           f"{it['env']['record']['client_context_id']}:{it['seq']}" for it in order}
        sched = SidingScheduler(self.hub.audit, {name[it["seq"]]: cls(it) for it in order})
        by_name = {name[it["seq"]]: it for it in order}
        ready = []
        self._busy = True
        try:
            for it in order:
                n = name[it["seq"]]
                r = sched.request_segment(n, n, it["env"]["record"]["to_agent"])
                if r["granted"]:
                    ready.append(it)
        finally:
            self._busy = False
        self._log("playbook.waiting_released", {"count": len(order), "why": why,
                                                "order": [name[it["seq"]] for it in order]})
        while ready:
            ready.sort(key=lambda it: (cls(it), it["seq"]))
            it = ready.pop(0)
            env = self._rebuild(it["env"])
            if it.get("playbook"):
                self._forced[env.envelope_id] = it["playbook"]
            self.hub.send(env)
            self._busy = True
            try:
                nxt = sched.release_segment(name[it["seq"]], env.to_agent)
            finally:
                self._busy = False
            if nxt:
                ready.append(by_name[nxt["resumed"]])

    # ------------------------------------------------------------- ending
    def end_by_owner(self, run_id: str, outcome: str, by: Optional[str]) -> dict:
        if run_id not in self.runs or self.runs[run_id]["status"] not in ("open", "held"):
            return {"ended": False, "reason": f"no open run {run_id!r}",
                    "open": self.open_runs()}
        self._end(run_id, outcome or "ended_by_owner", f"ended by {by or 'the owner'}")
        return {"ended": True, "run_id": run_id, "report": self.runs[run_id].get("report")}

    def _end(self, rid: str, outcome: str, reason: Optional[str]):
        run = self.runs[rid]
        run["status"] = outcome
        run["ended_at"] = time.time()
        if outcome == "completed":
            run["tail"] = True
        self._log("playbook.completed", {"playbook": run["playbook"], "run_id": rid,
                                         "client_context_id": run["ctx"], "outcome": outcome,
                                         "reason": reason, "steps": len(run["steps"])})
        # the report is written when the message being handled is finished,
        # so the acknowledgements of this run's last steps are on the log
        run["report_due"] = {"outcome": outcome, "reason": reason}
        if self._depth == 0:
            self._write_due_reports()
        dropped = self.parked.pop(rid, [])
        if dropped:
            self._log("playbook.entries_dropped", {
                "run_id": rid, "envelope_ids": [d["record"]["envelope_id"] for d in dropped],
                "reason": "the run ended while they waited"})
        for w in self.waiting:
            if w["why"] == f"after:{rid}":
                w["why"] = "ready"     # released at the end of the current message
        if self._depth == 0:
            self._release_waiting()

    # ------------------------------------------------------------ deciding
    def _resume(self, ws, decision_payload: dict):
        item = self.held.pop(ws.wait_id, None)
        if item is None:
            return "nothing held under this wait"
        d = decision_of(decision_payload)
        env = self._rebuild(item["env"])
        ctx = item["ctx"]
        fields = ws.original_payload
        if item["kind"] == "two_matches":
            choice = fields.get("playbook")
            if d == "cancel":
                self._log("playbook.start_dropped", {"client_context_id": ctx,
                                                     "envelope_id": env.envelope_id,
                                                     "candidates": item["candidates"],
                                                     "by": "your decision"})
                return "dropped"
            if d != "continue" or choice not in item["candidates"]:
                return self._rehold(env, item, f"choose one of {item['candidates']}")
            self._log("playbook.chosen", {"client_context_id": ctx, "envelope_id": env.envelope_id,
                                          "playbook": choice, "candidates": item["candidates"]})
            self._forced[env.envelope_id] = choice
            res = self.hub.send(env)
            return f"{choice} started; message {res.get('status') if isinstance(res, dict) else res}"
        # conflict
        old, new = item["open_run"], item["new"]
        first = fields.get("first")
        if d == "cancel":
            self.runs[old]["status"] = "open"
            self._log("playbook.sequenced", {"client_context_id": ctx, "first": item["open_playbook"],
                                             "dropped": new, "envelope_id": env.envelope_id,
                                             "by": "your decision"})
            self._deliver_parked(old)
            return f"{new} dropped; {item['open_playbook']} goes on"
        if d != "continue" or first not in (new, item["open_playbook"]):
            return self._rehold(env, item, f"first must be {new} or {item['open_playbook']}")
        self._log("playbook.sequenced", {"client_context_id": ctx, "first": first,
                                         "second": item["open_playbook"] if first == new else new,
                                         "envelope_id": env.envelope_id, "by": "your decision"})
        if first == new:
            self._end(old, "ended_by_your_sequencing", f"you put {new} first")
            self._forced[env.envelope_id] = new
            res = self.hub.send(env)
            return f"{new} started; {item['open_playbook']} ended by your decision " \
                   f"({res.get('status') if isinstance(res, dict) else res})"
        self.runs[old]["status"] = "open"
        self.counter += 1
        self.waiting.append({"env": self._keep(env), "playbook": new, "candidates": [new],
                             "why": f"after:{old}", "seq": self.counter, "since": time.time()})
        self._log("playbook.start_waiting", {"client_context_id": ctx, "envelope_id": env.envelope_id,
                                             "intent": env.intent, "candidates": [new],
                                             "reason": f"waits until {old} ends (your decision)"})
        self._deliver_parked(old)
        return f"{item['open_playbook']} goes on; {new} starts when it ends"

    def _deliver_parked(self, rid: str):
        for kept in self.parked.pop(rid, []):
            self.hub.send(self._rebuild(kept))

    def _rehold(self, env: Envelope, item: dict, why: str) -> str:
        if item["kind"] == "two_matches":
            self._hold_two_matches(env, item["candidates"])
        else:
            self.runs[item["open_run"]]["status"] = "open"
            self._hold_conflict(env, item["new"], item["open_run"])
        return f"not decided ({why}); held again"

    # ------------------------------------------------------------- reports
    def _write_due_reports(self):
        for rid, run in self.runs.items():
            run.pop("tail", None)
            due = run.pop("report_due", None)
            if due is None:
                continue
            try:
                run["report"] = self._write_report(rid, due["outcome"], due["reason"])
            except Exception as e:   # a report that cannot be written is said, never skipped
                self._log("after_action.failed", {"run_id": rid, "client_context_id": run["ctx"],
                                                  "error": f"{type(e).__name__}: {e}"})

    def _write_report(self, rid: str, outcome: str, reason: Optional[str]) -> dict:
        from .after_action import generate_report
        run = self.runs[rid]
        events = self.hub.audit.read()
        start = next((i for i, e in enumerate(events)
                      if e.get("kind") == "playbook.started" and e.get("run_id") == rid), 0)
        # from the run's start to now: the report is written when the
        # message that ended the run is finished, so this window holds the
        # run, what its last message set off, and their acknowledgements
        window = events[start:]
        steps = [s for s in run["steps"]]
        text = generate_report(window, run["playbook"], rid, run["ctx"], steps,
                               outcome=outcome, abort_reason=reason)
        decided, proposed = self._decisions_and_proposals(run, window)
        text += self._extra_sections(decided, proposed)
        os.makedirs(self.report_dir, exist_ok=True)
        path = os.path.join(self.report_dir, f"{rid}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        self._log("after_action.written", {"run_id": rid, "playbook": run["playbook"],
                                           "client_context_id": run["ctx"], "outcome": outcome,
                                           "path": path, "sha256": digest,
                                           "your_decisions": decided,
                                           "proposed_tuples": proposed})
        return {"path": path, "sha256": digest}

    def _decisions_and_proposals(self, run: dict, window: list[dict]):
        ctx = run["ctx"]
        mine = [e for e in window if e.get("client_context_id") == ctx]
        decided, proposed = [], []
        for e in mine:
            k = e.get("kind")
            if k == "hitl.decision.authorized":
                decided.append(f"{e.get('decision')} on {e.get('wait_id')} (agent {e.get('agent')})")
            elif k == "disclosure.declined":
                decided.append(f"declined held message {e.get('held_envelope_id') or e.get('envelope_id')}")
            elif k in ("playbook.chosen", "playbook.sequenced", "playbook.start_dropped"):
                decided.append(f"{k}: " + ", ".join(f"{x}={e.get(x)}" for x in
                                                    ("playbook", "first", "second", "dropped",
                                                     "candidates") if e.get(x)))
            elif k == "envelope.persisted" and e.get("intent") == "clarification.request":
                p = e.get("payload") or {}
                why = str(p.get("reason", ""))
                if "no tuple covers" in why:
                    said = p.get("verbatim") or p.get("message")
                    proposed.append(f"({e.get('from_agent')}: {why}"
                                    + (f"; the message: {said!r}" if said else "")
                                    + " -> ?) proposed, not ratified")
        return decided, proposed

    def _extra_sections(self, decided: list, proposed: list) -> str:
        lines = ["", "## playbook table",
                 f"- {self.table.status}: {self.table.status_line}",
                 f"- identity/playbooks.json sha256 {self.table.sha256}", "",
                 "## your signed decisions in this run (they win over the playbook as written)"]
        lines += [f"- {d}" for d in decided] or ["- none"]
        lines += ["", "## proposed tuples (an unlisted crossing was reached; for your ratification)"]
        lines += [f"- {p}" for p in proposed] or ["- none"]
        return "\n".join(lines) + "\n"
