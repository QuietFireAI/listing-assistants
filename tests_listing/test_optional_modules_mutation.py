"""Kills logic mutants that survived in readable_logger, model_checkpoint_manager
and hermes_seam (post-fix mutmut run, 2026-10-11)."""
import json
import os

import pytest
from dispatcher.core import AuditLog
from dispatcher.readable_logger import HumanReadableLogger
from dispatcher.model_checkpoint_manager import ModelCheckpointManager, GOLDEN_BROKER_EXAM
from dispatcher.hermes_seam import BrokerContextIngestor, HermesCognitiveSeam


# ---- readable_logger -----------------------------------------------------------

def test_integrity_counts_each_kind(tmp_path):
    a = AuditLog(str(tmp_path / "a.jsonl"))
    for kind in ("integrity.violation", "integrity.violation", "send", "reject"):
        a.append(kind, {"x": 1})
    lg = HumanReadableLogger(log_root=str(tmp_path / "logs"), drawers_root=None)
    rep = lg.generate_eod_report(date_str="2026-10-11", audit_log=a)
    assert rep["integrity"]["integrity_violations"] == 2 and rep["integrity"]["rejects"] == 1
    assert "integrity.violation entries: 2; reject entries: 1." in rep["markdown"]
    b = AuditLog(str(tmp_path / "b.jsonl"))
    b.append("send", {"x": 1})
    rep = lg.generate_eod_report(date_str="2026-10-11", audit_log=b)
    assert rep["integrity"]["integrity_violations"] == 0 and rep["integrity"]["rejects"] == 0


def test_object_without_verify_chain_is_not_computed(tmp_path):
    lg = HumanReadableLogger(log_root=str(tmp_path / "logs"), drawers_root=None)
    rep = lg.generate_eod_report(audit_log=object())
    assert rep["integrity"] == {"chain": None} and "Audit chain:** not computed" in rep["markdown"]


def test_eod_counts_per_client_and_category_and_writes_daily_file(tmp_path):
    lg = HumanReadableLogger(log_root=str(tmp_path / "logs"), drawers_root=None)
    lg.log_event("DISPATCH", "a", client_context_id="c1")
    lg.log_event("DISPATCH", "b", client_context_id="c1")
    lg.log_event("ALERT", "c", client_context_id="c2")
    lg.log_event("NOTE", "d")
    rep = lg.generate_eod_report()
    assert rep["breakdown"] == {"DISPATCH": 2, "ALERT": 1, "NOTE": 1}
    assert "| `c1` | 2 steps |" in rep["markdown"] and "| `c2` | 1 steps |" in rep["markdown"]
    assert rep["report_file"] == os.path.join(str(tmp_path / "logs"), "daily", f"eod_ledger_{rep['date']}.md")
    assert os.path.exists(rep["report_file"])


def test_eod_stream_shows_the_last_50_events(tmp_path):
    lg = HumanReadableLogger(log_root=str(tmp_path / "logs"), drawers_root=None)
    for i in range(60):
        lg.log_event("NOTE", f"event-{i:02d}")
    md = lg.generate_eod_report()["markdown"]
    assert "event-10" in md and "event-59" in md and "event-09" not in md


# ---- model_checkpoint_manager ---------------------------------------------------

class Log:
    def __init__(self):
        self.events = []

    def log_event(self, cat, msg, **k):
        self.events.append((cat, msg))


def good(q):
    return {"exam_fair_housing": "Fair housing: I can't include that.",
            "exam_wire_defense": "Verify by phone; secure portal only.",
            "exam_pricing_boundary": "I cannot guarantee a price.",
            "exam_nar_settlement": "A written buyer representation agreement comes first."}[
        [i["id"] for i in GOLDEN_BROKER_EXAM if i["question"] == q][0]]


def adapter(tmp_path, name):
    p = tmp_path / name
    p.write_bytes(b"x")
    return str(p)


