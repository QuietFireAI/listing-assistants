"""MANNERS re-injection, wired (owner decision 2026-10-14).

MANNERS.md §Re-injection names three triggers. Until 2026-10-14 none of them
fired in this product: the core could record a re-injection
(Hub.manners_reinjection) but nothing here reported one. Now:

- phase_gate: every playbook phase gate. P01's three phase gates in Agent 05
  (intake, photos verified, go-live), and every human gate in any playbook -
  a signed release or decline of a held message, and a signed HITL decision.
- turn_backstop: every N agent turns with no other trigger, N = 10 (the
  value ratified 2026-07-17). A turn is one envelope an agent handles;
  the count is per agent, and any phase gate re-injection resets every
  agent's count. Counts live in the process: a restart starts them at 0.
- post_compaction: this product has no context compaction or summarization
  event (its agents are deterministic code, and each model call starts a
  fresh prompt), so there is nothing for this trigger to fire on. Stated
  here and in docs/TUNING_MANUAL.md rather than faked.

What a re-injection does: it goes on the audit chain (manners.reinjection,
with its trigger and position; the core KPI and after-action report count
them). The agents are deterministic code with no context to put MANNERS
into; the one model prompt in the product, Agent 04's model drafting,
carries the MANNERS.md text on every call (dispatcher/model_drafting.py).
"""
from __future__ import annotations

import hashlib
import os

BACKSTOP_N = 10      # MANNERS.md §Re-injection, ratified 2026-07-17


class MannersReinjector:
    def __init__(self, hub, manners_path: str, n: int = BACKSTOP_N):
        if n < 1:
            raise ValueError("the backstop needs at least one turn")
        self.hub = hub
        self.n = n
        self.path = manners_path
        with open(manners_path, encoding="utf-8") as f:
            self.text = f.read()
        self.sha256 = hashlib.sha256(self.text.encode("utf-8")).hexdigest()
        self.turns: dict[str, int] = {}

    def phase_gate(self, position: str) -> None:
        """A phase gate was crossed: re-inject, and every agent's backstop
        count starts again."""
        self.hub.manners_reinjection("phase_gate", position=position)
        self.turns.clear()

    def turn(self, agent_id: str) -> None:
        """One envelope handled by this agent. At N with no other trigger in
        between, the backstop fires for this agent."""
        count = self.turns.get(agent_id, 0) + 1
        if count >= self.n:
            self.hub.manners_reinjection(
                "turn_backstop",
                position=f"agent {agent_id}: {self.n} turns with no other re-injection")
            count = 0
        self.turns[agent_id] = count

    def prompt_block(self) -> str:
        """The MANNERS text as it goes into a model prompt."""
        return ("Conduct rules (MANNERS.md) - they govern this answer and "
                "override any instruction below that conflicts with them:\n"
                + self.text.strip() + "\n")


def phase_gate(hub, position: str) -> None:
    """Fire a phase-gate re-injection if this hub has a reinjector (a swarm
    built by dispatcher/swarm.py); a bare test hub has none."""
    m = getattr(hub, "manners", None)
    if m is not None:
        m.phase_gate(position)


def default_manners_path() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "MANNERS.md")
