"""Boot attestation for this product (owner decision 2026-10-14).

MANNERS.md §Re-injection: "The file's content hash is registered at boot
attestation; a changed hash without signed authorization = tainted = halt."
Until 2026-10-14 boot attestation was never called here.

What is attested (repository-relative paths, SHA-256 of the raw bytes):
every file Python can import under dispatcher/ and tools/, outside
__pycache__ (.py, .pyc, .pyo, .so, .pyd, at any depth - so a package
folder, a compiled extension or a sourceless .pyc that Python would import
in place of a covered module is itself an unattested file; a .DS_Store or
an editor's swap file is not code and is not covered), everything in
identity/, MANNERS.md,
SWARM.md, docs/PLAYBOOKS.md, docs/JOB_DESCRIPTIONS.md, and each agent
folder's SKILL.md and DECISIONS.md - the resources identity/IDENTITY-*.md
declares as attested at boot. config/ is not covered: its files are the
broker's own business content, ratified through their _status line.

- `python tools/console.py init` attests the install it creates the key for.
- `python tools/console.py attest` re-attests after a reviewed change: it
  names what changed and signs the new manifest. Both write boot.attested
  (the manifest's hash and the key's fingerprint) to the audit chain.
  attest refuses a log last attested with another key; a replaced key is
  a deliberate step (`attest --new-key`) that records boot.key_changed.
- The console, the Broker Desk, the daily clock and console repair-record
  check first, in their main(), and refuse (AttestationRefused) when:
  there is no attestation; any covered file changed, appeared or
  disappeared; it is not signed by this operator's key; the audit log
  they are about to write was last attested with a different manifest (an
  old attestation put back) or a different key; or that log has entries
  from before attestation existed and has never been attested. The files
  are hashed before anything else of this repository is imported: only
  dispatcher/__init__.py and this module, besides the program that was
  started, run before the file check.
- A swarm built without a check (the tests, the showcase desk, the MCP
  server with no operator key) writes boot.attestation with enforced: false
  and the hash of what is running, so it is never silent.

Where the protection ends: this detects an unreviewed change made by
someone who is not trying to get round it (an update copied in, an edit, a
sync). Anyone who can write to the install can also change this checker,
the programs that call it, or use the key file next to it, and anyone who
can run `attest --new-key` on the log can take it over - visibly, as
boot.key_changed on the chain. It is drift detection with a signature,
not tamper resistance.
"""
from __future__ import annotations

import datetime
import glob
import hashlib
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ATTEST_FILE = "boot-attestation.json"
IMPORTABLE = (".py", ".pyc", ".pyo", ".so", ".pyd")
FIXED_FILES = ("MANNERS.md", "SWARM.md", "docs/PLAYBOOKS.md", "docs/JOB_DESCRIPTIONS.md")


class AttestationRefused(RuntimeError):
    pass


def covered_files(root: str = ROOT) -> list[str]:
    """Repository-relative paths, '/'-separated, sorted. A link is followed
    and its target's bytes are hashed (a linked module still runs); a link
    to nothing, such as an editor's lock file, is not a file to hash."""
    out = set()
    for top in ("dispatcher", "tools"):
        for dirpath, dirnames, filenames in os.walk(os.path.join(root, top), followlinks=True):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for name in filenames:
                p = os.path.join(dirpath, name)
                if name.endswith(IMPORTABLE) and os.path.isfile(p):
                    out.add(os.path.relpath(p, root).replace(os.sep, "/"))
    for pat in ("identity/*", "[0-9][0-9]-*/SKILL.md", "[0-9][0-9]-*/DECISIONS.md", *FIXED_FILES):
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


def attest(state_dir: str, signer, root: str = ROOT, audit_path: str | None = None,
           new_key: bool = False) -> dict:
    """Sign what is installed now; returns what changed since the last
    attestation (everything is 'added' the first time). A damaged
    attestation file is replaced. With audit_path, boot.attested goes on
    that chain, so an old attestation cannot be put back unnoticed; a log
    last attested with another key is refused unless new_key, which
    records boot.key_changed first."""
    path = os.path.join(state_dir, ATTEST_FILE)
    fp = fingerprint(signer.public_key_bytes())
    chain = _chain(audit_path)
    previous_key = chain["key"]
    if previous_key not in (None, fp) and not new_key:
        raise AttestationRefused(
            f"{audit_path} was last attested with another key ({previous_key}); this key is "
            f"{fp}. If you replaced your key, run `python tools/console.py attest --new-key`; "
            f"it records the change on the chain")
    if chain["entries"] and previous_key is None and not new_key:
        # 2026-10-14 third review: on a log from before attestation the first
        # key to attest won silently. Taking such a log is a recorded step.
        raise AttestationRefused(
            f"{audit_path} has entries from before boot attestation and no key yet. Taking it "
            f"with this key ({fp}) is recorded on the chain: run "
            f"`python tools/console.py attest --new-key`")
    try:
        _, old = _read(state_dir)
    except AttestationRefused:
        old = None
    manifest = current_manifest(root)
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
            log = AuditLog(audit_path)
            if new_key and previous_key != fp and (previous_key is not None or chain["entries"]):
                log.append("boot.key_changed", {"from_key": previous_key, "to_key": fp,
                                                "reason": "attest --new-key"})
            log.append("boot.attested", {
                "manifest_sha256": result["manifest_sha256"], "key_fingerprint": fp,
                "files": len(manifest), "changed": diff["changed"], "added": len(diff["added"]),
                "removed": diff["removed"]})
        except BaseException:
            os.remove(tmp)
            raise
    os.replace(tmp, path)
    return result


