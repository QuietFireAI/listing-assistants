"""MANNERS re-injection and boot attestation, wired (owner decision
2026-10-14). Before this, MANNERS.md (ratified v0.3) said the phase-gate
re-injection fires always and its hash is registered at boot; nothing in the
product did either."""
import hashlib
import json
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests_listing"))

from dispatcher import boot_attest  # noqa: E402
from dispatcher.core import AuditLog, Routes  # noqa: E402
from dispatcher.hub import Hub  # noqa: E402
from dispatcher.manners_reinjection import BACKSTOP_N, MannersReinjector  # noqa: E402
from dispatcher.signatures import Ed25519Signer, Ed25519Verifier  # noqa: E402

MANNERS = os.path.join(ROOT, "MANNERS.md")
ROUTES = os.path.join(ROOT, "identity", "routes.json")


def reinjections(hub, trigger=None):
    return [e for e in hub.audit.read() if e["kind"] == "manners.reinjection"
            and (trigger is None or e["trigger"] == trigger)]


# ------------------------------------------------------------ re-injection
def test_the_backstop_fires_every_n_turns_per_agent_and_a_gate_resets_it(tmp_path):
    hub = Hub(Routes(ROUTES), AuditLog(str(tmp_path / "a.jsonl")))
    m = MannersReinjector(hub, MANNERS)
    assert m.n == BACKSTOP_N == 10
    for _ in range(9):
        m.turn("02")
        m.turn("03")
    assert reinjections(hub) == []
    m.turn("02")                                        # 02's tenth turn
    fired = reinjections(hub, "turn_backstop")
    assert len(fired) == 1 and fired[0]["position"].startswith("agent 02: 10 turns")
    m.phase_gate("P01 phase 1 (signed intake) on c")    # resets 03 at 9
    m.turn("03")
    assert len(reinjections(hub, "turn_backstop")) == 1
    assert [e["position"] for e in reinjections(hub, "phase_gate")] == ["P01 phase 1 (signed intake) on c"]
    with pytest.raises(ValueError):
        MannersReinjector(hub, MANNERS, n=0)


def test_the_prompt_block_is_the_whole_manners_file(tmp_path):
    m = MannersReinjector(Hub(Routes(ROUTES), AuditLog(str(tmp_path / "a.jsonl"))), MANNERS)
    block = m.prompt_block()
    assert open(MANNERS, encoding="utf-8").read().strip() in block
    assert block.startswith("Conduct rules (MANNERS.md)")
    assert m.sha256 == hashlib.sha256(open(MANNERS, "rb").read()).hexdigest()


def test_p01_fires_its_three_phase_gates_and_the_human_releases(tmp_path, monkeypatch):
    import test_playbooks_e2e as e2e
    from dispatcher.swarm import _human_gates
    built = {}
    real_build = e2e.build_swarm

    def build_with_manners(path):
        hub, signer, spokes, external = real_build(path)
        hub.manners = MannersReinjector(hub, MANNERS)
        _human_gates(hub)
        built["hub"] = hub
        return hub, signer, spokes, external

    monkeypatch.setattr(e2e, "build_swarm", build_with_manners)
    e2e.test_p01_new_listing_onboarding_all_three_phases(tmp_path)
    positions = [e["position"] for e in reinjections(built["hub"], "phase_gate")]
    for phase in ("P01 phase 1 (signed intake)", "P01 phase 2 (photos verified)",
                  "P01 phase 3 (go-live)"):
        assert any(p.startswith(phase) for p in positions), (phase, positions)
    assert any(p.startswith("human release of ") for p in positions)


def test_a_signed_decline_is_a_human_gate_and_a_refused_one_is_not(tmp_path):
    from dispatcher.core import Envelope
    from dispatcher.swarm import build_swarm
    s = Ed25519Signer()
    sw = build_swarm(str(tmp_path / "a.jsonl"), verifier=s.verifier())
    held = Envelope(from_agent="09", to_agent="external", intent="vendor.schedule",
                    client_context_id="c1", payload={"vendor_id": "v1"},
                    provenance={"source": "spoke-09", "captured_at": "runtime",
                                "verbatim_available": True})
    sw.hub.send(held)
    assert held.envelope_id in sw.hub._absolute_holds

    def answer(sign):
        auth = Envelope(from_agent="human", to_agent="09", intent="disclosure.authority",
                        client_context_id="c1",
                        payload={"held_envelope_id": held.envelope_id, "decision": "decline"},
                        provenance={"source": "human", "captured_at": "runtime",
                                    "verbatim_available": True})
        if sign:
            s.sign(auth)
        return sw.hub.decline_disclosure(auth)

    assert answer(sign=False)["status"] == "reject"
    assert not [e for e in reinjections(sw.hub, "phase_gate") if "decline" in e["position"]]
    assert answer(sign=True)["status"] == "declined"
    assert [e["position"] for e in reinjections(sw.hub, "phase_gate")] == [
        f"human decline of {held.envelope_id}"]


