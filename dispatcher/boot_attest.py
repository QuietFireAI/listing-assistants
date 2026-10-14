"""Boot attestation for this product (owner decision 2026-10-14).

MANNERS.md §Re-injection: "The file's content hash is registered at boot
attestation; a changed hash without signed authorization = tainted = halt."
Until 2026-10-14 boot attestation was never called here.

What is attested (repository-relative paths, SHA-256 of the raw bytes):
every .py file in dispatcher/ (the vendored core and this identity's
agents), the three programs that start the swarm and check this
(tools/console.py, desk.py, run_sweeps.py and tools/fresh_bytecode.py),
everything in identity/, MANNERS.md, SWARM.md, docs/PLAYBOOKS.md,
docs/JOB_DESCRIPTIONS.md, and each agent folder's SKILL.md and
DECISIONS.md - the resources identity/IDENTITY-*.md declares as attested
at boot. config/ is not covered: its files are the broker's own business
content, ratified through their _status line.

- `python tools/console.py init` attests the install it creates the key for.
- `python tools/console.py attest` re-attests after a reviewed change: it
  names what changed and signs the new manifest. Both write boot.attested
  (the manifest's hash and the key's fingerprint) to the audit chain.
- The console, the Broker Desk, the daily clock and console repair-record
  check before writing anything, and refuse (AttestationRefused) when:
  there is no attestation; it is not signed by this operator's key; any
  covered file changed, appeared or disappeared; the audit log they are
  about to write was last attested with a different manifest (an old
  attestation put back) or a different key.
- A swarm built without a check (the tests, the showcase desk, the MCP
  server with no operator key) writes boot.attestation with enforced: false
  and the hash of what is running, so it is never silent.

Where the protection ends: this detects an unreviewed change made by
someone who is not trying to get round it (an update copied in, an edit, a
sync). Anyone who can write to the install can also change this checker,
the programs that call it, or use the key file next to it. It is drift
detection with a signature, not tamper resistance.
"""
from __future__ import annotations

import datetime
import glob
import hashlib
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ATTEST_FILE = "boot-attestation.json"
CHECKED_TOOLS = ("tools/console.py", "tools/desk.py", "tools/run_sweeps.py",
                 "tools/fresh_bytecode.py")
FIXED_FILES = ("MANNERS.md", "SWARM.md", "docs/PLAYBOOKS.md", "docs/JOB_DESCRIPTIONS.md")


class AttestationRefused(RuntimeError):
    pass


def covered_files(root: str = ROOT) -> list[str]:
    """Repository-relative paths, '/'-separated, sorted. A link is followed
    and its target's bytes are hashed (a linked module still runs); a link
    to nothing, such as an editor's lock file, is not a file to hash."""
    pats = ["dispatcher/*.py", "identity/*", "[0-9][0-9]-*/SKILL.md",
            "[0-9][0-9]-*/DECISIONS.md", *CHECKED_TOOLS, *FIXED_FILES]
    out = set()
    for pat in pats:
        for p in glob.glob(os.path.join(root, pat)):
            if os.path.isfile(p):
                out.add(os.path.relpath(p, root).replace(os.sep, "/"))
    return sorted(out)


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def current_manifest(root: str = ROOT) -> dict:
    return {rel: _sha256(os.path.join(root, rel)) for rel in covered_files(root)}


def canonical(manifest: dict) -> bytes:
    return json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")


def manifest_sha256(manifest: dict) -> str:
    return hashlib.sha256(canonical(manifest)).hexdigest()


def fingerprint(public_key_bytes: bytes) -> str:
    return hashlib.sha256(public_key_bytes).hexdigest()[:16]


def _read(state_dir: str):
    path = os.path.join(state_dir, ATTEST_FILE)
    if not os.path.exists(path):
        return path, None
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        if not isinstance(doc, dict) or not isinstance(doc.get("manifest"), dict) \
                or not isinstance(doc.get("signature"), str):
            raise ValueError("not an attestation (manifest or signature missing)")
    except (ValueError, OSError) as e:
        raise AttestationRefused(f"{path} is damaged ({e}); review the install, then run "
                                 f"`python tools/console.py attest`") from None
    return path, doc