def _chain(audit_path: str | None) -> dict:
    """What the log about to be written says: whether it has entries, its
    last boot.attested, and the key of its most recent key-bearing entry
    (boot.attested or an enforced boot.attestation)."""
    out = {"entries": False, "attested": None, "key": None}
    if not audit_path or not os.path.exists(audit_path) or os.path.getsize(audit_path) == 0:
        return out
    from .core import AuditLog
    for e in AuditLog.reader(audit_path).read():
        out["entries"] = True
        k = e.get("kind")
        if k == "boot.attested":       # a key change is always followed by one
            out["attested"], out["key"] = e, e.get("key_fingerprint")
        elif k == "boot.attestation" and e.get("enforced") is True:
            out["key"] = e.get("key_fingerprint")
    return out


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
    # the files first, before any other module of this repository is
    # imported (the signature check below imports dispatcher.signatures)
    found = differences(doc["manifest"], root)
    if found:
        raise AttestationRefused(
            "the install differs from what was attested - tainted, not starting: "
            + "; ".join(found)
            + ". Review the change, then run `python tools/console.py attest`")
    if not verify_bytes(canonical(doc["manifest"]), doc["signature"]):
        raise AttestationRefused(
            f"{path} is not signed by this operator's key. Review the install, then run "
            f"`python tools/console.py attest`")
    msha = manifest_sha256(doc["manifest"])
    chain = _chain(audit_path)
    last_attested = chain["attested"]
    if chain["key"] not in (None, key_fingerprint):
        raise AttestationRefused(
            f"{audit_path} was attested with another key ({chain['key']}); this key is "
            f"{key_fingerprint}. Use the state folder that belongs to this log, or, if you "
            f"replaced your key, run `python tools/console.py attest --new-key`")
    if chain["entries"] and chain["key"] is None:
        raise AttestationRefused(
            f"{audit_path} has entries from before boot attestation and was never attested. "
            f"Review the install, then run `python tools/console.py attest --new-key "
            f"--audit-log {audit_path}`")
    if last_attested is not None and last_attested.get("manifest_sha256") != msha:
        raise AttestationRefused(
            f"{path} is not the attestation last recorded on {audit_path} (an older or "
            f"replaced one). Review the install, then run `python tools/console.py attest`")
    return {"attested_on": doc.get("attested_on"), "files": len(doc["manifest"]),
            "key_fingerprint": key_fingerprint, "manifest_sha256": msha}


def preflight(state_dir: str, audit_path: str | None = None) -> dict:
    """The whole check for a program's main(), before it imports anything
    else from this repository: the files are compared first (only this
    module and dispatcher/__init__.py have run), then the operator key in
    state_dir is loaded to check the signature and the log."""
    key_path = os.path.join(state_dir, "operator-key.bin")
    if not os.path.exists(key_path):
        raise AttestationRefused(f"no operator key at {key_path}: run "
                                 f"`python tools/console.py init` first")
    path, doc = _read(state_dir)
    if doc is None:
        raise AttestationRefused(
            f"this install is not attested (no {path}). Review it, then run "
            f"`python tools/console.py attest`")
    found = differences(doc["manifest"])
    if found:
        raise AttestationRefused(
            "the install differs from what was attested - tainted, not starting: "
            + "; ".join(found)
            + ". Review the change, then run `python tools/console.py attest`")
    from .signatures import Ed25519Signer, Ed25519Verifier
    with open(key_path, "rb") as f:
        pub = Ed25519Signer(private_key_bytes=f.read()).public_key_bytes()
    return check(state_dir, Ed25519Verifier(pub).verify_bytes, fingerprint(pub),
                 audit_path=audit_path)
