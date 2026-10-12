"""hermes_seam - optional seam for a locally served Hermes-family model.

What it provides:
  1. parse_hermes_output(): splits a model reply into its <think>...</think>
     reasoning and the user-facing text.
  2. HermesCognitiveSeam.draft_and_trace(): calls an injected OpenAI-style
     chat client, sends the model's own reasoning to Hub.ingest_spoke_trace()
     (agent-open-mind taint gate), and offers the run to the learning loop.
  3. BrokerContextIngestor: a list of brokerage directives that is prepended
     to the prompt, plus an export of those directives as reference records.
  4. HermesLearningLoop: screens runs and collects the ones that pass into an
     exemplar pool that can be exported as JSONL.

Wiring status (2026-10-12): Agent 04 calls draft_and_trace() through
dispatcher/model_drafting.py when the broker signs drafting mode "model" and
the active checkpoint passed the broker exam on the served model; otherwise
no agent calls a model. The learning loop is not run on live drafts
(learn=False); it is used by its own tests and the operator tools.

Behavior fixed 2026-10-11 (audit H-2..H-5):
  - No model client, or a failed model call, raises HermesUnavailableError.
    Before, the seam wrote its own <think> text and a canned draft and fed
    both to the hub and to the training pool as if a model had produced them.
  - A reply with no <think> block sends an EMPTY thought to the hub, so the
    taint gate fires. Before, a placeholder thought was substituted and the
    gate never fired.
  - The open-mind / agent-open-mind pillars are required (requirements.txt).
    If either is missing, PILLARS_ARMED is False and the learning loop
    refuses to assimilate. Before, local stand-ins always reported "aligned".
  - evaluate_policy_compliance() is a phrase screen. Passing it does not
    establish Fair Housing or wire-safety compliance; a human reviews drafts.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Optional, Tuple

_missing: list[str] = []
try:
    from open_mind.comparator import Comparator
except ImportError:
    Comparator = None
    _missing.append("open_mind")
try:
    from agent_open_mind import taint_check
except ImportError:
    taint_check = None
    _missing.append("agent_open_mind")

PILLARS_ARMED: bool = not _missing
PILLARS_UNARMED_REASON: str = ("" if PILLARS_ARMED else
                               f"pillar package(s) not installed: {', '.join(_missing)} - "
                               f"learning loop refuses to assimilate (no stand-in logic)")


class HermesUnavailableError(RuntimeError):
    """No model produced a draft. Nothing was traced or assimilated."""

_THINK_TAG = re.compile(r"<think>(.*?)</think>", re.DOTALL)

DEFAULT_HERMES_SYSTEM_PROMPT = (
    "You are a licensed real estate agent assistant operating inside a governed brokerage swarm. "
    "You are in-house trained on broker standard operating procedures (SOPs), Fair Housing compliance, "
    "and statutory fiduciary rules. You must deliberate rigorously inside <think> </think> tags before "
    "emitting any client communication or listing copy. Never include discriminatory language, advice on "
    "pricing strategy, or informal wire instructions."
)


class BrokerContextIngestor:
    """Holds brokerage directives (4 built in, more via ingest_document) that
    format_curriculum_prompt() prepends to the model prompt. It does not
    train or fine-tune a model; export_reference_records() writes the
    directives out for a human to build training data from."""

    def __init__(self, materials_dir: Optional[str] = None):
        self.materials_dir = materials_dir
        self.knowledge_base: list[dict[str, str]] = []
        self._load_core_broker_directives()

    def _load_core_broker_directives(self):
        """Standard in-house curriculum provided to every new recruit."""
        self.knowledge_base.extend([
            {
                "topic": "nar_settlement_2024",
                "directive": "Written buyer representation agreement required BEFORE touring any home. "
                             "Never state, advertise, or negotiate buyer broker commission within the MLS."
            },
            {
                "topic": "fair_housing_hard_line",
                "directive": "Zero references to race, color, religion, sex, disability, familial status, "
                             "national origin, neighborhood demographics, schools, churches, or 'walkable to temples'. "
                             "Describe property physical characteristics only, never the kinds of people living there."
            },
            {
                "topic": "fiduciary_pricing_boundary",
                "directive": "Never set, negotiate, or volunteer property valuation. Price is the exclusive "
                             "fiduciary prerogative of the licensed broker and client. Route valuation questions to human."
            },
            {
                "topic": "wire_fraud_defense",
                "directive": "Never transmit wire instructions, routing numbers, or account details via email, SMS, "
                             "or chat. Wire instructions are delivered via encrypted closing portal or verbal verification."
            }
        ])

    def ingest_document(self, title: str, content: str, category: str = "brokerage_sop"):
        """Ingests brokerage-specific manuals, training slides, or local board rules."""
        self.knowledge_base.append({
            "topic": title,
            "directive": content.strip(),
            "category": category
        })

    def format_curriculum_prompt(self, max_items: int = 5) -> str:
        """Builds the in-context broker training prompt for Hermes inference."""
        lines = ["--- BROKERAGE IN-HOUSE TRAINING DIRECTIVES ---"]
        for item in self.knowledge_base[:max_items]:
            lines.append(f"[{item.get('topic', 'directive').upper()}]: {item['directive']}")
        lines.append("-------------------------------------------------")
        return "\n".join(lines)

    def export_reference_records(self, filepath: str) -> int:
        """Writes the directives as JSONL reference records
        {"topic", "directive", "category"}. These are source material for a
        human to build training data from; they are not instruction/response
        pairs. Replaces export_fine_tuning_pairs (audit OG-6), which wrote a
        code-authored "thought" and a "Policy acknowledged: ..." response for
        every directive. Returns the number of records written."""
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            for item in self.knowledge_base:
                f.write(json.dumps({"topic": item.get("topic"),
                                    "directive": item.get("directive"),
                                    "category": item.get("category", "core_directive")}) + "\n")
        return len(self.knowledge_base)


class HermesLearningLoop:
    """Screens (thought, action) runs offered by a caller and keeps the ones
    that pass in an exemplar pool, exportable as JSONL.

    A run is offered only when code calls assimilate_operational_run(); today
    the only caller is HermesCognitiveSeam.draft_and_trace(), and nothing in
    the swarm calls that. Screening, in order:
      0. pillars absent -> REFUSED_PILLARS_UNARMED
      1. agent-open-mind taint_check (e.g. empty thought) -> QUARANTINED_TAINTED
      2. composite variance = max(0.5*open-mind drift + 0.5*phrase-screen
         penalty, phrase-screen penalty); >= drift_threshold -> QUARANTINED_HIGH_VARIANCE
      3. otherwise ASSIMILATED
    With a logger, each outcome is written via log_training_update().
    """

    def __init__(
        self,
        ingestor: Optional[BrokerContextIngestor] = None,
        logger: Optional[Any] = None,
        drift_threshold: float = 0.35
    ):
        self.ingestor = ingestor or BrokerContextIngestor()
        self.logger = logger
        self.drift_threshold = drift_threshold
        self.assimilated_exemplars: list[dict] = []
        self.quarantined_exemplars: list[dict] = []
        self.running_avg_variance: float = 0.0
        self.update_history: list[dict] = []

    # Phrases screened by evaluate_policy_compliance(). The fair-housing list
    # carries the place-of-worship and familial-status terms named in this
    # module's own fair_housing_hard_line directive (added 2026-10-11, audit
    # H-5: "Great family neighborhood, walk to church!" passed the screen).
    WIRE_PHRASES = ("routing number", "wire your funds", "swift code", "transfer escrow to account")
    FAIR_HOUSING_PHRASES = ("caucasian", "christian neighborhood", "no kids", "exclusive demographic",
                            "church", "temple", "mosque", "synagogue", "family neighborhood",
                            "perfect for families", "walkable to temples")
    PRICE_PHRASES = ("guarantee price", "will definitely sell for $", "promise you $")

    def evaluate_policy_compliance(self, text: str) -> float:
        """Phrase screen against WIRE_PHRASES, FAIR_HOUSING_PHRASES and
        PRICE_PHRASES. Returns 0.0 (no listed phrase found) to 1.0. A 0.0
        means none of these phrases appear - it does not establish
        compliance. Human review of drafts is still required."""
        text_lower = text.lower()
        penalty = 0.0

        # Hard check 1: Wire instructions breach
        if any(w in text_lower for w in self.WIRE_PHRASES):
            penalty += 0.8

        # Hard check 2: Fair housing demographic breach
        if any(f in text_lower for f in self.FAIR_HOUSING_PHRASES):
            penalty += 0.8

        # Hard check 3: Unauthorized price guarantee
        if any(p in text_lower for p in self.PRICE_PHRASES):
            penalty += 0.5

        return min(penalty, 1.0)

    def calculate_variance(self, thought: str, action: str) -> dict:
        """Calculates multi-dimensional variance between internal deliberation,
        external action, and broker policy boundaries. Requires the open_mind
        pillar (no stand-in)."""
        if Comparator is None:
            raise RuntimeError(PILLARS_UNARMED_REASON)
        dr = Comparator.compare(thought, action)
        drift_score = float(dr.drift_score)
        policy_penalty = self.evaluate_policy_compliance(action)

        # Composite variance: balanced epistemic drift and policy adherence
        # If severe policy breach (penalty >= 0.5), variance reflects the breach directly
        base_variance = (0.5 * drift_score) + (0.5 * policy_penalty)
        composite_variance = round(max(base_variance, policy_penalty), 4)

        # Variance delta relative to running baseline
        variance_delta = round(composite_variance - self.running_avg_variance, 4) if self.assimilated_exemplars else 0.0

        return {
            "drift_score": drift_score,
            "policy_penalty": policy_penalty,
            "composite_variance": composite_variance,
            "variance_delta": variance_delta,
            "signals": list(dr.signals)
        }

    def assimilate_operational_run(
        self,
        agent_id: str,
        envelope_id: str,
        thought: str,
        action: str,
        client_context_id: str = "",
        topic: str = "operational_execution",
        metadata: Optional[dict] = None
    ) -> dict:
        """Assimilates a live sub-agent operational task into Hermes's continual learning pool."""
        rec = {
            "agent": agent_id,
            "envelope_id": envelope_id,
            "thought": thought,
            "result": action
        }

        # Step 0: pillars absent -> refuse, declared (no stand-in gate)
        if not PILLARS_ARMED:
            if self.logger and hasattr(self.logger, "log_training_update"):
                self.logger.log_training_update(agent_id=agent_id, client_context_id=client_context_id,
                                                topic=topic, variance=1.0,
                                                status="REFUSED_PILLARS_UNARMED",
                                                detail=PILLARS_UNARMED_REASON)
            return {"agent_id": agent_id, "envelope_id": envelope_id,
                    "status": "REFUSED_PILLARS_UNARMED", "reason": PILLARS_UNARMED_REASON,
                    "is_assimilated": False}

        # Step 1: agent-open-mind taint check gate
        gate = taint_check(rec)
        if gate.get("tainted"):
            status = "QUARANTINED_TAINTED"
            var_data = {
                "drift_score": 1.0,
                "policy_penalty": 1.0,
                "composite_variance": 1.0,
                "variance_delta": round(1.0 - self.running_avg_variance, 4),
                "signals": ["tainted_missing_thought"]
            }
            quarantine_record = {
                "agent_id": agent_id,
                "envelope_id": envelope_id,
                "client_context_id": client_context_id,
                "topic": topic,
                "thought": thought,
                "action": action,
                "status": status,
                "variance": 1.0,
                "reason": gate.get("reason", "Tainted by agent-open-mind gate")
            }
            self.quarantined_exemplars.append(quarantine_record)
            if self.logger and hasattr(self.logger, "log_training_update"):
                self.logger.log_training_update(
                    agent_id=agent_id,
                    client_context_id=client_context_id,
                    topic=topic,
                    variance=1.0,
                    status=status,
                    detail=f"Quarantined by agent-open-mind: {gate.get('reason')}"
                )
            return {
                "agent_id": agent_id,
                "envelope_id": envelope_id,
                "status": status,
                "variance": 1.0,
                "variance_delta": var_data["variance_delta"],
                "is_assimilated": False
            }

        # Step 2: Calculate operational variance
        var_data = self.calculate_variance(thought, action)
        composite_var = var_data["composite_variance"]

        # Step 3: Variance tolerance threshold gate
        if composite_var >= self.drift_threshold:
            status = "QUARANTINED_HIGH_VARIANCE"
            quarantine_record = {
                "agent_id": agent_id,
                "envelope_id": envelope_id,
                "client_context_id": client_context_id,
                "topic": topic,
                "thought": thought,
                "action": action,
                "status": status,
                "variance": composite_var,
                "variance_data": var_data
            }
            self.quarantined_exemplars.append(quarantine_record)
            if self.logger and hasattr(self.logger, "log_training_update"):
                self.logger.log_training_update(
                    agent_id=agent_id,
                    client_context_id=client_context_id,
                    topic=topic,
                    variance=composite_var,
                    status=status,
                    detail=f"Variance spike ({composite_var:.4f} >= {self.drift_threshold:.2f})"
                )
            return {
                "agent_id": agent_id,
                "envelope_id": envelope_id,
                "status": status,
                "variance": composite_var,
                "variance_delta": var_data["variance_delta"],
                "is_assimilated": False
            }

        # Step 4: Assimilate into active training pool
        status = "ASSIMILATED"
        exemplar = {
            "instruction": f"Execute real estate task for Agent {agent_id}: {topic}",
            "context": f"Client ID: {client_context_id} | Live Swarm Execution",
            "thought": thought,
            "response": action,
            "agent_id": agent_id,
            "envelope_id": envelope_id,
            "client_context_id": client_context_id,
            "variance": composite_var,
            "thought_origin": "trace_supplied_by_caller",
        }
        self.assimilated_exemplars.append(exemplar)

        # Update running average variance
        n = len(self.assimilated_exemplars)
        self.running_avg_variance = round(
            ((self.running_avg_variance * (n - 1)) + composite_var) / n, 4
        )

        update_entry = {
            "agent_id": agent_id,
            "envelope_id": envelope_id,
            "client_context_id": client_context_id,
            "topic": topic,
            "variance": composite_var,
            "variance_delta": var_data["variance_delta"],
            "status": status,
            "running_avg_variance": self.running_avg_variance
        }
        self.update_history.append(update_entry)

        # Step 5: Dual-log in real time
        if self.logger and hasattr(self.logger, "log_training_update"):
            self.logger.log_training_update(
                agent_id=agent_id,
                client_context_id=client_context_id,
                topic=topic,
                variance=composite_var,
                status=status,
                detail=f"Assimilated live experience (Running Avg: {self.running_avg_variance:.4f})"
            )

        return {
            "agent_id": agent_id,
            "envelope_id": envelope_id,
            "status": status,
            "variance": composite_var,
            "variance_delta": var_data["variance_delta"],
            "running_avg_variance": self.running_avg_variance,
            "is_assimilated": True,
            "total_assimilated": len(self.assimilated_exemplars)
        }

    def assimilate_human_feedback(
        self,
        agent_id: str,
        client_context_id: str,
        original_output: str,
        human_correction: str,
        user_notes: str = "",
        feedback_type: str = "wording_revision"
    ) -> dict:
        """Adds a broker's correction to the exemplar pool. The correction is
        screened with evaluate_policy_compliance() (a phrase screen, see its
        docstring). The exemplar's "thought" is a template built from the
        broker's notes, not model reasoning, and is marked
        thought_origin="template_from_human_notes" so it can be filtered out
        of a fine-tuning set."""
        # Step 1: Ensure the human correction doesn't introduce statutory violations
        policy_penalty = self.evaluate_policy_compliance(human_correction)
        if policy_penalty >= 0.5:
            status = "QUARANTINED_POLICY_BREACH"
            return {
                "status": status,
                "is_assimilated": False,
                "reason": "Human feedback conflicted with statutory non-negotiables (Fair Housing or Wire defense)."
            }

        status = "ASSIMILATED_HUMAN_GOLD"
        thought = (
            f"Adopting direct broker feedback for agent {agent_id}. "
            f"User notes: '{user_notes}'. Revising phrasing to match broker preference: '{human_correction}'."
        )
        exemplar = {
            "instruction": f"Apply broker preferred style and phrasing for Agent {agent_id}",
            "context": f"Broker Personalization | Original: {original_output[:120]}",
            "thought": thought,
            "response": human_correction,
            "agent_id": agent_id,
            "client_context_id": client_context_id,
            "feedback_type": feedback_type,
            "variance": 0.05,
            "thought_origin": "template_from_human_notes",
        }
        self.assimilated_exemplars.append(exemplar)

        n = len(self.assimilated_exemplars)
        self.running_avg_variance = round(
            ((self.running_avg_variance * (n - 1)) + 0.05) / n, 4
        )

        if self.logger and hasattr(self.logger, "log_training_update"):
            self.logger.log_training_update(
                agent_id=agent_id,
                client_context_id=client_context_id,
                topic=f"human_feedback_{feedback_type}",
                variance=0.05,
                status=status,
                detail=f"Personalized to broker voice: {user_notes or human_correction[:40]}"
            )
        return {
            "status": status,
            "is_assimilated": True,
            "total_assimilated": len(self.assimilated_exemplars),
            "message": "Human feedback ingested as gold exemplar for local personalization."
        }

    def export_operational_dataset(self, filepath: str):
        """Exports all assimilated live operational exemplars into JSONL format for LoRA fine-tuning."""
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            for item in self.assimilated_exemplars:
                f.write(json.dumps({
                    "instruction": item["instruction"],
                    "context": item["context"],
                    "thought": item["thought"],
                    "response": item["response"],
                    "thought_origin": item.get("thought_origin", "unknown"),
                }) + "\n")

    def get_metrics(self) -> dict:
        return {
            "total_assimilated": len(self.assimilated_exemplars),
            "total_quarantined": len(self.quarantined_exemplars),
            "running_avg_variance": self.running_avg_variance,
            "recent_updates": len(self.update_history)
        }


