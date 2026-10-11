#!/usr/bin/env python3
"""verify_update_pack.py - offline update-pack verifier (Ed25519 + SHA-256).

Verifies an update bundle delivered to an offline appliance (for example on
an encrypted USB drive) BEFORE anything from it is copied into place.

Pack layout (build it with tools/sign_manifest.py):
  pack_dir/
    manifest.json   {"version": "1.2.0", "files": {"rel/path": "<sha256>", ...}}
    signature.sig   hex Ed25519 signature over the exact bytes of manifest.json
    payload/        the files named in the manifest - and nothing else

A pack is valid only when ALL of these hold:
  1. signature.sig verifies against the authority public key you pass
     (--pubkey). There is no environment-variable bypass.
  2. every manifest path is a plain relative path inside payload/ (no
     absolute paths, no '..'), and every listed file's SHA-256 matches.
  3. payload/ contains no file the manifest does not list. Fixed 2026-10-11
     (audit A-2): unlisted files were ignored, and the install step copies the
     whole payload/ directory, so an unsigned file rode along.
  4. with --installed-version, the manifest version is strictly newer
     (blocks replaying an older signed pack to downgrade).

--dev-bypass skips ONLY the signature check, for staging without keys. The
result then says signature_verified=False and the CLI prints NOT VERIFIED;
it is never reported as a verified pack.

Fixed 2026-10-11 (audit A-1, A-3): the CLI could not take a public key, so a
correctly signed pack always failed; and ALLOW_INSECURE_DEV_UPDATE=1 in the
environment silently disabled signature checks.

Usage:
  python tools/verify_update_pack.py PACK_DIR --pubkey authority.pub [--installed-version 1.1.0]
  python tools/verify_update_pack.py PACK_DIR --dev-bypass
  python tools/verify_update_pack.py --guide
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dispatcher.signatures import Ed25519Verifier  # noqa: E402


def compute_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def _version_tuple(v) -> tuple:
    parts = str(v).split(".")
    if not parts or not all(p.isdigit() for p in parts):
        raise ValueError(f"version {v!r} is not dotted integers (e.g. 1.2.0)")
    return tuple(int(p) for p in parts)


def load_pubkey(path: str) -> bytes:
    """Accepts a 32-byte raw key file or a file holding 64 hex characters."""
    with open(path, "rb") as f:
        data = f.read()
    text = data.strip()
    if len(text) == 64:
        try:
            return bytes.fromhex(text.decode("ascii"))
        except (UnicodeDecodeError, ValueError):
            pass
    if len(data) == 32:
        return data
    raise ValueError(f"{path}: expected a 32-byte raw Ed25519 public key or 64 hex characters")


def _payload_files(payload_dir: str) -> set[str]:
    found = set()
    for dirpath, _dirs, files in os.walk(payload_dir):
        for name in files:
            full = os.path.join(dirpath, name)
            found.add(os.path.relpath(full, payload_dir).replace(os.sep, "/"))
    return found


def verify_update_pack(pack_dir: str, authority_pubkey_bytes: bytes | None = None,
                       dev_bypass: bool = False, installed_version: str | None = None) -> dict:
    results = {"valid": False, "signature_verified": False, "errors": [],
               "manifest": None, "verified_files": []}
    manifest_path = os.path.join(pack_dir, "manifest.json")
    sig_path = os.path.join(pack_dir, "signature.sig")
    payload_dir = os.path.join(pack_dir, "payload")

    if not os.path.exists(manifest_path):
        results["errors"].append("Missing manifest.json in update package")
        return results
    try:
        with open(manifest_path, "rb") as f:
            manifest_raw = f.read()
        manifest = json.loads(manifest_raw.decode("utf-8"))
        results["manifest"] = manifest
    except Exception as e:
        results["errors"].append(f"Invalid manifest.json: {e}")
        return results

    # 1. signature
    if dev_bypass:
        results["errors_ignored_by_dev_bypass"] = ["signature not checked"]
    else:
        if not os.path.exists(sig_path):
            results["errors"].append("Missing signature.sig")
            return results
        if not authority_pubkey_bytes:
            results["errors"].append("No authority public key provided (--pubkey)")
            return results
        try:
            with open(sig_path, "r", encoding="utf-8") as f:
                sig_hex = f.read().strip()
            if not Ed25519Verifier(authority_pubkey_bytes).verify_bytes(manifest_raw, sig_hex):
                results["errors"].append("Signature verification failed: manifest modified or untrusted key")
                return results
            results["signature_verified"] = True
        except Exception as e:
            results["errors"].append(f"Cryptographic verification error: {e}")
            return results

    # 2. version / downgrade
    try:
        new_v = _version_tuple(manifest.get("version"))
        if installed_version is not None and new_v <= _version_tuple(installed_version):
            results["errors"].append(
                f"Downgrade/replay refused: pack version {manifest.get('version')} is not "
                f"newer than installed {installed_version}")
    except ValueError as e:
        results["errors"].append(str(e))

    # 3. listed files: safe paths + hashes
    files_to_check = manifest.get("files")
    if not isinstance(files_to_check, dict) or not files_to_check:
        results["errors"].append("manifest.files must be a non-empty {path: sha256} map")
        return results
    real_payload = os.path.realpath(payload_dir)
    for rel_path, expected_hash in files_to_check.items():
        if (not isinstance(rel_path, str) or os.path.isabs(rel_path) or "\\" in rel_path
                or any(seg in ("", ".", "..") for seg in rel_path.split("/"))):
            results["errors"].append(f"Unsafe manifest path refused: {rel_path!r}")
            continue
        full_path = os.path.realpath(os.path.join(payload_dir, rel_path))
        if not full_path.startswith(real_payload + os.sep):
            results["errors"].append(f"Manifest path escapes payload/: {rel_path!r}")
            continue
        if not os.path.isfile(full_path):
            results["errors"].append(f"Payload file missing: {rel_path}")
            continue
        actual_hash = compute_sha256(full_path)
        if actual_hash.lower() != str(expected_hash).lower():
            results["errors"].append(f"Hash mismatch on {rel_path}: expected {expected_hash}, got {actual_hash}")
        else:
            results["verified_files"].append(rel_path)

    # 4. nothing unlisted
    extra = sorted(_payload_files(payload_dir) - set(files_to_check)) if os.path.isdir(payload_dir) else []
    for rel in extra:
        results["errors"].append(f"Unlisted file in payload/ (not signed): {rel}")

    results["valid"] = not results["errors"]
    return results


def print_operator_guide():
    print("""
