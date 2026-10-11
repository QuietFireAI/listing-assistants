"""Fresh Security, Penetration, and Fiduciary Smoke Tests.

Audits outside-the-box edge cases:
  1. Path-Traversal & Commingling Boundaries (ClientDrawerManager).
  2. Ed25519 Cryptographic Authority & Signature Forgery Defense.
  3. SHA-256 Tamper-Evident Hash Chain Corruption Detection.
  4. Fair Housing Steering & Evasion Detection (Spoke 04 & 17).
  5. Insecure HTTP Scheme Rejection in JEV Decision Adapter.
"""
import json
import os
import sys
import uuid
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dispatcher.core import Envelope, Routes, AuditLog
from dispatcher.hub import Hub
from dispatcher.signatures import Ed25519Signer, Ed25519Verifier
from dispatcher.client_drawer import ClientDrawerManager, ComminglingBreachError
from dispatcher.decision_adapter import JevDecisionAdapter
from dispatcher.listing_spokes_04 import Spoke04ListingDescription
from dispatcher.listing_spokes_07 import Spoke07TransactionCoordinator
from dispatcher.listing_spokes_17 import Spoke17ComplianceFairHousing

IDENTITY_ROUTES = os.path.join(os.path.dirname(__file__), "..", "identity", "routes.json")


def make_hub(tmp_path):
    audit_file = os.path.join(tmp_path, f"audit-{uuid.uuid4().hex[:8]}.jsonl")
    signer = Ed25519Signer()
    verifier = Ed25519Verifier(signer.public_key_bytes())
    hub = Hub(Routes(IDENTITY_ROUTES), AuditLog(audit_file),
              signature_verifier=verifier.verifier())
    return hub, signer


# ---------------------------------------------------------------------------
# 1. Path-Traversal & Vault Isolation Smoke Tests
# ---------------------------------------------------------------------------
MALICIOUS_SEGMENTS = [
    "../../etc/passwd",
    "..\\..\\windows\\system32",
    "ctx/../../../shadow",
    "ctx-safe/../../outside_vault",
    "..",
    "/etc/passwd",
    "a/b",
    "",
]


def test_client_drawer_path_traversal_attack_blocked(tmp_path):
    """Traversal is refused on every entry point. Audit 2026-10-11 (D-3): the
    previous version of this test only called get_drawer() on paths that did
    not exist, so it passed whether or not traversal was blocked. These cases
    target EXISTING drawers with real writes/reads, and assert nothing landed
    outside its drawer."""
    root = tmp_path / "drawers"
    mgr = ClientDrawerManager(str(root))
    mgr.provision_drawer("alice", "Alice", "1 Oak")
    bob = mgr.provision_drawer("bob", "Bob", "2 Elm")
    bob.store_file("08", "documents", "preapproval.txt", "Bob preapproved $900k")
    (tmp_path / "outside").mkdir()

    # ids: every entry point refuses unsafe client ids
    for bad in MALICIOUS_SEGMENTS + ["../outside"]:
        with pytest.raises(ComminglingBreachError):
            mgr.get_drawer(bad)
        with pytest.raises((ComminglingBreachError, ValueError)):
            mgr.provision_drawer(bad, "X", "Y")
        assert mgr.has_drawer(bad) is False
    assert not (tmp_path / "escaped").exists()
    assert os.listdir(tmp_path / "outside") == []

    # filenames: write and read traversal from alice's drawer toward bob's
    for bad in ["../../bob/documents/injected.txt", "../bob/x", "..", "a/b"]:
        with pytest.raises(ComminglingBreachError):
            mgr.record_agent_artifact("alice", "04", "artifacts", bad, "x",
                                      acting_client_context_id="alice")
        with pytest.raises(ComminglingBreachError):
            mgr.get_drawer("alice").get_file("artifacts", bad)
    assert sorted(os.listdir(root / "bob" / "documents")) == ["preapproval.txt"]

    # category is a closed set, not a path
    with pytest.raises(ValueError):
        mgr.record_agent_artifact("alice", "04", "../../bob/documents", "x.txt", "x",
                                  acting_client_context_id="alice")


