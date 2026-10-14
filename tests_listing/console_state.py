"""Set up a console state folder the way `python tools/console.py init` does:
an operator key and a signed attestation of this install (2026-10-14: the
console, the Broker Desk and the daily clock refuse to start without one)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def init_state(state_dir):
    from dispatcher.boot_attest import attest
    from dispatcher.private_file import write_private
    from dispatcher.signatures import Ed25519Signer
    os.makedirs(state_dir, exist_ok=True)
    signer = Ed25519Signer()
    write_private(os.path.join(str(state_dir), "operator-key.bin"), signer.private_key_bytes())
    attest(str(state_dir), signer)
    return signer
