#!/usr/bin/env python3
"""sign_manifest.py - build and sign an offline update pack (staging side).

Hashes EVERY file under PACK_DIR/payload/ into PACK_DIR/manifest.json and
signs the manifest bytes with the authority Ed25519 private key into
PACK_DIR/signature.sig. Verify on the appliance with
tools/verify_update_pack.py --pubkey.

Usage:
  python tools/sign_manifest.py --keygen authority          # writes authority.key / authority.pub (hex)
  python tools/sign_manifest.py PACK_DIR --private-key authority.key --version 1.2.0

The private key file stays on the staging workstation. Only the .pub file
goes to appliances.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dispatcher.signatures import Ed25519Signer  # noqa: E402
from tools.verify_update_pack import compute_sha256, _payload_files, _version_tuple  # noqa: E402


def keygen(prefix: str) -> tuple[str, str]:
    signer = Ed25519Signer()
    key_path, pub_path = f"{prefix}.key", f"{prefix}.pub"
    if os.path.exists(key_path):
        raise FileExistsError(f"{key_path} exists - refusing to overwrite a private key")
    fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(signer.private_key_bytes().hex())
    with open(pub_path, "w", encoding="utf-8") as f:
        f.write(signer.public_key_bytes().hex())
    return key_path, pub_path


def build_and_sign(pack_dir: str, private_key_hex: str, version: str) -> dict:
    _version_tuple(version)
    payload_dir = os.path.join(pack_dir, "payload")
    if not os.path.isdir(payload_dir):
        raise FileNotFoundError(f"{payload_dir} does not exist")
    files = {rel: compute_sha256(os.path.join(payload_dir, rel)) for rel in sorted(_payload_files(payload_dir))}
    if not files:
        raise ValueError("payload/ is empty - nothing to sign")
    manifest_raw = json.dumps({"version": version, "files": files}, sort_keys=True, indent=2).encode("utf-8")
    with open(os.path.join(pack_dir, "manifest.json"), "wb") as f:
        f.write(manifest_raw)
    signer = Ed25519Signer(bytes.fromhex(private_key_hex.strip()))
    with open(os.path.join(pack_dir, "signature.sig"), "w", encoding="utf-8") as f:
        f.write(signer.sign_bytes(manifest_raw))
    return {"version": version, "files": len(files)}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Build and sign an offline update pack.")
    p.add_argument("pack_dir", nargs="?")
    p.add_argument("--private-key", help="hex Ed25519 private key file")
    p.add_argument("--version", help="pack version, dotted integers (e.g. 1.2.0)")
    p.add_argument("--keygen", metavar="PREFIX", help="generate PREFIX.key and PREFIX.pub and exit")
    a = p.parse_args(argv)
    if a.keygen:
        k, pub = keygen(a.keygen)
        print(f"[OK] wrote {k} (keep private, mode 600) and {pub} (copy to appliances)")
        return 0
    if not (a.pack_dir and a.private_key and a.version):
        p.error("PACK_DIR, --private-key and --version are required (or use --keygen)")
    with open(a.private_key, encoding="utf-8") as f:
        info = build_and_sign(a.pack_dir, f.read(), a.version)
    print(f"[OK] signed {info['files']} files at version {info['version']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