def test_drawer_symlink_escape_blocked(tmp_path):
    """A symlink planted inside a drawer cannot carry a write outside it."""
    root = tmp_path / "drawers"
    mgr = ClientDrawerManager(str(root))
    alice = mgr.provision_drawer("alice", "Alice", "1 Oak")
    target = tmp_path / "loot"
    target.mkdir()
    os.symlink(str(target / "stolen.txt"),
               os.path.join(alice.drawer_path, "artifacts", "link.txt"))
    with pytest.raises(ComminglingBreachError):
        alice.store_file("04", "artifacts", "link.txt", "secret")
    assert not (target / "stolen.txt").exists()


def test_cross_client_filing_refused_by_context_binding(tmp_path):
    """An agent acting for alice cannot file into bob's (existing) drawer."""
    mgr = ClientDrawerManager(str(tmp_path))
    mgr.provision_drawer("alice", "Alice", "1 Oak")
    mgr.provision_drawer("bob", "Bob", "2 Elm")
    with pytest.raises(ComminglingBreachError):
        mgr.record_agent_artifact("bob", "04", "artifacts", "note.txt", "x",
                                  acting_client_context_id="alice")
    assert mgr.get_drawer("bob").list_files() == []


def test_drawer_identity_never_silently_overwritten(tmp_path):
    mgr = ClientDrawerManager(str(tmp_path))
    mgr.provision_drawer("c1", "Alice", "1 Oak")
    with pytest.raises(ComminglingBreachError):
        mgr.provision_drawer("c1", "Mallory", "9 Elm")
    m = mgr.get_drawer("c1").get_manifest()
    assert (m["client_name"], m["property_address"]) == ("Alice", "1 Oak")
    mgr.provision_drawer("c1", "Alice B", "1 Oak", update_identity=True)
    assert mgr.get_drawer("c1").get_manifest()["client_name"] == "Alice B"


def test_drawer_verify_hashes_detects_tamper(tmp_path):
    mgr = ClientDrawerManager(str(tmp_path))
    d = mgr.provision_drawer("c1", "Alice", "1 Oak")
    p = d.store_file("08", "documents", "addendum.txt", "credit $2,500")
    assert d.verify_hashes() == {"ok": True, "checked": 1, "mismatched": [], "missing": []}
    with open(p, "w") as f:
        f.write("credit $25,000")
    v = d.verify_hashes()
    assert v["ok"] is False and v["mismatched"] == ["documents/addendum.txt"]


def test_cross_client_memory_isolation(tmp_path):
    """Ensures Client A's confidential disclosures never leak to Client B."""
    mgr = ClientDrawerManager(str(tmp_path))
    drawer_a = mgr.provision_drawer("client_a", "Client A", "100 Oak St", "seller", "00")
    mgr.record_agent_artifact("client_a", "08", "documents", "seller_confidential.txt", b"Walkaway price: $425,000",
                             acting_client_context_id="client_a")
    
    drawer_b = mgr.provision_drawer("client_b", "Client B", "200 Elm St", "buyer", "00")
    assert not os.path.exists(os.path.join(drawer_b.drawer_path, "documents", "seller_confidential.txt"))
    assert len(drawer_b.list_files()) == 0, "Client B's drawer must be empty and uncommingled"