def changes(old: dict, new: dict) -> dict:
    return {"changed": sorted(k for k in new if k in old and old[k] != new[k]),
            "added": sorted(k for k in new if k not in old),
            "removed": sorted(k for k in old if k not in new)}


def differences(attested: dict, root: str = ROOT) -> list[str]:
    current = current_manifest(root)
    d = changes(attested, current)
    return ([f"{p}: changed since it was attested" for p in d["changed"]]
            + [f"{p}: not attested" for p in d["added"]]
            + [f"{p}: attested, now missing" for p in d["removed"]])


def attest(state_dir: str, signer, root: str = ROOT, audit_path: str | None = None) -> dict:
    """Sign what is installed now; returns what changed since the last
    attestation (everything is 'added' the first time). A damaged
    attestation file is replaced. With audit_path, boot.attested goes on
    that chain, so an old attestation cannot be put back unnoticed."""
    path = os.path.join(state_dir, ATTEST_FILE)
    try:
        _, old = _read(state_dir)
    except AttestationRefused:
        old = None
    manifest = current_manifest(root)
    fp = fingerprint(signer.public_key_bytes())
    doc = {"manifest": manifest,
           "signature": signer.sign_bytes(canonical(manifest)),
           "key_fingerprint": fp,
           "attested_on": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    diff = changes(old["manifest"] if old else {}, manifest)
    result = {"path": path, "files": len(manifest), "manifest_sha256": manifest_sha256(manifest),
              "key_fingerprint": fp, **diff}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
        f.write("\n")
    if audit_path is not None:
        # on the chain first: if the record cannot take it, the attestation
        # file is left as it was
        from .core import AuditLog
        try:
            AuditLog(audit_path).append("boot.attested", {
                "manifest_sha256": result["manifest_sha256"], "key_fingerprint": fp,
                "files": len(manifest), "changed": diff["changed"], "added": len(diff["added"]),
                "removed": diff["removed"]})
        except BaseException:
            os.remove(tmp)
            raise
    os.replace(tmp, path)
    return result


def _chain(audit_path: str | None):
    """The last boot.attested and the last enforced boot.attestation on the
    log about to be written, if it exists."""
    if not audit_path or not os.path.exists(audit_path) or os.path.getsize(audit_path) == 0:
        return None, None
    from .core import AuditLog
    attested = enforced = None
    for e in AuditLog.reader(audit_path).read():
        if e.get("kind") == "boot.attested":
            attested = e
        elif e.get("kind") == "boot.attestation" and e.get("enforced") is True:
            enforced = e
    return attested, enforced


def check(state_dir: str, verify_bytes, key_fingerprint: str, root: str = ROOT,
          audit_path: str | None = None) -> dict:
    """Refuse (AttestationRefused) unless what is installed is exactly what
    this operator's key attested, and the log about to be written agrees.
    verify_bytes(data, signature_hex) -> bool."""
    path, doc = _read(state_dir)
    if doc is None:
        raise AttestationRefused(
            f"this install is not attested (no {path}). Review it, then run "
            f"`python tools/console.py attest`")
    if not verify_bytes(canonical(doc["manifest"]), doc["signature"]):
        raise AttestationRefused(
            f"{path} is not signed by this operator's key. Review the install, then run "
            f"`python tools/console.py attest`")
    found = differences(doc["manifest"], root)
    if found:
        raise AttestationRefused(
            "the install differs from what was attested - tainted, not starting: "
            + "; ".join(found)
            + ". Review the change, then run `python tools/console.py attest`")
    msha = manifest_sha256(doc["manifest"])
    last_attested, last_enforced = _chain(audit_path)
    for e in (last_attested, last_enforced):
        if e is not None and e.get("key_fingerprint") not in (None, key_fingerprint):
            raise AttestationRefused(
                f"{audit_path} was attested with another key ({e['key_fingerprint']}); this "
                f"key is {key_fingerprint}. Use the state folder that belongs to this log")
    if last_attested is not None and last_attested.get("manifest_sha256") != msha:
        raise AttestationRefused(
            f"{path} is not the attestation last recorded on {audit_path} (an older or "
            f"replaced one). Review the install, then run `python tools/console.py attest`")
    return {"attested_on": doc.get("attested_on"), "files": len(doc["manifest"]),
            "key_fingerprint": key_fingerprint, "manifest_sha256": msha}