def test_agents_turns_are_counted_through_the_handoff_guard(tmp_path):
    from dispatcher.swarm import build_swarm
    sw = build_swarm(str(tmp_path / "a.jsonl"))
    from dispatcher.core import Envelope
    for i in range(BACKSTOP_N):
        sw.hub.send(Envelope(from_agent="18", to_agent="14", intent="interaction.log",
                             client_context_id=f"c{i}", payload={"kind": "note"},
                             provenance={"source": "spoke-18", "captured_at": "runtime",
                                         "verbatim_available": True}))
    fired = [e for e in reinjections(sw.hub, "turn_backstop")
             if e["position"].startswith("agent 14: ")]
    assert len(fired) == 1                                       # exactly once in 10 turns


def test_a_live_hitl_decision_is_one_phase_gate_and_a_refused_one_is_none(tmp_path):
    from dispatcher.core import Envelope
    from dispatcher.hitl_protocol import DECISION_INTENT, HITLAuthorizationError
    from dispatcher.swarm import build_swarm
    s = Ed25519Signer()
    sw = build_swarm(str(tmp_path / "a.jsonl"), verifier=s.verifier())
    ws = sw.hitl.pause_operation("c1", "02", "lead.scored", "needs a person", {"tier": "HOT"})

    def decision(sign):
        env = Envelope(from_agent="human", to_agent="hitl", intent=DECISION_INTENT,
                       client_context_id="c1", payload={"wait_id": ws.wait_id, "decision": "APPROVE"},
                       provenance={"source": "human", "captured_at": "runtime"})
        if sign:
            s.sign(env)
        return env

    before = len(reinjections(sw.hub, "phase_gate"))
    with pytest.raises(HITLAuthorizationError):
        sw.hitl.resume_operation(decision(sign=False))
    assert len(reinjections(sw.hub, "phase_gate")) == before
    sw.hitl.resume_operation(decision(sign=True))
    gates = reinjections(sw.hub, "phase_gate")[before:]
    assert [g["position"] for g in gates] == [f"HITL decision APPROVE on {ws.wait_id}"]


def test_any_accepted_signed_human_authority_is_one_gate(tmp_path):
    # 2026-10-14 review: a signed price change fired nothing
    from dispatcher.swarm import build_swarm
    import test_playbooks_e2e as e2e
    s = Ed25519Signer()
    sw = build_swarm(str(tmp_path / "a.jsonl"), verifier=s.verifier())
    sw.hub.send(e2e.signed(s, "05", "listing.change.authorized", "c1",
                           {"new_listing": {"beds": 3, "sqft": 2000, "price": 500000,
                                            "features": [], "photo_detected_features": []},
                            "today": "2026-07-01"}))
    sw.hub.send(e2e.signed(s, "05", "listing.change.authorized", "c1",
                           {"field": "price", "value": 499000}))
    unsigned = e2e.signed(s, "05", "listing.change.authorized", "c1", {"field": "price", "value": 1})
    unsigned.signature = None
    sw.hub.send(unsigned)
    positions = [g["position"] for g in reinjections(sw.hub, "phase_gate")]
    assert positions == ["P01 phase 1 (signed intake) on c1",          # once, not twice
                         "signed listing.change.authorized on c1"], positions


def test_a_refused_release_fires_no_gate(tmp_path):
    from dispatcher.core import Envelope
    from dispatcher.swarm import build_swarm
    s = Ed25519Signer()
    sw = build_swarm(str(tmp_path / "a.jsonl"), verifier=s.verifier())
    held = Envelope(from_agent="09", to_agent="external", intent="vendor.schedule",
                    client_context_id="c1", payload={"vendor_id": "v1"},
                    provenance={"source": "spoke-09", "captured_at": "runtime",
                                "verbatim_available": True})
    sw.hub.send(held)
    auth = Envelope(from_agent="human", to_agent="09", intent="disclosure.authority",
                    client_context_id="c1", payload={"held_envelope_id": held.envelope_id},
                    provenance={"source": "human", "captured_at": "runtime", "verbatim_available": True})
    Ed25519Signer().sign(auth)                                   # another key
    assert sw.hub.release_disclosure(auth)["status"] == "reject"
    assert reinjections(sw.hub, "phase_gate") == []
    s.sign(auth)
    assert sw.hub.release_disclosure(auth)["status"] != "reject"
    assert [g["position"] for g in reinjections(sw.hub, "phase_gate")] == [
        f"human release of {held.envelope_id}"]


