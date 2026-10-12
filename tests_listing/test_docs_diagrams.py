"""The pictures in the docs match the swarm (tools/gen_diagrams.py).

Agent folder READMEs are drawn from identity/routes.json; the playbook
pictures in docs/PLAY-BY-PLAY.md are drawn from real runs of the playbook
tests. A route or playbook change that is not regenerated fails here.
Regenerate with: python tools/gen_diagrams.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import gen_diagrams  # noqa: E402


def test_every_intent_has_plain_words():
    import json
    routes = json.load(open(os.path.join(ROOT, "identity", "routes.json")))["routes"]
    for r in routes:
        assert gen_diagrams.phrase(r["intent"])


def test_diagrams_are_current():
    files = gen_diagrams.build()
    stale = [os.path.relpath(p, ROOT) for p, body in files.items()
             if not os.path.exists(p) or open(p).read() != body]
    assert stale == [], f"run python tools/gen_diagrams.py: {stale}"


def test_every_agent_folder_and_playbook_has_a_picture():
    files = gen_diagrams.build()
    readmes = [p for p in files if p.endswith("README.md")
               and os.path.basename(os.path.dirname(p))[:2].isdigit()]
    assert len(readmes) == 21
    for p in readmes:
        assert "```mermaid" in files[p], p
    pbp = files[gen_diagrams.PLAY_BY_PLAY]
    for pb in gen_diagrams.PLAYBOOK_TESTS:
        assert f"<!-- diagram:{pb} " in pbp, pb


def test_hand_drawn_pictures_are_in_place():
    from doc_diagrams import BLOCKS
    files = gen_diagrams.build()
    for name, (rel, _anchor, _m, _c) in BLOCKS.items():
        assert f"<!-- diagram:{name} - drawn" in files[os.path.join(ROOT, rel)], name
