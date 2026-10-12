"""The ten operator scenes (scenes/*.jsonl), run the way the operator runs
them: one console session per scene, through tools/console.py, with the
swarm's state carried between sessions by the state store.

Added 2026-10-11. Every scene was filmable on paper and none had ever been
run; running them found fourteen places where real agent-to-agent traffic
broke while the unit tests (fed hand-built messages) passed. This test is
the guard against that recurring: each Expected in
docs/OPERATOR_TESTING_MANUAL.md is asserted here.

The only difference from the operator's run: the synthetic vendor roster is
ratified by this test (the operator ratifies it by hand in Scene 0).
"""
import json
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENES = sorted(f for f in os.listdir(os.path.join(ROOT, "scenes")) if f.endswith(".jsonl"))


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    d = tmp_path_factory.mktemp("scenes")
    cfg = d / "cfg"
    cfg.mkdir()
    roster = json.load(open(os.path.join(ROOT, "scenes", "config", "vendor_panel.json"), encoding="utf-8"))
    roster["_status"] = "RATIFIED 2026-10-12 scene test"
    (cfg / "vendor_panel.json").write_text(json.dumps(roster), encoding="utf-8")
    audit, state = d / "audit.jsonl", d / "state.sqlite"
    out = {}
    for f in SCENES:
        p = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "console.py"), "session",
                            os.path.join(ROOT, "scenes", f), "--audit-log", str(audit),
                            "--state-db", str(state), "--config-dir", str(cfg)],
                           capture_output=True, text=True, cwd=ROOT)
        lines = [json.loads(l) for l in p.stdout.splitlines() if l.startswith("{")]
        out[f[:7]] = {"rc": p.returncode, "lines": lines, "stderr": p.stderr}
    entries = [json.loads(l) for l in open(audit, encoding="utf-8")]
    return {"out": out, "audit": entries, "audit_path": str(audit), "dir": d}


def results(run, scene):
    return {l["line"]: l["result"] for l in run["out"][scene]["lines"] if "line" in l}


def pages(run, scene, queue=None):
    return [l["HUMAN_QUEUE"] if queue is None else l["record"]
            for l in run["out"][scene]["lines"]
            if "HUMAN_QUEUE" in l and (queue is None or l["HUMAN_QUEUE"] == queue)]


def persisted(run, intent, ctx=None):
    return [e for e in run["audit"] if e.get("kind") == "envelope.persisted"
            and e.get("intent") == intent and (ctx is None or e.get("client_context_id") == ctx)]


def test_every_scene_completes_with_no_errors_and_state_carried(run):
    assert len(SCENES) == 10
    for scene, o in run["out"].items():
        assert o["rc"] == 0, (scene, o["stderr"][-2000:])
        done = o["lines"][-1]
        assert done["session_complete"] and done["errors"] == 0 and done["chain"]["ok"], scene
        assert done["dead_letters"] == 0, scene
        assert done["state_saved"]["snapshot_id"] >= 1
    first = run["out"]["scene01"]["lines"][0]
    assert first["state"] == "fresh" and first["vendor_roster"] == "loaded"
    assert all(run["out"][s]["lines"][0]["state"] == "restored" for s in list(run["out"])[1:])


def test_scene01_unsigned_bounces_signed_lands(run):
    r = results(run, "scene01")
    assert r[1] == {**r[1], "status": "reject", "reason": "unverified signature on authority intent"}
    assert r[2]["status"] == "ack"


def test_scene02_malformed_ruleset_refused_prior_stays(run):
    held = [q for q in pages(run, "scene02", "clarification.request")
            if q["payload"].get("reason") == "malformed compliance ruleset rejected"]
    assert held and held[0]["payload"]["version"] == "r2"


def test_scene03_hot_lead_paged_duplicate_held_and_cancelled_no_outreach(run):
    hot = pages(run, "scene03", "escalation.hot_lead")
    assert [h["client_context_id"] for h in hot] == ["S3-hot"] and hot[0]["sla_s"] == 300
    waits = results(run, "scene03")[5]
    assert [w["client_context_id"] for w in waits] == ["S3-hot-again"]
    assert results(run, "scene03")[6]["handler_result"] == "cancelled"
    assert not persisted(run, "lead.captured", "S3-hot-again")
    nocall = [e for e in persisted(run, "interaction.log", "S3-nocall")
              if e["payload"].get("kind") == "lead.captured"]
    assert nocall and nocall[0]["payload"]["consent"] == {"call": "no", "text": "no", "email": "no"}
    assert not [e for e in persisted(run, "client.message.send")
                if e["client_context_id"].startswith("S3")]


def test_scene04_listing_end_to_end_and_no_proof_releases_nothing(run):
    r = results(run, "scene04")
    assert [x["intent"] for x in r[7] if x["ctx"] == "S4"] == ["vendor.schedule"], \
        "the proof-less deliverable must release nothing"
    final = [x["intent"] for x in r[11] if x["ctx"] == "S4"]
    assert final[0] == "vendor.schedule" and "campaign.publish" in final \
        and "client.message.send" in final
    assert {e["to_agent"] for e in persisted(run, "asset.release", "S4")} == {"05", "12"}
    assert {e["to_agent"] for e in persisted(run, "status.update", "S4")} >= {"11", "12", "14"}


