#!/usr/bin/env python3
"""manage_hitl_queue.py - Human-In-The-Loop wait-state inspection CLI.

Lists the wait-states recorded in client drawer timelines
(drawers/<client_id>/timeline/<wait_id>_pause.json). The record's status is
updated when a decision is applied, so a resolved wait no longer lists as
PENDING.

What this tool does NOT do: apply decisions. A decision must be a signed
'hitl.decision.authority' envelope applied by the running process that holds
the hub and the wait (HITLManager.resume_operation). A standalone CLI has no
access to that process, so --decide refuses with an explanation and a nonzero
exit. Fixed 2026-10-11 (audit HITL-1): --decide previously printed
"[SUCCESS] ... Agent resumed." without doing anything, even for wait ids
that did not exist.

Usage:
  python tools/manage_hitl_queue.py --list [--client CLIENT_ID] [--root DRAWERS_DIR]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def list_pending(drawers_root: str, client: str | None) -> list[dict]:
    pending = []
    if not os.path.isdir(drawers_root):
        return pending
    for c in sorted(os.listdir(drawers_root)):
        if client and c != client:
            continue
        t_dir = os.path.join(drawers_root, c, "timeline")
        if not os.path.isdir(t_dir):
            continue
        for f in sorted(os.listdir(t_dir)):
            if f.endswith("_pause.json"):
                with open(os.path.join(t_dir, f), "r", encoding="utf-8") as jf:
                    data = json.load(jf)      # a corrupt record is an error, not skipped
                if data.get("status") == "PENDING":
                    pending.append(data)
    return pending


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="List pending HITL wait-states recorded in client drawers.")
    parser.add_argument("--list", action="store_true", help="List pending human decisions (default)")
    parser.add_argument("--client", help="Filter by client context ID")
    parser.add_argument("--root", default=os.path.join(ROOT, "drawers"), help="Drawer root directory")
    parser.add_argument("--decide", help=argparse.SUPPRESS)
    parser.add_argument("--decision", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.decide:
        print("[REFUSED] This CLI cannot apply decisions.\n"
              "A decision must be a signed 'hitl.decision.authority' envelope applied by the\n"
              "running process that holds the hub and the wait "
              "(HITLManager.resume_operation).\nNothing was recorded.", file=sys.stderr)
        return 2

    pending = list_pending(args.root, args.client)
    print("\n  HUMAN-IN-THE-LOOP PENDING DECISIONS (from drawer timelines)")
    print("  " + "-" * 76)
    if not pending:
        print("  (No PENDING wait-state records found under " + args.root + ")")
    for p in pending:
        print(f"  {p['wait_id']:<40} {p['client_context_id']:<16} agent {p['agent_id']:<4} {p['required_decision']}")
        print(f"    Reason: {p['reason']}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
