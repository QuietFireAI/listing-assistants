"""hitl_protocol - Human-In-The-Loop (HITL) Wait-State & Resumption Protocol.

Lifecycle:
  1. PAUSE: a caller registers a WaitState for a client context. The wait is
     announced to Agent 18 (agent.status, sent as the paused agent), traced on
     the hub's audit chain, written to the client's drawer timeline when a
     drawer exists, and pushed to the real-time notifier.
  2. DECIDE: a human submits a SIGNED decision envelope
     (intent 'hitl.decision.authority'). The hub's signature verifier - and
     the signer registry, when armed - must accept it. There is no unsigned
     path. Fixed 2026-10-11 (audit HITL-2): resume previously accepted
     signature=None and verified nothing.
  3. RESUME: the decision is recorded on the audit chain and Agent 18's wait
     is cleared by the same agent that paused (a legal agent.status sender).
     Fixed 2026-10-11 (audit HITL-3): the clear was sent from "00", which the
     closed track rejects, so 18 kept reporting resolved waits as open.
     If the paused agent registered a resumption handler it is invoked;
     otherwise the result says so (status 'decision_recorded_no_handler')
     instead of claiming the agent resumed (audit HITL-4).

Wiring (2026-10-11): dispatcher/swarm.py creates one manager as hub.hitl.
Agents 01, 11 and 20 pause through dispatcher/human_holds.py and register
resumption handlers. Active waits are saved with the swarm's state
(dispatcher/state_snapshot.py) and survive a restart.

What this module does NOT do:
  - Delivery beyond the configured notifier: ESCALATE_TO_SUPPORT files the
    case in the hub's 'escalation.support' queue (and notifies the human
    channel if one is registered); it does not contact anyone else.
"""
from __future__ import annotations

import json
import sys
import time
import uuid
from typing import Any, Callable, Optional

DECISION_INTENT = "hitl.decision.authority"

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
DECISION_RECALIBRATE_RUBRIC = "RECALIBRATE_RUBRIC"

VALID_DECISIONS = {
    DECISION_APPROVE, DECISION_APPROVE_AS_IS, DECISION_APPROVE_WITH_OVERRIDE,
    DECISION_MODIFY, DECISION_CONTINUE_WITH_UPDATE, DECISION_REJECT,
    DECISION_REJECT_AND_ABORT, DECISION_HOLD, DECISION_HOLD_IN_SIDING,
    DECISION_CLOSE_SYSTEM, DECISION_ESCALATE_TO_SUPPORT, DECISION_RECALIBRATE_RUBRIC,
}
_UPDATE_DECISIONS = {DECISION_APPROVE_WITH_OVERRIDE, DECISION_MODIFY, DECISION_CONTINUE_WITH_UPDATE}


class HITLAuthorizationError(Exception):
    """A decision that is unsigned, badly signed, or not authorized."""


class WaitState:
    """Represents an active paused operation awaiting human intervention."""

    def __init__(self, wait_id: str, client_context_id: str, agent_id: str,
                 paused_intent: str, reason: str, original_payload: dict,
                 required_decision: str, created_at: Optional[float] = None):
        self.wait_id = wait_id
        self.client_context_id = client_context_id
        self.agent_id = agent_id
        self.paused_intent = paused_intent
        self.reason = reason
        self.original_payload = original_payload
        self.required_decision = required_decision
        self.created_at = created_at or time.time()
        self.status = "PENDING"
        self.resolution: Optional[dict] = None
        self.notice_result: Optional[dict] = None

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
            "resolution": self.resolution,
        }


