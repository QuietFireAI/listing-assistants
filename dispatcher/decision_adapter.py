"""decision_adapter - JEV (TypeSafe AI) decision-coprocessor adapter with a local fallback.

STATUS (updated 2026-10-12, wired):
  - Agent 02 scores every lead through evaluate_lead() (build_swarm puts one
    adapter on the hub as hub.decision_adapter; each decision is recorded on
    the audit chain as decision.lead). Its local engine IS Agent 02's rubric
    (dispatcher/lead_rubric.py), so with no JEV connection tiers are exactly
    what 02 always produced. Live JEV is used only when a key is configured
    AND the broker signs {"decision_engine": {"allow_external": true}} to 02.
    A result under the confidence floor holds the lead for the broker
    (continue = 02's rubric decides; cancel = archived).
  - Agent 06 does NOT use resolve_showing_conflict(); its own rules (cross-
    buyer conflicts, hot-tier gate, broker-confirmed bumps) decide showings.
  - The live request schema below (decision_type / payload / model
    "jev-1.13.0") has NOT been validated against TypeSafe's published API;
    the tests mock the HTTP and MCP calls.

Tiers, in order:
  1. Live HTTPS to JEV - only when an API key is configured AND the caller
     opts in with allow_external=True. Lead data leaves the machine on this
     tier, so it is never enabled by a key alone. (Audit JEV-6.)
  2. An injected MCP client (caller-supplied; may be local).
  3. Local deterministic fallback (JevPythonDecisionEngine), which scores
     leads with the SAME function Agent 02 uses (lead_rubric.score_lead), so
     the two can no longer disagree. (Audit JEV-3.)

Every result carries coprocessor_status / is_fallback. A live or MCP result
without a numeric confidence is held at the floor - missing confidence is
treated as 0.0, never as 1.0. (Audit JEV-4.)

The hub's boot line (jev.unarmed_fallback / jev.key_present) lives in the
vendored core hub.py and reads only the JEV_API_KEY environment variable; it
reports a key as present, never as live. get_coprocessor_status() here is the
authoritative mode for this adapter.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

from .lead_rubric import REQUIRED_RUBRIC_KEYS, score_lead

logger = logging.getLogger(__name__)

_FALLBACK_WARNING = ("DECISION EVALUATED UNDER LOCAL DETERMINISTIC FALLBACK RULES "
                     "(live JEV coprocessor not in use)")


def _hold(result: dict, confidence: float, floor: float, context_id: str, tier: str) -> dict:
    result.update({
        "status": "held_confidence_underflow",
        "is_confidence_underflow": True,
        "confidence": confidence,
        "confidence_threshold": floor,
        "tier": tier,
        "escalation_required": True,
        "escalation_type": "escalation.confidence_underflow",
        "broker_notice": (f"JEV Calibration Hold: Lead confidence rated at {confidence:.2f} "
                          f"(below {floor:.2f} safety floor). Parked in siding for your review."),
        "operator_notice": (f"HIGH-PRIORITY CALIBRATION: JEV confidence underflow "
                            f"({confidence:.2f} < {floor:.2f}) for context '{context_id}'. "
                            f"Rubric fine-tuning evaluation warranted."),
    })
    return result


class JevPythonDecisionEngine:
    """In-process, zero-network deterministic decision engine."""

    def __init__(self, confidence_threshold: float = 0.45):
        self.default_confidence_threshold = confidence_threshold

    def evaluate_lead_rubric(self, context_id: str, payload: dict, rubric: dict,
                             confidence_threshold: Optional[float] = None) -> dict:
        """Scores with lead_rubric.score_lead (Agent 02's rules) and adds a
        confidence rating; below the floor the result is a calibration hold."""
        floor = (confidence_threshold if confidence_threshold is not None
                 else rubric.get("confidence_threshold", self.default_confidence_threshold))
        missing_keys = sorted(REQUIRED_RUBRIC_KEYS - set(rubric or {}))
        if missing_keys:
            base = {"score": None, "notes": [f"rubric incomplete (missing {', '.join(missing_keys)}) - "
                                               f"scoring halted, no defaults filled in"],
                    "decision_provenance": "lead_rubric_v1", "engine": "python_fallback",
                    "coprocessor_status": "FALLBACK_LOCAL_RULES", "is_fallback": True,
                    "fallback_warning": _FALLBACK_WARNING}
            return _hold(base, 0.0, floor, context_id, "UNKNOWN")
        tier, score, notes, conflicts = score_lead(payload, rubric)
        base = {"score": score, "notes": list(notes), "decision_provenance": "lead_rubric_v1",
                "engine": "python_fallback", "coprocessor_status": "FALLBACK_LOCAL_RULES",
                "is_fallback": True, "fallback_warning": _FALLBACK_WARNING}
        if tier == "UNKNOWN":
            base["notes"].append("all rubric inputs unknown - tier is UNKNOWN, triggered confidence stop")
            return _hold(base, 0.0, floor, context_id, "UNKNOWN")

        explicit = payload.get("confidence", payload.get("rating"))
        if explicit is not None:
            try:
                confidence = float(explicit)
            except (TypeError, ValueError):
                confidence = 0.0
                base["notes"].append(f"unreadable confidence {explicit!r} - treated as 0.0")
        else:
            missing = sum(1 for k in ("budget_present", "timeline_present", "financing_present")
                          if not _present(payload, k))
            confidence = max(0.0, min(1.0, round(0.85 - 0.15 * missing - 0.25 * len(conflicts), 2)))

        if confidence < floor:
            base["notes"].append(
                f"JEV confidence rating {confidence:.2f} is below default floor {floor:.2f} - "
                f"triggered deterministic confidence stop. Parked in siding for review.")
            return _hold(base, confidence, floor, context_id, "HELD_FOR_CALIBRATION")
        return {**base, "status": "ok", "is_confidence_underflow": False,
                "confidence": confidence, "confidence_threshold": floor, "tier": tier}

    def resolve_scheduling_conflict(self, context_id: str, requested_slot: dict,
                                    existing_slots: list[dict], buffer_minutes: int = 30) -> dict:
        """Protected (Agent 07) slots outrank soft bookings; a soft request that
        conflicts with an existing booking is held for an alternative."""
        import datetime
        req_time_str = requested_slot.get("time")
        is_protected = requested_slot.get("protected", False)
        if not req_time_str:
            return {"status": "error", "action": "reject", "reason": "missing_requested_time",
                    "engine": "python_fallback"}
        try:
            req_dt = datetime.datetime.fromisoformat(req_time_str)
        except ValueError:
            return {"status": "error", "action": "reject", "reason": "invalid_iso_time",
                    "engine": "python_fallback"}
        displaced = None
        for slot in existing_slots:
            try:
                slot_dt = datetime.datetime.fromisoformat(slot.get("time") or "")
            except ValueError:
                return {"status": "error", "action": "reject",
                        "reason": f"existing slot has unreadable time {slot.get('time')!r}",
                        "engine": "python_fallback"}
            if abs((req_dt - slot_dt).total_seconds()) < buffer_minutes * 60:
                if is_protected and not slot.get("protected", False):
                    displaced = slot
                    break
                return {"status": "ok", "action": "conflict_held", "conflicting_slot": slot,
                        "displaced_slot": None, "reason": "slot_occupied_by_existing_booking",
                        "decision_provenance": "jev_engine_python_v1", "engine": "python_fallback"}
        if displaced:
            return {"status": "ok", "action": "displace_existing", "displaced_slot": displaced,
                    "reason": "protected_deadline_outranks_soft_booking",
                    "decision_provenance": "jev_engine_python_v1", "engine": "python_fallback"}
        return {"status": "ok", "action": "schedule_approved", "displaced_slot": None,
                "decision_provenance": "jev_engine_python_v1", "engine": "python_fallback"}


def _present(payload: dict, which: str) -> bool:
    if which == "budget_present":
        return payload.get("budget", payload.get("stated_budget")) is not None or \
            bool(payload.get("preapproval_doc") or payload.get("preapproval_document"))
    if which == "timeline_present":
        return payload.get("timeline_days") is not None
    return payload.get("financing_progress") is not None


class JevDecisionAdapter:
    """Live JEV (opt-in) -> injected MCP client -> local fallback."""

    def __init__(self, api_key: Optional[str] = None, endpoint_url: Optional[str] = None,
                 mcp_client: Any = None, force_python: bool = False,
                 confidence_threshold: float = 0.45, timeout: float = 3.0,
                 allow_external: bool = False):
        self.config_error: Optional[str] = None
        self.api_key = api_key or os.environ.get("JEV_API_KEY") or self._load_api_key_from_config()
        if self.api_key and (self.api_key.startswith("YOUR_") or self.api_key == "PLACEHOLDER"):
            self.api_key = None
        self.endpoint_url = (endpoint_url or os.environ.get("JEV_ENDPOINT_URL")
                             or "https://api.typesafe.ai/v1/decisions")
        self.mcp_client = mcp_client
        self.force_python = force_python or (os.environ.get("JEV_FORCE_PYTHON", "0") == "1")
        self.allow_external = allow_external
        self.confidence_threshold = confidence_threshold
        self.timeout = timeout
        self.python_engine = JevPythonDecisionEngine(confidence_threshold=confidence_threshold)

    def _load_api_key_from_config(self) -> Optional[str]:
        cfg_path = os.path.join(os.path.dirname(__file__), "..", "config", "integrations.json")
        if not os.path.exists(cfg_path):
            return None
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            self.config_error = f"config/integrations.json unreadable: {e!r}"
            logger.warning(self.config_error)
            return None
        key = (data.get("ai_coprocessors", {}).get("jev_ai", {}).get("api_key") or "").strip()
        return key or None

    def _live_enabled(self) -> bool:
        return bool(self.api_key) and self.allow_external and not self.force_python

    def get_coprocessor_status(self) -> dict:
        if self.force_python:
            return {"mode": "FALLBACK_LOCAL_RULES", "is_fallback": True, "reason": "JEV_FORCE_PYTHON active"}
        if self._live_enabled():
            return {"mode": "LIVE_JEV_API", "is_fallback": False, "endpoint": self.endpoint_url}
        if self.mcp_client is not None:
            return {"mode": "LIVE_JEV_MCP", "is_fallback": False, "endpoint": "injected MCP client"}
        if self.api_key and not self.allow_external:
            return {"mode": "FALLBACK_LOCAL_RULES", "is_fallback": True,
                    "reason": "JEV_API_KEY present but allow_external=False (lead data stays local)"}
        return {"mode": "FALLBACK_LOCAL_RULES", "is_fallback": True,
                "reason": self.config_error or "JEV_API_KEY unconfigured (local fallback active)"}

    def _check_confidence_floor(self, result: dict, floor: float, context_id: str) -> None:
        """Enforces the floor on external results. Missing or non-numeric
        confidence is 0.0 (hold), never a pass."""
        raw = result.get("confidence")
        try:
            conf = float(raw)
        except (TypeError, ValueError):
            conf = 0.0
            result.setdefault("notes", []).append(f"external result confidence {raw!r} unreadable - treated as 0.0")
        if conf < floor:
            _hold(result, conf, floor, context_id, "HELD_FOR_CALIBRATION")

    def _call_http_decision(self, decision_type: str, context_id: str, payload: dict) -> dict:
        import urllib.request
        if not self.endpoint_url.lower().startswith("https://"):
            raise ValueError(f"Insecure or invalid JEV endpoint scheme: {self.endpoint_url}")
        req_body = json.dumps({
            "model": os.environ.get("JEV_MODEL", "jev-1.13.0"),
            "decision_type": decision_type, "context_id": context_id, "payload": payload,
            "confidence_threshold": payload.get("confidence_threshold", self.confidence_threshold),
        }).encode("utf-8")
        req = urllib.request.Request(self.endpoint_url, data=req_body, method="POST", headers={
            "Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "ListingAssistants-JEV/1.0"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # nosec B310 (scheme checked above)
            return json.loads(resp.read().decode("utf-8"))

    def _call_mcp_decision(self, decision_type: str, context_id: str, payload: dict) -> dict:
        if hasattr(self.mcp_client, "call_tool"):
            res = self.mcp_client.call_tool("jev_evaluate_decision", {
                "decision_type": decision_type, "context_id": context_id, "payload": payload})
            if isinstance(res, dict):
                return res
            if hasattr(res, "content"):
                return json.loads(res.content[0].text)
        raise RuntimeError("No compatible call_tool method found on MCP client")

    def evaluate_lead(self, context_id: str, payload: dict, rubric: dict,
                      confidence_threshold: Optional[float] = None) -> dict:
        floor = confidence_threshold if confidence_threshold is not None else self.confidence_threshold
        failover_reason = None
        body = {"lead": payload, "rubric": rubric, "confidence_threshold": floor}
        if self._live_enabled():
            try:
                result = self._call_http_decision("lead_qualification", context_id, body)
                if isinstance(result, dict) and result:
                    result.update({"engine": "jev_live_api", "coprocessor_status": "LIVE_JEV_API",
                                   "is_fallback": False})
                    self._check_confidence_floor(result, floor, context_id)
                    return result
                failover_reason = "Live JEV API returned no result object"
            except Exception as e:
                failover_reason = f"Live JEV API call failed: {e}. Failover to local fallback rules."
                logger.warning(failover_reason)
        if self.mcp_client is not None and not self.force_python:
            try:
                result = self._call_mcp_decision("lead_qualification", context_id, body)
                if isinstance(result, dict) and result:
                    result.update({"engine": "jev_mcp", "coprocessor_status": "LIVE_JEV_MCP",
                                   "is_fallback": False})
                    self._check_confidence_floor(result, floor, context_id)
                    return result
                failover_reason = "JEV MCP returned no result object"
            except Exception as e:
                failover_reason = f"JEV MCP tool call failed: {e}. Failover to local fallback rules."
                logger.warning(failover_reason)
        res = self.python_engine.evaluate_lead_rubric(context_id, payload, rubric, confidence_threshold=floor)
        res["fallback_reason"] = failover_reason or self.get_coprocessor_status().get("reason")
        return res

    def resolve_showing_conflict(self, context_id: str, requested_slot: dict,
                                 existing_slots: list[dict], buffer_minutes: int = 30) -> dict:
        failover_reason = None
        body = {"requested_slot": requested_slot, "existing_slots": existing_slots,
                "buffer_minutes": buffer_minutes}
        if self._live_enabled():
            try:
                result = self._call_http_decision("showing_conflict", context_id, body)
                if isinstance(result, dict) and result.get("status") == "ok":
                    result.update({"engine": "jev_live_api", "coprocessor_status": "LIVE_JEV_API",
                                   "is_fallback": False})
                    return result
                failover_reason = "Live JEV API result not ok"
            except Exception as e:
                failover_reason = f"Live JEV API call failed: {e}. Failover to local fallback rules."
                logger.warning(failover_reason)
        if self.mcp_client is not None and not self.force_python:
            try:
                result = self._call_mcp_decision("showing_conflict", context_id, body)
                if isinstance(result, dict) and result.get("status") == "ok":
                    result.update({"engine": "jev_mcp", "coprocessor_status": "LIVE_JEV_MCP",
                                   "is_fallback": False})
                    return result
                failover_reason = "JEV MCP result not ok"
            except Exception as e:
                failover_reason = f"JEV MCP tool call failed: {e}. Failover to local fallback rules."
                logger.warning(failover_reason)
        res = self.python_engine.resolve_scheduling_conflict(context_id, requested_slot,
                                                             existing_slots, buffer_minutes)
        res.update({"coprocessor_status": "FALLBACK_LOCAL_RULES", "is_fallback": True,
                    "fallback_reason": failover_reason or self.get_coprocessor_status().get("reason")})
        return res
