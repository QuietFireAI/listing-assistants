"""Tests for the modules wired into the swarm on 2026-10-12 (owner: "these
items need to be addressed now"): the plain-language log, client drawers,
the JEV decision adapter in Agent 02, and the Hermes drafting path in Agent
04 with its checkpoint gate. Every test builds the swarm the way production
does (dispatcher/swarm.py)."""
import datetime
import json
import os

import pytest

from tests_listing.test_repairs_2026_10_11 import _swarm, _env, _signed, _persisted, _lead, RUBRIC


# ------------------------------------------------------------ readable log
def test_every_chain_event_a_broker_reads_lands_in_the_readable_log(tmp_path):
    sw, s = _swarm(tmp_path)
    sw.hub.send(_env("human", "05", "listing.change.authorized", "R1", {"field": "price", "value": 1}))
    sw.hub.send(_signed(s, "02", "R1", RUBRIC))
    stream = open(sw.readable.stream_path, encoding="utf-8").read()
    assert "Hub refused message" in stream and "unverified signature" in stream
    assert "You -> Agent 02: config.update" in stream
    # bookkeeping stays on the chain only
    kinds = {e["kind"] for e in sw.hub.audit.read()}
    assert "ack" in kinds and "[ACK]" not in stream
    assert sw.hub.audit.mirror_errors == []
    assert sw.hub.audit.verify_chain()["ok"]


def test_the_chain_bytes_are_unchanged_by_the_readable_view(tmp_path):
    from dispatcher.core import AuditLog
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "02", "R2", RUBRIC))
    plain = AuditLog(sw.hub.audit.path)
    assert plain.verify_chain()["ok"] and plain.read() == sw.hub.audit.read()


def test_a_failing_view_never_blocks_the_chain_and_is_counted(tmp_path):
    sw, s = _swarm(tmp_path)

    def boom(*a, **k):
        raise OSError("disk full")
    sw.readable.log_event = boom
    n = len(sw.hub.audit.read())
    sw.hub.send(_signed(s, "02", "R3", RUBRIC))
    assert len(sw.hub.audit.read()) > n and sw.hub.audit.verify_chain()["ok"]
    assert sw.hub.audit.mirror_errors and "disk full" in sw.hub.audit.mirror_errors[0]


def test_eod_ledger_is_built_from_the_chain_and_verifies_it(tmp_path):
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "02", "R4", RUBRIC))
    sw.hub.send(_lead("R4-lead"))
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    led = sw.write_eod(today)
    text = open(led["report_file"], encoding="utf-8").read()
    assert led["integrity"]["chain"]["ok"] and "verified" in text
    assert led["total_events"] > 0 and "`R4-lead`" in text
    # a second process the same day: the ledger still covers the first one's events
    sw2, _ = _swarm(tmp_path)   # same audit path ("a.jsonl")
    led2 = sw2.write_eod(today)
    assert led2["total_events"] >= led["total_events"]


# ------------------------------------------------------------ config re-sent
RULESET = {"ruleset": {"prohibited_phrases": [{"phrase": "perfect for young families",
                                                "rule_id": "FH-1"}], "state_rules": {}},
           "version": "r1"}


def test_same_config_sent_again_is_unchanged_not_unrecognized(tmp_path):
    """Scene 4 re-sends Scene 2's ruleset; it used to page 'matched no setting'."""
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "17", "c", RULESET))
    n_clar = len(sw.hub.queues["clarification.request"])
    sw.hub.send(_signed(s, "17", "c2", RULESET))
    assert len(sw.hub.queues["clarification.request"]) == n_clar
    kinds = [e["kind"] for e in sw.hub.audit.read()]
    assert "config.unchanged" in kinds and "config.unrecognized" not in kinds


def test_same_config_after_restart_is_still_unchanged(tmp_path):
    sw, s = _swarm(tmp_path, state=True)
    sw.hub.send(_signed(s, "17", "c", RULESET))
    sw.save_state()
    sw.close()
    from dispatcher.signatures import Ed25519Verifier
    from dispatcher.swarm import build_swarm
    sw2 = build_swarm(str(tmp_path / "a.jsonl"), state_db=str(tmp_path / "a.sqlite"),
                      verifier=Ed25519Verifier(s.public_key_bytes()).verifier())
    sw2.hub.send(_signed(s, "17", "c2", RULESET))
    assert not [q for q in sw2.hub.queues["clarification.request"] if q["client_context_id"] == "c2"]


def test_unknown_config_key_still_pages(tmp_path):
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "02", "c", {"rubirc": {}}))
    held = [q for q in sw.hub.queues["clarification.request"] if q["client_context_id"] == "c"]
    assert held and "changed nothing" in held[0]["payload"]["reason"]
