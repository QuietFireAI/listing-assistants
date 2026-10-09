#!/usr/bin/env python3
"""snapshot_drawer.py - Forensic Snapshot & Operational Diagnostic Tool.

Allows an operator or agent to capture an instant 'screenshot'/snapshot of:
  - Active wait-state and stoppage reason
  - Complete client drawer file inventory with SHA-256 digests
  - Alert notification history
  - Diagnostic environment data

Exports both a structured JSON bundle and a human-readable Markdown report
that can be provided directly to technical support or used for forensic audit.

Usage:
  python tools/snapshot_drawer.py <client_id> [--notes "Reason for ticket"]
"""
from __future__ import annotations

import argparse
import os
import sys

# Locate root
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dispatcher.client_drawer import ClientDrawerManager
from dispatcher.hitl_protocol import HITLManager


def main():
    parser = argparse.ArgumentParser(description="Capture forensic snapshot of a client drawer.")
    parser.add_argument("client_id", help="Client context ID to snapshot (e.g. ctx-listing-742)")
    parser.add_argument("--wait-id", help="Specific wait ID if known", default=None)
    parser.add_argument("--notes", help="Operator or support notes", default="Diagnostic capture by operator")
    args = parser.parse_args()

    drawers_root = os.path.join(ROOT, "drawers")
    if not os.path.exists(drawers_root):
        print(f"[ERROR] Drawers root '{drawers_root}' does not exist.")
        return 1

    drawer_mgr = ClientDrawerManager(drawers_root)
    if not drawer_mgr.has_drawer(args.client_id):
        print(f"[ERROR] Client drawer '{args.client_id}' not found in {drawers_root}.")
        return 1

    hitl = HITLManager(drawer_manager=drawer_mgr)
    snapshot = hitl.create_forensic_snapshot(
        client_context_id=args.client_id,
        wait_id=args.wait_id,
        notes=args.notes
    )

    print("\n" + "=" * 80)
    print(f"  FORENSIC DIAGNOSTIC SNAPSHOT GENERATED: {snapshot['snapshot_id']}")
    print("=" * 80)
    print(f"  Client ID:       {args.client_id}")
    print(f"  JSON Artifact:   {snapshot.get('json_path')}")
    print(f"  Markdown Report: {snapshot.get('markdown_path')}")
    print("-" * 80)
    print(snapshot["markdown_content"])
    print("=" * 80 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
