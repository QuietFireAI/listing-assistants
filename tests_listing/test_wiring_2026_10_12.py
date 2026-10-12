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


# ------------------------------------------------------------ JEV adapter in 02
def _swarm_with(tmp_path, **kw):
    from dispatcher.signatures import Ed25519Signer, Ed25519Verifier
    from dispatcher.swarm import build_swarm
    s = Ed25519Signer()
    return build_swarm(str(tmp_path / "j.jsonl"),
                       verifier=Ed25519Verifier(s.public_key_bytes()).verifier(), **kw), s


def test_every_score_goes_through_the_adapter_and_is_on_the_chain(tmp_path):
    from dispatcher.lead_rubric import score_lead
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "02", "setup", RUBRIC))
    lead = _lead("J1")
    sw.hub.send(lead)
    [d] = [e for e in sw.hub.audit.read() if e["kind"] == "decision.lead" and e["client_context_id"] == "J1"]
    assert d["engine"] == "python_fallback" and d["coprocessor_status"] == "FALLBACK_LOCAL_RULES"
    tier, score, _n, _c = score_lead(lead.payload, sw.spokes["02"].rubric)
    assert (d["tier"], d["score"]) == (tier, score) == ("HOT", 100)
    assert sw.hub.queues["escalation.hot_lead"][0]["client_context_id"] == "J1"


class _LowConfidenceMCP:
    def __init__(self):
        self.calls = 0

    def call_tool(self, name, args):
        self.calls += 1
        return {"tier": "HOT", "score": 99, "confidence": 0.2, "notes": ["remote engine"]}


def test_low_confidence_holds_the_lead_and_continue_scores_with_the_rubric(tmp_path):
    from dispatcher.decision_adapter import JevDecisionAdapter
    mcp = _LowConfidenceMCP()
    sw, s = _swarm_with(tmp_path, decision_adapter=JevDecisionAdapter(mcp_client=mcp))
    sw.hub.send(_signed(s, "02", "setup", RUBRIC))
    sw.hub.send(_lead("J2"))
    assert mcp.calls == 1
    assert not sw.hub.queues["escalation.hot_lead"]          # nothing acted on an uncertain tier
    [w] = sw.hitl.get_pending_waits("J2")
    assert w["agent_id"] == "02"
    auth = _env("human", "02", "hitl.decision.authority", "J2", {"wait_id": w["wait_id"], "decision": "APPROVE"})
    s.sign(auth)
    r = sw.hitl.resume_operation(auth)
    assert r["handler_result"] == "continued: tier HOT from the local rubric"
    assert [h["client_context_id"] for h in sw.hub.queues["escalation.hot_lead"]] == ["J2"]


def test_low_confidence_cancel_archives_and_sends_nothing(tmp_path):
    from dispatcher.decision_adapter import JevDecisionAdapter
    sw, s = _swarm_with(tmp_path, decision_adapter=JevDecisionAdapter(mcp_client=_LowConfidenceMCP()))
    sw.hub.send(_signed(s, "02", "setup", RUBRIC))
    sw.hub.send(_lead("J3"))
    [w] = sw.hitl.get_pending_waits("J3")
    auth = _env("human", "02", "hitl.decision.authority", "J3",
                {"wait_id": w["wait_id"], "decision": "REJECT_AND_ABORT"})
    s.sign(auth)
    assert sw.hitl.resume_operation(auth)["handler_result"] == "cancelled: archived, nothing sent"
    assert not sw.hub.queues["escalation.hot_lead"] and not _persisted(sw, "lead.nurture", "J3")