def test_the_model_prompt_carries_manners(tmp_path):
    from dispatcher.swarm import build_swarm
    sw = build_swarm(str(tmp_path / "a.jsonl"))
    d = sw.hub.drafting
    seen = {}
    d.gate = lambda: {"ok": True, "checkpoint": "c1"}
    d.seam.draft_and_trace = lambda agent, eid, prompt, learn=False: (
        seen.setdefault("prompt", prompt), ("thought", "A bright home."))[1]
    r = d.draft_remarks("04", "e1", [{"text": "3 beds"}], 800)
    assert r["ok"] is True
    assert seen["prompt"].startswith("Conduct rules (MANNERS.md)")
    assert open(MANNERS, encoding="utf-8").read().strip() in seen["prompt"]


def test_post_compaction_has_no_event_here_and_says_so():
    doc = open(os.path.join(ROOT, "dispatcher", "manners_reinjection.py"), encoding="utf-8").read()
    assert "post_compaction: this product has no context compaction" in doc
    manual = open(os.path.join(ROOT, "docs", "TUNING_MANUAL.md"), encoding="utf-8").read()
    assert "post_compaction" in manual


# ------------------------------------------------------------- attestation
def fake_install(tmp_path):
    root = tmp_path / "install"
    for rel in boot_attest.covered_files(ROOT):
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(os.path.join(ROOT, rel), dst)
    state = tmp_path / "state"
    state.mkdir()
    return str(root), str(state)


def keys():
    s = Ed25519Signer()
    return s, Ed25519Verifier(s.public_key_bytes()).verify_bytes, boot_attest.fingerprint(s.public_key_bytes())


def test_what_is_covered_matches_what_the_identity_declares():
    files = boot_attest.covered_files(ROOT)
    for must in ("MANNERS.md", "SWARM.md", "identity/routes.json", "identity/priority.json",
                 "identity/IDENTITY-real-estate-listing-agent.md", "docs/PLAYBOOKS.md",
                 "docs/JOB_DESCRIPTIONS.md", "05-mls-listing-management/SKILL.md",
                 "05-mls-listing-management/DECISIONS.md", "dispatcher/hub.py",
                 "dispatcher/boot_attest.py", "tools/console.py", "tools/desk.py",
                 "tools/run_sweeps.py", "tools/fresh_bytecode.py"):
        assert must in files, must
    assert len([f for f in files if f.endswith("/SKILL.md")]) == 21
    assert not [f for f in files if f.startswith("config/")]


def test_attest_then_check_and_every_refusal(tmp_path):
    root, state = fake_install(tmp_path)
    s, verify, fp = keys()
    with pytest.raises(boot_attest.AttestationRefused, match="not attested"):
        boot_attest.check(state, verify, fp, root)
    first = boot_attest.attest(state, s, root)
    assert first["changed"] == [] and "MANNERS.md" in first["added"]
    assert boot_attest.check(state, verify, fp, root)["files"] == first["files"]
    _, other_verify, other_fp = keys()
    with pytest.raises(boot_attest.AttestationRefused, match="not signed by this operator"):
        boot_attest.check(state, other_verify, other_fp, root)
    with open(os.path.join(root, "MANNERS.md"), "a", encoding="utf-8") as f:
        f.write("\nan unreviewed line\n")
    with pytest.raises(boot_attest.AttestationRefused,
                       match=r"tainted, not starting: MANNERS.md: changed since it was attested"):
        boot_attest.check(state, verify, fp, root)
    again = boot_attest.attest(state, s, root)
    assert again["changed"] == ["MANNERS.md"] and again["added"] == []
    boot_attest.check(state, verify, fp, root)
    with open(os.path.join(root, "05-mls-listing-management", "SKILL.md"), "a", encoding="utf-8") as f:
        f.write("x")
    with pytest.raises(boot_attest.AttestationRefused, match="05-mls-listing-management/SKILL.md"):
        boot_attest.check(state, verify, fp, root)
    boot_attest.attest(state, s, root)
    open(os.path.join(root, "dispatcher", "planted.py"), "w").close()
    with pytest.raises(boot_attest.AttestationRefused, match="dispatcher/planted.py: not attested"):
        boot_attest.check(state, verify, fp, root)
    os.remove(os.path.join(root, "dispatcher", "planted.py"))
    # an editor's lock link is not a file to hash (2026-10-14 review), but a
    # link that leads to a module is: that module would run
    try:
        os.symlink("nowhere", os.path.join(root, "dispatcher", ".#core.py"))
        os.symlink(os.path.join(root, "MANNERS.md"), os.path.join(root, "dispatcher", "linked.py"))
        linked = True
    except (OSError, NotImplementedError):      # Windows without the right to make links
        linked = False
    if linked:
        with pytest.raises(boot_attest.AttestationRefused, match="dispatcher/linked.py: not attested"):
            boot_attest.check(state, verify, fp, root)
        os.remove(os.path.join(root, "dispatcher", "linked.py"))
    boot_attest.check(state, verify, fp, root)
    for bad in ("{no", "[]", '"x"', '{"manifest": [], "signature": "a"}'):
        open(os.path.join(state, boot_attest.ATTEST_FILE), "w").write(bad)
        with pytest.raises(boot_attest.AttestationRefused, match="is damaged"):
            boot_attest.check(state, verify, fp, root)
    boot_attest.attest(state, s, root)                 # a damaged file is replaced
    boot_attest.check(state, verify, fp, root)