OFFLINE UPDATE PROCEDURE
Staging workstation (holds the authority PRIVATE key):
  1. Put the updated files under my_update/payload/ (paths mirror the install tree).
  2. python tools/sign_manifest.py my_update --private-key authority.key --version 1.2.0
     (writes my_update/manifest.json + my_update/signature.sig)
  3. Copy my_update/ to the transport drive.
Appliance (holds only the PUBLIC key):
  1. python tools/verify_update_pack.py /media/drive/my_update --pubkey authority.pub --installed-version 1.1.0
  2. Only on exit code 0, copy payload/ into the install directory.
  3. Re-run the test suite and the audit-chain check (python tools/console.py verify).
Key generation (once, on the staging workstation):
  python tools/sign_manifest.py --keygen authority   (writes authority.key and authority.pub)
""")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Verify an offline update package.")
    parser.add_argument("pack_dir", nargs="?", help="Path to update package directory")
    parser.add_argument("--pubkey", help="Authority Ed25519 public key file (raw 32 bytes or 64 hex chars)")
    parser.add_argument("--installed-version", help="Currently installed version; pack must be newer")
    parser.add_argument("--dev-bypass", action="store_true",
                        help="Skip the signature check (staging only; never reported as verified)")
    parser.add_argument("--guide", action="store_true", help="Print the operator procedure")
    args = parser.parse_args(argv)

    if args.guide or not args.pack_dir:
        print_operator_guide()
        return 0
    try:
        pubkey = load_pubkey(args.pubkey) if args.pubkey else None
    except (OSError, ValueError) as e:
        print(f"[FAIL] {e}")
        return 1
    res = verify_update_pack(args.pack_dir, authority_pubkey_bytes=pubkey,
                             dev_bypass=args.dev_bypass, installed_version=args.installed_version)
    if res["valid"] and res["signature_verified"]:
        print(f"[OK] Signature verified; {len(res['verified_files'])} files intact; nothing unlisted.")
        return 0
    if res["valid"] and args.dev_bypass:
        print(f"[NOT VERIFIED - DEV BYPASS] Signature NOT checked. Hashes match for "
              f"{len(res['verified_files'])} listed files; nothing unlisted. Do not install in production.")
        return 3
    print("[FAIL] Package verification failed:")
    for err in res["errors"]:
        print(f"  - {err}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
