"""handoff_guard - enforces the handoff rule on every spoke send.

The rule, in all 20 agent SKILL.md files: "No ack = the handoff did not
happen." Before 2026-10-11 (audit TU-2) all 295 hub.send() calls in the
spokes discarded the hub's result, so a rejected or dead-lettered handoff
left no human-visible trace beyond a line in the audit log.

Each spoke now holds HandoffGuard(hub, agent_id) instead of the bare hub.
It forwards everything to the hub unchanged (register, escalate, queues,
audit, ...). On send(), when the hub returns "reject" or "dead.letter" it:
  1. appends "handoff.failed" to the hash-chained audit log,
  2. records a spoke trace naming the failure,
  3. sends clarification.request (from the same agent, to "queue") carrying
     the failed envelope and the hub's result, so a human sees it.
"ack", "held", "duplicate" and "suspended" are left alone: held and
suspended envelopes are already in a human queue; duplicate is the
ack-loss retry case.

Method note: the SKILL.md rule says "retry once, then raise handoff.failed".
The guard does not retry. Both failure statuses are deterministic in this
in-process hub: a reject (schema, closed track, signature) rejects again,
and a dead-lettered envelope id is already in seen_ids, so the same
envelope comes back "duplicate". A human gets it on the first failure.

The guard lives outside the core files (tools/sync_core.py CORE_FILES), so
core parity with dispatcher-agents is unchanged.
"""
from __future__ import annotations

from typing import Any

from .core import Envelope

FAILED_STATUSES = frozenset({"reject", "dead.letter"})


class HandoffGuard:
    __slots__ = ("_hub", "_agent_id")

    def __init__(self, hub: Any, agent_id: str):
        object.__setattr__(self, "_hub", hub)
        object.__setattr__(self, "_agent_id", agent_id)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._hub, name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(self._hub, name, value)

    @property
    def unwrapped(self) -> Any:
        return self._hub

    def send(self, env: Envelope) -> dict:
        res = self._hub.send(env)
        status = res.get("status") if isinstance(res, dict) else None
        if status not in FAILED_STATUSES:
            return res
        if env.to_agent == "queue" or env.intent == "clarification.request":
            # the human-facing hold itself failed; record it, never recurse
            self._hub.audit.append("handoff.failed", {
                "agent": self._agent_id, "envelope_id": env.envelope_id,
                "intent": env.intent, "to_agent": env.to_agent,
                "status": status, "reason": res.get("reason"),
                "clarification_sent": False})
            return res
        # the hub omits "reason" only for the no-handler dead letter
        reason = res.get("reason") or (f"no handler registered for {env.to_agent}"
                                       if status == "dead.letter" else "")
        self._hub.audit.append("handoff.failed", {
            "agent": self._agent_id, "envelope_id": env.envelope_id,
            "intent": env.intent, "to_agent": env.to_agent,
            "client_context_id": env.client_context_id,
            "status": status, "reason": reason, "clarification_sent": True})
        self._hub.ingest_spoke_trace(
            self._agent_id, env.envelope_id,
            thought=f"{env.intent} to {env.to_agent} came back {status!r} ({reason}) - "
                    f"no ack means the handoff did not happen; holding for a human",
            result="held: handoff.failed")
        self._hub.send(Envelope(
            from_agent=self._agent_id, to_agent="queue", intent="clarification.request",
            client_context_id=env.client_context_id,
            payload={"reason": f"handoff.failed: {env.intent} -> {env.to_agent}: {status} {reason}".strip(),
                     "failed_envelope": env.to_record(), "hub_result": res},
            provenance={"source": f"spoke-{self._agent_id}", "captured_at": "runtime",
                        "verbatim_available": True}))
        return res


def guard(hub: Any, agent_id: str) -> Any:
    """Wraps hub once; an already-guarded hub is re-wrapped for this agent."""
    if isinstance(hub, HandoffGuard):
        hub = hub.unwrapped
    return HandoffGuard(hub, agent_id)


def _snapshot(spoke: Any) -> bytes:
    import pickle
    return pickle.dumps({k: v for k, v in vars(spoke).items() if k != "hub"})


def _config_digest(payload: Any) -> str:
    import hashlib
    import json
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str)
                          .encode("utf-8")).hexdigest()


def register(hub: Any, agent_id: str, spoke: Any) -> None:
    """Registers spoke.handle with the hub. A signed config.update that the
    agent does not act on (no audit entry, no change to its state) is no
    longer acknowledged in silence: it is recorded as config.unrecognized and
    held for the broker with the keys that were sent. Added 2026-10-11: every
    one of the 20 agents acked a config with a misspelled or unknown setting
    and changed nothing, with no sign anywhere that it had been ignored."""
    handler = spoke.handle

    def handle(env):
        if env.intent != "config.update":
            return handler(env)
        before_tip = hub.audit._prev
        before_state = _snapshot(spoke)
        result = handler(env)
        keys = sorted((env.payload or {}).keys())
        digest = _config_digest(env.payload)
        effective = getattr(spoke, "_effective_configs", None)
        if effective is None:
            effective = {}
        if _snapshot(spoke) != before_state:
            # took effect: remember these exact values (survives restart -
            # the snapshot carries spoke attributes)
            effective[digest] = keys
            spoke._effective_configs = effective
            return result
        if hub.audit._prev != before_tip:
            return result   # acted on it without a state change (e.g. refused it, on the record)
        if digest in effective:
            # Fixed 2026-10-12 (scene run): the same signed values sent again
            # (Scene 4 re-sends Scene 2's ruleset) changed nothing because
            # they were already in effect - that is not "unrecognized" and
            # does not page the broker. Recorded on the chain.
            hub.audit.append("config.unchanged", {
                "agent": agent_id, "envelope_id": env.envelope_id,
                "client_context_id": env.client_context_id, "keys": keys,
                "reason": "the same values were already in effect"})
            return result
        hub.audit.append("config.unrecognized", {
            "agent": agent_id, "envelope_id": env.envelope_id,
            "client_context_id": env.client_context_id, "keys": keys})
        hub.send(Envelope(
            from_agent=agent_id, to_agent="queue", intent="clarification.request",
            client_context_id=env.client_context_id,
            payload={"reason": f"config.update to Agent {agent_id} changed nothing: "
                               f"no setting of this agent matched these keys, or "
                               f"the values equal what this agent already uses",
                     "keys": keys},
            provenance={"source": f"spoke-{agent_id}", "captured_at": "runtime",
                        "verbatim_available": True}))
        return result

    handle.__wrapped__ = handler
    hub.register(agent_id, handle)
