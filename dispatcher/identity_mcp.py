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
    python3 -m dispatcher.identity_mcp                  # inside your running Broker Desk
    IDENTITY_ROOT=/path python3 -m dispatcher.identity_mcp
    python3 -m dispatcher.identity_mcp --standalone     # its own private swarm
    python3 -m dispatcher.identity_mcp --demo-signing   # DEMO ONLY, see below

Desk mode (the default, owner decision 2026-10-22): the server works inside
the broker's RUNNING Broker Desk, on the broker's own records, through the
desk's door (POST /api/mcp on 127.0.0.1 with the token the desk writes to
desk-mcp.json in its state folder). One record: what the assistant brings in
is on the desk at once. Five tools: identity.status reads the desk,
identity.submit brings in an inquiry (lead.inbound only), identity.audit
checks the record, identity.describe names the surface, and
identity.authority is always refused: the assistant never signs. With no
desk running, every call says to start it. --standalone (and
--demo-signing) build a separate swarm in this process instead.

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
    probe_path = os.path.join(tempfile.gettempdir(), f"conformance-{uuid.uuid4().hex[:8]}.jsonl")
    probe_audit = AuditLog(probe_path)
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
    # the probe's log is thrown away (2026-10-14: every boot left one in the
    # temp folder; 4,389 had piled up on one test machine)
    for leftover in (probe_path, probe_path + ".lock"):
        try:
            os.remove(leftover)
        except OSError:
            pass

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
                                 verifier=verifier.verifier(),
                                 attestation=operator_attestation())
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
# Desk mode (owner decision 2026-10-22, the default): the assistant works
# inside the broker's RUNNING Broker Desk, on the broker's records, through
# the desk's own door (POST /api/mcp with the token from the private file
# desk-mcp.json the desk writes at start). One record: what the assistant
# brings in shows on the desk at once, survives a restart and is seen by the
# clock. The assistant can read the desk and bring in an inquiry; it cannot
# sign, release or decide anything - that is the broker, on the desk.
# ---------------------------------------------------------------------------
class DeskIdentity:
    demo_signing = False
    spokes = None      # describe() reads it; the desk holds the agents

    def __init__(self, state_dir=None):
        self.state_dir = state_dir or os.environ.get("LISTINGASSISTANTS_STATE_DIR") or \
            os.path.join(ROOT, "console-state")
        self.door_file = os.path.join(self.state_dir, "desk-mcp.json")

    def _call(self, tool, args=None):
        import urllib.error
        import urllib.request
        not_running = {"ok": False, "desk": "not running",
                       "reason": "Your Broker Desk is not running. Start it (desktop shortcut "
                                 "'ListingAssistants Desk'); the assistant works inside your "
                                 "running desk, on your records."}
        try:
            door = json.load(open(self.door_file, encoding="utf-8"))
        except (OSError, ValueError):
            return not_running
        req = urllib.request.Request(
            f"http://127.0.0.1:{int(door['port'])}/api/mcp", method="POST",
            data=json.dumps({"tool": tool, "args": args or {}}).encode(),
            headers={"Content-Type": "application/json", "X-MCP-Token": door["token"]})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                body = json.loads(e.read() or b"{}")
            except ValueError:
                body = {}
            return {"ok": False, "reason": body.get("error") or f"desk answered {e.code}"}
        except (urllib.error.URLError, OSError):
            return not_running

    def describe(self):
        out = GovernedIdentity.describe(self)
        out["governance"]["server_signs_for_host"] = False
        out["governance"]["note"] = (
            "You work inside the broker's running Broker Desk, on the broker's records. "
            "Read it with identity.status; bring in an inquiry with identity.submit "
            "(intent lead.inbound). You never sign: listings, prices, releases and "
            "decisions are signed by the broker on the Desk.")
        out["runtime"] = "the broker's running desk" if self._call("audit").get("ok") \
            else "desk not running"
        return out

    def status(self):
        return self._call("status")

    def submit(self, intent, payload, context_id=None):
        return self._call("submit", {"intent": intent, "payload": payload,
                                     "context_id": context_id})

    def authority(self, intent, payload, signature_hex=None, context_id=None):
        return {"ok": False, "intent": intent,
                "reason": "The assistant cannot sign. Prepare what is needed and tell the "
                          "broker; the broker signs it on the Broker Desk with their own key."}

    def audit(self):
        return self._call("audit")


