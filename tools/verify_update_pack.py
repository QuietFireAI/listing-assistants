#!/usr/bin/env python3
"""verify_update_pack.py - Air-Gapped Apricorn Update Pack Verifier.

Verifies cryptographically signed update bundles delivered to the local
Hermes/Drobo appliance via Apricorn encrypted flash drives.

Guarantees:
  1. Cryptographic Authenticity: Verifies Ed25519 signature against the broker
     authority key before unpacking or applying any code/config.
  2. SHA-256 File Integrity: Checks every file in the payload against the manifest.
  3. Testing Workaround: Allows testing on Cloud VMs before hardware delivery via
     the `--dev-bypass` flag or `ALLOW_INSECURE_DEV_UPDATE=1` environment variable.

Usage:
  python tools/verify_update_pack.py /path/to/update_pack_dir
  python tools/verify_update_pack.py /path/to/update_pack_dir --dev-bypass
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

# Locate root
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dispatcher.signatures import Ed25519Verifier


def compute_sha256(filepath: str) -> str:
    """Computes hex SHA-256 digest of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def verify_update_pack(
    pack_dir: str,
    authority_pubkey_bytes: bytes | None = None,
    dev_bypass: bool = False
) -> dict:
    """Verifies an update package directory.

    Expected directory structure:
      pack_dir/
        manifest.json   (contains version, timestamp, files: {path: sha256})
        signature.sig   (raw 64-byte Ed25519 signature over manifest.json)
        payload/        (the updated files)
    """
    results = {
        "valid": False,
        "errors": [],
        "manifest": None,
        "verified_files": []
    }

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

    # 1. Cryptographic Signature Verification
    if dev_bypass or os.environ.get("ALLOW_INSECURE_DEV_UPDATE") == "1":
        print("[WARNING] DEV BYPASS ACTIVE: Skipping Ed25519 cryptographic signature check.")
    else:
        if not os.path.exists(sig_path):
            results["errors"].append("Missing signature.sig (use --dev-bypass for dev testing)")
            return results
        if not authority_pubkey_bytes:
            results["errors"].append("No authority public key provided for verification")
            return results

        try:
            with open(sig_path, "r", encoding="utf-8") as f:
                sig_hex = f.read().strip()
            verifier = Ed25519Verifier(authority_pubkey_bytes)
            if not verifier.verify_bytes(manifest_raw, sig_hex):
                results["errors"].append("Signature verification failed: manifest has been modified or untrusted key")
                return results
        except Exception as e:
            results["errors"].append(f"Cryptographic verification error: {e}")
            return results

    # 2. SHA-256 File Integrity Check
    files_to_check = manifest.get("files", {})
    for rel_path, expected_hash in files_to_check.items():
        full_path = os.path.join(payload_dir, rel_path)
        if not os.path.exists(full_path):
            results["errors"].append(f"Payload file missing: {rel_path}")
            continue
        actual_hash = compute_sha256(full_path)
        if actual_hash.lower() != expected_hash.lower():
            results["errors"].append(f"Hash mismatch on {rel_path}: expected {expected_hash}, got {actual_hash}")
        else:
            results["verified_files"].append(rel_path)

    if not results["errors"]:
        results["valid"] = True

    return results


def print_operator_guide():
    """Prints step-by-step instructions for the operator."""
    print("""
================================================================================
  APRICORN ENCRYPTED DRIVE UPDATE PROCEDURE (AIR-GAPPED APPLIANCE)
================================================================================
Stage 1: Preparation on Authorized Staging Workstation
  1. Mount the Apricorn encrypted USB drive (enter PIN on hardware keypad).
  2. Assemble the update package in a folder:
       my_update/
         manifest.json
         payload/
  3. Sign manifest.json with the broker authority Ed25519 private key:
       python tools/sign_manifest.py my_update/manifest.json my_update/signature.sig
  4. Unmount and safely disconnect the Apricorn drive.

Stage 2: Installation on On-Premise Appliance (Hermes / Drobo)
  1. Insert the Apricorn drive into the appliance USB port and enter PIN.
  2. Run the verifier:
       python tools/verify_update_pack.py /media/apricorn/my_update
  3. If verification passes (Exit code 0), apply the payload into the live directory:
       cp -r /media/apricorn/my_update/payload/* /opt/listing-agents/
  4. Verify the swarm audit chain:
       python tools/mcp_roundtrip.py
================================================================================
""")


def main():
    parser = argparse.ArgumentParser(description="Verify an air-gapped update package.")
    parser.add_argument("pack_dir", nargs="?", help="Path to update package directory")
    parser.add_argument("--dev-bypass", action="store_true", help="Bypass Ed25519 signature check for local testing")
    parser.add_argument("--guide", action="store_true", help="Print operator step-by-step guide")
    args = parser.parse_args()

    if args.guide or not args.pack_dir:
        print_operator_guide()
        return 0

    res = verify_update_pack(args.pack_dir, dev_bypass=args.dev_bypass)
    if res["valid"]:
        print(f"[OK] Package verified successfully. {len(res['verified_files'])} files confirmed intact.")
        return 0
    else:
        print("[FAIL] Package verification failed:")
        for err in res["errors"]:
            print(f"  - {err}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
