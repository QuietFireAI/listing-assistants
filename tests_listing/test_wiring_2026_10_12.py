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


# ------------------------------------------------------------ client drawers
def _drawer(sw, ctx):
    return sw.hub.drawers.get_drawer(ctx)


def _chain(sw, kind, ctx=None):
    return [e for e in sw.hub.audit.read() if e["kind"] == kind
            and (ctx is None or e.get("client_context_id") == ctx)]


def test_listing_package_provisions_the_drawer_with_its_address_and_is_filed(tmp_path):
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "05", "D1", {"new_listing": {"beds": 3, "price": 450000, "address": "12 Oak St",
                                                         "seller_name": "Dana Seller", "features": []}},
                        intent="listing.change.authorized"))
    m = _drawer(sw, "D1").get_manifest()
    assert m["property_address"] == "12 Oak St" and m["client_name"] == "Dana Seller"
    pkg = [f for f in m["file_index"].values() if f["filename"].startswith("listing_package_")]
    assert len(pkg) == 1 and pkg[0]["agent_id"] == "05"
    filed = _chain(sw, "drawer.filed", "D1")
    assert any(e["filename"] == pkg[0]["filename"] and e["sha256"] == pkg[0]["sha256"] for e in filed)
    assert _drawer(sw, "D1").verify_hashes()["ok"]


def test_documents_timeline_expenses_and_crm_entries_land_in_the_right_categories(tmp_path):
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "07", "D2", {"timeline_init": {"inspection": "2026-10-20"}, "today": "2026-10-12"}))
    sw.hub.send(_env("11", "08", "document.submission", "D2",
                     {"doc_type": "inspection_report", "opens_correctly": True, "content_hash": "h"}))
    sw.hub.send(_signed(s, "15", "D2", {"add_expense": {"amount": "120.00", "categories": ["staging"],
                                                       "tax_flags": ["deductible"], "receipt_on_file": True}}))
    cats = {f["category"] for f in _drawer(sw, "D2").list_files()}
    assert {"timeline", "documents", "financials", "interactions"} <= cats
    doc = [f for f in _drawer(sw, "D2").list_files("documents")][0]
    body = json.loads(_drawer(sw, "D2").get_file("documents", doc["filename"]))
    assert body["doc_type"] == "inspection_report" and body["received"]["content_hash"] == "h"
    # every CRM entry 14 appended has its own drawer file
    assert len(_drawer(sw, "D2").list_files("interactions")) == len(sw.spokes["14"].records["D2"])


def test_approved_description_is_filed_after_compliance_approves(tmp_path):
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "17", "D3", {"ruleset": {"prohibited_phrases": [], "state_rules": {}},
                                       "version": "r1"}))
    sw.hub.send(_env("05", "04", "listing.data", "D3", {"beds": 2, "baths": 1, "features": ["porch"],
                                                        "photo_detected_features": ["porch"],
                                                        "today": "2026-10-12"}))
    arts = [f["filename"] for f in _drawer(sw, "D3").list_files("artifacts")]
    assert any(a.startswith("description_") for a in arts)


def test_a_different_identity_later_is_kept_out_and_held(tmp_path):
    sw, s = _swarm(tmp_path)
    for addr, eid_ctx in (("12 Oak St", "D4"), ("99 Elm St", "D4")):
        sw.hub.send(_signed(s, "05", eid_ctx, {"new_listing": {"beds": 3, "address": addr, "features": []}},
                            intent="listing.change.authorized"))
    assert _drawer(sw, "D4").get_manifest()["property_address"] == "12 Oak St"
    assert _chain(sw, "drawer.identity_conflict", "D4")
    assert any("identity conflict" in q["payload"].get("reason", "")
               for q in sw.hub.queues["clarification.request"] if q["client_context_id"] == "D4")


def test_an_unsafe_client_id_is_refused_on_the_record_and_held(tmp_path):
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "07", "../escape", {"timeline_init": {"inspection": "2026-10-20"}}))
    assert not os.path.exists(tmp_path / "escape")
    refused = _chain(sw, "drawer.refused", "../escape")
    assert refused and "ComminglingBreachError" in refused[0]["reason"]
    assert any(q["payload"].get("reason") == "client drawer filing refused"
               for q in sw.hub.queues["clarification.request"])
    assert sw.hub.audit.verify_chain()["ok"]


def test_a_held_thread_is_recorded_in_the_drawer_and_shows_as_action_required(tmp_path):
    from tools.dashboard import load_all_clients
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "02", "r", RUBRIC))
    sw.hub.send(_lead("H1", phone="555-0101"))
    sw.hub.send(_lead("H1-again", phone="555 0101"))
    assert sw.hitl.get_pending_waits("H1-again")
    clients = {c["client_id"]: c for c in load_all_clients(str(tmp_path / "drawers"))}
    assert clients["H1-again"]["stage_name"] == "ACTION REQUIRED"


def test_drawer_files_survive_and_are_not_rewritten_across_processes(tmp_path):
    sw, s = _swarm(tmp_path)   # no state store: 14's entry counter restarts in a new process
    sw.hub.send(_signed(s, "07", "D5", {"timeline_init": {"inspection": "2026-10-20"}}))
    first = {k: v["sha256"] for k, v in _drawer(sw, "D5").get_manifest()["file_index"].items()}
    sw2, s2 = _swarm(tmp_path)
    sw2.hub.send(_signed(s2, "07", "D5", {"timeline_init": {"appraisal": "2026-10-25"}}))
    after = {k: v["sha256"] for k, v in _drawer(sw2, "D5").get_manifest()["file_index"].items()}
    assert all(after[k] == v for k, v in first.items()) and len(after) > len(first)
