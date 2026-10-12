import json
import os
import tempfile
import pytest

from dispatcher.core import Envelope, Routes, AuditLog
from dispatcher.hub import Hub
from dispatcher.signer_registry import SignerRegistry

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Audit 2026-10-11 (CFG-1): these tests used to arm the REPO's
# config/authority_signers.json, which had been flipped to "RATIFIED" with a
# placeholder login so the tests could pass. The repo file is back to the
# UNRATIFIED TEMPLATE (only the owner ratifies real IdP logins); the tests
# now arm a fixture identity root of their own.
FIXTURE_SIGNERS = {
    "_status": "RATIFIED (test fixture only)",
    "entries": [{
        "intent": "listing.change.authorized",
        "signer_login": "principal.broker@example.test",
        "idp": "test-idp",
        "mfa_required": True,
        "effective": "2026-01-01",
        "revoked": None,
    }],
}


def fixture_identity_root(tmpdir):
    root = os.path.join(tmpdir, "identity_root")
    os.makedirs(os.path.join(root, "config"), exist_ok=True)
    with open(os.path.join(root, "config", "authority_signers.json"), "w", encoding="utf-8") as f:
        json.dump(FIXTURE_SIGNERS, f)
    return root


def make_hub_with_armed_registry(tmpdir):
    audit = AuditLog(os.path.join(tmpdir, "audit.jsonl"))
    routes = Routes(os.path.join(REPO_ROOT, "identity", "routes.json"))
    # Pass signature verification for envelopes signed with "valid_sig"
    hub = Hub(routes, audit, signature_verifier=lambda env: getattr(env, "signature", None) == "valid_sig")
    hub.arm_signer_registry(fixture_identity_root(tmpdir))
    hub.register("05", lambda env: None)
    return hub, audit


def test_repo_signer_config_is_an_unratified_template_and_refuses_to_arm():
    with pytest.raises(ValueError, match="UNRATIFIED"):
        SignerRegistry.load(REPO_ROOT)


def test_signer_registry_loads_ratified_fixture(tmp_path):
    registry = SignerRegistry.load(fixture_identity_root(str(tmp_path)))
    assert list(registry._by_intent) == ["listing.change.authorized"]


def test_armed_registry_authorized_signer():
    with tempfile.TemporaryDirectory() as tmpdir:
        hub, audit = make_hub_with_armed_registry(tmpdir)

        # An envelope with authorized intent, valid crypto signature, and ratified signer stamp
        env = Envelope(
            from_agent="human",
            to_agent="05",
            intent="listing.change.authorized",
            client_context_id="prop_401",
            payload={"change_type": "price_reduction", "new_price": 550000},
            provenance={
                "source": "human",
                "signer": {
                    "signer_login": "principal.broker@example.test",
                    "mfa": True,
                    "idp_session_ref": "okta_session_9981"
                }
            },
            confidence="source_verified",
            signature="valid_sig"
        )

        res = hub.send(env)
        assert res["status"] == "ack"

        # Check audit log contains signer.verified
        events = [e["kind"] for e in audit.read()]
        assert "signer.verified" in events


def test_armed_registry_unauthorized_signer_rejected():
    with tempfile.TemporaryDirectory() as tmpdir:
        hub, audit = make_hub_with_armed_registry(tmpdir)

        # Envelope with unauthorized login
        env = Envelope(
            from_agent="human",
            to_agent="05",
            intent="listing.change.authorized",
            client_context_id="prop_401",
            payload={"change_type": "price_reduction", "new_price": 550000},
            provenance={
                "source": "human",
                "signer": {
                    "signer_login": "rogue_actor@external.com",
                    "mfa": True,
                    "idp_session_ref": "session_fake"
                }
            },
            confidence="source_verified",
            signature="valid_sig"
        )

        res = hub.send(env)
        assert res["status"] == "reject"
        assert "signer registry:" in res["reason"]
        assert len(hub.queues["integrity.violation"]) == 1

        # Check audit log contains integrity.violation
        events = [e["kind"] for e in audit.read()]
        assert "integrity.violation" in events


def test_armed_registry_missing_mfa_rejected():
    with tempfile.TemporaryDirectory() as tmpdir:
        hub, audit = make_hub_with_armed_registry(tmpdir)

        # Envelope with valid login but MFA false
        env = Envelope(
            from_agent="human",
            to_agent="05",
            intent="listing.change.authorized",
            client_context_id="prop_401",
            payload={"change_type": "price_reduction"},
            provenance={
                "source": "human",
                "signer": {
                    "signer_login": "principal.broker@example.test",
                    "mfa": False,  # doctrine violation
                    "idp_session_ref": "session_123"
                }
            },
            confidence="source_verified",
            signature="valid_sig"
        )

        res = hub.send(env)
        assert res["status"] == "reject"
        assert "does not attest MFA" in res["reason"]
