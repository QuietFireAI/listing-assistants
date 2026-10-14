#!/usr/bin/env python3
"""sync_core.py - the mechanism that replaces hand-copying.

Found live 2026-07-17: dispatcher-agents core received fixes
(queue_and_notify, resume_loop_suspension, the unarmed pillar path) that
listing-assistants' vendored dispatcher/ never got - 105 diff lines of fork
drift in hub.py alone, four silent-notification bugs still live there
after they were "fixed". The doctrine says vendored copies are generated
from core, never hand-copied; until this file existed there was no
generator, so every sync WAS a hand-copy.

The same file ships in every identity repo (listing, freight, medbilling,
claim, hr, enrollment, practice, mortgage, property-mgmt); it compares
the repo it sits in, or --target, against a dispatcher-agents checkout.

Usage:
  python tools/sync_core.py --core ../dispatcher-agents          # sync
  python tools/sync_core.py --core ../dispatcher-agents --check  # CI gate

--check exits 1 on any drift and prints per-file diff-line counts.

The pin (owner decision D1, 2026-10-14): CORE_PIN.json at the repo root
names the exact dispatcher-agents commit these files came from. A sync
writes it, and refuses when the core checkout has uncommitted changes in
dispatcher/ (the pin would name a commit that is not what was copied).
--check also compares the core checkout's commit with the pin: a mismatch
is printed as a note, and --require-pin makes it fail. --print-pin prints the pinned
commit for CI to check out. CI checks listing against its pin, not
against whatever core main is today, so a core merge never turns listing
red, and a release names the core it ships.
Never syncs identity-owned files (*_spokes*.py, identity_mcp.py,
sweep_runner.py stay untouched);
never deletes; core is the single source for exactly the files below.
"""
import argparse
import datetime
import difflib
import filecmp
import json
import os
import shutil
import subprocess
import sys

# The vendored core surface. Identity files (*_spokes*.py and the like) are
# deliberately absent - they are owned by the identity repo, not by core.
# absolute_signal.py added 2026-10-12: hub.py imports it, so a core without
# it does not boot.
CORE_FILES = [
    "__init__.py", "absolute_signal.py", "after_action.py", "analysis.py",
    "attestation.py",
    "core.py", "hub.py", "kpi.py", "loader.py", "notifier.py",
    "pillars.py", "priority.py", "runs.py", "signatures.py",
    "signer_registry.py", "territory.py",
]


PIN_FILE = "CORE_PIN.json"