def test_an_old_attestation_put_back_and_another_key_are_refused_by_the_log(tmp_path):
    root, state = fake_install(tmp_path)
    log = str(tmp_path / "audit.jsonl")
    s, verify, fp = keys()
    boot_attest.attest(state, s, root, audit_path=log)
    old_doc = open(os.path.join(state, boot_attest.ATTEST_FILE)).read()
    old_skill = open(os.path.join(root, "MANNERS.md"), "rb").read()
    with open(os.path.join(root, "MANNERS.md"), "ab") as f:
        f.write(b"\nreviewed change\n")
    boot_attest.attest(state, s, root, audit_path=log)
    boot_attest.check(state, verify, fp, root, audit_path=log)
    # roll back: the old file and its old, validly signed attestation
    open(os.path.join(root, "MANNERS.md"), "wb").write(old_skill)
    open(os.path.join(state, boot_attest.ATTEST_FILE), "w").write(old_doc)
    with pytest.raises(boot_attest.AttestationRefused, match="not the attestation last recorded"):
        boot_attest.check(state, verify, fp, root, audit_path=log)
    # another key's state folder against this log
    other_state = tmp_path / "other"
    other_state.mkdir()
    s2, verify2, fp2 = keys()
    boot_attest.attest(str(other_state), s2, root)
    with pytest.raises(boot_attest.AttestationRefused, match="attested with another key"):
        boot_attest.check(str(other_state), verify2, fp2, root, audit_path=log)


def test_an_enforcing_swarm_refuses_before_writing_and_records_a_match(tmp_path):
    from dispatcher.swarm import build_swarm
    s, verify, fp = keys()
    state = str(tmp_path)
    log = os.path.join(state, "a.jsonl")
    att = {"state_dir": state, "verify_bytes": verify, "key_fingerprint": fp}
    with pytest.raises(boot_attest.AttestationRefused):
        build_swarm(log, attestation=att)
    assert not os.path.exists(log) or os.path.getsize(log) == 0      # nothing written
    boot_attest.attest(state, s)
    sw = build_swarm(log, attestation=att)
    rec = [e for e in sw.hub.audit.read() if e["kind"] == "boot.attestation"]
    assert len(rec) == 1 and rec[0]["enforced"] is True and rec[0]["matches"] is True
    assert rec[0]["key_fingerprint"] == fp


def test_the_check_runs_before_any_agent_module_is_imported():
    src = open(os.path.join(ROOT, "dispatcher", "swarm.py"), encoding="utf-8").read()
    body = src[src.index("def build_swarm("):]
    assert body.index("boot_attest.check(") < body.index("from .listing_spokes import")


def test_an_unenforced_swarm_still_records_what_is_running(tmp_path):
    from dispatcher.swarm import build_swarm
    sw = build_swarm(str(tmp_path / "a.jsonl"))
    rec = [e for e in sw.hub.audit.read() if e["kind"] == "boot.attestation"]
    want = hashlib.sha256(open(MANNERS, "rb").read()).hexdigest()
    assert len(rec) == 1 and rec[0]["enforced"] is False and rec[0]["manners_sha256"] == want
    assert sw.hub.manners.sha256 == want                  # one hash, from the raw bytes


def console(state, *args):
    env = dict(os.environ, LISTINGASSISTANTS_STATE_DIR=str(state))
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "console.py"), *args],
                       capture_output=True, text=True, env=env, cwd=ROOT)
    return r.returncode, [json.loads(l) for l in r.stdout.splitlines() if l.startswith("{")]


