"""portal - the one line between an agent and the dispatcher.

Owner decision 2026-10-26 (agent isolation V1): every agent runs alone, in
its own process or container, and reaches nothing except the dispatcher.
Its only line out is one private socket, and on that line it can ask for a
fixed menu of things and nothing else. The dispatcher knows which agent is
speaking by which line the request came in on, so an agent cannot speak
as another agent.

Wire format: JSON-RPC 2.0, one message per frame (a 4-byte big-endian
length, then UTF-8 JSON). Values are written with the same explicit type
tags as the saved state (dispatcher/state_snapshot.py: envelopes, sets,
tuples, waits); never pickle, so nothing an agent sends can run code in
the dispatcher.

Both ends are re-entrant: while one side waits for the answer to its own
request, it serves the requests the other side sends in the meantime. An
agent handling a message can ask the dispatcher to send another message,
which may be delivered back to the same agent before the first answer
comes; that is exactly the call stack the one-process swarm has, now
spread over two processes.

The menus (what each side may ask of the other):

  dispatcher -> agent   init, deliver, resume, state, restore
  agent -> dispatcher   send, trace, escalate, log_note, outbound_state,
                        on_record, file_record, hold, phase_gate,
                        decide, decision_status, draft_gate, draft_remarks

What each agent -> dispatcher call does, and which agents may use the
narrow ones, is in dispatcher/portal_dispatcher.py. A request for anything
not on the menu is refused and reported as a violation.
"""
from __future__ import annotations

import itertools
import json
import socket
import struct
from typing import Any, Callable, Optional

from .state_snapshot import decode, encode

PROTOCOL = "listingassistants-portal/1"
MAX_FRAME = 16 * 1024 * 1024          # one message; a bigger frame cuts the line

DISPATCHER_TO_AGENT = frozenset({"init", "deliver", "resume", "state", "restore"})
AGENT_TO_DISPATCHER = frozenset({
    "send", "trace", "escalate", "log_note", "outbound_state", "on_record",
    "file_record", "hold", "phase_gate", "decide", "decision_status",
    "draft_gate", "draft_remarks"})


class PortalError(Exception):
    """The line broke or carried something it must not."""


class PortalClosed(PortalError):
    """The other end closed the line."""


class RemoteError(Exception):
    """An exception raised on the other end of the line. repr() is the
    original exception's repr, so what the hub records for a failing agent
    reads exactly as it does when the agent runs in the same process."""

    def __init__(self, type_name: str, message: str, original_repr: str):
        super().__init__(message)
        self.type_name = type_name
        self.original_repr = original_repr

    def __repr__(self) -> str:
        return self.original_repr


class Refused(Exception):
    """Raised by a handler to refuse a request; the message goes back as the
    error, with no traceback detail."""


class Peer:
    """One end of a portal line.

    handlers: method -> callable(**params). allowed: the methods this end
    serves (its menu). on_off_menu(method) is called when the other end asks
    for something not on the menu, before the refusal goes back."""

    def __init__(self, sock: socket.socket, handlers: dict[str, Callable[..., Any]],
                 allowed: frozenset, name: str = "",
                 on_off_menu: Optional[Callable[[str], None]] = None):
        self.sock = sock
        self.handlers = handlers
        self.allowed = allowed
        self.name = name
        self.on_off_menu = on_off_menu
        self._ids = itertools.count(1)
        self.closed = False

    # ------------------------------------------------------------ framing
    def _send_frame(self, obj: dict) -> None:
        # key order kept as the sender built it: a message's payload reads
        # the same on the record whichever process wrote it
        data = json.dumps(obj, separators=(",", ":")).encode("utf-8")
        if len(data) > MAX_FRAME:
            raise PortalError(f"frame of {len(data)} bytes is over the {MAX_FRAME}-byte limit")
        try:
            self.sock.sendall(struct.pack(">I", len(data)) + data)
        except OSError as e:
            self.closed = True
            raise PortalClosed(f"{self.name}: line closed while sending ({e})") from e

    def _recv_exact(self, n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            try:
                chunk = self.sock.recv(n - len(buf))
            except socket.timeout as e:
                raise PortalError(f"{self.name}: no answer in time") from e
            except OSError as e:
                self.closed = True
                raise PortalClosed(f"{self.name}: line closed ({e})") from e
            if not chunk:
                self.closed = True
                raise PortalClosed(f"{self.name}: line closed by the other end")
            buf.extend(chunk)
        return bytes(buf)

    def _recv_frame(self) -> dict:
        (n,) = struct.unpack(">I", self._recv_exact(4))
        if n > MAX_FRAME:
            self.close()
            raise PortalError(f"{self.name}: frame of {n} bytes is over the limit; line cut")
        try:
            msg = json.loads(self._recv_exact(n).decode("utf-8"))
        except ValueError as e:
            self.close()
            raise PortalError(f"{self.name}: not JSON; line cut") from e
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
            self.close()
            raise PortalError(f"{self.name}: not a JSON-RPC 2.0 message; line cut")
        return msg

    # ------------------------------------------------------------ calls
    def call(self, method: str, params: Optional[dict] = None) -> Any:
        """Asks the other end; serves its requests until the answer comes."""
        if self.closed:
            raise PortalClosed(f"{self.name}: line is closed")
        rid = next(self._ids)
        self._send_frame({"jsonrpc": "2.0", "id": rid, "method": method,
                          "params": encode(params or {})})
        while True:
            msg = self._recv_frame()
            if "method" in msg:
                self._serve(msg)
                continue
            if msg.get("id") != rid:
                self.close()
                raise PortalError(f"{self.name}: answer to request {msg.get('id')} "
                                  f"while waiting for {rid}; line cut")
            if "error" in msg:
                err = msg["error"] or {}
                data = err.get("data") or {}
                raise RemoteError(str(data.get("type") or "RemoteError"),
                                  str(err.get("message")),
                                  str(data.get("repr") or err.get("message")))
            return decode(msg.get("result"))

    def _serve(self, msg: dict) -> None:
        method, rid = msg.get("method"), msg.get("id")
        if method not in self.allowed or method not in self.handlers:
            if self.on_off_menu is not None:
                self.on_off_menu(str(method))
            self._send_frame({"jsonrpc": "2.0", "id": rid,
                              "error": {"code": -32601,
                                        "message": f"not on the portal menu: {method!r}",
                                        "data": {"type": "Refused",
                                                 "repr": f"Refused('not on the portal menu: {method!r}')"}}})
            return
        try:
            params = decode(msg.get("params") or {})
            if not isinstance(params, dict):
                raise Refused("params must be an object")
            result = encode(self.handlers[method](**params))
        except Exception as e:      # raw reason back to the caller, never softened
            self._send_frame({"jsonrpc": "2.0", "id": rid,
                              "error": {"code": -32000, "message": str(e),
                                        "data": {"type": type(e).__name__,
                                                 "repr": (e.original_repr if isinstance(e, RemoteError)
                                                          else repr(e))}}})
            return
        self._send_frame({"jsonrpc": "2.0", "id": rid, "result": result})

    def serve_forever(self) -> None:
        """Serves the other end's requests until the line closes."""
        while not self.closed:
            try:
                msg = self._recv_frame()
            except PortalClosed:
                return
            if "method" not in msg:
                self.close()
                raise PortalError(f"{self.name}: an answer nobody asked for; line cut")
            self._serve(msg)

    def close(self) -> None:
        self.closed = True
        try:
            self.sock.close()
        except OSError:
            pass
