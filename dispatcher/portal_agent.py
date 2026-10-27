"""portal_agent - runs ONE agent alone, connected to the dispatcher by its portal.

Owner decision 2026-10-26 (agent isolation V1). Started as

    python -m dispatcher.portal_agent <agent id> <socket path>

inside the agent's own container (no network, read-only, its own socket
only) or, for tests and small setups, as its own process. The agent's code
is unchanged: it is handed an AgentHub instead of the real hub. The
AgentHub has the portal menu and nothing else; any other use of the hub
fails at once with "not on the portal menu", so a hidden reach shows up
instead of working quietly.

What the agent can do through it is listed in dispatcher/portal.py. It has
no drawers, no log, no key and no other agent: the dispatcher does those
things for it, as the agent it knows is on this line.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import socket
import sys
import time
from typing import Any

# the same rule as the other entry points: bytecode compiled fresh into a
# private folder, so a planted .pyc beside a source file is never loaded
import atexit as _atexit, shutil as _shutil, tempfile as _tempfile  # noqa: E401,E402
if not getattr(sys, "_listing_fresh_bytecode", False):
    sys.pycache_prefix = _tempfile.mkdtemp(prefix="listing-pyc-")
    _atexit.register(_shutil.rmtree, sys.pycache_prefix, True)
    sys._listing_fresh_bytecode = True

AGENT_CLASSES = {
    "01": ("listing_spokes", "Spoke01LeadCapture"),
    "02": ("listing_spokes_02", "Spoke02LeadQualification"),
    "03": ("listing_spokes_03", "Spoke03LeadNurture"),
    "04": ("listing_spokes_04", "Spoke04ListingDescription"),
    "05": ("listing_spokes_05", "Spoke05MLSListingManagement"),
    "06": ("listing_spokes_06", "Spoke06ShowingScheduler"),
    "07": ("listing_spokes_07", "Spoke07TransactionCoordinator"),
    "08": ("listing_spokes_08", "Spoke08DocumentCollection"),
    "09": ("listing_spokes_09", "Spoke09VendorCoordination"),
    "10": ("listing_spokes_10", "Spoke10MarketData"),
    "11": ("listing_spokes_11", "Spoke11ClientCommunication"),
    "12": ("listing_spokes_12", "Spoke12MarketingCampaign"),
    "13": ("listing_spokes_13", "Spoke13BuyerSearchMatch"),
    "14": ("listing_spokes", "Spoke14CRMPipeline"),
    "15": ("listing_spokes_15", "Spoke15FinancialTracking"),
    "16": ("listing_spokes_16", "Spoke16AfterCloseReferral"),
    "17": ("listing_spokes_17", "Spoke17ComplianceFairHousing"),
    "18": ("listing_spokes_18", "Spoke18CalendarTask"),
    "19": ("listing_spokes_19", "Spoke19Prospecting"),
    "20": ("listing_spokes_20", "Spoke20SocialMediaMonitoring"),
}


def _off_menu(name: str):
    raise AttributeError(f"not on the portal menu: hub.{name}")


class _Part:
    """A piece of the hub an agent reaches with a dot (hub.audit, hub.hitl,
    ...); only the named methods exist."""
    _names: tuple = ()

    def __init__(self, peer):
        object.__setattr__(self, "_peer", peer)

    def __getattr__(self, name):
        _off_menu(f"{type(self).__name__.lower()}.{name}")

    def __setattr__(self, name, value):
        _off_menu(f"{type(self).__name__.lower()}.{name}")


class Audit(_Part):
    def append(self, kind: str, data: dict):
        return self._peer.call("log_note", {"kind": kind, "data": data})

    def read(self):
        # Agent 18 checks which envelopes are on the record. It gets the
        # envelope ids and nothing else of the log.
        return [{"kind": "envelope.persisted", "envelope_id": i}
                for i in self._peer.call("on_record")]


class Hitl(_Part):
    def __init__(self, peer):
        super().__init__(peer)
        object.__setattr__(self, "resumers", {})

    def pause_operation(self, client_context_id, agent_id, paused_intent, reason,
                        original_payload, required_decision="APPROVE_OR_REJECT"):
        return self._peer.call("hold", {
            "client_context_id": client_context_id, "agent_id": agent_id,
            "paused_intent": paused_intent, "reason": reason,
            "original_payload": original_payload, "required_decision": required_decision})

    def register_resumption_handler(self, agent_id, handler):
        self.resumers[agent_id] = handler


class Manners(_Part):
    def phase_gate(self, position: str):
        return self._peer.call("phase_gate", {"position": position})


class Decision(_Part):
    def __init__(self, peer):
        super().__init__(peer)
        object.__setattr__(self, "_allow_external", False)

    def __setattr__(self, name, value):
        if name == "allow_external":       # Agent 02 sets it from the broker's signed setting
            object.__setattr__(self, "_allow_external", bool(value))
            return
        _off_menu(f"decision.{name}")

    def evaluate_lead(self, client_context_id, payload, rubric, confidence_threshold=0.45):
        return self._peer.call("decide", {
            "client_context_id": client_context_id, "payload": payload, "rubric": rubric,
            "confidence_threshold": confidence_threshold,
            "allow_external": self._allow_external})

    def get_coprocessor_status(self):
        return self._peer.call("decision_status", {"allow_external": self._allow_external})


class Drafting(_Part):
    def gate(self):
        return self._peer.call("draft_gate")

    def draft_remarks(self, agent_id, envelope_id, facts, char_limit):
        return self._peer.call("draft_remarks", {"agent_id": agent_id, "envelope_id": envelope_id,
                                                 "facts": facts, "char_limit": char_limit})


class AgentHub:
    """The hub as one agent sees it: the portal menu, nothing else."""

    def __init__(self, peer, agent_id: str):
        d = self.__dict__
        d["_peer"], d["_agent_id"] = peer, agent_id
        d["audit"], d["hitl"], d["manners"] = Audit(peer), Hitl(peer), Manners(peer)
        d["decision_adapter"], d["drafting"] = Decision(peer), Drafting(peer)
        d["handlers"] = {}

    def __getattr__(self, name):
        _off_menu(name)

    def __setattr__(self, name, value):
        _off_menu(name)

    def send(self, env):
        return self._peer.call("send", {"envelope": env})

    def ingest_spoke_trace(self, agent_id, envelope_id, thought, result):
        return self._peer.call("trace", {"agent_id": agent_id, "envelope_id": envelope_id,
                                         "thought": thought, "result": result})

    def escalate(self, queue, record):
        return self._peer.call("escalate", {"queue": queue, "record": record})

    def outbound_state(self, envelope_id):
        return self._peer.call("outbound_state", {"envelope_id": envelope_id})

    def file_record_via_dispatcher(self, agent_id, ctx, category, name, record, identity=None):
        return self._peer.call("file_record", {"agent_id": agent_id, "ctx": ctx,
                                               "category": category, "name": name,
                                               "record": record, "identity": identity})

    def register(self, agent_id, handler):
        # the dispatcher wraps the agent's handler (config checks, turn
        # counting) on its side; here the agent's own handle() is kept
        self.handlers[agent_id] = getattr(handler, "__wrapped__", handler)


class AgentRunner:
    def __init__(self, agent_id: str):
        if agent_id not in AGENT_CLASSES:
            raise SystemExit(f"unknown agent {agent_id!r}")
        self.agent_id = agent_id
        self.spoke = None
        self.hub = None
        self._sent_digest = None

    def handlers(self, peer) -> dict:
        self.peer = peer
        return {"init": self.init, "deliver": self.deliver, "resume": self.resume,
                "state": self.state, "restore": self.restore}

    def _state(self) -> dict:
        from .state_snapshot import agent_state
        return agent_state(self.spoke)

    def _changed_state(self):
        """The agent's state when it changed since it was last sent, else None."""
        from .state_snapshot import encode
        enc = encode(self._state())
        digest = hashlib.sha256(json.dumps(enc, sort_keys=True).encode("utf-8")).hexdigest()
        if digest == self._sent_digest:
            return None
        self._sent_digest = digest
        return self._state()

    def init(self, agent_id: str, kwargs: dict):
        if agent_id != self.agent_id:
            raise ValueError(f"this is agent {self.agent_id}, not {agent_id}")
        if self.spoke is not None:
            raise ValueError("already started")
        mod, cls = AGENT_CLASSES[agent_id]
        klass = getattr(importlib.import_module(f"dispatcher.{mod}"), cls)
        self.hub = AgentHub(self.peer, agent_id)
        self.spoke = klass(self.hub, **(kwargs or {}))
        return {"registered": sorted(self.hub.handlers),
                "resumers": sorted(self.hub.hitl.resumers),
                "state": self._changed_state()}

    def deliver(self, envelope):
        from .clock import take_results
        handler = self.hub.handlers[self.agent_id]
        result = handler(envelope)
        return {"result": result, "tick_results": take_results(envelope.envelope_id),
                "state": self._changed_state()}

    def resume(self, wait_state, decision):
        handler = self.hub.hitl.resumers[self.agent_id]
        result = handler(wait_state, decision)
        return {"result": result, "state": self._changed_state()}

    def state(self):
        self._sent_digest = None
        return self._changed_state()

    def restore(self, attrs: dict):
        for k, v in attrs.items():
            setattr(self.spoke, k, v)
        return {"restored": sorted(attrs), "state": self._changed_state()}


def connect(path: str, wait_s: float = 60.0) -> socket.socket:
    end = time.monotonic() + wait_s
    while True:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            s.connect(path)
            return s
        except OSError:
            s.close()
            if time.monotonic() > end:
                raise
            time.sleep(0.05 if wait_s <= 60 else 1.0)


def main(argv=None) -> int:
    from .portal import DISPATCHER_TO_AGENT, Peer, PortalError
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print("usage: python -m dispatcher.portal_agent <agent id> <socket path>", file=sys.stderr)
        return 2
    agent_id, path = argv
    if os.name != "nt":
        os.umask(0o077)
    runner = AgentRunner(agent_id)
    # in a container the agent waits for the dispatcher as long as it takes
    # (LISTINGASSISTANTS_CONNECT_WAIT=0); a started process gives up after 60 s
    wait = float(os.environ.get("LISTINGASSISTANTS_CONNECT_WAIT", "60"))
    sock = connect(path, wait_s=wait if wait > 0 else float("inf"))
    peer = Peer(sock, {}, DISPATCHER_TO_AGENT, name=f"agent {agent_id}")
    peer.handlers = runner.handlers(peer)
    try:
        peer.serve_forever()
    except PortalError as e:
        print(f"agent {agent_id}: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
