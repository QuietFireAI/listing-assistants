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
    assert any(e["position"].startswith("agent 14: 10 turns")
               for e in reinjections(sw.hub, "turn_backstop"))


def test_a_hitl_decision_is_a_phase_gate(tmp_path):
    from dispatcher import manners_reinjection
    calls = []
    hub = type("H", (), {"manners": type("M", (), {"phase_gate": lambda self, p: calls.append(p)})()})()
    manners_reinjection.phase_gate(hub, "HITL decision continue on w1")
    manners_reinjection.phase_gate(object(), "no reinjector: nothing happens")
    assert calls == ["HITL decision continue on w1"]
    src = open(os.path.join(ROOT, "dispatcher", "hitl_protocol.py"), encoding="utf-8").read()
    i = src.index('phase_gate(self.hub, f"HITL decision {decision} on {wait_id}")')
    assert src.index('"hitl.decision.authorized"') < i < src.index("resolution = {")


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
    shutil.copytree(os.path.join(ROOT, "dispatcher"), root / "dispatcher",
                    ignore=shutil.ignore_patterns("__pycache__"))
    (root / "identity").mkdir()
    shutil.copy(ROUTES, root / "identity" / "routes.json")
    shutil.copy(MANNERS, root / "MANNERS.md")
    state = tmp_path / "state"
    state.mkdir()
    return str(root), str(state)


def test_attest_then_check_and_every_refusal(tmp_path):
    root, state = fake_install(tmp_path)
    s = Ed25519Signer()
    v = Ed25519Verifier(s.public_key_bytes())
    with pytest.raises(boot_attest.AttestationRefused, match="not attested"):
        boot_attest.check(state, v.verify_bytes, root)
    first = boot_attest.attest(state, s, root)
    assert first["changed"] == [] and "MANNERS.md" in first["added"]
    ok = boot_attest.check(state, v.verify_bytes, root)
    assert ok["files"] == first["files"]
    # another key's attestation does not count
    other = Ed25519Verifier(Ed25519Signer().public_key_bytes())
    with pytest.raises(boot_attest.AttestationRefused, match="not signed by this operator"):
        boot_attest.check(state, other.verify_bytes, root)
    # MANNERS.md changed without a new signature: tainted, halt
    with open(os.path.join(root, "MANNERS.md"), "a", encoding="utf-8") as f:
        f.write("\nan unreviewed line\n")
    with pytest.raises(boot_attest.AttestationRefused, match=r"tainted, not starting: MANNERS.md: hash mismatch"):
        boot_attest.check(state, v.verify_bytes, root)
    again = boot_attest.attest(state, s, root)                     # reviewed: re-attest
    assert again["changed"] == ["MANNERS.md"] and again["added"] == []
    boot_attest.check(state, v.verify_bytes, root)
    # a file added to dispatcher/ is unattested code
    open(os.path.join(root, "dispatcher", "planted.py"), "w").close()
    with pytest.raises(boot_attest.AttestationRefused, match="planted.py: on disk, absent from manifest"):
        boot_attest.check(state, v.verify_bytes, root)
    # a damaged file is named, and attest replaces it
    open(os.path.join(state, boot_attest.ATTEST_FILE), "w").write("{no")
    with pytest.raises(boot_attest.AttestationRefused, match="is damaged"):
        boot_attest.check(state, v.verify_bytes, root)
    boot_attest.attest(state, s, root)
    boot_attest.check(state, v.verify_bytes, root)


def test_an_enforcing_swarm_refuses_before_writing_and_records_a_match(tmp_path):
    from dispatcher.swarm import build_swarm
    s = Ed25519Signer()
    v = Ed25519Verifier(s.public_key_bytes())
    state = str(tmp_path)
    log = os.path.join(state, "a.jsonl")
    with pytest.raises(boot_attest.AttestationRefused):
        build_swarm(log, attestation={"state_dir": state, "verify_bytes": v.verify_bytes})
    assert not os.path.exists(log) or os.path.getsize(log) == 0      # nothing written
    boot_attest.attest(state, s)
    sw = build_swarm(log, attestation={"state_dir": state, "verify_bytes": v.verify_bytes})
    rec = [e for e in sw.hub.audit.read() if e["kind"] == "boot.attestation"]
    assert len(rec) == 1 and rec[0]["enforced"] is True and rec[0]["matches"] is True


def test_an_unenforced_swarm_still_records_what_is_running(tmp_path):
    from dispatcher.swarm import build_swarm
    sw = build_swarm(str(tmp_path / "a.jsonl"))
    rec = [e for e in sw.hub.audit.read() if e["kind"] == "boot.attestation"]
    want = hashlib.sha256(open(MANNERS, "rb").read()).hexdigest()
    assert len(rec) == 1 and rec[0]["enforced"] is False and rec[0]["manners_sha256"] == want


def console(state, *args):
    env = dict(os.environ, LISTINGASSISTANTS_STATE_DIR=str(state))
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "console.py"), *args],
                       capture_output=True, text=True, env=env, cwd=ROOT)
    return r.returncode, [json.loads(l) for l in r.stdout.splitlines() if l.startswith("{")]


def test_console_init_attests_and_a_changed_attestation_stops_the_console(tmp_path):
    state = tmp_path / "cs"
    rc, out = console(state, "init")
    assert rc == 0 and out[0]["attested"]["files"] > 20
    att = state / boot_attest.ATTEST_FILE
    doc = json.loads(att.read_text())
    doc["manifest"]["MANNERS.md"] = "0" * 64                        # edited after signing
    att.write_text(json.dumps(doc))
    script = tmp_path / "s.json"
    script.write_text('{"do": "show", "what": "queues"}\n')
    rc, out = console(state, "session", str(script))
    assert rc == 2 and out[-1]["error"] == "install not attested"
    assert "not signed by this operator" in out[-1]["reason"]
    rc, out = console(state, "attest")
    assert rc == 0 and out[0]["attested"]["changed"] == ["MANNERS.md"]
    rc, out = console(state, "session", str(script))
    assert rc == 0


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
