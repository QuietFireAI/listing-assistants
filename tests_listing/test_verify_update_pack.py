"""Tests for Air-Gapped Apricorn Update Pack Verifier."""
import hashlib
import json
import os
import tempfile
import pytest
from dispatcher.signatures import Ed25519Signer
from tools.verify_update_pack import verify_update_pack, compute_sha256


def test_update_pack_verification_signed():
    signer = Ed25519Signer()
    pubkey = signer.public_key_bytes()

    with tempfile.TemporaryDirectory() as tmpdir:
        payload_dir = os.path.join(tmpdir, "payload")
        os.makedirs(payload_dir, exist_ok=True)

        test_file = os.path.join(payload_dir, "new_spoke.py")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("# Updated spoke logic\n")
        file_hash = compute_sha256(test_file)

        manifest = {
            "version": "1.1.0",
            "files": {"new_spoke.py": file_hash}
        }
        manifest_raw = json.dumps(manifest).encode("utf-8")
        manifest_path = os.path.join(tmpdir, "manifest.json")
        with open(manifest_path, "wb") as f:
            f.write(manifest_raw)

        # Sign manifest
        sig_hex = signer.sign_bytes(manifest_raw)
        with open(os.path.join(tmpdir, "signature.sig"), "w", encoding="utf-8") as f:
            f.write(sig_hex)

        # Verify
        res = verify_update_pack(tmpdir, authority_pubkey_bytes=pubkey)
        assert res["valid"] is True
        assert "new_spoke.py" in res["verified_files"]


def test_update_pack_dev_bypass_without_signature():
    with tempfile.TemporaryDirectory() as tmpdir:
        payload_dir = os.path.join(tmpdir, "payload")
        os.makedirs(payload_dir, exist_ok=True)

        test_file = os.path.join(payload_dir, "config.json")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write('{"dev": true}')
        file_hash = compute_sha256(test_file)

        manifest = {
            "version": "dev-01",
            "files": {"config.json": file_hash}
        }
        with open(os.path.join(tmpdir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f)

        # Verify with dev bypass active (no signature.sig present)
        res = verify_update_pack(tmpdir, dev_bypass=True)
        assert res["valid"] is True
        assert "config.json" in res["verified_files"]


def test_update_pack_detects_tampering():
    signer = Ed25519Signer()
    pubkey = signer.public_key_bytes()

    with tempfile.TemporaryDirectory() as tmpdir:
        payload_dir = os.path.join(tmpdir, "payload")
        os.makedirs(payload_dir, exist_ok=True)

        test_file = os.path.join(payload_dir, "file.txt")
        with open(test_file, "w") as f:
            f.write("legit content")
        file_hash = compute_sha256(test_file)

        manifest = {"files": {"file.txt": file_hash}}
        manifest_raw = json.dumps(manifest).encode("utf-8")
        with open(os.path.join(tmpdir, "manifest.json"), "wb") as f:
            f.write(manifest_raw)

        sig_hex = signer.sign_bytes(manifest_raw)
        with open(os.path.join(tmpdir, "signature.sig"), "w", encoding="utf-8") as f:
            f.write(sig_hex)

        # Tamper with file
        with open(test_file, "w") as f:
            f.write("tampered content")

        res = verify_update_pack(tmpdir, authority_pubkey_bytes=pubkey)
        assert res["valid"] is False
        assert any("Hash mismatch" in err for err in res["errors"])
