#!/usr/bin/env python3
"""run_sweeps.py - the daily clock, run by your scheduler.

Builds the swarm through dispatcher/swarm.py from the SAME audit log and
state store your console sessions use, sends one clock.tick per agent
through the hub (dispatcher/sweep_runner.py), saves the state, and exits
nonzero if any check errored so the scheduler's own alerting fires.

Deployment (any ONE of these):
  cron:     0 7 * * *  cd /path/to/listing-assistants && python tools/run_sweeps.py
  systemd:  a timer unit invoking the same command
  console:  {"do": "sweep", "today": "..."} inside a session script

Defaults match the console: console-state/console-audit.jsonl and
console-state/swarm-state.sqlite. If the saved state does not match the
audit log (see dispatcher/state_snapshot.py), nothing runs and the exit
code is 2.

Clock discipline: this process reads the wall clock exactly once and hands
that timestamp to every check. --today / --now-iso override it for replay.

Changed 2026-10-11 (owner decision #12): before the state store existed,
this CLI built an empty swarm, so a scheduled run found nothing to check.
"""
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--audit-log", default=os.path.join(root, "console-state", "console-audit.jsonl"))
    ap.add_argument("--state-db", default=os.path.join(root, "console-state", "swarm-state.sqlite"))
    ap.add_argument("--config-dir", default=None)
    ap.add_argument("--today", default=None, help="ISO date override")
    ap.add_argument("--now-iso", default=None, help="ISO datetime override")
    args = ap.parse_args(argv)

    # The single wall-clock read.
    now = datetime.datetime.now()
    today = args.today or now.date().isoformat()
    now_iso = args.now_iso or now.replace(microsecond=0).isoformat()

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from console import desk_running, load_pager
    other = desk_running(os.path.dirname(os.path.abspath(args.audit_log)))
    if other:
        print(json.dumps({"error": f"the Broker Desk is running on this state (pid {other}); "
                                   f"use its 'Run today's checks' button, or stop it first"}))
        return 2
    from dispatcher.sweep_runner import run_daily_sweeps
    from dispatcher.swarm import build_swarm
    from dispatcher.state_snapshot import StateIntegrityError
    try:
        pager = load_pager(os.path.dirname(os.path.abspath(args.audit_log)))
    except ValueError as e:
        print(json.dumps({"error": str(e)}))
        return 2
    try:
        sw = build_swarm(args.audit_log, state_db=args.state_db, config_dir=args.config_dir,
                         human_notifier=pager)       # the pager, when on, texts you from the clock too
    except StateIntegrityError as e:
        print(json.dumps({"error": "saved state refused", "reason": str(e)}))
        return 2
    if pager:
        pager.audit = sw.hub.audit
    hub, spokes = sw.hub, sw.spokes
    results = run_daily_sweeps(hub, spokes, today=today, now_iso=now_iso)
    sw.save_state()
    errors = 0
    for r in results:
        print(json.dumps(r))
        if r.get("error"):
            errors += 1
    print(json.dumps({"sweeps": len(results), "errors": errors,
                      "today": today, "anchor": hub.audit.anchor()}))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
