#!/usr/bin/env python3
"""restore_point.py - operator CLI for the model checkpoint manifest.

Moves the active-checkpoint pointer in the checkpoint manifest and runs the
broker exam against a served model. It does not copy or load weights. Agent
04 reads the active pointer (dispatcher/model_drafting.py): it drafts with a
model only while the ACTIVE checkpoint passed the exam on that served model.

Usage:
  python tools/restore_point.py --list                 # checkpoints and the active pointer
  python tools/restore_point.py --snapshot             # record today's restore point
  python tools/restore_point.py --restore baseline     # point back at the baseline entry
  python tools/restore_point.py --restore <point_id>   # point back at a named entry
  python tools/restore_point.py --exam <new_id> --model-url http://localhost:11434/v1 --model-name <served model>
                                                       # ask the served model the four exam questions,
                                                       # record the graded answers, activate on a pass
  [--checkpoints-dir DIR]                              # default: <repo>/console-state/checkpoints

--exam without --model-url and --model-name refuses (exit 2): there is no
model to ask. Fixed 2026-10-11 (audit C-1): --exam graded a built-in
compliant sentence and printed PASSED 100% for any id. Since 2026-10-12 it
asks the served model and stores every answer for review.
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
    if os.name != "nt":
        os.umask(0o077)     # what this writes about clients is readable only by this account
    parser = argparse.ArgumentParser(description="Manage the model checkpoint manifest.")
    parser.add_argument("--list", action="store_true", help="List checkpoints and the active pointer.")
    parser.add_argument("--snapshot", action="store_true", help="Record today's restore point.")
    parser.add_argument("--notes", type=str, default="Operator daily restore point", help="Notes for the snapshot.")
    parser.add_argument("--restore", type=str, metavar="CHECKPOINT_ID", help="Point the active entry at this ID.")
    parser.add_argument("--exam", type=str, metavar="CHECKPOINT_ID",
                        help="Run the broker exam against the served model and register the result.")
    parser.add_argument("--model-url", help="OpenAI-style endpoint of the served model, e.g. http://localhost:11434/v1")
    parser.add_argument("--model-name", help="Model name as the server knows it")
    parser.add_argument("--allow-remote-model", action="store_true",
                        help="Allow a model endpoint that is not this machine (exam questions leave it)")
    parser.add_argument("--checkpoints-dir", default=os.path.join(ROOT, "console-state", "checkpoints"))
    args = parser.parse_args(argv)

    if args.exam:
        if not (args.model_url and args.model_name):
            print("[REFUSED] The exam asks a served model four questions; pass --model-url and\n"
                  "--model-name. Nothing was graded or recorded.", file=sys.stderr)
            return 2
        from dispatcher.model_drafting import DraftingModel, OpenAICompatibleClient
        try:
            client = OpenAICompatibleClient(args.model_url, allow_remote=args.allow_remote_model)
            dm = DraftingModel(None, client, args.model_name, args.checkpoints_dir)
            entry = dm.examine(args.exam)
        except Exception as e:
            print(f"[ERROR] exam not completed: {type(e).__name__}: {e}", file=sys.stderr)
            return 1
        print(f"\n[{'PASSED' if entry['exam_passed'] else 'FAILED'}] {entry['checkpoint_id']}: "
              f"{_exam_str(entry)} - status {entry['status']}")
        for d in (entry.get("exam_details") or {}).get("details", []):
            print(f"  {d['exam_id']}: {'pass' if d['passed'] else 'FAIL'}"
                  f"  prohibited={d['prohibited_found']} posture={d['posture_found']}")
        print("  (keyword screen; every answer is stored in the manifest for you to read)\n")
        return 0 if entry["exam_passed"] else 1

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
        print("     (manifest only - no weights loaded; Agent 04 drafts with a model only while the\n"
              "      active entry passed the exam on the served model)\n")
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
