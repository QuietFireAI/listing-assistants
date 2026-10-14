"""Boot attestation for this product (owner decision 2026-10-14).

MANNERS.md §Re-injection: "The file's content hash is registered at boot
attestation; a changed hash without signed authorization = tainted = halt."
Until 2026-10-14 boot attestation was never called here.

What is attested: every .py file in dispatcher/ (the vendored core and this
identity's agents), identity/routes.json and MANNERS.md - the core's
dispatcher/attestation.py manifest. The broker signs the manifest with the
console's operator key; it is kept in boot-attestation.json in the console
state folder.

- `python tools/console.py init` attests the install it creates the key for.
- `python tools/console.py attest` re-attests after a reviewed change (an
  offline update pack, a core sync): it names what changed and signs the
  new manifest.
- The console, the Broker Desk and the daily clock check it before they
  write anything: no attestation, a signature that does not verify with
  this operator's key, or any file that differs from what was attested
  stops them with the reason (AttestationRefused). On a match the swarm
  writes boot.attestation (enforced: true) to the chain.
- A swarm built without a check (the tests, the MCP server) writes
  boot.attestation with enforced: false and the hash of what is running,
  so it is never silent.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os

from .attestation import build_manifest, verify_manifest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ATTEST_FILE = "boot-attestation.json"


class AttestationRefused(RuntimeError):
    pass


def _paths(root: str):
    return (os.path.join(root, "dispatcher"), os.path.join(root, "identity", "routes.json"),
            [os.path.join(root, "MANNERS.md")])


def current_manifest(root: str = ROOT) -> dict:
    pkg, routes, extra = _paths(root)
    return build_manifest(pkg, routes, extra)


def canonical(manifest: dict) -> bytes:
    return json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")


def manifest_sha256(manifest: dict) -> str:
    return hashlib.sha256(canonical(manifest)).hexdigest()


def _read(state_dir: str):
    path = os.path.join(state_dir, ATTEST_FILE)
    if not os.path.exists(path):
        return path, None
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        if not isinstance(doc.get("manifest"), dict) or not isinstance(doc.get("signature"), str):
            raise ValueError("manifest or signature missing")
    except (ValueError, OSError) as e:
        raise AttestationRefused(f"{path} is damaged ({e}); review the install, then run "
                                 f"`python tools/console.py attest`") from None
    return path, doc


def changes(old: dict, new: dict) -> dict:
    return {"changed": sorted(k for k in new if k in old and old[k] != new[k]),
            "added": sorted(k for k in new if k not in old),
            "removed": sorted(k for k in old if k not in new)}


def attest(state_dir: str, signer, root: str = ROOT) -> dict:
    """Sign what is installed now. Returns what changed since the last
    attestation (everything is 'added' the first time). A damaged
    attestation file is replaced."""
    path = os.path.join(state_dir, ATTEST_FILE)
    try:
        _, old = _read(state_dir)
    except AttestationRefused:
        old = None
    manifest = current_manifest(root)
    doc = {"manifest": manifest,
           "signature": signer.sign_bytes(canonical(manifest)),
           "key_fingerprint": hashlib.sha256(signer.public_key_bytes()).hexdigest()[:16],
           "attested_on": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)
    return {"path": path, "files": len(manifest), "manifest_sha256": manifest_sha256(manifest),
            **changes(old["manifest"] if old else {}, manifest)}


def check(state_dir: str, verify_bytes, root: str = ROOT) -> dict:
    """Refuse (AttestationRefused) unless what is installed is exactly what
    this operator's key attested. verify_bytes(data, signature_hex) -> bool."""
    path, doc = _read(state_dir)
    if doc is None:
        raise AttestationRefused(
            f"this install is not attested (no {path}). Review it, then run "
            f"`python tools/console.py attest`")
    if not verify_bytes(canonical(doc["manifest"]), doc["signature"]):
        raise AttestationRefused(
            f"{path} is not signed by this operator's key. Review the install, then run "
            f"`python tools/console.py attest`")
    pkg, routes, extra = _paths(root)
    violations = verify_manifest(doc["manifest"], pkg, routes, extra)
    if violations:
        raise AttestationRefused(
            "the install differs from what was attested - tainted, not starting: "
            + "; ".join(violations)
            + ". Review the change, then run `python tools/console.py attest`")
    return {"attested_on": doc.get("attested_on"), "files": len(doc["manifest"]),
            "key_fingerprint": doc.get("key_fingerprint"),
            "manifest_sha256": manifest_sha256(doc["manifest"])}
