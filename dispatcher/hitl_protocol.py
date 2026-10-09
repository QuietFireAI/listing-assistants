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
import sys
import time
import uuid
from typing import Any, Callable, Dict, List, Optional


# Standardized HITL Decisions
DECISION_APPROVE = "APPROVE"
DECISION_APPROVE_AS_IS = "APPROVE_AS_IS"
DECISION_APPROVE_WITH_OVERRIDE = "APPROVE_WITH_OVERRIDE"
DECISION_MODIFY = "MODIFY"
DECISION_CONTINUE_WITH_UPDATE = "CONTINUE_WITH_UPDATE"
DECISION_REJECT = "REJECT"
DECISION_REJECT_AND_ABORT = "REJECT_AND_ABORT"
DECISION_HOLD = "HOLD"
DECISION_HOLD_IN_SIDING = "HOLD_IN_SIDING"
DECISION_CLOSE_SYSTEM = "CLOSE_SYSTEM"
DECISION_ESCALATE_TO_SUPPORT = "ESCALATE_TO_SUPPORT"

VALID_DECISIONS = {
    DECISION_APPROVE,
    DECISION_APPROVE_AS_IS,
    DECISION_APPROVE_WITH_OVERRIDE,
    DECISION_MODIFY,
    DECISION_CONTINUE_WITH_UPDATE,
    DECISION_REJECT,
    DECISION_REJECT_AND_ABORT,
    DECISION_HOLD,
    DECISION_HOLD_IN_SIDING,
    DECISION_CLOSE_SYSTEM,
    DECISION_ESCALATE_TO_SUPPORT,
}


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
        self.status = "PENDING"  # PENDING, RESOLVED, EXPIRED, CLOSED
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
    """Orchestrates human decision wait-states, real-time alerts, and resumption dispatch."""

    def __init__(self, hub: Any = None, drawer_manager: Any = None, real_time_notifier: Any = None):
        self.hub = hub
        self.drawer_manager = drawer_manager
        self.real_time_notifier = real_time_notifier
        self.active_waits: dict[str, WaitState] = {}  # wait_id -> WaitState
        self.resumption_handlers: dict[str, Callable[[WaitState, dict], Any]] = {}
        self.notification_log: list[dict] = []

    def register_resumption_handler(self, agent_id: str, handler: Callable[[WaitState, dict], Any]):
        """Registers a spoke callback to be invoked when a human decision arrives."""
        self.resumption_handlers[agent_id] = handler

    def dispatch_realtime_notice(self, ws: WaitState) -> dict:
        """Sends an immediate real-time alert (SMS/webhook/push) whenever a human decision is needed."""
        alert_body = (
            f"[DECISION REQUIRED] Agent {ws.agent_id} halted on Client '{ws.client_context_id}'. "
            f"Reason: {ws.reason}. Action required: {ws.required_decision}. Wait ID: {ws.wait_id}"
        )
        record = {
            "type": "decision_required",
            "wait_id": ws.wait_id,
            "client_context_id": ws.client_context_id,
            "agent_id": ws.agent_id,
            "reason": ws.reason,
            "required_decision": ws.required_decision,
            "body": alert_body,
            "timestamp": time.time()
        }
        self.notification_log.append(record)

        if self.real_time_notifier and callable(self.real_time_notifier):
            try:
                record["notifier_result"] = self.real_time_notifier(record)
            except Exception as e:
                record["notifier_error"] = str(e)
        elif self.hub and getattr(self.hub, "human_notifier", None):
            try:
                record["hub_notifier_result"] = self.hub.human_notifier("decision_required", {
                    "client_context_id": ws.client_context_id,
                    "agent": ws.agent_id,
                    "reason": ws.reason,
                    "wait_id": ws.wait_id,
                    "trigger": f"DECISION REQUIRED: {ws.required_decision}"
                })
            except Exception as e:
                record["hub_notifier_error"] = str(e)

        return record

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

        # Fire immediate real-time notification
        self.dispatch_realtime_notice(ws)

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
        human_decision: str,  # "APPROVE", "APPROVE_AS_IS", "APPROVE_WITH_OVERRIDE", "MODIFY", "CONTINUE_WITH_UPDATE", "REJECT", "HOLD", "CLOSE_SYSTEM"
        human_payload: dict,
        human_agent_id: str = "00",
        signature: Optional[str] = None
    ) -> dict:
        """Called when the human makes their decision. Resumes the halted agent or executes system closure."""
        ws = self.active_waits.get(wait_id)
        if not ws:
            raise ValueError(f"WaitState {wait_id!r} not found or already resolved.")

        # Normalize decision
        norm_decision = human_decision.upper().strip()

        # Handle Emergency CLOSE_SYSTEM
        if norm_decision == DECISION_CLOSE_SYSTEM:
            ws.status = "SYSTEM_CLOSED"
            ws.resolution = {
                "decision": DECISION_CLOSE_SYSTEM,
                "human_agent_id": human_agent_id,
                "human_payload": human_payload,
                "resolved_at": time.time(),
                "signature": signature
            }
            if self.hub and hasattr(self.hub, "ingest_spoke_trace"):
                self.hub.ingest_spoke_trace(
                    ws.agent_id,
                    wait_id,
                    thought=f"Emergency CLOSE_SYSTEM triggered by {human_agent_id}. Halting task completely.",
                    result="system_closed"
                )
            return {
                "status": "system_closed",
                "wait_id": wait_id,
                "decision": DECISION_CLOSE_SYSTEM,
                "agent_id": ws.agent_id
            }

        # Handle ESCALATE_TO_SUPPORT (One-Click Support Lifeline)
        if norm_decision == DECISION_ESCALATE_TO_SUPPORT:
            ws.status = "ESCALATED_TO_SUPPORT"
            notes = f"Escalated to Support by {human_agent_id}: {human_payload.get('user_notes', '')}"
            snapshot = self.create_forensic_snapshot(
                ws.client_context_id,
                wait_id=wait_id,
                notes=notes
            )
            ticket_id = f"TICKET-{wait_id[:8].upper()}"
            ws.resolution = {
                "decision": DECISION_ESCALATE_TO_SUPPORT,
                "human_agent_id": human_agent_id,
                "human_payload": human_payload,
                "resolved_at": time.time(),
                "ticket_id": ticket_id,
                "snapshot_id": snapshot.get("snapshot_id")
            }
            if self.hub and hasattr(self.hub, "escalate"):
                self.hub.escalate("escalation.complaint", {
                    "ticket_id": ticket_id,
                    "wait_id": wait_id,
                    "agent_id": ws.agent_id,
                    "client_context_id": ws.client_context_id,
                    "reason": ws.reason,
                    "snapshot_id": snapshot.get("snapshot_id"),
                    "action": "escalated_to_support"
                })
            return {
                "status": "escalated_to_support",
                "wait_id": wait_id,
                "decision": DECISION_ESCALATE_TO_SUPPORT,
                "agent_id": ws.agent_id,
                "ticket_id": ticket_id,
                "message": "Diagnostic package packaged and dispatched to QuietFire Support Desk."
            }

        # Handle Overrides / Updated Values (APPROVE_WITH_OVERRIDE / MODIFY / CONTINUE_WITH_UPDATE)
        if norm_decision in (DECISION_APPROVE_WITH_OVERRIDE, DECISION_MODIFY, DECISION_CONTINUE_WITH_UPDATE):
            updated_fields = human_payload.get("updated_fields", human_payload)
            if isinstance(updated_fields, dict):
                ws.original_payload.update(updated_fields)

        ws.status = "RESOLVED"
        ws.resolution = {
            "decision": norm_decision,
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
                thought=f"Human decision received from {human_agent_id}: {norm_decision}. Resuming operation.",
                result=f"resumed: {norm_decision}"
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
            "decision": norm_decision,
            "agent_id": ws.agent_id,
            "handler_result": handler_result
        }

    def create_forensic_snapshot(
        self,
        client_context_id: str,
        wait_id: Optional[str] = None,
        notes: str = ""
    ) -> dict:
        """Generates a complete forensic diagnostic snapshot ('screenshot') of drawer state,
        active wait-states, file fingerprints, and recent notifications for operational troubleshooting.
        """
        snapshot_timestamp = time.time()
        time_str = time.strftime("%Y%m%d_%H%M%S", time.localtime(snapshot_timestamp))
        snapshot_id = f"snap_{client_context_id}_{time_str}"

        ws = self.active_waits.get(wait_id) if wait_id else None
        if not ws:
            # Check if there is an active wait for this client
            for active in self.active_waits.values():
                if active.client_context_id == client_context_id and active.status == "PENDING":
                    ws = active
                    break

        files_inventory = []
        if self.drawer_manager and self.drawer_manager.has_drawer(client_context_id):
            drawer = self.drawer_manager.get_drawer(client_context_id)
            files_inventory = drawer.list_files()

        client_notifications = [
            n for n in self.notification_log
            if n.get("client_context_id") == client_context_id
        ]

        snapshot_data = {
            "snapshot_id": snapshot_id,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(snapshot_timestamp)),
            "client_context_id": client_context_id,
            "notes": notes,
            "wait_state": ws.to_dict() if ws else None,
            "files_inventory": files_inventory,
            "notifications": client_notifications,
            "platform_info": {
                "python_version": sys.version.split()[0],
                "active_waits_count": len(self.active_waits),
                "storage_type": "ClientDrawer_SQLite_Drobo"
            }
        }

        # Render human-readable Markdown 'Screenshot' Report
        md_lines = [
            f"# ListingAssistants Forensic Snapshot: {client_context_id}",
            f"**Snapshot ID:** `{snapshot_id}`  ",
            f"**Timestamp:** {snapshot_data['timestamp']}  ",
            f"**Operator Notes:** {notes or 'N/A'}  ",
            "",
            "## 1. Active Wait-State Status",
        ]
        if ws:
            md_lines.extend([
                f"- **Wait ID:** `{ws.wait_id}`",
                f"- **Halted Agent:** Agent {ws.agent_id}",
                f"- **Paused Intent:** `{ws.paused_intent}`",
                f"- **Reason for Stoppage:** {ws.reason}",
                f"- **Required Decision:** `{ws.required_decision}`",
                f"- **Status:** `{ws.status}`",
                f"- **Payload at Pause:**",
                "```json",
                json.dumps(ws.original_payload, indent=2),
                "```"
            ])
        else:
            md_lines.append("- *(No pending wait-state currently active for this client)*")

        md_lines.extend([
            "",
            "## 2. Drawer File Inventory & Cryptographic Hashes",
            "| Filename | Category | Size (Bytes) | SHA-256 Digest |",
            "|---|---|---|---|"
        ])
        if files_inventory:
            for f in files_inventory:
                md_lines.append(
                    f"| {f.get('filename')} | {f.get('category')} | {f.get('size_bytes')} | `{f.get('sha256', '')[:16]}...` |"
                )
        else:
            md_lines.append("| *(No files found in drawer)* | - | - | - |")

        md_lines.extend([
            "",
            "## 3. Real-Time Alert Log",
        ])
        if client_notifications:
            for n in client_notifications:
                md_lines.append(
                    f"- **[{time.strftime('%H:%M:%S', time.localtime(n.get('timestamp', 0)))}]** {n.get('body')}"
                )
        else:
            md_lines.append("- *(No alerts recorded for this client)*")

        md_report = "\n".join(md_lines)

        json_path = None
        md_path = None
        if self.drawer_manager and self.drawer_manager.has_drawer(client_context_id):
            try:
                json_path = self.drawer_manager.record_agent_artifact(
                    client_id=client_context_id,
                    agent_id="00",
                    category="timeline",
                    filename=f"{snapshot_id}.json",
                    content=json.dumps(snapshot_data, indent=2)
                )
                md_path = self.drawer_manager.record_agent_artifact(
                    client_id=client_context_id,
                    agent_id="00",
                    category="timeline",
                    filename=f"{snapshot_id}.md",
                    content=md_report
                )
            except Exception:
                pass

        return {
            "snapshot_id": snapshot_id,
            "json_path": json_path,
            "markdown_path": md_path,
            "markdown_content": md_report,
            "data": snapshot_data
        }
