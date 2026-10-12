"""Audit MCP-1 (2026-10-11): the MCP server signed authority actions for
any host. It now does so only when started with --demo-signing."""
import os
import subprocess
import sys

import pytest

pytest.importorskip("mcp")
from dispatcher import identity_mcp                                         # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LISTING = {"new_listing": {"beds": 3, "sqft": 2000, "price": 500000, "features": ["garage"],
                           "photo_detected_features": ["garage"]},
           "authorize_go_live": True, "today": "2026-07-01"}


def identity(demo):
    routes, signer, verifier = identity_mcp._boot_conformance()
    return identity_mcp.GovernedIdentity(routes, signer, verifier, demo_signing=demo)


def test_default_server_signs_nothing_for_the_host():
    ident = identity(False)
    r = ident.submit("listing.authorize", LISTING)
    assert r["ok"] is False and "broker's signature" in r["reason"]
    r = ident.authority("listing.change.authorized", {"to": "05", "new_listing": {}},
                        signature_hex="DEMO_SIGN_WITH_SERVER_KEY")
    assert r["ok"] is False and r["hub_status"] == "reject"
    assert ident.describe()["governance"]["server_signs_for_host"] is False
    assert not [e for e in ident.hub.audit.read()
                if e["kind"] == "envelope.persisted" and e["intent"] == "listing.change.authorized"]


def test_demo_mode_is_explicit_and_works():
    ident = identity(True)
    assert ident.submit("listing.authorize", LISTING)["ok"] is True
    assert ident.describe()["governance"]["server_signs_for_host"] is True


def test_mount_docs_do_not_enable_demo_signing():
    text = open(os.path.join(ROOT, "docs", "MOUNTING.md"), encoding="utf-8").read()
    arg_lines = [l for l in text.splitlines() if "args" in l]
    assert arg_lines and not [l for l in arg_lines if "--demo-signing" in l]
