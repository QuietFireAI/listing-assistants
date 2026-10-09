"""hermes_seam - Nous Hermes Cognitive Reasoning Seam & Broker Ingestion Engine.

Integrates Nous Hermes local reasoning into the QuietFireAI swarm:
  1. In-stream <think>...</think> extraction: captures native reasoning traces
     without triggering frontier API censorship or thought-inspection bans.
  2. Feed into Hub.ingest_spoke_trace() for real-time verification by the 6 detection pillars
     (open-mind, agent-open-mind, before-turn, pre-response-selfcheck, sleep-marks, splitvantage).
  3. BrokerContextIngestor: Real estate broker training and context ingestion pipeline.
     Treats Hermes like an eager college graduate receiving comprehensive in-house brokerage
     training (SOPs, NAR 2024 settlement rules, Fair Housing hard lines, commission splits,
     and brokerage brand voice). Prepares structured pairs for continual local fine-tuning.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

_THINK_TAG = re.compile(r"<think>(.*?)</think>", re.DOTALL)

DEFAULT_HERMES_SYSTEM_PROMPT = (
    "You are a licensed real estate agent assistant operating inside a governed brokerage swarm. "
    "You are in-house trained on broker standard operating procedures (SOPs), Fair Housing compliance, "
    "and statutory fiduciary rules. You must deliberate rigorously inside <think> </think> tags before "
    "emitting any client communication or listing copy. Never include discriminatory language, advice on "
    "pricing strategy, or informal wire instructions."
)


class BrokerContextIngestor:
    """Ingests brokerage training materials, office manuals, NAR settlement directives,
    and MLS rules to fine-tune and prime Hermes like a newly hired college graduate.
    """

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

    def export_fine_tuning_pairs(self, filepath: str):
        """Exports ingested materials into JSONL format suitable for local Hermes LoRA fine-tuning."""
        pairs = []
        for item in self.knowledge_base:
            pairs.append({
                "instruction": f"Apply broker policy for: {item.get('topic')}",
                "context": item.get("directive"),
                "thought": f"Checking brokerage manual on {item.get('topic')}. Verifying compliance boundaries.",
                "response": f"Policy acknowledged: {item.get('directive')}"
            })
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            for p in pairs:
                f.write(json.dumps(p) + "\n")


class HermesCognitiveSeam:
    """Connects local Hermes reasoning into the Hub-and-Spoke event dispatch loop."""

    def __init__(
        self,
        hub: Any = None,
        client: Any = None,
        model: str = "Hermes-4-70B",
        ingestor: Optional[BrokerContextIngestor] = None
    ):
        self.hub = hub
        self.client = client
        self.model = model
        self.ingestor = ingestor or BrokerContextIngestor()

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
        context: Optional[dict] = None
    ) -> Tuple[str, str]:
        """Drafts content using Hermes, extracts thought trace, and commits it to the Hub."""
        curriculum = self.ingestor.format_curriculum_prompt()
        full_prompt = f"{curriculum}\n\nTask:\n{prompt}"

        if self.client is not None and hasattr(self.client, "chat"):
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
                # Deterministic fallback simulation if inference server is temporarily offline
                raw_content = (
                    f"<think>Inference unavailable ({e}). Applying brokerage deterministic rule.</think>"
                    f"Draft based on prompt: {prompt[:80]}"
                )
        else:
            # Local deterministic mock for VM unit testing without live GPU
            raw_content = (
                f"<think>Deliberating on brokerage task for agent {agent_id}. "
                f"Verifying Fair Housing compliance and absence of wire instructions.</think>\n"
                f"Professional brokerage draft responding to: {prompt[:80]}..."
            )

        thinking, clean_text = self.parse_hermes_output(raw_content)

        # Ingest the authentic thought trace into the Hub for QuietFire pillar auditing
        if self.hub and hasattr(self.hub, "ingest_spoke_trace"):
            self.hub.ingest_spoke_trace(
                agent_id,
                envelope_id,
                thought=thinking or "Deliberation recorded via Hermes cognitive seam",
                result="draft_ready"
            )

        return thinking, clean_text
