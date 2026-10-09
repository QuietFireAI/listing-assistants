import os
import tempfile
import pytest

from dispatcher.core import Envelope, Routes, AuditLog
from dispatcher.hub import Hub
from dispatcher.signer_registry import SignerRegistry


def make_hub_with_armed_registry(tmpdir):
    audit_path = os.path.join(tmpdir, "audit.jsonl")
    audit = AuditLog(audit_path)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    routes = Routes(os.path.join(root, "identity", "routes.json"))
    # Pass signature verification for envelopes signed with "valid_sig"
    hub = Hub(routes, audit, signature_verifier=lambda env: getattr(env, "signature", None) == "valid_sig")
    hub.arm_signer_registry(root)
    hub.register("05", lambda env: None)
    return hub, audit


def test_signer_registry_loads_ratified_config():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    registry = SignerRegistry.load(root)
    assert registry is not None
    assert "listing.change.authorized" in registry._by_intent
    assert "payment.authority" in registry._by_intent


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
                    "signer_login": "principal.broker@listingassistants.com",
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
                    "signer_login": "principal.broker@listingassistants.com",
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
