"""The review agent (owner decisions 2026-10-26): an observer outside the
group. When an agent is stopped it builds the case for a person from the
record and the attested install; it reads, it reports, it never acts."""
import json
import os
import sys
import time

import pytest

if os.name == "nt":
    pytest.skip("the review agent runs beside the agents' portals (Linux)", allow_module_level=True)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests_isolation"))

from dispatcher import review_agent  # noqa: E402
from dispatcher.boot_attest import current_manifest  # noqa: E402
from test_portal import MENTION, _env, _swarm  # noqa: E402


def _wait_for_case(folder, prefix, seconds=20):
    end = time.time() + seconds
    while time.time() < end:
        done = [f for f in os.listdir(folder) if f.startswith(prefix) and f.endswith(".json")] \
            if os.path.isdir(folder) else []
        if done:
            return json.load(open(os.path.join(folder, done[0]))), \
                open(os.path.join(folder, done[0][:-5] + ".md")).read()
        time.sleep(0.2)
    raise AssertionError(f"no case file {prefix}* in {folder}")


def test_a_stop_gets_a_case_file_built_from_the_record(tmp_path):
    def act(peer, env):
        peer.call("send", {"envelope": _env("13", "02", "lead.captured", "X", {})})
    sw = _swarm(str(tmp_path), rogue=("20", act))
    try:
        sw.hub.send(_env("external", "20", "social.mention", "M-1", MENTION))
        [stop] = [e for e in sw.hub.audit.read() if e["kind"] == "portal.agent_stopped"]
        case, text = _wait_for_case(str(tmp_path / "reviews"), stop["code"])
    finally:
        sw.close()
    assert case["code"] == stop["code"] and case["agent"] == "20"
    assert case["violation"] == "impersonation"
    assert case["was_handling"]["intent"] == "social.mention"
    assert case["was_handling"]["client_context_id"] == "M-1"
    assert case["tried"] == {"intent": "lead.captured", "from_agent": "13", "to_agent": "02",
                             "envelope_id": case["tried"]["envelope_id"]}
    assert case["tried_is_on_track"] is False and case["tried_route_used_before"] == 0
    assert {"intent": "social.mention", "to": ["20"]} not in case["allowed_routes"]
    assert any(r["intent"] for r in case["allowed_routes"])
    assert case["code_check"]["checked"] is False          # this test install was not attested
    assert "first reading for a person, not a verdict" in text
    assert f"# Case {stop['code']}: agent 20 stopped" in text
    # the review agent wrote nothing on the record
    assert not [e for e in sw.hub.audit.read() if "review" in e["kind"]]


def test_the_code_check_names_a_changed_agent_file(tmp_path):
    state = str(tmp_path)
    manifest = current_manifest()
    json.dump({"manifest": manifest}, open(os.path.join(state, "boot-attestation.json"), "w"))
    ok = review_agent.code_check(state, "05")
    assert ok["checked"] and ok["ok"] and "dispatcher/listing_spokes_05.py" in ok["match"]
    manifest["dispatcher/listing_spokes_05.py"] = "0" * 64
    json.dump({"manifest": manifest}, open(os.path.join(state, "boot-attestation.json"), "w"))
    bad = review_agent.code_check(state, "05")
    assert not bad["ok"] and bad["differ"] == ["dispatcher/listing_spokes_05.py"]
    reading = review_agent.first_reading({"code_check": bad, "violation": "route_not_on_track",
                                          "tried_route_used_before": 0})
    assert reading[0].startswith("The agent's files differ from the attested install")


def test_one_case_file_per_stop_and_never_rewritten(tmp_path):
    def act(peer, env):
        peer.call("send", {"envelope": _env("20", "02", "lead.captured", "X", {})})
    sw = _swarm(str(tmp_path), rogue=("20", act))
    try:
        sw.hub.send(_env("external", "20", "social.mention", "M-1", MENTION))
        [stop] = [e for e in sw.hub.audit.read() if e["kind"] == "portal.agent_stopped"]
        _wait_for_case(str(tmp_path / "reviews"), stop["code"])
    finally:
        sw.close()
    out = str(tmp_path / "reviews")
    first = open(os.path.join(out, stop["code"] + ".md")).read()
    assert review_agent.review(str(tmp_path), out) == []      # already written: left as it is
    assert open(os.path.join(out, stop["code"] + ".md")).read() == first
    case = json.load(open(os.path.join(out, stop["code"] + ".json")))
    assert case["violation"] == "route_not_on_track" and "never used before" in first
