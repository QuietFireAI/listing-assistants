"""listing-assistants declares the intents it signs (owner decision D2,
2026-10-14). The core no longer hard-codes listing.change.authorized; this
identity names it in identity/routes.json under "signed_intents". These
tests fail if an authorization-shaped intent named anywhere in this
repository's code would pass the hub without a signature."""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dispatcher.core import AuditLog, Envelope, Routes  # noqa: E402
from dispatcher.hub import Hub, is_authority  # noqa: E402
from dispatcher.signatures import Ed25519Signer  # noqa: E402

ROUTES = os.path.join(ROOT, "identity", "routes.json")
SHAPED = re.compile(r"""["']([a-z_]+(?:\.[a-z_]+)*\.(?:authority|authorized))["']""")


def code_files():
    for pattern in ("dispatcher/*.py", "tools/*.py"):
        yield from glob.glob(os.path.join(ROOT, pattern))


def test_every_authorization_intent_in_the_code_needs_a_signature():
    routes = Routes(ROUTES)
    declared = routes.signed_intents
    on_track = {i for i, _, _ in routes.entries}
    named = set()
    for f in code_files():
        named |= set(SHAPED.findall(open(f, encoding="utf-8").read()))
    # audit event names share the shape (disclosure.authorized,
    # hitl.decision.authorized) but are not messages; only intents count:
    # the ones on the track, and the .authority lanes the hub serves directly
    named = {i for i in named if i in on_track or i.endswith(".authority")}
    named.add("config.update")
    assert "listing.change.authorized" in named          # the scan finds the one that matters
    undeclared = sorted(i for i in named if not is_authority(i, declared))
    assert undeclared == [], f"signed in code but not declared in routes.json: {undeclared}"


def test_an_unsigned_listing_change_is_refused_on_the_real_track(tmp_path):
    hub = Hub(Routes(ROUTES), AuditLog(str(tmp_path / "a.jsonl")),
              signature_verifier=Ed25519Signer().verifier())
    hub.register("05", lambda e: None)
    env = Envelope(from_agent="human", to_agent="05", intent="listing.change.authorized",
                   client_context_id="c", payload={}, provenance={"source": "t"})
    r = hub.send(env)
    assert r["status"] == "reject" and "unverified signature" in r["reason"]


def test_the_declaration_is_in_the_routes_file():
    doc = json.load(open(ROUTES, encoding="utf-8"))
    assert doc["signed_intents"] == ["listing.change.authorized"]