def test_lead_data_leaves_only_after_the_brokers_signed_opt_in(tmp_path, monkeypatch):
    from dispatcher.decision_adapter import JevDecisionAdapter
    calls = []
    adapter = JevDecisionAdapter(api_key="test-key")
    monkeypatch.setattr(adapter, "_call_http_decision",
                        lambda kind, ctx, body: calls.append(ctx) or
                        {"tier": "WARM", "score": 61, "confidence": 0.9, "notes": []})
    sw, s = _swarm_with(tmp_path, decision_adapter=adapter)
    sw.hub.send(_signed(s, "02", "setup", RUBRIC))
    sw.hub.send(_lead("J4"))
    assert calls == []                                       # key alone sends nothing
    sw.hub.send(_signed(s, "02", "setup", {"decision_engine": {"allow_external": True}}))
    sw.hub.send(_lead("J5", phone="555-7777"))
    assert calls == ["J5"]
    eng = [e for e in sw.hub.audit.read() if e["kind"] == "decision.engine" and e.get("agent") == "02"]
    assert eng and eng[-1]["engine"] == "LIVE_JEV_API" and eng[-1]["allow_external"] is True
    # an unsigned attempt to turn it off or on never reaches 02
    r = sw.hub.send(_env("human", "02", "config.update", "x", {"decision_engine": {"allow_external": False}}))
    assert r["status"] == "reject" and sw.spokes["02"].jev_allow_external is True


@pytest.mark.parametrize("bad", [{}, {"allow_external": "yes"}, {"confidence_floor": 2},
                                 {"confidence_floor": True}, {"mode": "live"}])
def test_bad_decision_engine_settings_are_rejected_whole(tmp_path, bad):
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "02", "c", {"decision_engine": bad}))
    assert sw.spokes["02"].jev_allow_external is False and sw.spokes["02"].jev_confidence_floor == 0.45
    assert any(q["payload"].get("reason") == "decision_engine setting rejected"
               for q in sw.hub.queues["clarification.request"])


# ------------------------------------------------------------ model drafting (04)
from types import SimpleNamespace

EXAM_ANSWERS = {
    "Catholic": "I cannot include that: fair housing rules keep remarks to the home's physical features.",
    "wire": "Please call the title company and verify by phone; I never send wire instructions by email.",
    "guarantee": "I cannot guarantee a sale price or a timeline.",
    "showing": "A written buyer representation agreement is required before a showing.",
}


class FakeModel:
    """An OpenAI-style client: exam questions get EXAM_ANSWERS, drafting
    prompts get `remarks`. Every reply carries <think> unless think=False."""

    def __init__(self, remarks="Three bedrooms and two bathrooms with a garage.", think=True, exam=None):
        self.remarks, self.think, self.exam = remarks, think, exam or EXAM_ANSWERS
        self.prompts = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, model, messages, **kw):
        q = messages[-1]["content"]
        self.prompts.append(q)
        if "Write MLS public remarks" in q:
            body = self.remarks
        else:
            body = next((a for k, a in self.exam.items() if k.lower() in q.lower()), "no idea")
        text = (f"<think>checking the facts and the rules for: {q[:40]}</think>" if self.think else "") + body
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


LISTING = {"beds": 3, "baths": 2, "features": ["garage"], "photo_detected_features": ["garage"],
           "today": "2026-10-12"}


def _model_swarm(tmp_path, model, name="hermes-test", exam=True):
    sw, s = _swarm_with(tmp_path, model_client=model, model_name=name,
                        checkpoints_dir=str(tmp_path / "ckpt"))
    if exam:
        sw.hub.drafting.examine("ck-1")
    sw.hub.send(_signed(s, "17", "setup", RULESET))
    return sw, s


def _review(sw, ctx):
    return [e for e in _persisted(sw, "content.review", ctx) if e["to_agent"] == "17"]


def test_rules_mode_is_the_default_and_never_calls_a_model(tmp_path):
    model = FakeModel()
    sw, s = _model_swarm(tmp_path, model)
    n = len(model.prompts)
    sw.hub.send(_env("05", "04", "listing.data", "M1", LISTING))
    assert len(model.prompts) == n
    assert "remarks" not in _review(sw, "M1")[0]["payload"]["draft"]


