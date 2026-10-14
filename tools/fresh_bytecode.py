"""Run only attested source (2026-10-14 review): Python loads a module's
cached bytecode (__pycache__/*.pyc) when its timestamp and size match the
source, so a planted .pyc could run code the attestation never saw. The
console, the Broker Desk and the daily clock call use_fresh_bytecode()
before importing anything from dispatcher/: bytecode is then compiled into
a new private folder for this process only, and removed when it exits."""
import atexit
import shutil
import sys
import tempfile


def use_fresh_bytecode() -> None:
    if getattr(sys, "_listing_fresh_bytecode", False):
        return
    sys.pycache_prefix = tempfile.mkdtemp(prefix="listing-pyc-")
    atexit.register(shutil.rmtree, sys.pycache_prefix, True)
    sys._listing_fresh_bytecode = True
