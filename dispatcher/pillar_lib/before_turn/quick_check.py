#!/usr/bin/env python3
"""
quick_check.py - Before-turn self-reflection protocol

Read the last N reasoning steps from the current session transcript.
Run this BEFORE composing any response. Every turn. No exceptions.

The protocol is unconditional. If you find yourself reasoning about
whether to run it, run it first, then continue reasoning.

Usage:
    python scripts/quick_check.py --conversation-id <id> [--last-n 3]

The canonical failure mode:
    Skipping the check because "it just ran 1 minute ago."
    That is timing rationalization. It breaks the protocol.
    The fix: run it. Then proceed.
"""

import argparse
import json
from pathlib import Path

APP_DATA_DIR = Path.home() / ".gemini" / "antigravity"
BRAIN_DIR = APP_DATA_DIR / "brain"

BEFORE_TURN_QUESTIONS = [
    "Is my current reasoning consistent with where I was heading?",
    "Did I leave something unresolved that this turn should address?",
    "Is what I am about to say aligned with what I was actually thinking?",
    "Did I review the output from my last turn -- not just confirm it exists?",
]


def quick_check(conversation_id: str, last_n: int = 3) -> None:
    # Reject path traversal: the id is a single directory name, never a path.
    if any(sep in conversation_id for sep in ("/", "\\")) or conversation_id in (".", ".."):
        print(f"Invalid conversation ID (must be a plain directory name): {conversation_id!r}")
        return
    transcript = (
        BRAIN_DIR / conversation_id / ".system_generated" / "logs" / "transcript.jsonl"
    )
    if not transcript.exists():
        print(f"No transcript found at: {transcript}")
        print("Check the conversation ID and that the session has been run.")
        return

    thoughts = []
    for line in transcript.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            step = json.loads(line)
            if step.get("type") == "PLANNER_RESPONSE" and step.get("thinking", "").strip():
                thoughts.append({
                    "step": step["step_index"],
                    "thinking": step["thinking"].strip(),
                })
        except Exception:
            continue

    recent = thoughts[-last_n:] if thoughts else []
    total = len(thoughts)

    print(f"\nbefore-turn check | Last {len(recent)} of {total} thinking steps")
    print("=" * 64)

    for t in recent:
        print(f"\n[Step {t['step']}]")
        print(t["thinking"][:600])

    print("\n" + "=" * 64)
    print("\nNow answer these before responding:\n")
    for i, q in enumerate(BEFORE_TURN_QUESTIONS, 1):
        print(f"  {i}. {q}")

    print("\nThen respond.\n")


def main(argv=None) -> None:
    """Console entry point (referenced by [project.scripts] in pyproject.toml)."""
    parser = argparse.ArgumentParser(
        description="Before-turn self-reflection protocol",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--conversation-id",
        required=True,
        help="Current session conversation ID",
    )
    parser.add_argument(
        "--last-n",
        type=int,
        default=3,
        help="Number of recent thinking steps to review (default: 3)",
    )
    args = parser.parse_args(argv)
    quick_check(args.conversation_id, args.last_n)


if __name__ == "__main__":
    main()
