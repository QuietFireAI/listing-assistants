# Folded 2026-10-20 from the pillar's own repository with the package
# (dispatcher/pillar_lib/README.md); only the imports changed.
"""
test_quick_check.py - Tests for the before-turn protocol

Tests cover:
- Protocol runs and produces output
- All four before-turn questions always appear
- Handles missing transcript gracefully
- Canonical failure mode: timing rationalization is not an excuse
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

import sys
import importlib
qc_module = importlib.import_module("dispatcher.pillar_lib.before_turn.quick_check")
quick_check = qc_module.quick_check
BEFORE_TURN_QUESTIONS = qc_module.BEFORE_TURN_QUESTIONS


def make_transcript(thoughts: list[dict], tmp_path: Path) -> tuple[str, Path]:
    """Create a fake transcript with thinking steps."""
    conv_id = "test-conversation-id"
    log_dir = tmp_path / conv_id / ".system_generated" / "logs"
    log_dir.mkdir(parents=True)
    transcript = log_dir / "transcript.jsonl"

    lines = []
    for i, t in enumerate(thoughts):
        lines.append(json.dumps({
            "step_index": i * 2,
            "type": "PLANNER_RESPONSE",
            "thinking": t["thinking"],
            "content": t.get("content", ""),
        }))

    transcript.write_text("\n".join(lines), encoding="utf-8")
    return conv_id, tmp_path


def test_four_questions_always_present(tmp_path, capsys):
    """All four before-turn questions must always appear in output."""
    thoughts = [{"thinking": "I was reasoning about X."}]
    conv_id, base = make_transcript(thoughts, tmp_path)

    with patch.object(qc_module, "BRAIN_DIR", base):
        quick_check(conv_id, last_n=3)

    captured = capsys.readouterr()
    for q in BEFORE_TURN_QUESTIONS:
        assert q in captured.out, f"Missing question: {q}"


def test_shows_requested_n_steps(tmp_path, capsys):
    """Only the last N steps should appear."""
    thoughts = [
        {"thinking": "Step A thinking"},
        {"thinking": "Step B thinking"},
        {"thinking": "Step C thinking"},
        {"thinking": "Step D thinking"},
    ]
    conv_id, base = make_transcript(thoughts, tmp_path)

    with patch.object(qc_module, "BRAIN_DIR", base):
        quick_check(conv_id, last_n=2)

    captured = capsys.readouterr()
    assert "Step C thinking" in captured.out
    assert "Step D thinking" in captured.out
    assert "Step A thinking" not in captured.out
    assert "Step B thinking" not in captured.out


def test_missing_transcript_handled_gracefully(tmp_path, capsys):
    """Missing transcript should produce a clear message, not a crash."""
    with patch.object(qc_module, "BRAIN_DIR", tmp_path):
        quick_check("nonexistent-id", last_n=3)

    captured = capsys.readouterr()
    assert "No transcript found" in captured.out


def test_empty_transcript_handled(tmp_path, capsys):
    """Empty transcript (no thinking steps) should not crash."""
    conv_id = "empty-conv"
    log_dir = tmp_path / conv_id / ".system_generated" / "logs"
    log_dir.mkdir(parents=True)
    (log_dir / "transcript.jsonl").write_text("", encoding="utf-8")

    with patch.object(qc_module, "BRAIN_DIR", tmp_path):
        quick_check(conv_id, last_n=3)

    captured = capsys.readouterr()
    assert "Last 0 of 0" in captured.out


def test_canonical_failure_mode_documented():
    """
    The canonical failure mode is timing rationalization.
    This test documents it as a known, named failure -- not tested by running code
    but by asserting the failure mode is described in the module docstring.
    """
    assert "timing rationalization" in qc_module.__doc__.lower(), (
        "The canonical failure mode (timing rationalization) must be documented "
        "in the module docstring. It is the first and most common way this "
        "protocol gets broken."
    )


def test_steps_in_order(tmp_path, capsys):
    """Steps should appear in chronological order."""
    thoughts = [
        {"thinking": "First thought"},
        {"thinking": "Second thought"},
        {"thinking": "Third thought"},
    ]
    conv_id, base = make_transcript(thoughts, tmp_path)

    with patch.object(qc_module, "BRAIN_DIR", base):
        quick_check(conv_id, last_n=3)

    captured = capsys.readouterr()
    pos_first = captured.out.find("First thought")
    pos_second = captured.out.find("Second thought")
    pos_third = captured.out.find("Third thought")
    assert pos_first < pos_second < pos_third