class HITLManager:
    """Orchestrates human decision wait-states, real-time alerts, and resumption."""

    def __init__(self, hub: Any = None, drawer_manager: Any = None,
                 real_time_notifier: Any = None):
        self.hub = hub
        self.drawer_manager = drawer_manager
        self.real_time_notifier = real_time_notifier
        self.active_waits: dict[str, WaitState] = {}
        self.resumption_handlers: dict[str, Callable[[WaitState, dict], Any]] = {}
        self.notification_log: list[dict] = []
        self.errors: list[str] = []   # every swallowed-before failure is now recorded here

    # ------------------------------------------------------------ helpers
    def _record_in_drawer(self, ws: WaitState, filename: str, agent_id: str) -> Optional[str]:
        if not self.drawer_manager:
            return None
        try:
            if not self.drawer_manager.has_drawer(ws.client_context_id):
                # a hold can be the first thing on file for a client (2026-10-12:
                # drawers are wired, so the pause record always has a home)
                self.drawer_manager.provision_drawer(ws.client_context_id, client_name="",
                                                     property_address="", role="client")
            return self.drawer_manager.record_agent_artifact(
                client_id=ws.client_context_id, agent_id=agent_id, category="timeline",
                filename=filename, content=json.dumps(ws.to_dict(), indent=2),
                acting_client_context_id=ws.client_context_id)
        except Exception as e:   # recorded, never silent
            self.errors.append(f"drawer write {filename}: {e!r}")
            return None

    def _notify_18(self, ws: WaitState, payload: dict) -> Optional[dict]:
        if not (self.hub and hasattr(self.hub, "send")):
            return None
        from .core import Envelope
        return self.hub.send(Envelope(
            from_agent=ws.agent_id, to_agent="18", intent="agent.status",
            client_context_id=ws.client_context_id, payload=payload,
            provenance={"source": f"spoke-{ws.agent_id}", "captured_at": "runtime"}))

    # ------------------------------------------------------------ registration
    def register_resumption_handler(self, agent_id: str, handler: Callable[[WaitState, dict], Any]):
        """Registers a spoke callback invoked when a verified human decision arrives."""
        self.resumption_handlers[agent_id] = handler

    # ------------------------------------------------------------ alerts
    def dispatch_realtime_notice(self, ws: WaitState) -> dict:
        """Sends an immediate alert through the configured notifier."""
        if ws.paused_intent == "jev.confidence_underflow" or "confidence" in ws.reason.lower():
            alert_body = (
                f"[JEV CALIBRATION HOLD] Agent {ws.agent_id} on Client '{ws.client_context_id}': "
                f"{ws.original_payload.get('broker_notice', ws.reason)}. "
                f"Action required: {ws.required_decision}. Wait ID: {ws.wait_id}")
        else:
            alert_body = (
                f"[DECISION REQUIRED] Agent {ws.agent_id} halted on Client '{ws.client_context_id}'. "
                f"Reason: {ws.reason}. Action required: {ws.required_decision}. Wait ID: {ws.wait_id}")
        record = {
            "type": "decision_required", "wait_id": ws.wait_id,
            "client_context_id": ws.client_context_id, "agent_id": ws.agent_id,
            "reason": ws.reason, "required_decision": ws.required_decision,
            "body": alert_body, "timestamp": time.time(),
        }
        self.notification_log.append(record)
        if self.real_time_notifier and callable(self.real_time_notifier):
            try:
                record["notifier_result"] = self.real_time_notifier(record)
            except Exception as e:
                record["notifier_error"] = str(e)
                self.errors.append(f"notifier: {e!r}")
        elif self.hub and getattr(self.hub, "human_notifier", None):
            # through the hub, so the outcome is on the chain like every other
            # notification (2026-10-13 cold review: this called the notifier
            # directly - no human.notified / notify_failed was recorded, and
            # the notifier's raw answer was kept here)
            record["hub_notification"] = self.hub.notify("decision_required", {
                "client_context_id": ws.client_context_id, "agent": ws.agent_id,
                "reason": ws.reason, "wait_id": ws.wait_id,
                "trigger": f"DECISION REQUIRED: {ws.required_decision}"})
            if record["hub_notification"] == "notify_failed":
                self.errors.append("hub notifier: notification failed (see human.notify_failed)")
        else:
            record["undelivered"] = "no notifier configured - alert logged locally only"
        return record

    # ------------------------------------------------------------ pause
    def pause_operation(self, client_context_id: str, agent_id: str, paused_intent: str,
                        reason: str, original_payload: dict,
                        required_decision: str = "APPROVE_OR_REJECT") -> WaitState:
        """Formally pause and await a signed human decision."""
        wait_id = f"wait-{client_context_id}-{agent_id}-{uuid.uuid4().hex[:6]}"
        ws = WaitState(wait_id, client_context_id, agent_id, paused_intent, reason,
                       dict(original_payload), required_decision)
        self.active_waits[wait_id] = ws
        self.dispatch_realtime_notice(ws)
        ws.notice_result = self._notify_18(ws, {
            "waiting_on": f"human_{required_decision.lower()}",
            "since": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ws.created_at)),
            "wait_id": wait_id, "reason": reason})
        if self.hub and hasattr(self.hub, "ingest_spoke_trace"):
            self.hub.ingest_spoke_trace(
                agent_id, wait_id,
                thought=f"Operation paused for client {client_context_id!r}. Reason: {reason}. Awaiting human.",
                result=f"paused: {required_decision}")
        self._record_in_drawer(ws, f"{wait_id}_pause.json", agent_id)
        return ws

    def pause_confidence_underflow(self, client_context_id: str, agent_id: str,
                                   decision_result: dict,
                                   paused_intent: str = "jev.confidence_underflow") -> WaitState:
        """Pause for a JEV confidence-floor hold: broker alert + operator escalation."""
        conf = decision_result.get("confidence", 0.0)
        floor = decision_result.get("confidence_threshold", 0.45)
        reason = f"JEV confidence rating {conf:.2f} below safety floor {floor:.2f}"
        broker_msg = decision_result.get(
            "broker_notice",
            f"JEV Calibration Hold: Data certainty scored at {conf:.2f} (below {floor:.2f} floor). "
            f"Parked in siding for your review.")
        operator_msg = decision_result.get(
            "operator_notice",
            f"HIGH-PRIORITY CALIBRATION: JEV confidence underflow ({conf:.2f} < {floor:.2f}) "
            f"for context '{client_context_id}'. Rubric fine-tuning evaluation warranted.")
        ws = self.pause_operation(
            client_context_id=client_context_id, agent_id=agent_id, paused_intent=paused_intent,
            reason=reason,
            original_payload={**decision_result, "broker_notice": broker_msg, "operator_notice": operator_msg},
            required_decision="APPROVE_OR_RECALIBRATE")
        if self.hub and hasattr(self.hub, "escalate"):
            try:
                self.hub.escalate("escalation.confidence_underflow", {
                    "wait_id": ws.wait_id, "client_context_id": client_context_id,
                    "agent_id": agent_id, "confidence": conf, "confidence_threshold": floor,
                    "reason": reason, "operator_notice": operator_msg,
                    "action": "operator_fine_tuning_evaluation"})
            except Exception as e:
                self.errors.append(f"escalate confidence_underflow: {e!r}")
        return ws

    def get_pending_waits(self, client_context_id: Optional[str] = None) -> list[dict]:
        waits = [ws.to_dict() for ws in self.active_waits.values() if ws.status == "PENDING"]
        if client_context_id:
            return [w for w in waits if w["client_context_id"] == client_context_id]
        return waits

    # ------------------------------------------------------------ decide + resume
    def _verify_decision(self, auth) -> None:
        """Same trust bar as the hub's authority lanes: crypto signature, plus
        the signer registry when armed. Every refusal lands on the chain."""
        if self.hub is None or not hasattr(self.hub, "verify_sig"):
            raise HITLAuthorizationError(
                "no hub signature verifier available - a human decision cannot be "
                "authenticated, so none is accepted (fail closed)")
        if getattr(auth, "intent", None) != DECISION_INTENT:
            raise HITLAuthorizationError(f"decision must be intent {DECISION_INTENT!r}")
        if auth.from_agent != "human":
            raise HITLAuthorizationError("decision sender must be 'human'")
        if not self.hub.verify_sig(auth):
            self.hub.audit.append("integrity.violation", {
                "envelope_id": auth.envelope_id,
                "reason": "hitl decision without verified signature"})
            raise HITLAuthorizationError("unverified signature on HITL decision")
        registry = getattr(self.hub, "signer_registry", None)
        if registry is not None:
            v = registry.check(auth)
            if not v.ok:
                self.hub.audit.append("integrity.violation", {
                    "envelope_id": auth.envelope_id, "reason": f"signer registry: {v.reason}"})
                raise HITLAuthorizationError(f"signer registry: {v.reason}")
        else:
            self.hub.audit.append("signer.unarmed", {
                "envelope_id": auth.envelope_id,
                "reason": "no signer registry armed - WHO-signed binding off, "
                          "declared not silent (crypto check only)"})

    def resume_operation(self, auth) -> dict:
        """Apply a SIGNED human decision. `auth` is an Envelope with intent
        'hitl.decision.authority', from_agent 'human', and payload
        {wait_id, decision, updated_fields?, user_notes?}."""
        self._verify_decision(auth)
        payload = auth.payload or {}
        wait_id = payload.get("wait_id")
        ws = self.active_waits.get(wait_id)
        if not ws or ws.status != "PENDING":
            raise ValueError(f"WaitState {wait_id!r} not found or already resolved.")
        if auth.client_context_id != ws.client_context_id:
            raise HITLAuthorizationError(
                f"decision signed for context {auth.client_context_id!r} cannot "
                f"resolve a wait on {ws.client_context_id!r}")
        decision = str(payload.get("decision", "")).upper().strip()
        if decision not in VALID_DECISIONS:
            raise ValueError(f"unknown decision {decision!r}; valid: {sorted(VALID_DECISIONS)}")

        updated = payload.get("updated_fields") or {}
        if decision in _UPDATE_DECISIONS:
            if not isinstance(updated, dict) or not updated:
                raise ValueError(f"{decision} requires a non-empty updated_fields dict")
            unknown = sorted(set(updated) - set(ws.original_payload))
            if unknown:
                # A human override corrects a paused value; it never introduces
                # new fields the paused agent did not ask about (audit HITL-5).
                raise ValueError(f"updated_fields names fields not in the paused "
                                 f"payload: {unknown}")
        elif updated:
            raise ValueError(f"{decision} does not take updated_fields")

        self.hub.audit.append("hitl.decision.authorized", {
            "wait_id": wait_id, "decision": decision,
            "authorized_by_envelope": auth.envelope_id,
            "client_context_id": ws.client_context_id, "agent": ws.agent_id})
        # a signed human decision is a gate in every playbook: re-inject
        # MANNERS (dispatcher/manners_reinjection.py, 2026-10-14)
        from .manners_reinjection import phase_gate
        phase_gate(self.hub, f"HITL decision {decision} on {wait_id}")
        resolution = {"decision": decision, "human_payload": payload,
                      "resolved_at": time.time(), "authorized_by_envelope": auth.envelope_id}

        if decision == DECISION_ESCALATE_TO_SUPPORT:
            ws.status = "ESCALATED_TO_SUPPORT"
            snapshot = self.create_forensic_snapshot(
                ws.client_context_id, wait_id=wait_id,
                notes=f"Escalated to support: {payload.get('user_notes', '')}")
            ticket_id = f"TICKET-{uuid.uuid4().hex[:8].upper()}"
            ws.resolution = {**resolution, "ticket_id": ticket_id,
                             "snapshot_id": snapshot.get("snapshot_id")}
            self.hub.queue_and_notify("escalation.support", {
                "ticket_id": ticket_id, "wait_id": wait_id, "agent_id": ws.agent_id,
                "client_context_id": ws.client_context_id, "reason": ws.reason,
                "snapshot_id": snapshot.get("snapshot_id")})
            self._record_in_drawer(ws, f"{wait_id}_pause.json", ws.agent_id)
            return {"status": "escalated_to_support", "wait_id": wait_id,
                    "decision": decision, "agent_id": ws.agent_id, "ticket_id": ticket_id,
                    "message": "Case filed in the hub's escalation.support queue with a "
                               "forensic snapshot; human channel notified if one is configured."}

        if decision in _UPDATE_DECISIONS:
            ws.original_payload.update(updated)

        if decision == DECISION_CLOSE_SYSTEM:
            ws.status = "CLOSED"
        elif decision in (DECISION_HOLD, DECISION_HOLD_IN_SIDING):
            ws.status = "HELD"
        else:
            ws.status = "RESOLVED"
        ws.resolution = resolution

        clear = None
        if ws.status in ("RESOLVED", "CLOSED"):
            clear = self._notify_18(ws, {
                "waiting_on": f"human_{ws.required_decision.lower()}",
                "resolved": True, "wait_id": wait_id})
        if self.hub and hasattr(self.hub, "ingest_spoke_trace"):
            self.hub.ingest_spoke_trace(
                ws.agent_id, wait_id,
                thought=f"Signed human decision {decision} received (envelope {auth.envelope_id}).",
                result=f"decision: {decision}")

        handler = self.resumption_handlers.get(ws.agent_id)
        handler_result, status = None, None
        if ws.status == "CLOSED":
            status = "wait_closed"
        elif ws.status == "HELD":
            status = "held"
        elif handler is not None:
            handler_result = handler(ws, payload)
            status = "resumed"
        else:
            status = "decision_recorded_no_handler"
            ws.status = "RESOLVED_NO_HANDLER"

        self._record_in_drawer(ws, f"{wait_id}_pause.json", ws.agent_id)
        self._record_in_drawer(ws, f"{wait_id}_resolved.json", "00")
        return {"status": status, "wait_id": wait_id, "decision": decision,
                "agent_id": ws.agent_id, "handler_result": handler_result,
                "agent18_clear": clear}

    # ------------------------------------------------------------ snapshot
    def create_forensic_snapshot(self, client_context_id: str, wait_id: Optional[str] = None,
                                 notes: str = "") -> dict:
        """Diagnostic snapshot of drawer state, the wait, and alerts for this client."""
        snapshot_timestamp = time.time()
        time_str = time.strftime("%Y%m%d_%H%M%S", time.localtime(snapshot_timestamp))
        snapshot_id = f"snap_{client_context_id}_{time_str}"

        ws = self.active_waits.get(wait_id) if wait_id else None
        if not ws:
            for active in self.active_waits.values():
                if active.client_context_id == client_context_id and active.status == "PENDING":
                    ws = active
                    break

        files_inventory = []
        if self.drawer_manager and self.drawer_manager.has_drawer(client_context_id):
            files_inventory = self.drawer_manager.get_drawer(client_context_id).list_files()

        client_notifications = [n for n in self.notification_log
                                if n.get("client_context_id") == client_context_id]
        snapshot_data = {
            "snapshot_id": snapshot_id,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(snapshot_timestamp)),
            "client_context_id": client_context_id, "notes": notes,
            "wait_state": ws.to_dict() if ws else None,
            "files_inventory": files_inventory, "notifications": client_notifications,
            "platform_info": {"python_version": sys.version.split()[0],
                              "active_waits_count": len(self.active_waits)},
        }

        md_lines = [f"# ListingAssistants Forensic Snapshot: {client_context_id}",
                    f"**Snapshot ID:** `{snapshot_id}`  ",
                    f"**Timestamp:** {snapshot_data['timestamp']}  ",
                    f"**Operator Notes:** {notes or 'N/A'}  ", "",
                    "## 1. Active Wait-State Status"]
        if ws:
            md_lines.extend([
                f"- **Wait ID:** `{ws.wait_id}`", f"- **Halted Agent:** Agent {ws.agent_id}",
                f"- **Paused Intent:** `{ws.paused_intent}`",
                f"- **Reason for Stoppage:** {ws.reason}",
                f"- **Required Decision:** `{ws.required_decision}`",
                f"- **Status:** `{ws.status}`", "- **Payload at Pause:**",
                "```json", json.dumps(ws.original_payload, indent=2), "```"])
        else:
            md_lines.append("- *(No pending wait-state currently active for this client)*")
        md_lines.extend(["", "## 2. Drawer File Inventory & SHA-256 Hashes",
                         "| Filename | Category | Size (Bytes) | SHA-256 Digest |",
                         "|---|---|---|---|"])
        if files_inventory:
            for f in files_inventory:
                md_lines.append(f"| {f.get('filename')} | {f.get('category')} | "
                                f"{f.get('size_bytes')} | `{f.get('sha256', '')[:16]}...` |")
        else:
            md_lines.append("| *(No files found in drawer)* | - | - | - |")
        md_lines.extend(["", "## 3. Real-Time Alert Log"])
        if client_notifications:
            for n in client_notifications:
                md_lines.append(f"- **[{time.strftime('%H:%M:%S', time.localtime(n.get('timestamp', 0)))}]** {n.get('body')}")
        else:
            md_lines.append("- *(No alerts recorded for this client)*")
        md_report = "\n".join(md_lines)

        json_path = md_path = None
        if self.drawer_manager and self.drawer_manager.has_drawer(client_context_id):
            try:
                json_path = self.drawer_manager.record_agent_artifact(
                    client_id=client_context_id, agent_id="00", category="timeline",
                    filename=f"{snapshot_id}.json", content=json.dumps(snapshot_data, indent=2),
                    acting_client_context_id=client_context_id)
                md_path = self.drawer_manager.record_agent_artifact(
                    client_id=client_context_id, agent_id="00", category="timeline",
                    filename=f"{snapshot_id}.md", content=md_report,
                    acting_client_context_id=client_context_id)
            except Exception as e:
                self.errors.append(f"snapshot write: {e!r}")
        return {"snapshot_id": snapshot_id, "json_path": json_path,
                "markdown_path": md_path, "markdown_content": md_report, "data": snapshot_data}
