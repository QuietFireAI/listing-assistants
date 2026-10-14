#!/usr/bin/env python3
"""identity_mcp - a generic MCP server that mounts a QuietFireAI governed
identity behind a deliberately NARROW closed surface.

Why narrow: the host agent's LLM must NOT be handed the identity's
internals as free tools - that would return routing to the host and
dissolve the closed track. Instead the host gets exactly four tools that
push intents at the FRONT DOOR; the governed hub does all routing,
signing, sealing, and logging behind them. The MCP shell is the open
socket; the hub is the governed cartridge.

Runs as a stdio MCP server, so one wrapper mounts identically on Hermes
(`mcp_servers:` in config.yaml), OpenClaw (MCP server config), and Claude
Desktop - zero per-host code.

Boot conformance: the server REFUSES TO START unless the closed track,
the signer registry, and the audit chain are intact. The governance
guarantee travels with the server; it cannot be silently mounted broken.

Usage:
    python3 -m dispatcher.identity_mcp                  # serve the identity
    IDENTITY_ROOT=/path python3 -m dispatcher.identity_mcp
    python3 -m dispatcher.identity_mcp --demo-signing   # DEMO ONLY, see below

Signing (fixed 2026-10-11, audit MCP-1): the server holds a key it generates
at boot. Before this fix it used that key to sign `listing.authorize` and
any `identity.authority` call carrying "DEMO_SIGN_WITH_SERVER_KEY" for
whatever host asked, so over MCP an authority action proved only that the
host asked, not that a human signed. Now the server signs nothing for a host
unless it was started with --demo-signing (used by tools/mcp_roundtrip.py
to show the signed path). Without it, both are refused with a reason. A
production signed lane needs the host to present an envelope signed with the
broker's own key; that protocol is not built yet.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import uuid

# --- locate the identity this wrapper serves -------------------------------
ROOT = os.environ.get(
    "IDENTITY_ROOT",
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from dispatcher.core import Envelope, Routes, AuditLog          # noqa: E402
from dispatcher.hub import Hub                                   # noqa: E402
from dispatcher.signatures import Ed25519Signer, Ed25519Verifier  # noqa: E402


IDENTITY_NAME = os.path.basename(ROOT.rstrip("/")) or "identity"
ROUTES_PATH = os.path.join(ROOT, "identity", "routes.json")
PRIORITY_PATH = os.path.join(ROOT, "identity", "priority.json")


# ---------------------------------------------------------------------------
# Boot conformance gate - the guarantee travels with the server.
# ---------------------------------------------------------------------------
class ConformanceError(RuntimeError):
    pass


def _boot_conformance():
    """Refuse to start unless closed track, signer path, and audit chain
    are intact. Returns (routes, signer, verifier) on success."""
    problems = []

    # 1. Closed track loads and is non-empty.
    try:
        routes = Routes(ROUTES_PATH)
    except Exception as e:  # noqa: BLE001
        raise ConformanceError(f"closed track failed to load: {e}")
    n_routes = len(json.load(open(ROUTES_PATH, encoding="utf-8"))["routes"])
    if n_routes == 0:
        problems.append("closed track has zero routes")

    # 2. Signature path is real: a signed envelope verifies, an unsigned
    #    authority envelope is rejected by the hub.
    signer = Ed25519Signer()
    verifier = Ed25519Verifier(signer.public_key_bytes())
    probe_audit = AuditLog(
        os.path.join(tempfile.gettempdir(), f"conformance-{uuid.uuid4().hex[:8]}.jsonl"))
    hub = Hub(routes, probe_audit,
              signature_verifier=verifier.verifier())
    hub.register("human", lambda e: None)
    hub.on_turn_start()
    # Probe THIS identity's own first authority lane (a route requiring a
    # signature), so the gate is tested for the right reason on any
    # identity - never a hardcoded intent that might be an illegal route.
    all_routes = json.load(open(ROUTES_PATH, encoding="utf-8"))["routes"]
    auth = next((r for r in all_routes
                 if "authorized" in r["intent"] or "authority" in r["intent"]),
                None)
    if auth is None:
        problems.append("no authority lane found to test the signer gate")
    else:
        to = auth["receivers"][0]
        hub.register(to, lambda e: None)
        unsigned = Envelope(from_agent=auth["senders"][0], to_agent=to,
                            intent=auth["intent"],
                            client_context_id="conformance-probe",
                            payload={"probe": True},
                            provenance={"source": "human",
                                        "captured_at": "boot",
                                        "verbatim_available": True})
        res = hub.send(unsigned)
        if res.get("status") == "ack":
            problems.append(
                f"signer gate OPEN: unsigned {auth['intent']} accepted")

    # 3. Audit chain verifies and is tamper-evident.
    if not probe_audit.verify_chain().get("ok"):
        problems.append("audit chain does not verify at boot")

    if problems:
        raise ConformanceError(
            "identity NOT conformant - refusing to mount:\n  - "
            + "\n  - ".join(problems))
    return routes, signer, verifier


# ---------------------------------------------------------------------------
# The governed identity behind the MCP surface.
# ---------------------------------------------------------------------------
class GovernedIdentity:
    """Builds the hub + spokes once, keeps state across submits within the
    server's lifetime, and exposes only front-door operations."""

    def _declare_server_signed(self, env) -> None:
        """--demo-signing: say on the chain that the server, not a person,
        signed this authority envelope (2026-10-14 cold review: before, a
        server-signed authorization looked the same on the chain as a
        broker-signed one)."""
        self.hub.audit.append("authority.server_signed", {
            "envelope_id": env.envelope_id, "intent": env.intent,
            "client_context_id": env.client_context_id,
            "reason": "--demo-signing: the MCP server signed for the host; no person signed"})

    def __init__(self, routes, signer, verifier, demo_signing: bool = False):
        self.signer = signer
        self.demo_signing = demo_signing
        self.audit_path = os.path.join(
            tempfile.gettempdir(), f"{IDENTITY_NAME}-mcp-{uuid.uuid4().hex[:8]}.jsonl")
        # One swarm builder for every entry point (dispatcher/swarm.py),
        # fixed 2026-10-11: this server used to build 18 of the 20 agents by
        # hand, with a made-up photography vendor ("v-photo") and made-up
        # listing scope, and re-registered each agent's bare handler so the
        # unrecognized-config check was skipped. Now: all 20 agents, the HITL
        # manager, the vendor roster only from a ratified file
        # (LISTING_CONFIG_DIR, default config/), and saved state only when
        # LISTING_STATE_DB names a file.
        from .swarm import build_swarm
        self.swarm = build_swarm(self.audit_path,
                                 state_db=os.environ.get("LISTING_STATE_DB") or None,
                                 config_dir=os.environ.get("LISTING_CONFIG_DIR") or None,
                                 verifier=verifier.verifier())
        self.hub = self.swarm.hub
        self.external = self.swarm.external
        self.spokes = self.swarm.spokes
        from . import listing_spokes as _ls
        self.spoke_mod = _ls

    # --- front-door operations -------------------------------------------
    def describe(self):
        routes = json.load(open(ROUTES_PATH, encoding="utf-8"))
        priority = {}
        if os.path.exists(PRIORITY_PATH):
            priority = json.load(open(PRIORITY_PATH, encoding="utf-8")).get("classes", {})
        return {
            "identity": IDENTITY_NAME,
            "vertical": routes.get("vertical", "unstated"),
            "closed_track": {
                "route_count": len(routes["routes"]),
                "legal_intents": sorted({r["intent"] for r in routes["routes"]}),
            },
            "playbooks": priority,
            "governance": {
                "signed_authority_required": True,
                "server_signs_for_host": self.demo_signing,
                "reconciliation_tolerance": "$0.00",
                "audit": "hash-chained, tamper-evident (see identity.audit)",
                "note": ("This is a governed identity, not a toolbox. The "
                         "host submits intents at the front door; the hub "
                         "routes, gates, signs, and seals internally."),
            },
            "runtime": "wired" if self.spokes else "spec-only (no spoke module)",
        }

    def submit(self, intent, payload, context_id=None):
        ctx = context_id or f"mcp-{uuid.uuid4().hex[:8]}"
        if not self.spokes:
            return {"ok": False,
                    "reason": "identity is spec-only in this build; no "
                              "runtime spokes to execute the intent",
                    "context_id": ctx}
        # Front-door intents only: drive the identity's real entry points.
        result = self._drive(intent, payload, ctx)
        return result

    def _drive(self, intent, payload, ctx):
        """Map a small set of front-door intents to the identity's real
        entry points. Anything not a legal front-door op is refused."""
        modname = getattr(self.spoke_mod, "__name__", "") if self.spoke_mod \
            else ""
        if modname.endswith("listing_spokes"):
            if intent == "listing.authorize":
                # front door: the signed new-listing authorization (P01)
                if not self.demo_signing:
                    return {"ok": False, "context_id": ctx,
                            "reason": "listing.authorize needs the broker's "
                                      "signature; this server signs for a host "
                                      "only in --demo-signing mode"}
                from dispatcher.core import Envelope
                env = Envelope(from_agent="human", to_agent="05",
                               intent="listing.change.authorized",
                               client_context_id=ctx, payload=payload,
                               provenance={"source": "mcp-host",
                                           "captured_at": "runtime",
                                           "verbatim_available": True})
                self._declare_server_signed(env)
                self.signer.sign(env)
                res = self.hub.send(env)
                return {"ok": res.get("status") == "ack",
                        "context_id": ctx,
                        "note": "listing authorization submitted; the swarm "
                                "runs P01 setup->production->go-live behind "
                                "the gates",
                        "audit_entries": len(self.hub.audit.read())}
            return {"ok": False, "context_id": ctx,
                    "reason": f"'{intent}' is not a legal front-door intent "
                              f"for listing; the signed lane is "
                              f"'listing.authorize'"}
        return {"ok": False, "context_id": ctx,
                "reason": f"'{intent}' is not a legal front-door intent for "
                          f"{IDENTITY_NAME}; call identity.describe for the "
                          f"legal surface"}

    def authority(self, intent, payload, signature_hex=None, context_id=None):
        """The signed-money lane, explicit and separate. Without a real
        signature the hub rejects it - proving the gate to the caller."""
        ctx = context_id or f"mcp-{uuid.uuid4().hex[:8]}"
        if not payload.get("to"):
            return {"ok": False, "context_id": ctx, "hub_status": None,
                    "reason": "payload.to (the receiving agent) is required"}
        env = Envelope(from_agent="human",
                       to_agent=payload["to"],
                       intent=intent, client_context_id=ctx,
                       payload=payload,
                       provenance={"source": "mcp-host",
                                   "captured_at": "runtime",
                                   "verbatim_available": True})
        if signature_hex == "DEMO_SIGN_WITH_SERVER_KEY" and self.demo_signing:
            # explicit demo affordance: server signs so a host can see the
            # signed path succeed. Production hosts present their OWN
            # signature; this is clearly labelled, not a hidden bypass.
            self._declare_server_signed(env)
            self.signer.sign(env)
        res = self.hub.send(env)
        accepted = res.get("status") == "ack"
        return {"ok": accepted, "context_id": ctx,
                "hub_status": res.get("status"),
                "reason": ("signed authority executed" if accepted
                           else "REJECTED: authority requires a valid "
                                "signature (this is the gate working)")}

    def audit(self):
        v = self.hub.audit.verify_chain()
        return {"identity": IDENTITY_NAME,
                "audit_path": self.audit_path,
                "entries": len(self.hub.audit.read()),
                "chain_verified": v.get("ok"),
                "dead_letters": len(self.hub.queues.get("dead.letter", [])),
                "statement": ("The log is tamper-evident. Alter any line and "
                              "chain_verified becomes false, naming the line.")}