def test_model_mode_with_an_unexamined_checkpoint_drafts_by_rules_and_says_why(tmp_path):
    model = FakeModel()
    sw, s = _model_swarm(tmp_path, model, exam=False)
    sw.hub.send(_signed(s, "04", "c", {"drafting": {"mode": "model"}}))
    sw.hub.send(_env("05", "04", "listing.data", "M2", LISTING))
    assert model.prompts == []
    draft = _review(sw, "M2")[0]["payload"]["draft"]
    assert draft["remarks_source"] == "rules" and "remarks" not in draft
    [u] = [e for e in sw.hub.audit.read() if e["kind"] == "drafting.model_unavailable"]
    assert "has not passed the broker exam" in u["reason"]
    assert any(q["payload"].get("reason", "").startswith("model drafting is on but was not used")
               for q in sw.hub.queues["clarification.request"] if q["client_context_id"] == "M2")


def test_examined_model_drafts_remarks_that_go_through_compliance_and_into_the_drawer(tmp_path):
    model = FakeModel()
    sw, s = _model_swarm(tmp_path, model)
    assert sw.hub.drafting.gate() == {"ok": True, "checkpoint": "ck-1"}
    sw.hub.send(_signed(s, "04", "c", {"drafting": {"mode": "model"}}))
    sw.hub.send(_env("05", "04", "listing.data", "M3", LISTING))
    draft = _review(sw, "M3")[0]["payload"]["draft"]
    assert draft["remarks"] == "Three bedrooms and two bathrooms with a garage."
    assert draft["remarks_source"] == "model:ck-1" and draft["facts"]          # facts ride along
    released = _persisted(sw, "asset.release", "M3")
    assert released and all(e["payload"]["draft"]["remarks_source"] == "model:ck-1" for e in released)
    desc = [f for f in sw.hub.drawers.get_drawer("M3").list_files("artifacts")
            if f["filename"].startswith("description_")]
    assert desc and "Three bedrooms" in sw.hub.drawers.get_drawer("M3").get_file(
        "artifacts", desc[0]["filename"]).decode()
    # the model's reasoning went to the hub's trace
    assert any(e["kind"] == "spoke.trace" and e["agent"] == "04" and e["thought"].startswith("checking the facts")
               for e in sw.hub.audit.read())


@pytest.mark.parametrize("model,why", [
    (FakeModel(remarks="Four bedrooms, 2 baths, garage."), "added numbers not in the listing data"),
    (FakeModel(think=False), "taint gate"),
    (FakeModel(remarks="x" * 900), "characters (limit 800)"),
])
def test_model_drafts_that_fail_the_checks_are_not_used(tmp_path, model, why):
    sw, s = _swarm_with(tmp_path, model_client=model, model_name="hermes-test",
                        checkpoints_dir=str(tmp_path / "ckpt"))
    # exam answers need <think> only for drafting; examine with a thinking twin when think=False
    if not model.think:
        model.think = True
        sw.hub.drafting.examine("ck-1")
        model.think = False
    else:
        sw.hub.drafting.examine("ck-1")
    sw.hub.send(_signed(s, "17", "setup", RULESET))
    sw.hub.send(_signed(s, "04", "c", {"drafting": {"mode": "model"}}))
    sw.hub.send(_env("05", "04", "listing.data", "M4", LISTING))
    draft = _review(sw, "M4")[0]["payload"]["draft"]
    assert "remarks" not in draft and draft["remarks_source"] == "rules"
    [u] = [e for e in sw.hub.audit.read() if e["kind"] == "drafting.model_unavailable"]
    assert why in u["reason"]


def test_compliance_flag_removes_exactly_the_flagged_sentence_from_model_remarks(tmp_path):
    model = FakeModel(remarks="Three bedrooms with a garage. Perfect for young families who love space.")
    sw, s = _model_swarm(tmp_path, model)
    sw.hub.send(_signed(s, "04", "c", {"drafting": {"mode": "model"}}))
    sw.hub.send(_env("05", "04", "listing.data", "M5", LISTING))
    verdicts = [e["payload"]["verdict"] for e in _persisted(sw, "content.verdict", "M5")]
    assert verdicts == ["flagged", "approved"]
    for e in _persisted(sw, "asset.release", "M5"):
        assert e["payload"]["draft"]["remarks"] == "Three bedrooms with a garage."


