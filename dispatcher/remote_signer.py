"""remote_signer - the dispatcher's side when the key lives in the signer.

Owner decisions 2026-10-26: the dispatcher cannot reach the signer and
never holds the key. It holds only the operator's public key, so it can
check a signature but never make one.

Every place that signs today calls signer.sign(envelope). With the signer
in its own room, that call cannot be answered here: it raises
NeedsSignature with the prepared message. The Desk hands that message to
your browser, your browser to the signer's page, and the signature comes
back the same way. supply() checks it against your public key and keeps
it; the action then runs again, and sign() finds the signature for exactly
that message (same receiver, intent, client and payload) and uses the
signed message's id and provenance, so what runs is what you signed.

Signed files work the same way: `console.py session --signed FILE` loads
the signatures the signer made in a batch.
"""
from __future__ import annotations

import json
from typing import Any


class NeedsSignature(Exception):
    """The message needs your signature on the signer."""

    def __init__(self, env: Any):
        super().__init__(f"{env.intent} to {env.to_agent} ({env.client_context_id}) needs your "
                         f"signature on the signer")
        self.env = env


def match_key(env_or_record: Any) -> str:
    r = env_or_record if isinstance(env_or_record, dict) else env_or_record.to_record()
    return json.dumps([r.get("to_agent"), r.get("intent"), r.get("client_context_id"),
                       r.get("payload")], sort_keys=True, separators=(",", ":"))


class RemoteSigner:
    """Has the public key only. sign() uses a signature you supplied for
    that exact message, or asks for one."""

    def __init__(self, public_key_bytes: bytes):
        from .signatures import Ed25519Verifier
        self.pub = public_key_bytes
        self.verifier = Ed25519Verifier(public_key_bytes)
        self.ready: dict[str, list[dict]] = {}

    def public_key_bytes(self) -> bytes:
        return self.pub

    def check(self, record: dict) -> Any:
        """The Envelope of a signed record, when the signature is the
        operator's; else ValueError."""
        from .core import Envelope
        from .signatures import _canonical
        sig = record.get("signature")
        keep = {k: record.get(k) for k in ("envelope_id", "from_agent", "to_agent", "intent",
                                           "in_reply_to", "client_context_id", "payload",
                                           "provenance", "confidence", "escalation_flag")}
        keep["confidence"] = keep.get("confidence") or "unknown"
        keep["escalation_flag"] = bool(keep.get("escalation_flag"))
        env = Envelope(**keep)
        if not isinstance(sig, str) or not self.verifier.verify_bytes(_canonical(env), sig):
            raise ValueError("the signature is not your key's signature for this message")
        env.signature = sig
        return env

    def supply(self, record: dict) -> None:
        self.check(record)
        self.ready.setdefault(match_key(record), []).append(record)

    def sign(self, env: Any) -> str:
        queue = self.ready.get(match_key(env))
        if not queue:
            raise NeedsSignature(env)
        rec = queue.pop(0)
        env.envelope_id = rec["envelope_id"]
        env.provenance = rec["provenance"]
        env.signature = rec["signature"]
        return env.signature

    def sign_bytes(self, data: bytes) -> str:
        raise RuntimeError("the dispatcher holds no key: the signer attests the install "
                           "(signer_service attest), and `console.py attest --from-signer` records it")


class SignerAttestation:
    """Records, on the dispatcher's side, the list of installed files the
    signer signed (dispatcher/signer_service.py `init` / `attest`). It signs
    nothing: sign_bytes returns the signer's signature only for exactly the
    files the signer listed."""

    def __init__(self, doc: dict, public_key_bytes: bytes):
        from .boot_attest import canonical
        from .signatures import Ed25519Verifier
        self.doc, self.pub = doc, public_key_bytes
        if not Ed25519Verifier(public_key_bytes).verify_bytes(canonical(doc["manifest"]), doc["signature"]):
            raise ValueError("the signer's list of files is not signed by this key")

    def public_key_bytes(self) -> bytes:
        return self.pub

    def sign_bytes(self, data: bytes) -> str:
        from .boot_attest import AttestationRefused, canonical
        if data != canonical(self.doc["manifest"]):
            raise AttestationRefused("the signer attested different files from the ones installed "
                                     "here; rebuild both from the same image, then attest again")
        return self.doc["signature"]
