"""The Broker Desk's user's manual and testing guide stay true to the page
(added 2026-10-12). If a button, a queue title, a track step, a team state,
a command flag, a picture or an internal link named in
docs/BROKER_DESK_MANUAL.md or docs/BROKER_DESK_TESTING_GUIDE.md stops
existing, this fails and names it."""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)

import desk as desk_mod  # noqa: E402

MANUAL = os.path.join(ROOT, "docs", "BROKER_DESK_MANUAL.md")
GUIDE = os.path.join(ROOT, "docs", "BROKER_DESK_TESTING_GUIDE.md")
PAGE = open(os.path.join(ROOT, "tools", "desk.html"), encoding="utf-8").read()
DESK_PY = open(os.path.join(ROOT, "tools", "desk.py"), encoding="utf-8").read()


def text(p):
    return open(p, encoding="utf-8").read()


# every button or control the manual tells a broker to press
BUTTONS = ["Send", "Tap again to sign and send", "Don't send", "Sign: don't send",
           "Keep it held", "Continue", "Cancel", "Done", "Called",
           "Run today's checks", "Check the record", "Next", "play on its own",
           "Continue to which agent?"]


def test_every_button_the_manual_names_is_on_the_page():
    manual = re.sub(r"\s+", " ", text(MANUAL))     # a phrase may wrap across source lines
    for b in BUTTONS:
        assert f"**{b}**" in manual or f'"{b}"' in manual, f"manual no longer names {b!r}"
        assert b in PAGE, f"the manual names {b!r} but the page has no such control"


def test_queue_titles_in_the_manual_match_the_desk():
    manual = text(MANUAL)
    for title in desk_mod.QUEUE_TITLE.values():
        assert f"| {title} |" in manual, f"queue title {title!r} missing from the manual's table"


def test_track_steps_in_the_manual_match_the_desk():
    manual = text(MANUAL)
    for _, label in desk_mod.ReadModel.STEPS:
        assert f"| {label} |" in manual, f"track step {label!r} missing from the manual"


def test_team_states_in_the_manual_match_the_page():
    manual = text(MANUAL)
    words = re.search(r"const stateWord = \{(.*?)\};", PAGE).group(1)
    for w in re.findall(r':\s*"([^"]+)"', words):
        assert f"| {w.upper()} |" in manual, f"team state {w!r} missing from the manual"


def test_command_flags_exist():
    flags = set(re.findall(r'ap\.add_argument\("(--[a-z-]+)"', DESK_PY))
    for doc in (MANUAL, GUIDE):
        for f in set(re.findall(r"tools[/\\]desk\.py[^\n`]*", text(doc))):
            for flag in re.findall(r"(--[a-z-]+)", f):
                assert flag in flags, f"{os.path.basename(doc)} uses desk.py {flag}, which does not exist"


def test_pictures_exist():
    for doc in (MANUAL, GUIDE):
        for img in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text(doc)):
            assert os.path.isfile(os.path.join(os.path.dirname(doc), img)), \
                f"{os.path.basename(doc)} shows {img}, which is missing"


def slug(heading):
    s = heading.strip().lower()
    s = re.sub(r"[^\w\- ]", "", s)
    return s.replace(" ", "-")


def test_links_resolve():
    for doc in (MANUAL, GUIDE):
        body = text(doc)
        anchors = {slug(h) for h in re.findall(r"^#{1,6} (.+)$", body, re.M)}
        for target in re.findall(r"\]\(([^)]+)\)", body):
            if target.startswith("http"):
                continue
            path, _, frag = target.partition("#")
            if path:
                assert os.path.exists(os.path.join(os.path.dirname(doc), path)), \
                    f"{os.path.basename(doc)} links to {path}, which is missing"
            elif frag:
                assert frag in anchors, f"{os.path.basename(doc)} links to #{frag}, no such heading"