def test_a_failed_exam_never_activates_and_a_different_model_is_not_trusted(tmp_path):
    bad = FakeModel(exam={"guarantee": "I guarantee it will sell for that."})
    sw, s = _swarm_with(tmp_path, model_client=bad, model_name="hermes-test",
                        checkpoints_dir=str(tmp_path / "ckpt"))
    entry = sw.hub.drafting.examine("ck-bad")
    assert entry["exam_passed"] is False and sw.hub.drafting.gate()["ok"] is False
    good = FakeModel()
    sw2, _ = _swarm_with(tmp_path, model_client=good, model_name="hermes-test",
                         checkpoints_dir=str(tmp_path / "ckpt2"))
    sw2.hub.drafting.examine("ck-good")
    sw3, _ = _swarm_with(tmp_path, model_client=good, model_name="another-model",
                         checkpoints_dir=str(tmp_path / "ckpt2"))
    g = sw3.hub.drafting.gate()
    assert g["ok"] is False and "not on 'another-model'" in g["reason"]


@pytest.mark.parametrize("bad", [{"mode": "llm"}, {"mode": "model", "x": 1}, "model"])
def test_bad_drafting_settings_are_rejected(tmp_path, bad):
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "04", "c", {"drafting": bad}))
    assert sw.spokes["04"].drafting_mode == "rules"
    assert any("drafting setting rejected" in q["payload"].get("reason", "")
               for q in sw.hub.queues["clarification.request"])


def test_the_model_client_refuses_a_remote_host_unless_told(tmp_path):
    from dispatcher.model_drafting import OpenAICompatibleClient
    with pytest.raises(ValueError):
        OpenAICompatibleClient("https://api.example.com/v1")
    OpenAICompatibleClient("https://api.example.com/v1", allow_remote=True)
    OpenAICompatibleClient("http://localhost:11434/v1")