class HermesCognitiveSeam:
    """Connects local Hermes reasoning into the Hub-and-Spoke event dispatch loop."""

    def __init__(
        self,
        hub: Any = None,
        client: Any = None,
        model: str = "Hermes-4-70B",
        ingestor: Optional[BrokerContextIngestor] = None,
        learning_loop: Optional[HermesLearningLoop] = None,
        logger: Optional[Any] = None
    ):
        self.hub = hub
        self.client = client
        self.model = model
        self.ingestor = ingestor or BrokerContextIngestor()
        self.logger = logger
        self.learning_loop = learning_loop or HermesLearningLoop(ingestor=self.ingestor, logger=self.logger)

    def parse_hermes_output(self, raw_text: str) -> Tuple[str, str]:
        """Separates in-stream <think> tokens from final user-facing text."""
        thinking_parts = _THINK_TAG.findall(raw_text)
        thinking = "\n".join(thinking_parts).strip()
        final_text = _THINK_TAG.sub("", raw_text).strip()
        return thinking, final_text

    def draft_and_trace(
        self,
        agent_id: str,
        envelope_id: str,
        prompt: str,
        context: Optional[dict] = None,
        learn: bool = True
    ) -> Tuple[str, str]:
        """Calls the injected model, sends its <think> reasoning to the hub
        and offers the run to the learning loop. Raises HermesUnavailableError
        when there is no model client or the call fails."""
        curriculum = self.ingestor.format_curriculum_prompt()
        full_prompt = f"{curriculum}\n\nTask:\n{prompt}"

        if self.client is None or not hasattr(self.client, "chat"):
            raise HermesUnavailableError(
                "no model client configured - no draft produced, nothing traced or assimilated")
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": DEFAULT_HERMES_SYSTEM_PROMPT},
                    {"role": "user", "content": full_prompt}
                ]
            )
            raw_content = response.choices[0].message.content or ""
        except Exception as e:
            raise HermesUnavailableError(
                f"model call failed ({type(e).__name__}: {e}) - no draft produced") from e

        thinking, clean_text = self.parse_hermes_output(raw_content)

        # The model's own reasoning goes to the hub. A reply with no <think>
        # block sends an empty thought so the agent-open-mind taint gate fires.
        if self.hub and hasattr(self.hub, "ingest_spoke_trace"):
            self.hub.ingest_spoke_trace(agent_id, envelope_id, thought=thinking, result="draft_ready")

        # Assimilate into the Hermes continuous learning loop with live variance tracking
        if learn and self.learning_loop:
            client_id = context.get("client_context_id", "") if context else ""
            self.learning_loop.assimilate_operational_run(
                agent_id=agent_id,
                envelope_id=envelope_id,
                thought=thinking,
                action=clean_text,
                client_context_id=client_id,
                topic=prompt[:60]
            )

        return thinking, clean_text
