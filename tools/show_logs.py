#!/usr/bin/env python3
"""show_logs.py - Human-Readable Log Stream & Daily EOD Ledger Viewer.

Reads what the console's swarm writes (2026-10-12): the plain-language
stream at console-state/readable/stream.log, and the hash-chained audit log
console-state/console-audit.jsonl, from which the end-of-day ledger is built
and verified.

Usage:
  python tools/show_logs.py                  # last 25 plain-language events
  python tools/show_logs.py --tail 50        # last 50
  python tools/show_logs.py --client <id>    # one client's events
  python tools/show_logs.py --eod            # today's end-of-day ledger, from the chain, chain verified
  python tools/show_logs.py --eod --date 2026-10-12 --audit-log <other audit log>
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# Locate root
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dispatcher.readable_logger import HumanReadableLogger

STATE_DIR = os.path.join(ROOT, "console-state")


def main():
    parser = argparse.ArgumentParser(description="View human-readable operational logs and EOD ledger.")
    parser.add_argument("--tail", type=int, default=25, help="Number of recent log lines to display (default: 25)")
    parser.add_argument("--client", help="Filter logs by client context ID")
    parser.add_argument("--eod", action="store_true", help="Compile and display today's End-of-Day operations ledger")
    parser.add_argument("--date", help="Specific date for EOD report (YYYY-MM-DD)")
    parser.add_argument("--audit-log", help="audit log to build the EOD ledger from "
                                            "(default: console-state/console-audit.jsonl)")
    parser.add_argument("--log-dir", default=os.path.join(STATE_DIR, "readable"),
                        help="plain-language log folder (default: console-state/readable)")
    args = parser.parse_args()

    logger = HumanReadableLogger(log_root=args.log_dir, drawers_root=None)

    if args.eod:
        from dispatcher.core import AuditLog
        from dispatcher.readable_audit import write_eod
        path = args.audit_log or os.path.join(STATE_DIR, "console-audit.jsonl")
        if not os.path.exists(path):
            if args.audit_log:
                print(f"[ERROR] audit log not found: {path}", file=sys.stderr)
                return 1
            print(f"\n[INFO] No console audit log yet ({path}); run a console session first.\n")
            return 0
        from dispatcher.core import AuditLogDamaged
        try:
            report = write_eod(AuditLog(path), logger, args.date)
        except AuditLogDamaged as e:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from console import damaged_record_error
            print(json.dumps(damaged_record_error(e, path)))
            return 2
        print("\n" + "=" * 80)
        print(f"  END-OF-DAY (EOD) OPERATIONS DOSSIER: {report['date']}")
        print("=" * 80)
        print(f"  Report File: {report['report_file']}")
        print(f"  Total Events Logged: {report['total_events']}")
        print("-" * 80)
        print(report["markdown"])
        print("=" * 80 + "\n")
        return 0

    log_path = logger.stream_path
    if not os.path.exists(log_path):
        print(f"\n[INFO] Real-time log stream '{log_path}' is currently empty. No events logged yet.\n")
        return 0

    with open(log_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    if args.client:
        lines = [line for line in lines if f"[Client: {args.client}]" in line or args.client in line]

    print("\n================================================================================")
    print(f"  REAL-TIME OPERATIONAL LOG STREAM (Showing last {min(args.tail, len(lines))} of {len(lines)} events)")
    print("================================================================================")
    if not lines:
        print("  (No log events matching criteria)")
    else:
        for line in lines[-args.tail:]:
            print(f"  {line}")
    print("================================================================================\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