# ---------------------------------------------------------------------------
# MCP server: four tools, no more.
# ---------------------------------------------------------------------------
def build_server(identity):
    from mcp.server import Server
    import mcp.types as types

    server = Server(f"quietfire-identity-{IDENTITY_NAME}")

    TOOLS = [
        types.Tool(
            name="identity.describe",
            description=(f"Describe the governed {IDENTITY_NAME} identity: "
                         "its closed track (legal intents), playbooks, and "
                         "governance guarantees. Read-only. Call this first "
                         "to learn what the identity accepts."),
            inputSchema={"type": "object", "properties": {}}),
        types.Tool(
            name="identity.submit",
            description=("Submit ONE intent at the identity's front door. "
                         "The governed hub validates it against the closed "
                         "track, runs the playbook, enforces every gate, and "
                         "returns the result or a refusal-with-reason. You do "
                         "NOT get to route internally - the hub does."),
            inputSchema={"type": "object",
                         "properties": {
                             "intent": {"type": "string"},
                             "payload": {"type": "object"},
                             "context_id": {"type": "string"}},
                         "required": ["intent", "payload"]}),
        types.Tool(
            name="identity.authority",
            description=("The signed-money lane, kept explicit and separate. "
                         "Authority intents (listing.change.authorized, "
                         "config.update) "
                         "require a valid signature; without one the hub "
                         "rejects - and returns the rejection so you can see "
                         "the gate working."),
            inputSchema={"type": "object",
                         "properties": {
                             "intent": {"type": "string"},
                             "payload": {"type": "object"},
                             "signature_hex": {"type": "string"},
                             "context_id": {"type": "string"}},
                         "required": ["intent", "payload"]}),
        types.Tool(
            name="identity.audit",
            description=("Return the hash-chain verification for this "
                         "session's audit log so you can prove tamper-"
                         "evidence: entry count, chain_verified, dead "
                         "letters."),
            inputSchema={"type": "object", "properties": {}}),
    ]

    @server.list_tools()
    async def list_tools():
        return TOOLS

    @server.call_tool()
    async def call_tool(name, arguments):
        arguments = arguments or {}
        if name == "identity.describe":
            out = identity.describe()
        elif name == "identity.submit":
            out = identity.submit(arguments["intent"], arguments["payload"],
                                  arguments.get("context_id"))
        elif name == "identity.authority":
            out = identity.authority(arguments["intent"], arguments["payload"],
                                     arguments.get("signature_hex"),
                                     arguments.get("context_id"))
        elif name == "identity.audit":
            out = identity.audit()
        else:
            out = {"ok": False, "reason": f"unknown tool {name}"}
        return [types.TextContent(type="text",
                                  text=json.dumps(out, indent=2))]

    return server


async def _serve():
    routes, signer, verifier = _boot_conformance()
    sys.stderr.write(
        f"[identity_mcp] conformance PASSED for {IDENTITY_NAME}: "
        f"closed track + signer gate + audit chain intact\n")
    demo = "--demo-signing" in sys.argv[1:]
    if demo:
        sys.stderr.write("[identity_mcp] DEMO SIGNING ON: the server will sign "
                         "authority actions for the host. Not for production.\n")
    identity = GovernedIdentity(routes, signer, verifier, demo_signing=demo)
    server = build_server(identity)
    from mcp.server.stdio import stdio_server
    async with stdio_server() as (read, write):
        await server.run(read, write,
                         server.create_initialization_options())


def main():
    try:
        asyncio.run(_serve())
    except ConformanceError as e:
        sys.stderr.write(f"[identity_mcp] BOOT REFUSED\n{e}\n")
        sys.exit(2)


if __name__ == "__main__":
    main()