# ---------------------------------------------------------------------------
# MCP server: four tools (five in desk mode), no more.
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

    if isinstance(identity, DeskIdentity):
        # in desk mode the host is told plainly what it may do, so the
        # assistant does not try acts that are the broker's (2026-10-22)
        TOOLS[1] = types.Tool(
            name="identity.submit",
            description=("Bring a new inquiry onto the broker's running Broker Desk. "
                         "intent must be 'lead.inbound'; payload: channel (web_form, "
                         "email, sms, phone or walk_in), name, email and/or phone, "
                         "message, property_interest, and consent per channel, e.g. "
                         "{\"email\": \"yes\"}. Give context_id to name the lead. "
                         "Every other act (listings, releases, changes) is done by "
                         "the broker on the Desk and is refused here."),
            inputSchema={"type": "object",
                         "properties": {
                             # not an enum: another intent gets a reason back
                             # ("done by you on the Broker Desk"), not a schema error
                             "intent": {"type": "string"},
                             "payload": {"type": "object"},
                             "context_id": {"type": "string"}},
                         "required": ["intent", "payload"]})
        TOOLS[2] = types.Tool(
            name="identity.authority",
            description=("Always refused: the assistant never signs. When something "
                         "needs a signature, prepare what is needed and tell the "
                         "broker; the broker signs on the Broker Desk with their own key."),
            inputSchema=TOOLS[2].inputSchema)
        TOOLS.insert(1, types.Tool(
            name="identity.status",
            description=("Read the broker's running Broker Desk: what needs the broker, "
                         "listings and where each stands, leads, prospects waiting, the "
                         "outbox count and whether the record is intact. Read-only."),
            inputSchema={"type": "object", "properties": {}}))

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
        elif name == "identity.status" and isinstance(identity, DeskIdentity):
            out = identity.status()
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
    if demo or "--standalone" in sys.argv[1:]:
        # its own throwaway record (a demo or a test), not the broker's
        identity = GovernedIdentity(routes, signer, verifier, demo_signing=demo)
    else:
        identity = DeskIdentity()
        sys.stderr.write(f"[identity_mcp] desk mode: the broker's running desk at "
                         f"{identity.state_dir}\n")
    server = build_server(identity)
    from mcp.server.stdio import stdio_server
    async with stdio_server() as (read, write):
        await server.run(read, write,
                         server.create_initialization_options())


def operator_attestation():
    """2026-10-14: when this machine has an operator key (`console init`),
    the MCP server holds to the operator's attestation as the console does,
    and refuses to start on a changed install. Without one (a demo, a fresh
    clone, CI) it records boot.attestation enforced: false."""
    from dispatcher.boot_attest import fingerprint
    state = os.environ.get("LISTINGASSISTANTS_STATE_DIR") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "console-state")
    from dispatcher.boot_attest import PUBLIC_FILE, operator_public_key
    if not any(os.path.exists(os.path.join(state, f)) for f in ("operator-key.bin", PUBLIC_FILE)):
        return None
    pub = operator_public_key(state)       # the key here, or the signer's public key
    return {"state_dir": state, "verify_bytes": Ed25519Verifier(pub).verify_bytes,
            "key_fingerprint": fingerprint(pub)}


def main():
    if os.name != "nt":
        os.umask(0o077)     # its audit log and state are readable only by this account
    from dispatcher.boot_attest import AttestationRefused
    try:
        asyncio.run(_serve())
    except ConformanceError as e:
        sys.stderr.write(f"[identity_mcp] BOOT REFUSED\n{e}\n")
        sys.exit(2)
    except AttestationRefused as e:
        sys.stderr.write(f"[identity_mcp] BOOT REFUSED - install not attested\n{e}\n")
        sys.exit(2)


if __name__ == "__main__":
    main()
