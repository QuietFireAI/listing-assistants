"""hitl_protocol - Human-In-The-Loop (HITL) Wait-State & Resumption Protocol.

Solves the critical gap: How does a swarm agent resume execution once work has
been paused for a human decision?

Lifecycle:
  1. PAUSE: When an agent hits a hard stop (pricing question, Fair Housing flag,
     unverified sender, angry client hold, schedule conflict), it registers a WaitState.
  2. QUEUE: The WaitState is indexed by client_context_id, stored in SQLite/Drawer,
     and surfaced to Agent 18 (Briefing) and the Human Review Queue.
  3. DECIDE: The human principal (Agent 00) makes a decision (APPROVE, REJECT, MODIFY, OVERRIDE).
  4. RESUME: The protocol signs the human decision, records it on the audit chain,
     and dispatches a resumption envelope to the target spoke, triggering deterministic
     execution continuation.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Callable, Dict, List, Optional


class WaitState:
    """Represents an active paused operation awaiting human intervention."""

    def __init__(
        self,
        wait_id: str,
        client_context_id: str,
        agent_id: str,
        paused_intent: str,
        reason: str,
        original_payload: dict,
        required_decision: str,
        created_at: Optional[float] = None
    ):
        self.wait_id = wait_id
        self.client_context_id = client_context_id
        self.agent_id = agent_id
        self.paused_intent = paused_intent
        self.reason = reason
        self.original_payload = original_payload
        self.required_decision = required_decision
        self.created_at = created_at or time.time()
        self.status = "PENDING"  # PENDING, RESOLVED, EXPIRED
        self.resolution: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "wait_id": self.wait_id,
            "client_context_id": self.client_context_id,
            "agent_id": self.agent_id,
            "paused_intent": self.paused_intent,
            "reason": self.reason,
            "original_payload": self.original_payload,
            "required_decision": self.required_decision,
            "created_at": self.created_at,
            "status": self.status,
            "resolution": self.resolution
        }


class HITLManager:
    """Orchestrates human decision wait-states and resumption dispatch."""

    def __init__(self, hub: Any = None, drawer_manager: Any = None):
        self.hub = hub
        self.drawer_manager = drawer_manager
        self.active_waits: dict[str, WaitState] = {}  # wait_id -> WaitState
        self.resumption_handlers: dict[str, Callable[[WaitState, dict], Any]] = {}

    def register_resumption_handler(self, agent_id: str, handler: Callable[[WaitState, dict], Any]):
        """Registers a spoke callback to be invoked when a human decision arrives."""
        self.resumption_handlers[agent_id] = handler

    def pause_operation(
        self,
        client_context_id: str,
        agent_id: str,
        paused_intent: str,
        reason: str,
        original_payload: dict,
        required_decision: str = "APPROVE_OR_REJECT"
    ) -> WaitState:
        """Called by a spoke agent to formally pause execution and await human direction."""
        wait_id = f"wait-{client_context_id}-{agent_id}-{uuid.uuid4().hex[:6]}"
        ws = WaitState(
            wait_id=wait_id,
            client_context_id=client_context_id,
            agent_id=agent_id,
            paused_intent=paused_intent,
            reason=reason,
            original_payload=original_payload,
            required_decision=required_decision
        )
        self.active_waits[wait_id] = ws

        # Notify Agent 18 (Calendar & Task wait-state tracker)
        if self.hub and hasattr(self.hub, "send"):
            from .core import Envelope
            self.hub.send(Envelope(
                from_agent=agent_id,
                to_agent="18",
                intent="agent.status",
                client_context_id=client_context_id,
                payload={
                    "waiting_on": f"human_{required_decision.lower()}",
                    "since": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ws.created_at)),
                    "wait_id": wait_id,
                    "reason": reason
                },
                provenance={"source": f"spoke-{agent_id}", "captured_at": "runtime"}
            ))

        # Log trace on Hub audit chain
        if self.hub and hasattr(self.hub, "ingest_spoke_trace"):
            self.hub.ingest_spoke_trace(
                agent_id,
                wait_id,
                thought=f"Operation paused for client {client_context_id!r}. Reason: {reason}. Awaiting human.",
                result=f"paused: {required_decision}"
            )

        # Record in Client Drawer if available
        if self.drawer_manager and self.drawer_manager.has_drawer(client_context_id):
            try:
                self.drawer_manager.record_agent_artifact(
                    client_id=client_context_id,
                    agent_id=agent_id,
                    category="timeline",
                    filename=f"{wait_id}_pause.json",
                    content=json.dumps(ws.to_dict(), indent=2)
                )
            except Exception:
                pass

        return ws

    def get_pending_waits(self, client_context_id: Optional[str] = None) -> list[dict]:
        """Lists pending human decisions, optionally filtered by client context."""
        waits = [
            ws.to_dict() for ws in self.active_waits.values()
            if ws.status == "PENDING"
        ]
        if client_context_id:
            return [w for w in waits if w["client_context_id"] == client_context_id]
        return waits

    def resume_operation(
        self,
        wait_id: str,
        human_decision: str,  # "APPROVE", "REJECT", "MODIFY", "OVERRIDE"
        human_payload: dict,
        human_agent_id: str = "00",
        signature: Optional[str] = None
    ) -> dict:
        """Called when the human makes their decision. Resumes the halted agent."""
        ws = self.active_waits.get(wait_id)
        if not ws:
            raise ValueError(f"WaitState {wait_id!r} not found or already resolved.")

        ws.status = "RESOLVED"
        ws.resolution = {
            "decision": human_decision,
            "human_agent_id": human_agent_id,
            "human_payload": human_payload,
            "resolved_at": time.time(),
            "signature": signature
        }

        # Clear wait status on Agent 18
        if self.hub and hasattr(self.hub, "send"):
            from .core import Envelope
            self.hub.send(Envelope(
                from_agent=human_agent_id,
                to_agent="18",
                intent="agent.status",
                client_context_id=ws.client_context_id,
                payload={
                    "waiting_on": f"human_{ws.required_decision.lower()}",
                    "resolved": True,
                    "wait_id": wait_id
                },
                provenance={"source": "human", "captured_at": "runtime"}
            ))

        # Trace on Hub audit log
        if self.hub and hasattr(self.hub, "ingest_spoke_trace"):
            self.hub.ingest_spoke_trace(
                ws.agent_id,
                wait_id,
                thought=f"Human decision received from {human_agent_id}: {human_decision}. Resuming operation.",
                result=f"resumed: {human_decision}"
            )

        # Dispatch resumption to the owning spoke handler if registered
        handler_result = None
        if ws.agent_id in self.resumption_handlers:
            handler_result = self.resumption_handlers[ws.agent_id](ws, human_payload)

        # Record resolution in Client Drawer
        if self.drawer_manager and self.drawer_manager.has_drawer(ws.client_context_id):
            try:
                self.drawer_manager.record_agent_artifact(
                    client_id=ws.client_context_id,
                    agent_id="00",
                    category="timeline",
                    filename=f"{wait_id}_resumed.json",
                    content=json.dumps(ws.to_dict(), indent=2)
                )
            except Exception:
                pass

        return {
            "status": "resumed",
            "wait_id": wait_id,
            "decision": human_decision,
            "agent_id": ws.agent_id,
            "handler_result": handler_result
        }
