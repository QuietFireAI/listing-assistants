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
            "version": "0.0.1",
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


# --- audit 2026-10-11 (A-1..A-4) -------------------------------------------
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _make_signed_pack(tmp, version="1.2.0", files=None):
    from tools.sign_manifest import build_and_sign
    signer = Ed25519Signer()
    payload = os.path.join(tmp, "pack", "payload")
    os.makedirs(os.path.join(payload, "dispatcher"), exist_ok=True)
    for rel, body in (files or {"dispatcher/spoke.py": "# signed update\n"}).items():
        with open(os.path.join(payload, rel), "w") as f:
            f.write(body)
    pack = os.path.join(tmp, "pack")
    build_and_sign(pack, signer.private_key_bytes().hex(), version)
    pub = os.path.join(tmp, "authority.pub")
    with open(pub, "w") as f:
        f.write(signer.public_key_bytes().hex())
    return pack, pub, signer


def _cli(*args):
    return subprocess.run([sys.executable, os.path.join(ROOT, "tools", "verify_update_pack.py"), *args],
                          capture_output=True, text=True)


def test_cli_accepts_pubkey_and_passes_signed_pack(tmp_path):
    pack, pub, _ = _make_signed_pack(str(tmp_path))
    out = _cli(pack, "--pubkey", pub)
    assert out.returncode == 0, out.stdout
    assert "[OK] Signature verified" in out.stdout


def test_unlisted_payload_file_fails(tmp_path):
    pack, pub, _ = _make_signed_pack(str(tmp_path))
    with open(os.path.join(pack, "payload", "backdoor.py"), "w") as f:
        f.write("import os\n")
    res = verify_update_pack(pack, authority_pubkey_bytes=bytes.fromhex(open(pub).read()))
    assert res["valid"] is False
    assert any("Unlisted file in payload/" in e and "backdoor.py" in e for e in res["errors"])
    assert _cli(pack, "--pubkey", pub).returncode == 1


def test_environment_variable_no_longer_bypasses_signature(tmp_path, monkeypatch):
    pack, pub, _ = _make_signed_pack(str(tmp_path))
    with open(os.path.join(pack, "signature.sig"), "w") as f:
        f.write("00" * 64)
    monkeypatch.setenv("ALLOW_INSECURE_DEV_UPDATE", "1")
    res = verify_update_pack(pack, authority_pubkey_bytes=bytes.fromhex(open(pub).read()))
    assert res["valid"] is False and res["signature_verified"] is False


def test_dev_bypass_is_never_reported_as_verified(tmp_path):
    pack, _, _ = _make_signed_pack(str(tmp_path))
    out = _cli(pack, "--dev-bypass")
    assert out.returncode == 3 and "NOT VERIFIED" in out.stdout


def test_downgrade_replay_refused(tmp_path):
    pack, pub, _ = _make_signed_pack(str(tmp_path), version="1.1.0")
    key = bytes.fromhex(open(pub).read())
    assert verify_update_pack(pack, key, installed_version="1.1.0")["valid"] is False
    assert verify_update_pack(pack, key, installed_version="1.0.9")["valid"] is True


def test_unsafe_manifest_paths_refused(tmp_path):
    signer = Ed25519Signer()
    pack = tmp_path / "pack"
    (pack / "payload").mkdir(parents=True)
    (tmp_path / "secret.txt").write_text("x")
    manifest = json.dumps({"version": "1.0.0", "files": {"../../secret.txt": compute_sha256(str(tmp_path / "secret.txt"))}}).encode()
    (pack / "manifest.json").write_bytes(manifest)
    (pack / "signature.sig").write_text(signer.sign_bytes(manifest))
    res = verify_update_pack(str(pack), signer.public_key_bytes())
    assert res["valid"] is False and any("Unsafe manifest path" in e for e in res["errors"])


def test_sign_manifest_keygen_refuses_to_overwrite(tmp_path):
    from tools.sign_manifest import keygen
    prefix = str(tmp_path / "authority")
    k, p = keygen(prefix)
    assert oct(os.stat(k).st_mode & 0o777) == "0o600" and len(open(p).read()) == 64
    with pytest.raises(FileExistsError):
        keygen(prefix)
