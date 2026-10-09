#!/usr/bin/env python3
"""show_logs.py - Human-Readable Log Stream & Daily EOD Ledger Viewer.

Usage:
  python tools/show_logs.py                  # Shows recent 25 real-time operational events
  python tools/show_logs.py --tail 50        # Shows last 50 events
  python tools/show_logs.py --client <id>    # Shows events for a specific client
  python tools/show_logs.py --eod            # Compiles and displays the End-of-Day Ledger
"""
from __future__ import annotations

import argparse
import os
import sys

# Locate root
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dispatcher.readable_logger import HumanReadableLogger, get_readable_logger


def main():
    parser = argparse.ArgumentParser(description="View human-readable operational logs and EOD ledger.")
    parser.add_argument("--tail", type=int, default=25, help="Number of recent log lines to display (default: 25)")
    parser.add_argument("--client", help="Filter logs by client context ID")
    parser.add_argument("--eod", action="store_true", help="Compile and display today's End-of-Day operations ledger")
    parser.add_argument("--date", help="Specific date for EOD report (YYYY-MM-DD)")
    args = parser.parse_args()

    logger = get_readable_logger()

    if args.eod:
        report = logger.generate_eod_report(date_str=args.date)
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