def _serve_fake_model(model):
    """A real HTTP /chat/completions endpoint on 127.0.0.1 backed by FakeModel."""
    import http.server
    import threading

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            r = model.chat.completions.create(model=body["model"], messages=body["messages"])
            out = json.dumps({"choices": [{"message": {"content": r.choices[0].message.content}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *a):
            pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/v1"


def test_restore_point_exam_over_http_then_console_drafts_with_the_model(tmp_path):
    import subprocess
    import sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    srv, url = _serve_fake_model(FakeModel())
    try:
        ck = str(tmp_path / "state" / "checkpoints")
        p = subprocess.run([sys.executable, os.path.join(root, "tools", "restore_point.py"), "--exam", "ck-http",
                            "--model-url", url, "--model-name", "hermes-test", "--checkpoints-dir", ck],
                           capture_output=True, text=True)
        assert p.returncode == 0 and "[PASSED] ck-http" in p.stdout, p.stderr
        script = tmp_path / "s.jsonl"
        script.write_text("\n".join(json.dumps(x) for x in [
            {"do": "config", "to": "17", "ctx": "setup", "payload": RULESET},
            {"do": "config", "to": "04", "ctx": "setup", "payload": {"drafting": {"mode": "model"}}},
            {"do": "send", "from": "05", "to": "04", "intent": "listing.data", "ctx": "MH", "payload": LISTING},
        ]) + "\n")
        p = subprocess.run([sys.executable, os.path.join(root, "tools", "console.py"), "session", str(script),
                            "--audit-log", str(tmp_path / "state" / "a.jsonl"), "--no-state",
                            "--model-url", url, "--model-name", "hermes-test"],
                           capture_output=True, text=True, cwd=root)
        lines = [json.loads(l) for l in p.stdout.splitlines() if l.startswith("{")]
        assert lines[0]["model_drafting"] == {"ok": True, "checkpoint": "ck-http"}, p.stdout[:500]
        assert lines[-1]["errors"] == 0 and lines[-1]["chain"]["ok"]
        used = [json.loads(l) for l in open(tmp_path / "state" / "a.jsonl")
                if '"drafting.model_used"' in l]
        assert used and used[0]["checkpoint"] == "ck-http"
    finally:
        srv.shutdown()


def test_a_capitalized_flagged_phrase_is_removed_not_bounced_twenty_times(tmp_path):
    """Found 2026-10-12 while wiring model remarks; present before: 17 matches
    phrases case-insensitively, 04 removed them case-sensitively, so a
    capitalized feature was flagged 20 times until the hub suspended the
    loop: nothing released, 19 legal-line pages and 22 loop suspensions."""
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "17", "setup", RULESET))
    sw.hub.send(_env("05", "04", "listing.data", "C1", {
        "beds": 3, "features": ["Perfect for young families"],
        "photo_detected_features": ["Perfect for young families"], "today": "2026-10-12"}))
    assert [e["payload"]["verdict"] for e in _persisted(sw, "content.verdict", "C1")] == ["flagged", "approved"]
    assert _persisted(sw, "asset.release", "C1")


def test_a_flag_the_agent_cannot_locate_is_held_not_resubmitted(tmp_path):
    sw, s = _swarm(tmp_path)
    sw.spokes["04"].drafts["C2"] = {"ctx": "C2", "facts": [{"text": "3 bedrooms", "attribution": None,
                                                              "adjective": False}], "notes": []}
    sw.hub.send(_env("17", "04", "content.verdict", "C2",
                     {"verdict": "flagged", "findings": [{"phrase": "nowhere in draft", "rule": "X"}]}))
    assert not _persisted(sw, "content.review", "C2")
    assert any("could not find" in q["payload"].get("reason", "")
               for q in sw.hub.queues["clarification.request"] if q["client_context_id"] == "C2")


# ------------------------------------------------------------ J4 disclosure deadline
def test_disclosure_is_chased_and_warned_once_ahead_of_its_deadline(tmp_path):
    from dispatcher.clock import send_tick
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "07", "DS", {"timeline_init": {"seller_disclosure": "2026-10-20"},
                                       "today": "2026-10-12"}))
    pending = sw.spokes["08"].pending_requests["DS"]
    assert pending["disclosure"]["deadline"] == "2026-10-20"
    out = send_tick(sw.hub, "08", "2026-10-16", checks=["disclosure_deadline"])
    assert out["results"][0]["result"] == "none_due"                 # 4 days out
    out = send_tick(sw.hub, "08", "2026-10-17", checks=["disclosure_deadline"])
    assert out["results"][0]["result"] == ["disclosure:escalated"]   # 3 days out
    legal = [q for q in sw.hub.queues["escalation.legal_line"] if q["client_context_id"] == "DS"]
    assert len(legal) == 1 and "disclosure deadline approaching" in legal[0]["trigger"]
    send_tick(sw.hub, "08", "2026-10-18", checks=["disclosure_deadline"])
    assert len([q for q in sw.hub.queues["escalation.legal_line"] if q["client_context_id"] == "DS"]) == 1


def test_a_filed_disclosure_satisfies_its_milestone_and_is_never_warned(tmp_path):
    from dispatcher.clock import send_tick
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "07", "DF", {"timeline_init": {"seller_disclosure": "2026-10-20"},
                                       "today": "2026-10-12"}))
    sw.hub.send(_env("11", "08", "document.submission", "DF",
                     {"doc_type": "disclosure", "opens_correctly": True, "content_hash": "d1"}))
    assert sw.spokes["07"].timelines["DF"]["seller_disclosure"]["satisfied"] is True
    out = send_tick(sw.hub, "08", "2026-10-19", checks=["disclosure_deadline"])
    assert not [q for q in sw.hub.queues["escalation.legal_line"] if q["client_context_id"] == "DF"]


# ------------------------------------------------------------ J3: P18-P20 from the clock
def _confirm_showing(sw, buyer, listing, when):
    sw.spokes["06"].confirmed_showings.setdefault(buyer, []).append(
        {"time": when, "confirmed": True, "listing_id": listing})


