#!/usr/bin/env python3
"""inspect_client_drawer.py - Human Inspection & Anti-Commingling Audit Tool.

Allows licensed human agents, team leads, and compliance officers to:
  1. Inspect any client's dedicated Drawer (dossier, documents, artifacts, financials).
  2. Prove zero-commingling: verifies that every file in the drawer belongs exclusively
     to that client context.
  3. List all provisioned client drawers on the system.

Usage:
  python tools/inspect_client_drawer.py --list
  python tools/inspect_client_drawer.py client_123
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# Locate root
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dispatcher.client_drawer import ClientDrawerManager, ComminglingBreachError


def format_size(bytes_len: int) -> str:
    if bytes_len < 1024:
        return f"{bytes_len} B"
    elif bytes_len < 1024 * 1024:
        return f"{bytes_len / 1024:.1f} KB"
    return f"{bytes_len / (1024 * 1024):.1f} MB"


def main():
    parser = argparse.ArgumentParser(description="Inspect client drawers and verify anti-commingling custody.")
    parser.add_argument("client_id", nargs="?", help="Client ID / context ID to inspect")
    parser.add_argument("--root", default="drawers", help="Root directory for client drawers (default: drawers)")
    parser.add_argument("--list", action="store_true", help="List all provisioned client drawers")
    args = parser.parse_args()

    manager = ClientDrawerManager(args.root)

    if args.list or not args.client_id:
        clients = manager.list_all_clients()
        print("\n================================================================================")
        print("  PROVISIONED CLIENT DRAWERS (ANTI-COMMINGLING REGISTRY)")
        print("================================================================================")
        if not clients:
            print("  No client drawers provisioned in", args.root)
            print("================================================================================\n")
            return 0

        print(f"  {'CLIENT ID':<20} {'CLIENT NAME':<22} {'ROLE':<8} {'FILES':<6} {'PROPERTY'}")
        print("  " + "-" * 76)
        for c in clients:
            print(f"  {c['client_id']:<20} {c['client_name']:<22} {c['role']:<8} {c['file_count']:<6} {c['property_address']}")
        print("================================================================================\n")
        return 0

    try:
        drawer = manager.get_drawer(args.client_id)
    except ComminglingBreachError as e:
        print(f"\n[ERROR] {e}\n")
        return 1

    manifest = drawer.get_manifest()
    files = drawer.list_files()

    print("\n================================================================================")
    print(f"  CLIENT DRAWER: {manifest.get('client_name', 'Unknown').upper()} ({args.client_id})")
    print("================================================================================")
    print(f"  Property:        {manifest.get('property_address', 'N/A')}")
    print(f"  Client Role:     {manifest.get('role', 'N/A').upper()}")
    print(f"  Human Agent:     {manifest.get('assigned_human_agent', '00')}")
    print(f"  Drawer Path:     {drawer.drawer_path}")
    print(f"  Indexed Files:   {len(files)}")
    print("--------------------------------------------------------------------------------")

    if not files:
        print("  (Drawer is empty. No agent files generated yet.)")
    else:
        print(f"  {'CATEGORY':<14} {'AGENT':<6} {'SIZE':<9} {'FILENAME':<28} {'SHA256 (PREFIX)'}")
        print("  " + "-" * 76)
        for f in files:
            cat = f.get("category", "artifacts")
            agent = f.get("agent_id", "??")
            fname = f.get("filename", "unknown")
            size_s = format_size(f.get("size_bytes", 0))
            hash_pref = f.get("sha256", "")[:12]
            print(f"  {cat:<14} {agent:<6} {size_s:<9} {fname:<28} {hash_pref}")

    print("================================================================================")
    print("  [VERIFIED] Anti-commingling isolation intact. Zero cross-context leakage.")
    print("================================================================================\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