def script(tmp_path):
    p = tmp_path / "s.jsonl"
    p.write_text('{"do": "show", "what": "queues"}\n')
    return str(p)


def test_console_init_attests_and_a_changed_attestation_stops_the_console(tmp_path):
    state = tmp_path / "cs"
    rc, out = console(state, "init")
    assert rc == 0 and out[0]["attested"]["files"] > 60
    kinds = [json.loads(l)["kind"] for l in open(state / "console-audit.jsonl", encoding="utf-8")]
    assert kinds == ["boot.attested"]
    att = state / boot_attest.ATTEST_FILE
    doc = json.loads(att.read_text())
    doc["manifest"]["MANNERS.md"] = "0" * 64                        # edited after signing
    att.write_text(json.dumps(doc))
    rc, out = console(state, "session", script(tmp_path))
    assert rc == 2 and out[-1]["error"] == "install not attested"
    assert "not signed by this operator" in out[-1]["reason"]
    rc, out = console(state, "attest")
    assert rc == 0 and out[0]["attested"]["changed"] == ["MANNERS.md"]
    rc, out = console(state, "session", script(tmp_path))
    assert rc == 0


def test_a_throwaway_key_cannot_write_to_the_operators_log(tmp_path):
    # 2026-10-14 review: the console took key and attestation from one folder
    # and wrote to any --audit-log
    real, fresh = tmp_path / "real", tmp_path / "fresh"
    console(real, "init")
    assert console(real, "session", script(tmp_path))[0] == 0
    console(fresh, "init")
    log = real / "console-audit.jsonl"
    before = log.read_text()
    rc, out = console(fresh, "session", script(tmp_path), "--audit-log", str(log),
                      "--state-db", str(real / "swarm-state.sqlite"))
    assert rc == 2 and "attested with another key" in out[-1]["reason"]
    assert log.read_text() == before


def test_repair_record_needs_an_attested_install(tmp_path):
    state = tmp_path / "cs"
    console(state, "init")
    doc = json.loads((state / boot_attest.ATTEST_FILE).read_text())
    doc["manifest"]["dispatcher/core.py"] = "0" * 64
    (state / boot_attest.ATTEST_FILE).write_text(json.dumps(doc))
    log = state / "console-audit.jsonl"
    with open(log, "a", encoding="utf-8") as f:
        f.write('{"kind": "cut off')
    before = log.read_text()
    rc, out = console(state, "repair-record")
    assert rc == 2 and out[0]["repaired"] is False and "install not attested" in out[0]["refused"]
    assert log.read_text() == before


def test_the_showcase_never_touches_an_operator_folder(tmp_path):
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import desk
    real = tmp_path / "real"
    console(real, "init")
    before = (real / boot_attest.ATTEST_FILE).read_text()
    with pytest.raises(SystemExit, match="not a showcase folder"):
        desk.Desk(str(real), showcase=True)
    with pytest.raises(SystemExit, match="deletes only a showcase folder"):
        desk.main(["--showcase", "--fresh", "--state-dir", str(real)])
    assert (real / boot_attest.ATTEST_FILE).read_text() == before
    assert not desk.is_showcase_folder(str(real))


def test_the_programs_compile_bytecode_into_a_private_folder():
    code = ("import sys; sys.path.insert(0, 'tools'); from fresh_bytecode import use_fresh_bytecode; "
            "use_fresh_bytecode(); import dispatcher.boot_attest as b; "
            "print(sys.pycache_prefix); print(b.__cached__)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         cwd=ROOT).stdout.split("\n")
    assert "listing-pyc-" in out[0] and out[1].startswith(out[0])
    for prog in ("console.py", "desk.py", "run_sweeps.py"):
        src = open(os.path.join(ROOT, "tools", prog), encoding="utf-8").read()
        main = src[src.index("def main("):]
        assert main.index("use_fresh_bytecode()") < main.index("ap = argparse.ArgumentParser(")


def test_the_clock_needs_the_key_and_the_attestation(tmp_path):
    clock = os.path.join(ROOT, "tools", "run_sweeps.py")
    log = tmp_path / "console-audit.jsonl"
    r = subprocess.run([sys.executable, clock, "--audit-log", str(log), "--state-db",
                        str(tmp_path / "s.sqlite")], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 2 and "no operator key" in r.stdout
    console(tmp_path, "init")
    r = subprocess.run([sys.executable, clock, "--audit-log", str(log), "--state-db",
                        str(tmp_path / "s.sqlite")], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout[-400:]
    kinds = [json.loads(l)["kind"] for l in open(log, encoding="utf-8")]
    assert "verifier.unarmed" not in kinds and "boot.attestation" in kinds