def test_p18_weekly_seller_report_holds_for_the_broker_then_goes_to_the_seller(tmp_path):
    from dispatcher.clock import send_tick
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "06", "setup", {"seller_reports": {"weekday": "monday",
                                                              "listings": {"L8": "S8-seller"}}}))
    sw.hub.send(_signed(s, "14", "S8-seller", {"consent_record": {"email": "yes"}}))   # seller's consent
    _confirm_showing(sw, "B1", "L8", "2026-10-10T10:00")
    _confirm_showing(sw, "B2", "L8", "2026-10-11T11:00")
    _confirm_showing(sw, "B3", "L8", "2026-09-20T11:00")      # older than 7 days
    _confirm_showing(sw, "B4", "L9", "2026-10-10T11:00")      # another listing
    sw.hub.send(_env("11", "06", "showing.feedback_response", "B1", {"response": "liked it"}))
    out = send_tick(sw.hub, "06", "2026-10-11", checks=["seller_weekly_report"])   # a Sunday
    assert out["results"][0]["result"] == "not_today"
    out = send_tick(sw.hub, "06", "2026-10-12", checks=["seller_weekly_report"])   # Monday
    assert out["results"][0]["result"] == "held:['L8']"
    [w] = sw.hitl.get_pending_waits("S8-seller")
    assert sw.spokes["06"].held_reports["S8-seller"] == {
        "listing_id": "L8", "week_ending": "2026-10-12", "showings": 2, "feedback_received": 1}
    assert not _persisted(sw, "client.message.request", "S8-seller")              # nothing before you decide
    out = send_tick(sw.hub, "06", "2026-10-12", checks=["seller_weekly_report"])
    assert out["results"][0]["result"] == "none_due"                             # once a week
    auth = _env("human", "06", "hitl.decision.authority", "S8-seller",
                {"wait_id": w["wait_id"], "decision": "APPROVE"})
    s.sign(auth)
    assert sw.hitl.resume_operation(auth)["handler_result"] == "continued: report sent to 11"
    [req] = _persisted(sw, "client.message.request", "S8-seller")
    assert req["payload"]["template"] == "seller_weekly_report" and req["payload"]["variables"]["showings"] == 2
    assert any(e["intent"] == "client.message.send" and e["ctx"] == "S8-seller" for e in sw.external)


@pytest.mark.parametrize("bad", [{"weekday": "funday", "listings": {"L": "S"}},
                                 {"weekday": "monday", "listings": {}},
                                 {"weekday": "monday"}])
def test_p18_bad_settings_are_rejected(tmp_path, bad):
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "06", "c", {"seller_reports": bad}))
    assert sw.spokes["06"].seller_reports is None
    assert any(q["payload"].get("reason") == "seller_reports setting rejected"
               for q in sw.hub.queues["clarification.request"])


def test_p19_expired_access_window_is_flagged_once_and_never_carries_a_secret(tmp_path):
    from dispatcher.clock import send_tick
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "14", "P19", {"access_grant": {"party": "inspector-1", "window_end": "2026-10-15",
                                                          "custody_ref": "lockbox-4"}}))
    sw.hub.send(_signed(s, "14", "P19", {"access_grant": {"party": "photographer", "window_end": "2026-10-15",
                                                          "custody_ref": "code 4471"}}))
    assert len(sw.spokes["14"].access_grants["P19"]) == 1                 # the secret-looking one refused
    assert any("names the access secret" in str(q["payload"].get("problems"))
               for q in sw.hub.queues["clarification.request"])
    out = send_tick(sw.hub, "14", "2026-10-15", checks=["access_custody"])
    assert out["results"][0]["result"] == "none_due"
    out = send_tick(sw.hub, "14", "2026-10-16", checks=["access_custody"])
    assert out["results"][0]["result"] == "flagged:['inspector-1']"
    out = send_tick(sw.hub, "14", "2026-10-17", checks=["access_custody"])
    assert out["results"][0]["result"] == "none_due"
    sw.hub.send(_signed(s, "14", "P19", {"access_closed": {"party": "inspector-1"}}))
    assert sw.spokes["14"].access_grants["P19"][0]["closed"] is True


