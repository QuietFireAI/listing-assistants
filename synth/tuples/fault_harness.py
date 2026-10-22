#!/usr/bin/env python3
"""Run a tuple session with one injected fault - for the tuples whose
crossing no product entry can produce (2026-10-15).

Some of the dispatcher's tuples are about failures: the audit log cannot be
written, the plain-language view fails, a page to the broker fails, a reply
never comes back, the same envelope arrives twice. The console takes only
real entries, so it cannot make these happen. This harness runs the same
session the console runs (the same build, the same apply_action) in one
process, and a line {"do": "fault", ...} injects one failure at that point.

It is a test harness: nothing in the product reads it. Its observations
that the audit log cannot hold (the log may be the thing that failed) go to
<state>/harness.jsonl, one JSON object per line, and the runner reads them
as audit-style entries of kind "harness.<what>".

    python synth/tuples/fault_harness.py <session.jsonl> --config-dir <dir>

Fault lines:
  {"do": "fault", "type": "audit_unwritable"}     every later audit write fails
  {"do": "fault", "type": "queue_overflow"}       every later human-queue append fails
  {"do": "fault", "type": "readable_view_fails"}  the plain-language view fails from here
  {"do": "fault", "type": "pager_fails", "status": "HTTP 401"}
                                                   the notifier reports a failed page
  {"do": "fault", "type": "no_record_response", "agent": "14"}
                                                   Agent 14 stops answering dedupe lookups
  {"do": "fault", "type": "send_raw", "envelope": {...}}
                                                   an envelope built as given (e.g. a
                                                   pre-filled sequence), straight to the hub
  {"do": "fault", "type": "send_twice", "line": {<a send line>}}
                                                   the same envelope (same id) sent twice
  {"do": "fault", "type": "inject_wait", "ctx": ..., "waiting_on": ...}
                                                   a briefing item whose source envelope
                                                   is not on the log
  {"do": "fault", "type": "advance_clock", "minutes": N}
                                                   the wall clock moves N minutes forward
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)

import console  # noqa: E402  (reads LISTINGASSISTANTS_STATE_DIR at import)


class Harness:
    def __init__(self, state_dir):
        self.path = os.path.join(state_dir, "harness.jsonl")
        self.clock_offset = 0.0

    def note(self, what: str, **rec):
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"kind": f"harness.{what}", **rec}, default=str) + "\n")


def apply_fault(h: Harness, sw, f: dict) -> dict:
    hub = sw.hub
    t = f.get("type")
    if t == "audit_unwritable":
        def broken(kind, rec):
            raise OSError("audit log unwritable (injected)")
        hub.audit.append = broken
        return {"injected": t}
    if t == "queue_overflow":
        # a full queue stays full: every later append to a human queue fails
        def overflow(*a, **k):
            raise MemoryError("queue cannot take another item (injected)")
        hub.queue_and_notify = overflow
        hub.escalate = overflow
        return {"injected": t}
    if t == "readable_view_fails":
        def broken_view(*a, **k):
            raise OSError("plain-language view unwritable (injected)")
        hub.audit.readable.log_event = broken_view
        return {"injected": t}
    if t == "pager_fails":
        status = f.get("status", "HTTP 401")
        hub.human_notifier = lambda queue, record: {"status": "failed", "error": status}
        return {"injected": t, "status": status}
    if t == "no_record_response":
        spoke = sw.spokes[f.get("agent", "14")]
        real = spoke.handle

        def silent(env):
            if env.intent == "record.request" and env.payload.get("dedupe_key") is not None:
                h.note("dropped", envelope_id=env.envelope_id, intent=env.intent,
                       client_context_id=env.client_context_id)
                return None
            return real(env)
        spoke.handle = silent
        hub.handlers[f.get("agent", "14")] = silent
        return {"injected": t}
    if t == "send_raw":
        from dispatcher.core import Envelope
        e = f["envelope"]
        env = Envelope(from_agent=e["from"], to_agent=e["to"], intent=e["intent"],
                       client_context_id=e.get("ctx", "harness"), payload=e.get("payload", {}),
                       sequence=e.get("sequence"),
                       provenance={"source": "external" if e["from"] == "external" else e["from"],
                                   "captured_at": "runtime", "verbatim_available": True})
        return {"injected": t, "result": hub.send(env)}
    if t == "send_twice":
        a = f["line"]
        env = console.make_env(a["from"], a["to"], a["intent"], a.get("ctx", "console"),
                               a.get("payload", {}))
        first, second = hub.send(env), hub.send(env)
        h.note("send_twice", envelope_id=env.envelope_id, first=first, second=second)
        return {"injected": t, "first": first, "second": second}
    if t == "inject_wait":
        # a briefing item whose source envelope is not on the log, as a wait
        # restored from saved state after its envelope was lost would be
        w = {"agent": f.get("agent", "07"), "ctx": f["ctx"], "waiting_on": f["waiting_on"],
             "since": f.get("since"), "wait_id": None, "reason": None,
             "source_envelope_id": f.get("source_envelope_id", "missing-envelope")}
        sw.spokes["18"].waiting[f"{w['agent']}:{w['ctx']}:{w['waiting_on']}"] = w
        return {"injected": t}
    if t == "advance_clock":
        h.clock_offset += 60.0 * float(f["minutes"])
        return {"injected": t, "offset_minutes": h.clock_offset / 60}
    raise ValueError(f"unknown fault type {t!r}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("--config-dir", default=None)
    args = ap.parse_args(argv)
    h = Harness(console.STATE_DIR)
    # the clock the product reads is time.time(); advance_clock moves it
    _real_time = time.time
    time.time = lambda: _real_time() + h.clock_offset
    sw, signer = console.build(console.AUDIT_PATH, args.config_dir, console.STATE_DB)
    operator = console._operator()
    errors = 0
    for lineno, line in enumerate(open(args.script, encoding="utf-8"), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        a = json.loads(line)
        if a.get("do") == "fault":
            r = apply_fault(h, sw, a)
            h.note("fault", line=lineno, **{k: v for k, v in r.items() if k != "result"},
                   result=r.get("result"))
            console._p({"line": lineno, "do": "fault", "result": r})
            continue
        try:
            r, err = console.apply_action(sw, signer, operator, a, sw.external)
        except Exception as e:   # what the product raised, verbatim
            h.note("raised", line=lineno, error=f"{type(e).__name__}: {e}")
            console._p({"line": lineno, "do": a.get("do"), "raised": f"{type(e).__name__}: {e}"})
            errors += 1
            continue
        if isinstance(r, dict) and r.get("status") == "halted":
            h.note("halted_result", line=lineno, reason=r.get("reason"))
        if err:
            errors += 1
        console._p({"line": lineno, "do": a.get("do"), "result": r})
    hub = sw.hub
    h.note("end", halted=hub.halted,
           system_halt_queue=hub.queues.get("escalation.system_halt", []),
           readable_log_errors=len(getattr(hub.audit, "mirror_errors", [])),
           mirror_errors=getattr(hub.audit, "mirror_errors", [])[:5])
    try:
        saved = sw.save_state()
    except Exception as e:   # with an unwritable log nothing may be saved; say so
        saved = {"not_saved": f"{type(e).__name__}: {e}"}
    console._p({"session_complete": True, "errors": errors, "state_saved": saved,
                "halted": hub.halted,
                "readable_log_errors": len(getattr(hub.audit, "mirror_errors", []))})
    return 0


if __name__ == "__main__":
    sys.exit(main())
