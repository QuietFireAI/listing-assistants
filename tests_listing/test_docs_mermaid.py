"""Mermaid diagrams in the docs must parse on GitHub.

Added 2026-10-12: the README's P01 sequence diagram failed to render on
GitHub ("Parse error on line 19") because a message label contained a
semicolon, which Mermaid treats as a statement separator. The diagram was
render-checked with mermaid-cli 11.4.2 after the fix; this test guards the
cheap-to-detect causes so it cannot recur silently.
"""
import glob
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _blocks():
    for path in glob.glob(os.path.join(ROOT, "**", "*.md"), recursive=True):
        text = open(path, encoding="utf-8").read()
        for m in re.finditer(r"```mermaid\n(.*?)```", text, re.S):
            yield os.path.relpath(path, ROOT), m.group(1)


def test_there_are_diagrams_to_check():
    assert any(p == "README.md" for p, _ in _blocks())


def test_no_semicolons_inside_mermaid_statements():
    bad = [(p, i, line.strip()) for p, b in _blocks()
           for i, line in enumerate(b.splitlines(), 1) if ";" in line]
    assert not bad, f"';' ends a Mermaid statement early: {bad}"


def test_sequence_messages_have_a_label():
    arrow = re.compile(r"^\s*\w+\s*-{1,2}>>?\+?-?\s*\w+")
    bad = [(p, i, line.strip()) for p, b in _blocks() if b.lstrip().startswith("sequenceDiagram")
           for i, line in enumerate(b.splitlines(), 1)
           if arrow.match(line) and ":" not in line]
    assert not bad, bad