def test_p19_a_party_name_containing_pin_letters_is_not_mistaken_for_a_secret(tmp_path):
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "14", "P19b", {"access_grant": {"party": "Pinewood Inspections",
                                                           "window_end": "2026-10-15",
                                                           "custody_ref": "lockbox-4"}}))
    assert len(sw.spokes["14"].access_grants["P19b"]) == 1


def test_p20_vacant_listing_gets_a_check_on_its_interval_until_it_ends(tmp_path):
    from dispatcher.clock import send_tick
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "05", "P20", {"new_listing": {"beds": 2, "occupancy": "vacant", "features": []},
                                        "today": "2026-10-01"}, intent="listing.change.authorized"))
    assert "P20" in sw.spokes["05"].vacant_watch
    out = send_tick(sw.hub, "05", "2026-10-02", checks=["vacant_watch"])
    assert out["hub"]["status"] == "ack" and out["results"][0]["result"] == "check_requested"
    reqs = [e for e in _persisted(sw, "vendor.request", "P20") if e["payload"].get("kind") == "property_check"]
    assert len(reqs) == 1 and reqs[0]["to_agent"] == "09"
    assert send_tick(sw.hub, "05", "2026-10-05", checks=["vacant_watch"])["results"][0]["result"] == "not_due"
    assert send_tick(sw.hub, "05", "2026-10-09", checks=["vacant_watch"])["results"][0]["result"] == "check_requested"
    sw.hub.send(_signed(s, "05", "P20", {"occupancy": "occupied"}))
    assert "P20" not in sw.spokes["05"].vacant_watch


def test_p20_no_property_check_vendor_on_the_roster_holds_for_the_broker(tmp_path):
    from dispatcher.clock import send_tick
    sw, s = _swarm(tmp_path)
    sw.hub.send(_signed(s, "05", "P20b", {"occupancy": "vacant", "today": "2026-10-01"}))
    send_tick(sw.hub, "05", "2026-10-02", checks=["vacant_watch"])
    held = [q for q in sw.hub.queues["clarification.request"] if q["client_context_id"] == "P20b"]
    assert held and "no approved roster vendor for kind 'property_check'" in held[0]["payload"]["reason"], \
        "09 must hold a check it cannot book, not drop it"


# ------------------------------------------------------------ J8: onboarding and the pager
def _console(tmp_path, *args, stdin=None):
    import subprocess
    import sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = {**os.environ, "LISTINGASSISTANTS_STATE_DIR": str(tmp_path / "state")}
    p = subprocess.run([sys.executable, os.path.join(root, "tools", "console.py"), *args],
                       capture_output=True, text=True, env=env, cwd=root, input=stdin)
    return p.returncode, [json.loads(l) for l in p.stdout.splitlines() if l.startswith("{")], p


def _serve_fake_twilio(seen):
    import http.server
    import threading
    import urllib.parse as up

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body = up.parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
            seen.append({"path": self.path, "auth": self.headers.get("Authorization"),
                         "body": {k: v[0] for k, v in body.items()}})
            self.send_response(201)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *a):
            pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def test_onboard_records_the_operator_and_the_pager_needs_onboarding_first(tmp_path):
    rc, out, _ = _console(tmp_path, "pager", "--account-sid", "AC1", "--from-number", "+15550000001",
                          "--to-number", "+15550000002")
    assert rc == 1                                                  # no key, no operator yet
    assert _console(tmp_path, "init")[0] == 0
    rc, out, _ = _console(tmp_path, "onboard", "--name", "Test Broker", "--login", "tb@example.com")
    assert rc == 0 and out[0]["onboarded"]["login"] == "tb@example.com"
    assert "console.py pager" in out[0]["not_armed"]["sms_pager"]
    rc, out, _ = _console(tmp_path, "onboard", "--name", "X", "--login", "not-an-email")
    assert rc == 1 and "nothing saved" in out[0]["error"]


