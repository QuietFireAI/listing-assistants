"""docs/GLOSSARY.md stays reachable and true (added 2026-10-13).

The owner asked for a definitions section "at first ... especially on the
readme" so real estate readers can follow the software words. This fails
when: a link to a glossary word points at no heading; a word is missing
from the glossary's index; a page that should point to the glossary stops
doing so; or a fact the glossary states (an intent, a route, a file, a
count, a label) stops matching the code.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)

GLOSSARY = os.path.join(ROOT, "docs", "GLOSSARY.md")
POINTER = "**Words used here.**"
POINTED = ["docs/START_HERE.md", "docs/AGENT_USER_MANUAL.md", "docs/BROKER_DESK_MANUAL.md",
           "docs/BROKER_DESK_TESTING_GUIDE.md", "docs/PLAYBOOKS.md", "docs/PLAY-BY-PLAY.md",
           "docs/WHAT_SUCCESS_MEANS.md", "docs/JOB_DESCRIPTIONS.md", "docs/TUNING_MANUAL.md",
           "docs/OPERATOR_TUNING_GUIDE.md", "docs/OPERATOR_TESTING_MANUAL.md",
           "docs/FINANCIAL_CAPABILITY.md", "docs/JEV_DECISION_PLATFORM.md", "docs/MOUNTING.md",
           "docs/ROADMAP.md", "OPERATOR_TESTING_GUIDE.md", "QUICKSTART_WINDOWS.md"]


def text(rel):
    return open(os.path.join(ROOT, rel), encoding="utf-8").read()


def slug(heading):                      # GitHub's anchor for a heading
    s = re.sub(r"[^\w\- ]", "", heading.strip().lower())
    return s.replace(" ", "-")


GLOSS = text("docs/GLOSSARY.md")
ANCHORS = {slug(h) for h in re.findall(r"^#{1,6} (.+)$", GLOSS, re.M)}
WORDS = [slug(h) for h in re.findall(r"^### (.+)$", GLOSS, re.M)]


def md_files():
    for dirpath, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "__pycache__")]
        for f in files:
            if f.endswith(".md"):
                yield os.path.join(dirpath, f)


def test_every_link_to_a_glossary_word_lands_on_it():
    bad = []
    for path in md_files():
        body = open(path, encoding="utf-8").read()
        for target in re.findall(r"\]\(([^)\s]*GLOSSARY\.md(?:#[^)\s]*)?)\)", body):
            file_part, _, frag = target.partition("#")
            resolved = os.path.normpath(os.path.join(os.path.dirname(path), file_part))
            if resolved != GLOSSARY:
                bad.append(f"{os.path.relpath(path, ROOT)} -> {target} (not docs/GLOSSARY.md)")
            elif frag and frag not in ANCHORS:
                bad.append(f"{os.path.relpath(path, ROOT)} -> #{frag} (no such word)")
        if path == GLOSSARY:
            for frag in re.findall(r"\]\(#([^)]+)\)", body):
                if frag not in ANCHORS:
                    bad.append(f"GLOSSARY.md index -> #{frag} (no such word)")
    assert not bad, bad


def test_every_word_is_in_the_index_at_the_top():
    index = GLOSS.split("\n---\n", 1)[0]
    missing = [w for w in WORDS if f"(#{w})" not in index]
    assert not missing, f"words with no entry in the index: {missing}"


def test_the_readme_explains_the_words_before_anything_else():
    readme = text("README.md")
    assert readme.index("## Words used here") < readme.index("## What it does")
    section = readme.split("## Words used here", 1)[1].split("\n## ", 1)[0]
    rows = [r for r in section.splitlines() if r.startswith("| [")]
    assert len(rows) >= 15, len(rows)
    for r in rows:
        assert "](docs/GLOSSARY.md#" in r, r
    for word in ("tuple", "playbook", "swarm", "closed-track", "hold", "hitl"):
        assert f"docs/GLOSSARY.md#{word}" in section, word


def test_the_pages_a_broker_reads_point_to_the_glossary():
    for rel in POINTED:
        assert POINTER in text(rel), f"{rel} has no glossary pointer"
    agent_dirs = sorted(d for d in os.listdir(ROOT) if re.match(r"\d\d-", d))
    assert len(agent_dirs) == 21
    for d in agent_dirs:
        assert POINTER in text(os.path.join(d, "README.md")), d


def test_what_the_glossary_says_matches_the_code():
    routes = json.load(open(os.path.join(ROOT, "identity", "routes.json"), encoding="utf-8"))["routes"]
    intents = {r["intent"] for r in routes}
    for i in ("listing.data", "vendor.request", "content.review", "campaign.publish",
              "clock.tick", "clarification.request", "listing.change.authorized"):
        assert f"`{i}`" in GLOSS or i in GLOSS, i
        assert i in intents, f"the glossary names intent {i}, which no route has"
    lead = next(r for r in routes if r["intent"] == "lead.captured")
    assert sorted(lead["senders"]) == ["01", "16"] and lead["receivers"] == ["02"]
    assert "`lead.captured` may be sent by 01 or 16 and received by 02" in re.sub(r"\s+", " ", GLOSS)

    from dispatcher.core import CONFIDENCE
    for label in CONFIDENCE:
        assert f"`{label}`" in GLOSS, label
    assert "one of three" in GLOSS and len(CONFIDENCE) == 3

    import desk
    assert len(desk.QUEUE_TITLE) == 8       # the eight waiting lists the glossary names
    assert "an agent that broke a rule and was stopped" in re.sub(r"\s+", " ", GLOSS)

    import console
    assert os.path.basename(console.KEY_PATH) == "operator-key.bin" and "`operator-key.bin`" in GLOSS

    origin = text("dispatcher/CORE_ORIGIN.md")
    listed = [w for w in origin.split() if w.endswith(".py") and "/" not in w]
    assert len(listed) == 16 and "Sixteen files" in GLOSS
    assert all(os.path.exists(os.path.join(ROOT, "dispatcher", f)) for f in listed)

    req = text("requirements.txt")
    for pillar in ("before-turn", "open-mind", "agent-open-mind", "pre-response-selfcheck",
                   "sleep-marks"):
        pkg = pillar.replace("-", "_")
        assert os.path.isdir(os.path.join(ROOT, "dispatcher", "pillar_lib", pkg)), pillar
        assert pillar in GLOSS and f"{pillar} @ git+" not in req, pillar
    assert "splitvantage" not in req and "Five self-checks" in GLOSS

    handoff = text("dispatcher/handoff_guard.py")
    assert '"handoff.failed"' in handoff and "`handoff.failed`" in GLOSS
    tuple_line = ("(status change requested without signed listing.change.authorized, refuse; "
                  "verbal or email instruction is not authority)")
    assert tuple_line in text("05-mls-listing-management/DECISIONS.md")
    assert tuple_line[1:-1] in re.sub(r"\s+", " ", GLOSS)
    for path in ("config/authority_signers.json", "identity/routes.json"):
        assert os.path.exists(os.path.join(ROOT, path)) and f"`{path}`" in GLOSS, path
    assert "stream.log" in text("dispatcher/readable_logger.py")
    assert "`console-state/readable/stream.log`" in GLOSS


def test_the_desk_test_count_is_said_right_everywhere():
    n = len(re.findall(r"^## T\d+ ", text("docs/BROKER_DESK_TESTING_GUIDE.md"), re.M))
    words = {12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen", 16: "sixteen"}
    w = words[n]
    assert f"{w} tests to run" in text("README.md")
    assert f"{w} desk tests" in text("README.md")
    assert f"{w} tests, with what you" in text("QUICKSTART_WINDOWS.md")
    assert text("docs/BROKER_DESK_TESTING_GUIDE.md").splitlines()[4].startswith(w.capitalize()) or \
        f"{w.capitalize()} tests, in order" in text("docs/BROKER_DESK_TESTING_GUIDE.md")