def test_activate_and_rollback_bookkeeping(tmp_path):
    log = Log()
    m = ModelCheckpointManager(str(tmp_path / "ck"), logger=log)
    a = m.register_checkpoint("a", adapter(tmp_path, "a.bin"), test_responder=good)
    assert a["parent_id"] == "baseline_v1.0.0"
    b = m.register_checkpoint("b", adapter(tmp_path, "b.bin"), parent_id="a", test_responder=good)
    assert b["parent_id"] == "a"
    m.activate_checkpoint("a")
    m.activate_checkpoint("b")
    man = json.load(open(m.manifest_path, encoding="utf-8"))
    assert man["checkpoints"]["a"]["status"] == "ARCHIVED" and man["checkpoints"]["b"]["status"] == "ACTIVE"
    last = man["history"][-1]
    assert last["action"] == "ACTIVATE" and last["previous_id"] == "a" and last["forced"] is False
    r = m.rollback("a", reason="drift")
    man = json.load(open(m.manifest_path, encoding="utf-8"))
    assert man["checkpoints"]["b"]["status"] == "QUARANTINED_ROLLED_BACK"
    assert man["checkpoints"]["a"]["status"] == "ACTIVE" and man["active_checkpoint_id"] == "a"
    assert man["history"][-1] == {**man["history"][-1], "action": "ROLLBACK", "from_id": "b", "to_id": "a", "reason": "drift"}
    m.rollback()
    man = json.load(open(m.manifest_path, encoding="utf-8"))
    assert man["checkpoints"]["baseline_v1.0.0"]["status"] == "GOLDEN_BASELINE"
    msgs = [e[1] for e in log.events]
    assert any("Registered model checkpoint 'a' -> [CANDIDATE] score: 100.0%" in x for x in msgs)
    assert any("Activated checkpoint 'b' (replaces 'a')" in x for x in msgs)
    assert any("Reverted active model from 'b' to 'a'. Reason: drift" in x for x in msgs)


def test_checkpoint_error_messages(tmp_path):
    m = ModelCheckpointManager(str(tmp_path / "ck"))
    with pytest.raises(ValueError, match="Checkpoint 'nope' not found in manifest."):
        m.activate_checkpoint("nope")
    with pytest.raises(ValueError, match="Rollback target 'nope' does not exist."):
        m.rollback("nope")
    with pytest.raises(FileNotFoundError, match="does not exist - nothing to register"):
        m.register_checkpoint("x", "/no/such/file")
    m.register_checkpoint("x", adapter(tmp_path, "x.bin"), test_responder=good)
    with pytest.raises(ValueError, match="checkpoint 'x' already registered"):
        m.register_checkpoint("x", adapter(tmp_path, "x.bin"), test_responder=good)


def test_exam_details(tmp_path):
    m = ModelCheckpointManager(str(tmp_path / "ck"))
    not_run = m.run_broker_regression_exam()
    assert not_run["passed_count"] == 0 and not_run["details"] == []
    three = lambda q: "Sure, wire your funds to this account." if "wire" in q.lower() else good(q)
    ex = m.run_broker_regression_exam(three)
    assert ex["score"] == 75.0 and ex["passed_count"] == 3
    wire = [d for d in ex["details"] if d["exam_id"] == "exam_wire_defense"][0]
    assert wire["prohibited_found"] == ["wire your funds to"] and wire["posture_found"] == []


# ---- hermes_seam -----------------------------------------------------------------

def test_reference_export_contents(tmp_path):
    ing = BrokerContextIngestor()
    ing.ingest_document("signs", "Yard signs Saturdays only.", category="office")
    out = tmp_path / "ref.jsonl"
    ing.export_reference_records(str(out))
    rows = [json.loads(l) for l in open(out, encoding="utf-8")]
    assert rows[-1] == {"topic": "signs", "directive": "Yard signs Saturdays only.", "category": "office"}
    assert rows[0]["topic"] == "nar_settlement_2024" and rows[0]["category"] == "core_directive"
    assert rows[0]["directive"].startswith("Written buyer representation agreement")


def test_curriculum_default_is_five_items():
    ing = BrokerContextIngestor()
    for i in range(3):
        ing.ingest_document(f"t{i}", "d")
    lines = ing.format_curriculum_prompt().splitlines()
    assert len(lines) == 2 + 5


def test_seam_passes_model_and_wires_its_parts():
    calls = {}

    class C:
        class chat:
            class completions:
                @staticmethod
                def create(**k):
                    calls.update(k)
                    from types import SimpleNamespace as N
                    return N(choices=[N(message=N(content="<think>t</think>ok"))])
    log = Log()
    seam = HermesCognitiveSeam(client=C, model="hermes-x", logger=log)
    assert seam.learning_loop.ingestor is seam.ingestor and seam.learning_loop.logger is log
    seam.draft_and_trace("04", "e1", "p", learn=False)
    assert calls["model"] == "hermes-x"
