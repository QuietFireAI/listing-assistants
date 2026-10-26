"""portal_dispatcher - the dispatcher's side of the agents' portals.

Owner decisions 2026-10-26 (agent isolation V1, claude/AGENT_ISOLATION_
DECISIONS_2026-10-26.md in the project):

  - Each agent has one private line (a Unix socket) and a fixed menu. The
    dispatcher knows the agent by its line: whatever arrives on agent 05's
    line is agent 05, whatever it writes in a "from" field.
  - A route not on identity/routes.json is the highest order of violation:
    refused, recorded, the agent stopped until Jeff clears it, and an alert
    sent with this system's id and an error code to look up on the record.
    So is speaking as another agent, and asking for anything off the menu.
  - A crash (the line breaks, or no answer in time) stops the agent and
    holds the message for Jeff. No automatic restart (to be reviewed after
    30 days of clean running).

The dispatcher stops an agent by cutting its line and refusing it; it needs
no control over containers, so it holds no power over the machine.

What each menu item does, as the agent on that line:

  send(envelope)            hub.send, after checking "from" is this agent
  trace(...)                hub.ingest_spoke_trace, as this agent
  escalate(queue, record)   hub.escalate
  log_note(kind, data)      a line on the record, only of the kinds agents
                            write (AGENT_NOTE_KINDS) and only as this agent
  outbound_state(id)        was a message held, sent or not sent
  on_record()               the ids of the envelopes on the record (Agent 18
                            used to read the whole log; it needs only these)
  file_record(...)          files into a client's drawer (agents 04 05 07 08
                            14 15); the drawers stay with the dispatcher
  hold(...)                 a hold for the broker (HITL), as this agent
  phase_gate(position)      a MANNERS re-injection point
  decide(...)/decision_status   the decision engine (Agent 02 only)
  draft_gate()/draft_remarks(...)   model drafting (Agent 04 only)
"""
from __future__ import annotations

import os
import secrets
import socket
from typing import Any, Callable, Optional

from .core import Envelope
from .portal import AGENT_TO_DISPATCHER, Peer, PortalClosed, PortalError, Refused, RemoteError

# the narrow items, and who may use them (from what the agents' code calls)
ONLY_FOR = {
    "file_record": {"04", "05", "07", "08", "14", "15"},
    "decide": {"02"}, "decision_status": {"02"},
    "draft_gate": {"04"}, "draft_remarks": {"04"},
}

# the kinds of record line an agent writes itself (everything else on the
# record is written by the dispatcher: envelopes, acks, state, signatures)
AGENT_NOTE_KINDS = frozenset({
    "config.load", "decision.lead", "decision.engine", "drafting.mode",
    "drafting.model_used", "drafting.model_unavailable", "drawer.provisioned",
    "drawer.identity_conflict", "drawer.filed", "drawer.refused", "sweep.error",
    "handoff.failed", "config.unchanged", "config.unrecognized"})

CALL_TIMEOUT_S = 120.0


class AgentStopped(RuntimeError):
    """The agent's line is cut; nothing is delivered to it until cleared."""


def system_id(state_dir: str) -> str:
    """This install's short id for alerts, made once and kept in the state
    folder (it names the system, not the broker or a client)."""
    path = os.path.join(state_dir, "system-id")
    try:
        with open(path, encoding="utf-8") as f:
            sid = f.read().strip()
        if sid:
            return sid
    except OSError:
        pass
    sid = "LA-" + secrets.token_hex(3).upper()
    from .private_file import write_private
    write_private(path, sid.encode("utf-8"))
    return sid