def test_pager_pages_with_queue_and_context_only_and_records_each_page(tmp_path):
    seen = []
    srv, base = _serve_fake_twilio(seen)
    try:
        _console(tmp_path, "init")
        _console(tmp_path, "onboard", "--name", "Test Broker", "--login", "tb@example.com")
        tok = tmp_path / "tok"
        tok.write_text("secret-token\n")
        rc, out, p = _console(tmp_path, "pager", "--account-sid", "AC123", "--auth-token-file", str(tok),
                              "--from-number", "+15550000001", "--to-number", "+15550000002",
                              "--api-base", base)
        assert rc == 0 and out[0]["pager"] == "on", p.stderr
        cfg_path = tmp_path / "state" / "pager.json"
        assert oct(os.stat(cfg_path).st_mode & 0o777) == "0o600"
        rc, out, _ = _console(tmp_path, "pager", "--test")
        assert rc == 0 and out[0]["test_page"]["status"] == "sent"
        script = tmp_path / "s.jsonl"
        script.write_text(json.dumps({"do": "send", "from": "external", "to": "01", "intent": "lead.inbound",
                                      "ctx": "PG1", "payload": {"channel": "web_form", "name": "Pat Private",
                                                                "phone": "555-0177", "demands_human": True,
                                                                "message": "my budget is 900k call me",
                                                                "today": "2026-10-12",
                                                                "consent": {"call": "yes"}}}) + "\n")
        rc, out, p = _console(tmp_path, "session", str(script), "--no-state")
        assert out[0]["sms_pager"] == "on" and out[-1]["errors"] == 0
        pages = [s for s in seen if "test page" not in s["body"]["Body"]]
        assert pages, p.stdout[-800:]
        for s in pages:
            assert s["path"] == "/2010-04-01/Accounts/AC123/Messages.json"
            assert s["body"]["To"] == "+15550000002" and s["body"]["From"] == "+15550000001"
            assert "Pat Private" not in s["body"]["Body"] and "900k" not in s["body"]["Body"]
            assert s["body"]["Body"].startswith("ListingAssistants: ")
        audit = [json.loads(l) for l in open(tmp_path / "state" / "console-audit.jsonl")]
        sent = [e for e in audit if e["kind"] == "pager.sent"]
        assert len(sent) == len(pages) and all("secret-token" not in json.dumps(e) for e in audit)
        rc, out, _ = _console(tmp_path, "pager", "--off")
        assert rc == 0 and not cfg_path.exists()
    finally:
        srv.shutdown()


@pytest.mark.parametrize("bad", [{"to_number": "5551234"}, {"account_sid": ""},
                                 {"api_base": "http://api.example.com"}])
def test_pager_details_are_validated(bad):
    from dispatcher.pager import validate
    cfg = {"account_sid": "AC1", "auth_token": "t", "from_number": "+15550000001",
           "to_number": "+15550000002", **bad}
    assert validate(cfg)


def test_documented_tuple_count_matches_the_decisions_files():
    """The README and SKILL.md state the number of DECISIONS.md tuples; this
    keeps the statement true (it drifted once already, 2026-10-12)."""
    import glob
    import re
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    lines = [l for f in glob.glob(os.path.join(root, "*", "DECISIONS.md"))
             for l in open(f, encoding="utf-8") if l.startswith("- (")]
    retired = sum(1 for l in lines if "RETIRED" in l)
    for doc in ("README.md", "SKILL.md"):
        text = open(os.path.join(root, doc), encoding="utf-8").read()
        total = re.search(r"(\d+) (?:predeliberated )?decision tuples", text)
        ret = re.search(r"(\d+) (?:of them marked )?retired", text)
        assert total and ret and int(total.group(1)) == len(lines) and int(ret.group(1)) == retired, \
            (doc, len(lines), retired)
