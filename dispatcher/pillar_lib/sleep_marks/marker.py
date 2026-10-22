"""
sleep-marks - SleepMarker

Captures the reasoning state of an agent at a session break point.
Produces reflection text that restores cognitive context in the next session.

The gap between sessions is where reasoning continuity dies.
sleep-marks closes that gap.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


APP_DATA_DIR = Path.home() / ".gemini" / "antigravity"
BRAIN_DIR = APP_DATA_DIR / "brain"


@dataclass
class SleepMark:
    """
    A captured reasoning state at a session break point.

    Attributes:
        conversation_id:  The session being marked
        context_summary:  What was being worked on
        reasoning_traces: The thinking steps captured at the break point
        open_questions:   Unresolved questions at time of break
        reflection_text:  Ready to prepend to the next session's context
        timestamp:        When the mark was created
    """
    conversation_id: str
    context_summary: str
    reasoning_traces: list[dict]
    open_questions:   list[str]
    reflection_text:  str
    timestamp:        str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def save(self, output_path: str | None = None) -> Path:
        """Save this sleep mark to JSON."""
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out = Path(output_path or f"sleep_mark_{ts}.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps({
                "timestamp":        self.timestamp,
                "conversation_id":  self.conversation_id,
                "context_summary":  self.context_summary,
                "open_questions":   self.open_questions,
                "reasoning_traces": self.reasoning_traces,
                "reflection_text":  self.reflection_text,
            }, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return out


@dataclass
class RestoredContext:
    """
    The result of loading a sleep mark for use in a new session.

    Attributes:
        reflection_text:  Formatted text to prepend to the new session context
        open_questions:   Unresolved questions from the previous session
        reasoning_state:  A human-readable summary of how the agent was thinking
        source_mark:      The original SleepMark data
    """
    reflection_text: str
    open_questions:  list[str]
    reasoning_state: str
    source_mark:     dict


class SleepMarker:
    """
    Captures and restores agent reasoning state across session breaks.
    """

    def __init__(self, brain_dir: str | None = None):
        self._brain = Path(brain_dir) if brain_dir else BRAIN_DIR

    def capture(
        self,
        conversation_id: str,
        context_summary: str,
        open_questions: list[str] | None = None,
        last_n_thoughts: int = 5,
        max_reflection_chars: int = 1500,
    ) -> SleepMark:
        """
        Capture the current reasoning state from a conversation transcript.

        Args:
            conversation_id:      The conversation to read thinking traces from
            context_summary:      Brief description of what was being worked on
            open_questions:       Explicitly unresolved questions (optional)
            last_n_thoughts:      How many recent thinking steps to capture
            max_reflection_chars: Max length of the reflection text

        Returns:
            SleepMark ready to save and later restore from
        """
        traces = self._extract_traces(conversation_id, last_n_thoughts)
        questions = open_questions or []
        reflection = self._format_reflection(
            context_summary=context_summary,
            traces=traces,
            open_questions=questions,
            max_chars=max_reflection_chars,
        )

        return SleepMark(
            conversation_id=conversation_id,
            context_summary=context_summary,
            reasoning_traces=traces,
            open_questions=questions,
            reflection_text=reflection,
        )

    @classmethod
    def restore(cls, mark_path: str) -> RestoredContext:
        """
        Load a sleep mark and produce a RestoredContext for the new session.

        Args:
            mark_path: Path to the saved sleep mark JSON file

        Returns:
            RestoredContext with reflection text and open questions
        """
        data = json.loads(Path(mark_path).read_text(encoding="utf-8"))
        traces = data.get("reasoning_traces", [])

        # Build reasoning state summary
        if traces:
            reasoning_state = "\n".join(
                f"[Step {t.get('step_index', i+1)}] {t.get('thinking', '')[:300]}"
                for i, t in enumerate(traces)
            )
        else:
            reasoning_state = "No reasoning traces captured in this mark."

        return RestoredContext(
            reflection_text=data.get("reflection_text", ""),
            open_questions=data.get("open_questions", []),
            reasoning_state=reasoning_state,
            source_mark=data,
        )

    def _extract_traces(self, conversation_id: str, last_n: int) -> list[dict]:
        """Extract the last N thinking traces from a transcript."""
        # Reject path traversal: the id is a single directory name, never a path.
        if any(sep in conversation_id for sep in ("/", "\\")) or conversation_id in (".", ".."):
            return []
        transcript = (
            self._brain
            / conversation_id
            / ".system_generated"
            / "logs"
            / "transcript.jsonl"
        )

        if not transcript.exists():
            return []

        traces = []
        for line in transcript.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                step = json.loads(line)
            except json.JSONDecodeError:
                continue

            if step.get("type") != "PLANNER_RESPONSE":
                continue
            thinking = step.get("thinking", "").strip()
            if not thinking:
                continue

            traces.append({
                "step_index": step.get("step_index"),
                "created_at": step.get("created_at"),
                "thinking":   thinking,
                "content":    step.get("content", "").strip()[:200],
            })

        return traces[-last_n:] if traces else []

    @classmethod
    def _format_reflection(
        cls,
        context_summary: str,
        traces: list[dict],
        open_questions: list[str],
        max_chars: int,
    ) -> str:
        """Format the sleep mark as reflection text for the next session."""
        lines = [
            "## Restored Reasoning Context (sleep-marks)",
            "",
            f"**Session was working on:** {context_summary}",
            "",
        ]

        if open_questions:
            lines.append("**Open questions at break point:**")
            for q in open_questions:
                lines.append(f"  - {q}")
            lines.append("")

        if traces:
            lines.append("**Reasoning at break point:**")
            chars_used = 0
            for t in traces:
                entry = f"> [Step {t.get('step_index', '?')}] {t['thinking']}"
                if chars_used + len(entry) > max_chars:
                    lines.append("> ...")
                    break
                lines.append(entry)
                chars_used += len(entry)
            lines.append("")
        else:
            lines.append("**Note:** No reasoning traces were captured for this mark.")
            lines.append("")

        lines += [
            "**Instructions:** Resume with awareness of the above reasoning state.",
            "Where uncertainty was present, do not treat prior conclusions as settled.",
            "",
            "---",
            "",
        ]

        return "\n".join(lines)
