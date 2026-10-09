"""decision_adapter - JEV AI Decision Platform Adapter with Pure Python Fallback.

Provides a unified decision coprocessor interface for the QuietFireAI swarm.
Integrates with JEV AI via:
  1. Primary: Model Context Protocol (MCP) tool invocation (tools/call_jev_decision).
  2. Fallback: In-process pure-Python deterministic decision engine (JevPythonDecisionEngine),
     requiring zero network connections and zero HTTP REST overhead.

Designed for stage 1 cloud VM validation and final air-gapped on-premise hardware
appliances (Hermes + Drobo NAS).
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class JevPythonDecisionEngine:
    """In-process, zero-network deterministic decision engine.
    Implements JEV AI decision evaluation rules natively in Python.
    """

    def evaluate_lead_rubric(
        self,
        context_id: str,
        payload: dict,
        rubric: dict
    ) -> dict:
        """Evaluates a lead against a signed rubric using deterministic multi-attribute scoring.

        Rules:
          - Preapproval document amount overrides stated budget if they conflict.
          - Verified financing progress outranks stated urgency 'high'.
          - Exact boundary scores assign the LOWER tier (fail-safe conservative rule).
          - Unknown inputs return tier UNKNOWN rather than guessing.
        """
        notes: list[str] = []
        budget = payload.get("stated_budget")
        preapproval_doc = payload.get("preapproval_document")
        timeline_days = payload.get("timeline_days")
        financing_progress = payload.get("financing_progress")
        stated_urgency = payload.get("stated_urgency")

        # Conflict resolution: verified doc outranks stated budget
        if preapproval_doc and preapproval_doc.get("verified"):
            if budget is not None and budget != preapproval_doc.get("amount"):
                notes.append(
                    f"stated budget {budget} conflicts with pre-approval doc amount "
                    f"{preapproval_doc['amount']} - doc wins for scoring, conflict logged verbatim"
                )
                budget = preapproval_doc["amount"]

        # Conflict resolution: verifiable financing outranks stated urgency
        if stated_urgency == "high" and financing_progress in (None, "none"):
            notes.append(
                "stated urgency 'high' conflicts with no financing progress - "
                "weighting verifiable financing over stated urgency, conflict logged"
            )

        inputs = {
            "budget": budget,
            "timeline_days": timeline_days,
            "financing_progress": financing_progress
        }

        if all(v is None for v in inputs.values()):
            return {
                "status": "ok",
                "tier": "UNKNOWN",
                "score": None,
                "notes": notes + ["all rubric inputs unknown - tier is UNKNOWN, not COLD"],
                "decision_provenance": "jev_engine_python_v1",
                "engine": "python_fallback"
            }

        score = 0
        if budget is not None and budget >= rubric.get("budget_threshold", 500_000):
            score += rubric.get("budget_weight", 40)
        if timeline_days is not None and timeline_days <= rubric.get("timeline_days_threshold", 30):
            score += rubric.get("timeline_weight", 40)
        if financing_progress == "preapproved":
            score += rubric.get("financing_weight", 20)

        hot = rubric.get("hot_threshold", 70)
        warm = rubric.get("warm_threshold", 40)

        # Boundary checks: exact boundary scores get the lower tier
        if score == hot:
            tier = "WARM"
            notes.append(
                f"score {score} sits exactly on a tier boundary (HOT/WARM) - "
                f"assigned the lower tier (WARM), flagged for human"
            )
        elif score == warm:
            tier = "COLD"
            notes.append(
                f"score {score} sits exactly on a tier boundary (WARM/COLD) - "
                f"assigned the lower tier (COLD), flagged for human"
            )
        elif score > hot:
            tier = "HOT"
        elif score > warm:
            tier = "WARM"
        else:
            tier = "COLD"

        return {
            "status": "ok",
            "tier": tier,
            "score": score,
            "notes": notes,
            "decision_provenance": "jev_engine_python_v1",
            "engine": "python_fallback"
        }

    def resolve_scheduling_conflict(
        self,
        context_id: str,
        requested_slot: dict,
        existing_slots: list[dict],
        buffer_minutes: int = 30
    ) -> dict:
        """Arbitrates showing schedule double-bookings and overlaps.

        Rules:
          - Protected deadline slots (from Agent 07) always outrank regular showings.
          - If new request is protected, existing regular showing is displaced.
          - If new request is regular and conflicts with an existing confirmed showing,
            the existing showing is preserved and alternative times are requested.
        """
        import datetime

        req_time_str = requested_slot.get("time")
        is_protected = requested_slot.get("protected", False)

        if not req_time_str:
            return {
                "status": "error",
                "action": "reject",
                "reason": "missing_requested_time",
                "engine": "python_fallback"
            }

        try:
            req_dt = datetime.datetime.fromisoformat(req_time_str)
        except Exception:
            return {
                "status": "error",
                "action": "reject",
                "reason": "invalid_iso_time",
                "engine": "python_fallback"
            }

        displaced = None
        for slot in existing_slots:
            slot_time_str = slot.get("time")
            if not slot_time_str:
                continue
            try:
                slot_dt = datetime.datetime.fromisoformat(slot_time_str)
            except Exception:
                continue

            diff_sec = abs((req_dt - slot_dt).total_seconds())
            if diff_sec < (buffer_minutes * 60):
                # Conflict detected!
                if is_protected and not slot.get("protected", False):
                    # Protected outranks soft booking
                    displaced = slot
                    break
                else:
                    return {
                        "status": "ok",
                        "action": "conflict_held",
                        "conflicting_slot": slot,
                        "displaced_slot": None,
                        "reason": "slot_occupied_by_existing_booking",
                        "decision_provenance": "jev_engine_python_v1",
                        "engine": "python_fallback"
                    }

        if displaced:
            return {
                "status": "ok",
                "action": "displace_existing",
                "displaced_slot": displaced,
                "reason": "protected_deadline_outranks_soft_booking",
                "decision_provenance": "jev_engine_python_v1",
                "engine": "python_fallback"
            }

        return {
            "status": "ok",
            "action": "schedule_approved",
            "displaced_slot": None,
            "decision_provenance": "jev_engine_python_v1",
            "engine": "python_fallback"
        }


class JevDecisionAdapter:
    """Primary JEV AI decision adapter.
    Dispatches to MCP client if configured and available, falling back seamlessly
    to the in-process pure Python engine.
    """

    def __init__(self, mcp_client: Any = None, force_python: bool = False):
        self.mcp_client = mcp_client
        self.force_python = force_python or (os.environ.get("JEV_FORCE_PYTHON", "0") == "1")
        self.python_engine = JevPythonDecisionEngine()

    def evaluate_lead(
        self,
        context_id: str,
        payload: dict,
        rubric: dict
    ) -> dict:
        """Evaluates a lead against a rubric via MCP or pure Python fallback."""
        if self.mcp_client is not None and not self.force_python:
            try:
                # Primary: Attempt JEV MCP tool call
                result = self._call_mcp_decision(
                    decision_type="lead_qualification",
                    context_id=context_id,
                    payload={"lead": payload, "rubric": rubric}
                )
                if result and result.get("status") == "ok":
                    result["engine"] = "jev_mcp"
                    return result
            except Exception as e:
                logger.warning(
                    f"JEV MCP tool call failed: {e}. Falling back to Python decision engine."
                )

        # Fallback: Deterministic pure Python engine
        return self.python_engine.evaluate_lead_rubric(context_id, payload, rubric)

    def resolve_showing_conflict(
        self,
        context_id: str,
        requested_slot: dict,
        existing_slots: list[dict],
        buffer_minutes: int = 30
    ) -> dict:
        """Resolves showing schedule conflicts via MCP or pure Python fallback."""
        if self.mcp_client is not None and not self.force_python:
            try:
                result = self._call_mcp_decision(
                    decision_type="showing_conflict",
                    context_id=context_id,
                    payload={
                        "requested_slot": requested_slot,
                        "existing_slots": existing_slots,
                        "buffer_minutes": buffer_minutes
                    }
                )
                if result and result.get("status") == "ok":
                    result["engine"] = "jev_mcp"
                    return result
            except Exception as e:
                logger.warning(
                    f"JEV MCP tool call failed: {e}. Falling back to Python decision engine."
                )

        return self.python_engine.resolve_scheduling_conflict(
            context_id, requested_slot, existing_slots, buffer_minutes
        )

    def _call_mcp_decision(
        self,
        decision_type: str,
        context_id: str,
        payload: dict
    ) -> dict:
        """Executes tool call against JEV AI MCP endpoint."""
        if hasattr(self.mcp_client, "call_tool"):
            res = self.mcp_client.call_tool(
                "jev_evaluate_decision",
                {
                    "decision_type": decision_type,
                    "context_id": context_id,
                    "payload": payload
                }
            )
            if isinstance(res, dict):
                return res
            elif hasattr(res, "content"):
                return json.loads(res.content[0].text)
        raise RuntimeError("No compatible call_tool method found on MCP client")