def _frozen(value: Any) -> Any:
    import types
    if isinstance(value, dict):
        return types.MappingProxyType({k: _frozen(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_frozen(v) for v in value)
    if isinstance(value, set):
        return frozenset(value)
    return value


class RemoteSpoke:
    """The dispatcher's handle on one agent running elsewhere. Reading an
    attribute reads the agent's last reported state (the Desk and the run
    tracker read agents this way); setting one sends it to the agent (the
    state restore at start-up)."""

    def __init__(self, team: "Team", agent_id: str):
        object.__setattr__(self, "_portal_team", team)
        object.__setattr__(self, "_portal_id", agent_id)
        object.__setattr__(self, "_portal_state", {})

    def __portal_state__(self) -> dict:
        return dict(self._portal_state)

    def _portal_apply(self, state: Optional[dict]) -> None:
        if state is not None:
            object.__setattr__(self, "_portal_state", state)

    def __getattr__(self, name: str) -> Any:
        state = object.__getattribute__(self, "_portal_state")
        if name in state:
            # read-only: changing a copy here would change nothing in the
            # agent, so it fails loudly instead (assign the attribute to send it)
            return _frozen(state[name])
        raise AttributeError(f"agent {self._portal_id} has no {name!r}")

    def __setattr__(self, name: str, value: Any) -> None:
        out = self._portal_team.call(self._portal_id, "restore", {"attrs": {name: value}})
        self._portal_apply(out.get("state"))

    def handle(self, env: Envelope):
        out = self._portal_team.call(self._portal_id, "deliver", {"envelope": env},
                                     message=env)
        self._portal_apply(out.get("state"))
        if out.get("tick_results"):
            from . import clock
            clock._RESULTS[env.envelope_id] = out["tick_results"]
        return out.get("result")

    def resume(self, wait_state, decision):
        out = self._portal_team.call(self._portal_id, "resume",
                                     {"wait_state": wait_state, "decision": decision})
        self._portal_apply(out.get("state"))
        return out.get("result")


class Team:
    """All the agents' lines, on the dispatcher's side.

    launcher(agent_id, socket_path) starts an agent process when the
    dispatcher starts its agents itself (tests, small setups); with
    containers it is None and each agent container connects on its own."""

    def __init__(self, hub, sockets_dir: str, state_dir: str,
                 launcher: Optional[Callable[[str, str], Any]] = None,
                 accept_timeout_s: float = 60.0, call_timeout_s: float = CALL_TIMEOUT_S,
                 alert: Optional[Callable[[str, dict], None]] = None):
        self.hub = hub
        self.sockets_dir = sockets_dir
        self.state_dir = state_dir
        self.launcher = launcher
        self.accept_timeout_s = accept_timeout_s
        self.call_timeout_s = call_timeout_s
        self.peers: dict[str, Peer] = {}
        self.stopped: dict[str, dict] = {}
        self.processes: dict[str, Any] = {}
        self._depth: dict[str, int] = {}
        self.remotes: dict[str, RemoteSpoke] = {}
        self.kwargs: dict[str, dict] = {}
        self.system_id = system_id(state_dir)
        self.alert = alert
        os.makedirs(sockets_dir, exist_ok=True)

    # ------------------------------------------------------------ lines
    def socket_path(self, agent_id: str) -> str:
        return os.path.join(self.sockets_dir, agent_id, "portal.sock")

    def connect_agent(self, agent_id: str) -> None:
        path = self.socket_path(agent_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path):
            os.remove(path)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(path)
        os.chmod(path, 0o600)
        server.listen(1)
        server.settimeout(self.accept_timeout_s)
        try:
            if self.launcher is not None:
                self.processes[agent_id] = self.launcher(agent_id, path)
            conn, _ = server.accept()
        except socket.timeout as e:
            raise RuntimeError(f"agent {agent_id} did not connect to its portal in "
                               f"{self.accept_timeout_s:.0f} s ({path})") from e
        finally:
            server.close()                 # one agent per line: nobody else can connect
            try:
                os.remove(path)
            except OSError:
                pass
        conn.settimeout(self.call_timeout_s)
        self.peers[agent_id] = Peer(conn, self._handlers(agent_id), AGENT_TO_DISPATCHER,
                                    name=f"agent {agent_id}",
                                    on_off_menu=lambda m, a=agent_id: self.violation(
                                        a, "off_menu", f"asked for {m!r}, which is not on its menu"))

    def call(self, agent_id: str, method: str, params: dict, message: Optional[Envelope] = None):
        if agent_id in self.stopped:
            raise AgentStopped(f"agent {agent_id} is stopped ({self.stopped[agent_id]['why']}); "
                               f"the message waits for you")
        peer = self.peers.get(agent_id)
        if peer is None:
            raise AgentStopped(f"agent {agent_id} is not connected")
        self._depth[agent_id] = self._depth.get(agent_id, 0) + 1
        try:
            return peer.call(method, params)
        except RemoteError:
            if agent_id in self.stopped:      # it was stopped while handling this message
                raise AgentStopped(f"agent {agent_id} was stopped while handling this message "
                                   f"({self.stopped[agent_id]['why']}); the message waits for you")
            raise                              # the agent's own exception, as in one process
        except PortalError as e:
            if agent_id not in self.stopped:
                self.crash(agent_id, f"{type(e).__name__}: {e}", message)
            raise AgentStopped(f"agent {agent_id} stopped: {e}; the message waits for you") from e
        finally:
            self._depth[agent_id] -= 1
            if agent_id in self.stopped and self._depth[agent_id] == 0:
                peer.close()                   # the line is cut once nothing is in flight on it

    # ------------------------------------------------------------ stops
    def _stop(self, agent_id: str, kind: str, why: str) -> None:
        self.stopped[agent_id] = {"kind": kind, "why": why}
        if not self._depth.get(agent_id):
            peer = self.peers.get(agent_id)
            if peer is not None:
                peer.close()

    def violation(self, agent_id: str, kind: str, detail: str,
                  envelope: Optional[Envelope] = None) -> str:
        """The highest order of violation: record, stop, alert. Returns the
        error code to look up on the record."""
        rec = {"agent": agent_id, "violation": kind, "detail": detail,
               "system_id": self.system_id}
        if envelope is not None:
            rec.update({"envelope_id": envelope.envelope_id, "intent": envelope.intent,
                        "from_agent": envelope.from_agent, "to_agent": envelope.to_agent})
        entry = self.hub.audit.append("portal.violation", rec)
        code = f"V{agent_id}-{str(entry)[:6].upper()}"
        self._stop(agent_id, "violation", f"{kind}: {detail} (code {code})")
        self.hub.audit.append("portal.agent_stopped", {
            "agent": agent_id, "stopped_for": "violation", "code": code, "system_id": self.system_id,
            "reason": "stopped until you review it and clear it on the Desk"})
        self._raise_alert("portal.violation", {
            "client_context_id": "portal", "agent": agent_id, "alert_code": code,
            "system_id": self.system_id, "violation": kind})
        return code

    def crash(self, agent_id: str, why: str, message: Optional[Envelope] = None) -> None:
        rec = {"agent": agent_id, "stopped_for": "crash", "reason": why, "system_id": self.system_id,
               "held_envelope_id": message.envelope_id if message is not None else None}
        entry = self.hub.audit.append("portal.agent_stopped", rec)
        code = f"C{agent_id}-{str(entry)[:6].upper()}"
        self._stop(agent_id, "crash", f"{why} (code {code})")
        self._raise_alert("portal.crash", {
            "client_context_id": "portal", "agent": agent_id, "alert_code": code,
            "system_id": self.system_id})

    def _raise_alert(self, queue: str, record: dict) -> None:
        self.hub.queue_and_notify(queue, record)
        if self.alert is not None:
            self.alert(queue, record)

    def clear(self, agent_id: str, by: str) -> dict:
        """Jeff (or the broker) reviewed a stopped agent and cleared it. It
        gets a new line: a fresh agent process or container connects, is
        built, and is given back the state it last reported, so it carries
        on where it stopped."""
        if agent_id not in self.stopped:
            return {"ok": False, "reason": f"agent {agent_id} is not stopped"}
        was = self.stopped.pop(agent_id)
        self.hub.audit.append("portal.agent_cleared", {"agent": agent_id, "by": by, "was": was})
        remote = self.remotes[agent_id]
        old = self.processes.pop(agent_id, None)
        _end(old)
        last = remote.__portal_state__()
        self.start_agent(agent_id, self.kwargs.get(agent_id), remote=remote)
        if last:
            out = self.call(agent_id, "restore", {"attrs": last})
            remote._portal_apply(out.get("state"))
        self.hub.audit.append("portal.agent_restarted", {"agent": agent_id, "by": by,
                                                         "state_restored": sorted(last)})
        return {"ok": True, "agent": agent_id}

    def close(self) -> None:
        for peer in self.peers.values():
            peer.close()
        for p in self.processes.values():
            _end(p)

    # ------------------------------------------------------------ menu
    def _handlers(self, aid: str) -> dict:
        hub = self.hub

        def live(item: str) -> None:
            if aid in self.stopped:
                raise Refused(f"agent {aid} is stopped")
            allowed = ONLY_FOR.get(item)
            if allowed is not None and aid not in allowed:
                self.violation(aid, "off_menu", f"asked for {item!r}, which is not on its menu")
                raise Refused(f"{item} is not on agent {aid}'s menu")

        def as_me(field_value: Any, what: str) -> None:
            if field_value not in (None, aid):
                self.violation(aid, "impersonation", f"{what} names agent {field_value!r}")
                raise Refused(f"agent {aid} cannot act as agent {field_value}")

        def send(envelope):
            live("send")
            if not isinstance(envelope, Envelope):
                self.violation(aid, "malformed", "send without a message")
                raise Refused("not a message")
            if envelope.from_agent != aid:
                self.violation(aid, "impersonation",
                               f"a message from {envelope.from_agent!r} on agent {aid}'s line",
                               envelope)
                return {"status": "reject", "envelope_id": envelope.envelope_id,
                        "reason": f"portal: agent {aid} cannot send as {envelope.from_agent}"}
            legal = hub.routes.tuple_legal(envelope.from_agent, envelope.intent, envelope.to_agent)
            res = hub.send(envelope)
            if not legal:
                self.violation(aid, "route_not_on_track",
                               f"{envelope.from_agent} -> {envelope.intent} -> {envelope.to_agent} "
                               f"is not on identity/routes.json", envelope)
            return res

        def trace(agent_id, envelope_id, thought, result):
            live("trace")
            as_me(agent_id, "a trace")
            return hub.ingest_spoke_trace(aid, envelope_id, thought=thought, result=result)

        def escalate(queue, record):
            live("escalate")
            return hub.escalate(queue, record)

        def log_note(kind, data):
            live("log_note")
            if kind not in AGENT_NOTE_KINDS:
                self.violation(aid, "record_kind", f"tried to write a {kind!r} line on the record")
                raise Refused(f"agents do not write {kind!r} lines")
            if isinstance(data, dict):
                as_me(data.get("agent"), f"a {kind} line")
            return hub.audit.append(kind, data)

        def outbound_state(envelope_id):
            live("outbound_state")
            return hub.outbound_state(envelope_id)

        def on_record():
            live("on_record")
            return [e.get("envelope_id") for e in hub.audit.read()
                    if e.get("kind") == "envelope.persisted"]

        def file_record(agent_id, ctx, category, name, record, identity=None):
            live("file_record")
            as_me(agent_id, "a drawer filing")
            from .drawer_filing import file_record as _file
            from .handoff_guard import guard
            return _file(guard(hub, aid), aid, ctx, category, name, record, identity)

        def hold(client_context_id, agent_id, paused_intent, reason, original_payload,
                 required_decision="APPROVE_OR_REJECT"):
            live("hold")
            as_me(agent_id, "a hold")
            return hub.hitl.pause_operation(client_context_id, aid, paused_intent, reason,
                                            original_payload, required_decision=required_decision)

        def phase_gate(position):
            live("phase_gate")
            m = getattr(hub, "manners", None)
            return m.phase_gate(position) if m is not None else None

        def _adapter(allow_external):
            a = getattr(hub, "decision_adapter", None)
            if a is None:
                from .decision_adapter import JevDecisionAdapter
                a = JevDecisionAdapter()
            a.allow_external = bool(allow_external)
            return a

        def decide(client_context_id, payload, rubric, confidence_threshold, allow_external):
            live("decide")
            return _adapter(allow_external).evaluate_lead(
                client_context_id, payload, rubric, confidence_threshold=confidence_threshold)

        def decision_status(allow_external):
            live("decision_status")
            return _adapter(allow_external).get_coprocessor_status()

        def draft_gate():
            live("draft_gate")
            dm = getattr(hub, "drafting", None)
            return dm.gate() if dm is not None else {"ok": False, "reason": "no drafting model wired"}

        def draft_remarks(agent_id, envelope_id, facts, char_limit):
            live("draft_remarks")
            as_me(agent_id, "a drafting request")
            dm = getattr(hub, "drafting", None)
            if dm is None:
                return {"ok": False, "reason": "no drafting model wired in this process"}
            return dm.draft_remarks(aid, envelope_id, facts, char_limit)

        return {"send": send, "trace": trace, "escalate": escalate, "log_note": log_note,
                "outbound_state": outbound_state, "on_record": on_record,
                "file_record": file_record, "hold": hold, "phase_gate": phase_gate,
                "decide": decide, "decision_status": decision_status,
                "draft_gate": draft_gate, "draft_remarks": draft_remarks}

    # ------------------------------------------------------------ start
    def start_agent(self, agent_id: str, kwargs: Optional[dict] = None,
                    remote: Optional[RemoteSpoke] = None) -> RemoteSpoke:
        """Connects the agent, builds it on its side, and registers it with
        the hub exactly as an agent in this process registers itself."""
        from .handoff_guard import register
        self.kwargs[agent_id] = kwargs or {}
        self.connect_agent(agent_id)
        remote = remote or RemoteSpoke(self, agent_id)
        self.remotes[agent_id] = remote
        out = self.call(agent_id, "init", {"agent_id": agent_id, "kwargs": kwargs or {}})
        if out.get("registered") != [agent_id]:
            self.violation(agent_id, "registration",
                           f"registered as {out.get('registered')} instead of {agent_id}")
            raise AgentStopped(f"agent {agent_id} registered as {out.get('registered')}")
        remote._portal_apply(out.get("state"))
        register(self.hub, agent_id, remote)
        if agent_id in (out.get("resumers") or []):
            hitl = getattr(self.hub, "hitl", None)
            if hitl is not None:
                hitl.register_resumption_handler(agent_id, remote.resume)
        return remote


def _end(p: Any) -> None:
    """Waits briefly for an agent process (or test thread) to end; stops it
    if it does not."""
    if p is None:
        return
    wait = getattr(p, "wait", None) or getattr(p, "join", None)
    try:
        if wait is not None:
            wait(timeout=10)
    except Exception:
        kill = getattr(p, "kill", None)
        if kill is not None:
            try:
                kill()
            except Exception:
                pass


def process_launcher(python: str, root: str, env: Optional[dict] = None):
    """Starts each agent as its own process (tests and small setups)."""
    import subprocess

    def launch(agent_id: str, path: str):
        e = dict(env if env is not None else os.environ)
        e["PYTHONPATH"] = root
        return subprocess.Popen([python, "-m", "dispatcher.portal_agent", agent_id, path],
                                cwd=root, env=e)
    return launch