def test_scene05_flag_exact_fix_approve_phrase_never_released(run):
    verdicts = [e["payload"]["verdict"] for e in persisted(run, "content.verdict", "S5")
                if e["to_agent"] == "04"]
    assert verdicts == ["flagged", "approved"]
    for e in persisted(run, "asset.release", "S5"):
        assert "perfect for young families" not in json.dumps(e["payload"])


def test_scene06_photo_contradiction_halts_before_compliance(run):
    held = [q for q in pages(run, "scene06", "clarification.request")
            if q["payload"].get("reason") == "photos contradict data sheet"]
    assert held and held[0]["payload"]["contradictions"]["claimed_in_data_not_in_photos"] == ["in-ground pool"]
    assert not persisted(run, "content.review", "S6")


def test_scene07_contract_to_close(run):
    legal = [p["trigger"] for p in pages(run, "scene07", "escalation.legal_line")]
    assert any("financing contingency date passed" in t for t in legal)
    overdue = [e for e in persisted(run, "deadline.alert", "S7") if e["to_agent"] == "11"]
    assert sorted(e["payload"]["milestone"] for e in overdue) == ["financing_contingency", "inspection"]
    closed = persisted(run, "transaction.closed", "S7")
    assert {e["to_agent"] for e in closed} == {"14", "15", "16"}
    assert all(e["payload"]["sale_price"] == 405000 and e["payload"]["close_date"] == "2026-11-01"
               for e in closed)
    sweep = results(run, "scene07")[12]
    assert {"agent": "16", "sweep": "post_close_milestones", "result": "sent:30"} in sweep
    # the client has consent on record (line 1), so the check-in actually leaves
    assert any(e["payload"]["template"] == "post_close_checkin_30day"
               for e in persisted(run, "client.message.send", "S7"))


def test_scene08_tier_gate_then_human_confirmed_bump(run):
    q = pages(run, "scene08", "clarification.request")
    assert any(x["client_context_id"] == "S8-buyerB" and "lead tier not HOT" in x["payload"]["reason"] for x in q)
    assert any(x["client_context_id"] == "S8-buyerC" and "human confirmation required" in x["payload"]["reason"]
               for x in q)
    ext = results(run, "scene08")[12]
    assert {"intent": "client.message.send", "ctx": "S8-buyerA",
            "payload": {"template": "showing_bumped_notice",
                        "variables": {"original_time": "2026-10-17T10:00",
                                      "reason": "protected_deadline_priority"}}} in ext
    assert any(x["ctx"] == "S8-buyerC" and x["payload"]["template"] == "showing_confirmation" for x in ext)


def test_scene09_complaint_holds_touches_until_released(run):
    c = pages(run, "scene09", "escalation.complaint")
    assert c and c[0]["priority"] == "viral" and c[0]["trigger"].startswith("Nobody from this brokerage")
    r = results(run, "scene09")
    assert not [x for x in r[5] if x["ctx"] == "S9"]
    assert [x["payload"]["template"] for x in r[8] if x["ctx"] == "S9"] == ["seller_weekly_report"]
    kinds = [e["payload"].get("kind") for e in persisted(run, "interaction.log", "S9")]
    assert kinds.index("touch_held_complaint_hold") < kinds.index("complaint_hold_released")


def test_scene10_briefing_spans_every_session_and_the_record_defends_itself(run, tmp_path):
    brief = results(run, "scene10")[1]
    waiting = {(w["agent"], w["context"], w["waiting_on"]) for w in brief["currently_waiting"]}
    assert ("02", "S3-hot", "hot_lead_human_response") in waiting      # from Scene 3's session
    assert ("08", "S7", "document:inspection_report") in waiting      # from Scene 7's session
    eod = results(run, "scene10")[2]
    assert eod["tier_snapshot"]["S3-hot"] == "HOT" and eod["logging_gaps"] == []
    # tamper with one line, verify names it
    lines = open(run["audit_path"], encoding="utf-8").read().splitlines()
    i = next(n for n, l in enumerate(lines) if '"Pat Hot"' in l)
    lines[i] = lines[i].replace("Pat Hot", "Pat Cold")
    bad = tmp_path / "tampered.jsonl"
    bad.write_text("\n".join(lines) + "\n", encoding="utf-8")
    p = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "console.py"), "verify",
                        "--audit-log", str(bad)], capture_output=True, text=True)
    v = json.loads(p.stdout)
    assert p.returncode == 1 and v["chain"]["ok"] is False and v["chain"]["break_at"] == i + 1


def test_no_wait_is_resolved_before_it_is_opened(run):
    """The ordering bug class found in 01 (July) and 04/12/15/19 (October):
    a wait opened after the request another agent answers synchronously."""
    open_, early = set(), set()
    for e in run["audit"]:
        if e.get("kind") == "envelope.persisted" and e.get("intent") == "agent.status":
            k = (e["from_agent"], e["client_context_id"], e["payload"].get("waiting_on"))
            if e["payload"].get("resolved"):
                (open_.discard(k) if k in open_ else early.add(k))
            else:
                assert k not in early, f"wait {k} was resolved before it was opened"
                open_.add(k)


def test_no_scene_client_message_is_blocked_for_missing_consent(run):
    """Owner decision 2026-10-12: Agent 11 sends nothing without consent on
    record at 14. Every scene client that gets messages has its consent
    recorded first (the broker's signed consent_record, or 01 at capture)."""
    blocked = [e for e in persisted(run, "interaction.log")
               if e["payload"].get("kind") == "send_blocked_no_consent"]
    assert blocked == []
