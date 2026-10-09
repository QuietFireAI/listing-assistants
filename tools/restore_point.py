#!/usr/bin/env python3
"""restore_point.py - Operator CLI for Model Checkpoints & Daily Warm Restore Points.

Provides AWS-style snapshot and Windows System Restore Point controls for Nous Hermes:
  1. Capture automated daily warm restore points (start of business day).
  2. List available restore points, training updates, and the factory Golden Baseline.
  3. One-command hot-swap rollback if live model drift or bad habits are detected.
  4. Run the Golden Broker Exam to verify fiduciary compliance before activation.

Usage:
  python tools/restore_point.py --list                 # View all restore points and active pointer
  python tools/restore_point.py --snapshot             # Capture today's morning warm restore point
  python tools/restore_point.py --restore baseline     # Instant rollback to factory Golden Baseline
  python tools/restore_point.py --restore <point_id>   # Revert to a specific daily restore point
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dispatcher.model_checkpoint_manager import ModelCheckpointManager
from dispatcher.readable_logger import HumanReadableLogger


def main():
    parser = argparse.ArgumentParser(description="Manage model checkpoints and daily warm restore points.")
    parser.add_argument("--list", action="store_true", help="List all available restore points and active model.")
    parser.add_argument("--snapshot", action="store_true", help="Capture a new daily warm restore point.")
    parser.add_argument("--notes", type=str, default="Operator daily restore point", help="Notes for the snapshot.")
    parser.add_argument("--restore", type=str, metavar="CHECKPOINT_ID", help="Roll back active model to target ID.")
    parser.add_argument("--exam", type=str, metavar="CHECKPOINT_ID", help="Run Golden Broker Exam on a checkpoint.")

    args = parser.parse_args()

    logger = HumanReadableLogger(log_root=os.path.join(ROOT, "logs"))
    mgr = ModelCheckpointManager(logger=logger)

    if args.snapshot:
        entry = mgr.create_daily_restore_point(notes=args.notes)
        print(f"\n[OK] Captured Daily Warm Restore Point: '{entry['checkpoint_id']}'")
        print(f"     Source Model:  {entry['parent_id']}")
        print(f"     Status:        {entry['status']}")
        print(f"     Exam Passed:   {entry['exam_passed']} (Score: {entry['exam_score']}%)")
        print(f"     Created At:    {entry['created_at']}\n")
        return

    if args.restore:
        target = "baseline_v1.0.0" if args.restore.lower() in ("baseline", "golden") else args.restore
        try:
            res = mgr.rollback(target_id=target, reason=f"CLI rollback requested by operator to '{target}'")
            print(f"\n[OK] Hot-Swap Rollback Successful!")
            print(f"     Active Model Now:      {res['active_checkpoint_id']}")
            print(f"     Previous Model:        {res['previous_checkpoint_id']}")
            print(f"     Restored Target:       {res['restored_checkpoint']['checkpoint_id']} ({res['restored_checkpoint']['status']})\n")
        except Exception as e:
            print(f"\n[ERROR] Rollback failed: {e}\n", file=sys.stderr)
            sys.exit(1)
        return

    if args.exam:
        print(f"\nRunning Golden Broker Regression Exam on '{args.exam}'...")
        exam = mgr.run_broker_regression_exam()
        status_str = "PASSED" if exam["overall_passed"] else "FAILED"
        print(f"Exam Status: [{status_str}] (Score: {exam['score']}%)")
        print(f"Passed {exam['passed_count']} of {exam['total_questions']} compliance gates.")
        for d in exam["details"]:
            p_str = "PASS" if d["passed"] else "FAIL"
            print(f"  - [{p_str}] {d['exam_id']}: {d['expected']}")
        print()
        return

    # Default action: list checkpoints
    active = mgr.get_active_checkpoint()
    all_ck = mgr.list_checkpoints()

    print("\n" + "=" * 80)
    print("  LISTINGASSISTANTS — MODEL CHECKPOINTS & DAILY WARM RESTORE POINTS")
    print("  AWS-Style Snapshot & Windows System Restore Point Architecture")
    print("=" * 80)
    print(f"\n  ACTIVE INFERENCE MODEL: {active.get('checkpoint_id')} [{active.get('status')}]")
    print("  " + "-" * 76)

    for ck in all_ck:
        is_active = ck["checkpoint_id"] == active.get("checkpoint_id")
        active_marker = "==> [ACTIVE]" if is_active else "   "
        cid = ck["checkpoint_id"]
        status = ck["status"]
        score = ck.get("exam_score", 100.0)
        created = ck.get("created_at", "N/A")
        notes = ck.get("notes", "")

        print(f"{active_marker} ID:     {cid:<32} Status: [{status}]")
        print(f"       Exam:   {score}% Passed              Created: {created}")
        print(f"       Notes:  {notes}")
        print("  " + "-" * 76)

    print("\n[TIP] If live drift or bad habits appear, run: python tools/restore_point.py --restore baseline\n")


if __name__ == "__main__":
    main()