def _git(core, *args):
    r = subprocess.run(["git", "-C", core, *args], capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


class PinError(ValueError):
    pass


def read_pin(target):
    """The pin, None when there is none; PinError when the file is not a pin
    (2026-10-14 cold review: a damaged file gave a traceback)."""
    path = os.path.join(target, PIN_FILE)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            pin = json.load(f)
        commit = pin["commit"]
    except (ValueError, KeyError, TypeError) as e:
        raise PinError(f"{path} is not a valid pin ({type(e).__name__}: {e}) - "
                       f"a sync (tools/sync_core.py --core <path>) rewrites it") from None
    if not isinstance(commit, str) or not commit:
        raise PinError(f"{path} names no commit - a sync (tools/sync_core.py --core <path>) rewrites it")
    return pin


def main() -> int:
    try:
        return _main()
    except PinError as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 2


def _main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--core", default=None,
                    help="path to a dispatcher-agents checkout (required except with --print-pin)")
    ap.add_argument("--check", action="store_true",
                    help="report drift and exit 1; change nothing")
    ap.add_argument("--target", default=None,
                    help="identity repo to sync INTO (default: this "
                         "script's own repo)")
    ap.add_argument("--require-pin", action="store_true",
                    help="with --check: fail unless the core checkout is at the pinned commit")
    ap.add_argument("--print-pin", action="store_true",
                    help="print the pinned core commit and exit")
    args = ap.parse_args()
    if args.print_pin:
        here = os.path.abspath(args.target) if args.target else \
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pin = read_pin(here)
        if not pin:
            print(f"FATAL: no {PIN_FILE} in {here}", file=sys.stderr)
            return 2
        print(pin["commit"])
        return 0
    if not args.core:
        ap.error("--core is required")

    # Fixed 2026-07-18, caught in the act: this resolved the target from
    # __file__, so invoking listing-agents' copy from inside ANOTHER
    # identity repo silently checked listing-agents against core and
    # reported THAT as the other repo's status - a drift checker that
    # checks the wrong repo and says "clean" is worse than no checker.
    # Target is now explicit, and the tool PRINTS what it compared so a
    # wrong invocation is visible in the output, not just the exit code.
    here = os.path.abspath(args.target) if args.target else \
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print(f"comparing target={here} against core={os.path.abspath(args.core)}")
    src_dir = os.path.join(os.path.abspath(args.core), "dispatcher")
    dst_dir = os.path.join(here, "dispatcher")
    if not os.path.isdir(src_dir):
        print(f"FATAL: {src_dir} is not a directory - fail closed, "
              f"syncing from nothing is not a sync", file=sys.stderr)
        return 2

    drifted = []
    for name in CORE_FILES:
        src, dst = os.path.join(src_dir, name), os.path.join(dst_dir, name)
        if not os.path.exists(src):
            print(f"FATAL: core is missing {name} - refusing to continue "
                  f"(a shrinking core surface is a question for a human, "
                  f"not a silent skip)", file=sys.stderr)
            return 2
        if not os.path.exists(dst) or not filecmp.cmp(src, dst, shallow=False):
            n = "new"
            if os.path.exists(dst):
                # difflib, not the diff program: Windows has none (2026-10-14)
                a = open(dst, encoding="utf-8", errors="replace").read().splitlines()
                b = open(src, encoding="utf-8", errors="replace").read().splitlines()
                n = str(sum(1 for l in difflib.unified_diff(a, b, lineterm="", n=0)
                            if l[:1] in "+-" and l[:3] not in ("+++", "---")))
            drifted.append((name, n))

    rc, head = _git(args.core, "rev-parse", "HEAD")
    head = head if rc == 0 else None

    if args.check:
        pin = read_pin(here)                 # a damaged pin fails the check
        pinned = pin["commit"] if pin else None
        if pinned != head:
            if args.require_pin:
                print(f"PIN MISMATCH: {PIN_FILE} names core {pinned}, the core checkout is at {head}")
                return 1
            # without --require-pin only the files are compared; say so
            # rather than pass a different commit silently (2026-10-14)
            print(f"note: {PIN_FILE} names core {pinned}, the core checkout is at {head}; "
                  f"comparing files only (--require-pin makes this fail)")
        if drifted:
            print("CORE DRIFT DETECTED (vendored copy lags core):")
            for name, n in drifted:
                print(f"  {name}: {n} diff lines")
            print("Run: python tools/sync_core.py --core <path>")
            return 1
        print(f"sync_core --check: {len(CORE_FILES)} files, zero drift"
              + (f" (core {head[:12]}, pinned {str(pinned)[:12]})" if head else ""))
        return 0

    if head is None:
        print(f"FATAL: {args.core} is not a git checkout - the pin needs a commit",
              file=sys.stderr)
        return 2
    rc, dirty = _git(args.core, "status", "--porcelain", "--", "dispatcher")
    if dirty:
        print(f"FATAL: the core checkout has uncommitted changes in dispatcher/ - commit "
              f"them first, so {PIN_FILE} names what is copied:\n{dirty}", file=sys.stderr)
        return 2

    # read the pin before copying anything: a damaged pin is rewritten by this
    # sync, never left behind next to freshly copied files (2026-10-14
    # second review: the sync copied, then failed on the damaged pin)
    try:
        pin = read_pin(here) or {}
    except PinError as e:
        print(f"note: {e}; this sync rewrites it")
        pin = {}
    for name, _ in drifted:
        shutil.copy2(os.path.join(src_dir, name), os.path.join(dst_dir, name))
        print(f"synced: {name}")
    if not drifted:
        print("already in sync - nothing copied")
    if pin.get("commit") != head:
        _, branch = _git(args.core, "rev-parse", "--abbrev-ref", "HEAD")
        pin = {"repo": "https://github.com/QuietFireAI/dispatcher-agents",
               "commit": head, "branch_at_sync": branch,
               "synced_on": datetime.date.today().isoformat(),
               "files": len(CORE_FILES)}
        with open(os.path.join(here, PIN_FILE), "w", encoding="utf-8") as f:
            json.dump(pin, f, indent=1)
            f.write("\n")
        print(f"{PIN_FILE}: core {head}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