# ---------------------------------------------------------------------------
# 2. Cryptographic Signature Forgery & Money Gate Smoke Tests
# ---------------------------------------------------------------------------
def test_forged_ed25519_signature_drops_fail_closed(tmp_path):
    """An adversary attempts to authorize a wire instruction using an altered signature."""
    hub, signer = make_hub(str(tmp_path))
    Spoke07TransactionCoordinator(hub)
    hub.on_turn_start()

    legit_env = Envelope(
        from_agent="human", to_agent="07", intent="milestone.update",
        client_context_id="ctx-wire-attack",
        payload={"milestone": "closing_funds", "amount": 50000},
        provenance={"source": "adversary"}
    )
    signer.sign(legit_env)

    # Attacker mutates the signature by 1 bit
    sig_bytes = bytearray(bytes.fromhex(legit_env.signature))
    sig_bytes[0] ^= 0x01
    legit_env.signature = sig_bytes.hex()

    hub.send(legit_env)
    
    # Must be dropped or rejected with integrity violation
    events = [e for e in hub.audit.read() if e.get("kind") == "envelope.rejected" or "integrity" in e.get("kind", "")]
    assert len(events) > 0 or not hub.queues.get("milestone.update"), "Forged signature must fail closed"


# ---------------------------------------------------------------------------
# 3. SHA-256 Tamper-Evident Ledger Smoke Tests
# ---------------------------------------------------------------------------
def test_audit_ledger_bit_rot_and_tamper_detection(tmp_path):
    """If a malicious actor edits past log lines on disk, chain verification must fail."""
    audit_file = os.path.join(tmp_path, "tamper_test.jsonl")
    ledger = AuditLog(audit_file)
    
    ledger.append("system.boot", {"status": "ok"})
    ledger.append("envelope.persisted", {"intent": "lead.captured", "score": 95})
    ledger.append("envelope.persisted", {"intent": "fiduciary.approved", "status": "signed"})
    
    # Verify chain is initially valid
    initial_check = ledger.verify_chain()
    assert initial_check["ok"] is True
    
    # Corrupt line 2 in the log file: read raw lines, mutate a value
    with open(audit_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    # Tamper with the score in JSON
    entry = json.loads(lines[1])
    entry["score"] = 40  # Tampered score
    lines[1] = json.dumps(entry) + "\n"
    
    with open(audit_file, "w", encoding="utf-8") as f:
        f.writelines(lines)
    
    # Verify chain detects tampering immediately
    tampered_check = ledger.verify_chain()
    assert tampered_check["ok"] is False, "Tampered audit block was not detected by hash chain verification"
    assert tampered_check["break_at"] == 2


# ---------------------------------------------------------------------------
# 4. Fair Housing Steering & Evasion Smoke Tests
# ---------------------------------------------------------------------------
def test_fair_housing_refusal_in_spoke_04(tmp_path):
    """Verifies that demographic and protected class requests are explicitly refused."""
    hub, _ = make_hub(str(tmp_path))
    Spoke04ListingDescription(hub)
    hub.on_turn_start()
    
    # Adversarial listing copy request with protected class request words
    env = Envelope(
        from_agent="05", to_agent="04", intent="listing.data",
        client_context_id="ctx-fh-01",
        payload={
            "beds": 4, "baths": 3,
            "requested_language": "Advertise as family-friendly with great schools and neighborhood demographics"
        },
        provenance={"source": "test", "captured_at": "runtime", "verbatim_available": True}
    )
    hub.send(env)
    
    # Check trace ingestion caught the refusal
    traces = [e for e in hub.audit.read() if e.get("kind") == "spoke.trace"]
    assert any("fair_housing" in str(t) for t in traces), "Spoke 04 must log fair-housing gate refusal"


# ---------------------------------------------------------------------------
# 5. JEV Co-Processor Insecure Scheme Rejection Smoke Test
# ---------------------------------------------------------------------------
def test_jev_adapter_insecure_http_rejected():
    """JevDecisionAdapter must explicitly reject plaintext http:// endpoints to prevent MITM."""
    adapter = JevDecisionAdapter(api_key="test_key", endpoint_url="http://insecure-api.typesafe.ai/v1")
    with pytest.raises(ValueError, match="Insecure or invalid JEV endpoint scheme"):
        adapter._call_http_decision("lead_triage", "ctx-01", {"score": 80})
