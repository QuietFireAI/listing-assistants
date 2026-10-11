#!/usr/bin/env python3
"""restore_point.py - operator CLI for the model checkpoint manifest.

Moves the active-checkpoint pointer in checkpoints/checkpoint_manifest.json.
It does not copy or load model weights, and nothing in the runtime reads the
pointer yet (see dispatcher/model_checkpoint_manager.py).

Usage:
  python tools/restore_point.py --list                 # checkpoints and the active pointer
  python tools/restore_point.py --snapshot             # record today's restore point
  python tools/restore_point.py --restore baseline     # point back at the baseline entry
  python tools/restore_point.py --restore <point_id>   # point back at a named entry
  [--checkpoints-dir DIR]                              # default: <repo>/checkpoints

--exam refuses (exit 2): the exam needs a responder that queries the
checkpoint's model, and this CLI has no model loader. Run
ModelCheckpointManager.run_broker_regression_exam(responder) from the code
that serves the model. Fixed 2026-10-11 (audit C-1): --exam graded a
built-in compliant sentence and printed PASSED 100% for any id.
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dispatcher.model_checkpoint_manager import ModelCheckpointManager  # noqa: E402
from dispatcher.readable_logger import HumanReadableLogger  # noqa: E402


def _exam_str(ck: dict) -> str:
    if ck.get("exam_score") is None:
        return "not run"
    return f"{ck['exam_score']}% ({'passed' if ck.get('exam_passed') else 'failed'})"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Manage the model checkpoint manifest.")
    parser.add_argument("--list", action="store_true", help="List checkpoints and the active pointer.")
    parser.add_argument("--snapshot", action="store_true", help="Record today's restore point.")
    parser.add_argument("--notes", type=str, default="Operator daily restore point", help="Notes for the snapshot.")
    parser.add_argument("--restore", type=str, metavar="CHECKPOINT_ID", help="Point the active entry at this ID.")
    parser.add_argument("--exam", type=str, metavar="CHECKPOINT_ID", help=argparse.SUPPRESS)
    parser.add_argument("--checkpoints-dir", default=os.path.join(ROOT, "checkpoints"))
    args = parser.parse_args(argv)

    if args.exam:
        print("[REFUSED] The regression exam needs a responder that queries the checkpoint's model;\n"
              "this CLI has no model loader. Call\n"
              "ModelCheckpointManager.run_broker_regression_exam(responder) from the code that serves\n"
              "the model. Nothing was graded or recorded.", file=sys.stderr)
        return 2

    logger = HumanReadableLogger(log_root=os.path.join(ROOT, "logs"))
    mgr = ModelCheckpointManager(checkpoints_dir=args.checkpoints_dir, logger=logger)

    if args.snapshot:
        try:
            entry = mgr.create_daily_restore_point(notes=args.notes)
        except ValueError as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            return 1
        print(f"\n[OK] Recorded restore point '{entry['checkpoint_id']}' -> {entry['parent_id']}")
        print(f"     Exam:       {_exam_str(entry)} (copied from {entry['parent_id']})")
        print(f"     Created at: {entry['created_at']}\n")
        return 0

    if args.restore:
        target = "baseline_v1.0.0" if args.restore.lower() in ("baseline", "golden") else args.restore
        try:
            res = mgr.rollback(target_id=target, reason=f"CLI rollback requested by operator to '{target}'")
        except Exception as e:
            print(f"\n[ERROR] Rollback failed: {e}\n", file=sys.stderr)
            return 1
        print(f"\n[OK] Active pointer moved: {res['previous_checkpoint_id']} -> {res['active_checkpoint_id']}")
        print("     (manifest only - no weights loaded; nothing in the runtime reads this pointer yet)\n")
        return 0

    active = mgr.get_active_checkpoint()
    print("\n" + "=" * 80)
    print("  LISTINGASSISTANTS - MODEL CHECKPOINT MANIFEST")
    print("=" * 80)
    print(f"\n  ACTIVE POINTER: {active.get('checkpoint_id')} [{active.get('status')}]")
    print("  " + "-" * 76)
    for ck in mgr.list_checkpoints():
        marker = "==> [ACTIVE]" if ck["checkpoint_id"] == active.get("checkpoint_id") else "   "
        print(f"{marker} ID:     {ck['checkpoint_id']:<32} Status: [{ck['status']}]")
        print(f"       Exam:   {_exam_str(ck):<24} Created: {ck.get('created_at', 'N/A')}")
        print(f"       Notes:  {ck.get('notes', '')}")
        print("  " + "-" * 76)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
