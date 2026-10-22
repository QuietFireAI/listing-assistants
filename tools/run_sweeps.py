#!/usr/bin/env python3
"""run_sweeps.py - the daily clock, run by your scheduler.

Builds the swarm through dispatcher/swarm.py from the SAME audit log and
state store your console sessions use, sends one clock.tick per agent
through the hub (dispatcher/sweep_runner.py), saves the state, and exits
nonzero if any check errored so the scheduler's own alerting fires.

Deployment (any ONE of these):
  cron:     0 7 * * *  cd /path/to/listing-assistants && python tools/run_sweeps.py
            0 18 * * * cd /path/to/listing-assistants && python tools/run_sweeps.py --evening
            (the evening clock: Agent 14's end-of-day books, with Agent 15's
            figures for the day, owner decision 9, 2026-10-21)
            */5 * * * *  cd /path/to/listing-assistants && python tools/run_sweeps.py --watch
            (the second re-alerts an escalation nobody has marked done at 30
            minutes and pages you at 60; once a day is too slow for that)
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

# Only attested source runs (2026-10-14): this process compiles its bytecode
# into a new private folder, set before any module of this repository is
# imported, so a .pyc planted beside a source file is never loaded. The
# folder is removed when the process ends; one left by a hard-killed run
# stays in the temp folder (no other run removes it: it could belong to a
# desk that is still running).
import atexit as _atexit, shutil as _shutil, tempfile as _tempfile  # noqa: E401,E402
if not getattr(sys, "_listing_fresh_bytecode", False):
    sys.pycache_prefix = _tempfile.mkdtemp(prefix="listing-pyc-")
    _atexit.register(_shutil.rmtree, sys.pycache_prefix, True)
    sys._listing_fresh_bytecode = True


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # the same state folder the console and the desk use: LISTINGASSISTANTS_
    # STATE_DIR when set (the Windows installer sets it, 2026-10-21)
    state = os.environ.get("LISTINGASSISTANTS_STATE_DIR") or os.path.join(root, "console-state")
    ap.add_argument("--audit-log", default=os.path.join(state, "console-audit.jsonl"))
    ap.add_argument("--state-db", default=os.path.join(state, "swarm-state.sqlite"))
    ap.add_argument("--config-dir", default=None)
    ap.add_argument("--today", default=None, help="ISO date override")
    ap.add_argument("--now-iso", default=None, help="ISO datetime override")
    ap.add_argument("--evening", action="store_true",
                    help="the evening clock: end-of-day books (14) with the day's figures (15)")
    ap.add_argument("--watch", action="store_true",
                    help="only re-alert unanswered escalations (run every few minutes)")
    args = ap.parse_args(argv)
    if os.name != "nt":
        # private by default (2026-10-14, integration snapshot finding 2):
        # the record, drawers and state are readable only by this account
        os.umask(0o077)

    # The single wall-clock read.
    now = datetime.datetime.now()
    today = args.today or now.date().isoformat()
    now_iso = args.now_iso or now.replace(microsecond=0).isoformat()

    # the install first, before anything else of this repository is loaded
    # (2026-10-14): the files, then the operator key and the log. It only
    # reads, so it is safe while a desk runs.
    from dispatcher.boot_attest import AttestationRefused, preflight
    state_dir = os.path.dirname(os.path.abspath(args.audit_log))
    try:
        preflight(state_dir, args.audit_log)
    except AttestationRefused as e:
        print(json.dumps({"error": "install not attested", "reason": str(e),
                          "action": "nothing was written; review the install, then run "
                                    "`python tools/console.py attest`"}))
        return 2
    except Exception as e:                      # a damaged or busy record, named below
        from dispatcher.core import AuditLogBusy, AuditLogDamaged
        if not isinstance(e, (AuditLogDamaged, AuditLogBusy)):
            raise
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from console import damaged_record_error
        print(json.dumps(damaged_record_error(e, args.audit_log)))
        return 2

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from console import damaged_record_error, desk_running, load_pager
    other = desk_running(os.path.dirname(os.path.abspath(args.audit_log)))
    if other:
        print(json.dumps({"error": f"the Broker Desk is running on this state (pid {other}); "
                                   f"use its 'Run today's checks' button, or stop it first"}))
        return 2
    from dispatcher.private_file import tighten_tree
    tighten_tree(state_dir)                 # a folder an earlier version left readable
    from dispatcher.sweep_runner import run_daily_sweeps, run_evening_sweep
    from dispatcher.swarm import build_swarm
    from dispatcher.state_snapshot import StateIntegrityError
    from dispatcher.core import AuditLogBusy, AuditLogDamaged
    try:
        pager = load_pager(os.path.dirname(os.path.abspath(args.audit_log)))
    except ValueError as e:
        print(json.dumps({"error": str(e)}))
        return 2
    from dispatcher.signatures import Ed25519Signer, Ed25519Verifier
    key = os.path.join(state_dir, "operator-key.bin")
    from dispatcher.boot_attest import fingerprint
    pub = Ed25519Signer(private_key_bytes=open(key, "rb").read()).public_key_bytes()
    verifier = Ed25519Verifier(pub)
    try:
        sw = build_swarm(args.audit_log, state_db=args.state_db, config_dir=args.config_dir,
                         verifier=verifier.verifier(),
                         human_notifier=pager,       # the pager, when on, texts you from the clock too
                         # the clock starts only on what the operator attested (2026-10-14)
                         attestation={"state_dir": state_dir, "verify_bytes": verifier.verify_bytes,
                                      "key_fingerprint": fingerprint(pub)})
    except AttestationRefused as e:
        print(json.dumps({"error": "install not attested", "reason": str(e),
                          "action": "nothing was written; review the install, then run "
                                    "`python tools/console.py attest`"}))
        return 2
    except StateIntegrityError as e:
        print(json.dumps({"error": "saved state refused", "reason": str(e)}))
        return 2
    except (AuditLogDamaged, AuditLogBusy) as e:
        print(json.dumps(damaged_record_error(e, args.audit_log)))
        return 2
    if pager:
        pager.audit = sw.hub.audit
    hub, spokes = sw.hub, sw.spokes
    try:
        if args.watch:
            from dispatcher.escalation_watch import check_unacknowledged
            results = [{"agent": "00", "sweep": "unacknowledged_escalations",
                        "result": check_unacknowledged(hub)}]
        elif args.evening:
            results = run_evening_sweep(hub, spokes, today=today, now_iso=now_iso)
        else:
            # a run on this machine's own clock is checked for skew; a run
            # with --today / --now-iso is a replay and is not
            results = run_daily_sweeps(hub, spokes, today=today, now_iso=now_iso,
                                       live=not (args.today or args.now_iso))
        sw.save_state()
    except (AuditLogDamaged, AuditLogBusy) as e:      # broke or changed while the clock ran
        print(json.dumps(damaged_record_error(e, args.audit_log)))
        return 2
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
