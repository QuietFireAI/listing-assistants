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
                 "tools/run_sweeps.py", "tools/gen_diagrams.py", "tools/doc_diagrams.py"):
        assert must in files, must
    assert len([f for f in files if f.endswith("/SKILL.md")]) == 21
    assert not [f for f in files if f.startswith("config/") or "__pycache__" in f]


def test_files_python_cannot_import_do_not_stop_the_system(tmp_path):
    # 2026-10-14 third review: a Finder .DS_Store or an editor swap file
    # stopped the console, the desk and the clock
    root, state = fake_install(tmp_path)
    s, verify, fp = keys()
    boot_attest.attest(state, s, root)
    for junk in ("tools/.DS_Store", "dispatcher/.core.py.swp", "dispatcher/Thumbs.db",
                 "dispatcher/notes.txt"):
        open(os.path.join(root, junk), "w").write("x")
    boot_attest.check(state, verify, fp, root)
    for code in ("dispatcher/extra.pyc", "dispatcher/fast.cpython-313-x86_64-linux-gnu.so",
                 "tools/helper.pyd"):
        open(os.path.join(root, code), "w").write("x")
        with pytest.raises(boot_attest.AttestationRefused, match=f"{code}: not attested"):
            boot_attest.check(state, verify, fp, root)
        os.remove(os.path.join(root, code))


def test_a_module_at_the_root_is_unattested(tmp_path):
    # 2026-10-14 fourth review: a glob.py at the root ran in place of the
    # standard library's, before the check that would have caught it
    root, state = fake_install(tmp_path)
    s, verify, fp = keys()
    boot_attest.attest(state, s, root)
    open(os.path.join(root, "glob.py"), "w").write("x = 1\n")
    with pytest.raises(boot_attest.AttestationRefused, match="glob.py: not attested"):
        boot_attest.check(state, verify, fp, root)


def test_a_package_folder_shadowing_a_module_is_unattested(tmp_path):
    # 2026-10-14 review: dispatcher/readable_audit/__init__.py would be
    # imported in place of the attested readable_audit.py
    root, state = fake_install(tmp_path)
    s, verify, fp = keys()
    boot_attest.attest(state, s, root)
    pkg = os.path.join(root, "dispatcher", "readable_audit")
    os.mkdir(pkg)
    open(os.path.join(pkg, "__init__.py"), "w").close()
    with pytest.raises(boot_attest.AttestationRefused,
                       match="dispatcher/readable_audit/__init__.py: not attested"):
        boot_attest.check(state, verify, fp, root)


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
    original = att.read_text()
    doc = json.loads(original)
    doc["signature"] = "00" * 64                                    # not this key's signature
    att.write_text(json.dumps(doc))
    rc, out = console(state, "session", script(tmp_path))
    assert rc == 2 and out[-1]["error"] == "install not attested"
    assert "not signed by this operator" in out[-1]["reason"]
    doc = json.loads(original)
    doc["manifest"]["MANNERS.md"] = "0" * 64                        # the list edited after signing
    att.write_text(json.dumps(doc))
    rc, out = console(state, "session", script(tmp_path))
    assert rc == 2 and "MANNERS.md: changed since it was attested" in out[-1]["reason"]
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
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "desk.py"), "--showcase",
                        "--fresh", "--state-dir", str(real), "--port", "0"],
                       capture_output=True, text=True, cwd=ROOT, timeout=60)
    assert r.returncode != 0 and "deletes only a showcase folder" in r.stderr
    assert (real / boot_attest.ATTEST_FILE).read_text() == before
    assert not desk.is_showcase_folder(str(real))
    other = tmp_path / "notes"                                  # no key, not a showcase folder
    other.mkdir()
    (other / "notes.txt").write_text("mine")
    # a subprocess with a timeout: if the guard broke, the desk would start
    # serving instead of failing
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "desk.py"), "--showcase",
                        "--fresh", "--state-dir", str(other), "--port", "0"],
                       capture_output=True, text=True, cwd=ROOT, timeout=60)
    assert r.returncode != 0 and "deletes only a showcase folder" in r.stderr
    assert (other / "notes.txt").read_text() == "mine"


def test_the_programs_compile_bytecode_into_a_private_folder():
    for prog in ("console.py", "desk.py", "run_sweeps.py"):
        src = open(os.path.join(ROOT, "tools", prog), encoding="utf-8").read()
        switch = src.index("sys.pycache_prefix = _tempfile.mkdtemp(")
        for local in ("\nimport console", "\nfrom console", "from dispatcher", "import dispatcher",
                      "from gen_diagrams"):
            i = src.find(local)
            assert i == -1 or switch < i, (prog, local)
    code = ("import importlib.util as u; s = u.spec_from_file_location('c', 'tools/console.py'); "
            "m = u.module_from_spec(s); s.loader.exec_module(m); import sys; "
            "import dispatcher.boot_attest as b; print(sys.pycache_prefix); print(b.__cached__)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         cwd=ROOT).stdout.split("\n")
    assert "listing-pyc-" in out[0] and out[1].startswith(out[0])


def copy_install(tmp_path):
    dst = tmp_path / "copy"
    shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", "console-state", "showcase-state", "*.sqlite"))
    return dst


def test_changed_modules_never_run_before_the_refusal(tmp_path):
    # 2026-10-14 review: the console and the clock imported state_snapshot,
    # pager, core and sweep_runner before checking
    inst = copy_install(tmp_path)
    state = tmp_path / "cs"
    env = dict(os.environ, LISTINGASSISTANTS_STATE_DIR=str(state))
    run = lambda *a: subprocess.run([sys.executable, *a], capture_output=True, text=True,  # noqa: E731
                                    cwd=str(inst), env=env)
    assert run("tools/console.py", "init").returncode == 0
    marker = tmp_path / "ran.txt"
    for mod in ("dispatcher/state_snapshot", "dispatcher/pager", "dispatcher/core",
                "dispatcher/sweep_runner", "dispatcher/swarm", "dispatcher/listing_spokes_17",
                "dispatcher/signatures", "tools/gen_diagrams", "tools/console"):
        with open(inst / f"{mod}.py", "a", encoding="utf-8") as f:
            f.write(f"\nopen(r'{marker}', 'a').write('{mod}\\n')\n")
    log = state / "console-audit.jsonl"
    before = log.read_text()
    # the clock and the desk load nothing but the checker before refusing
    r = run("tools/run_sweeps.py", "--audit-log", str(log), "--state-db", str(state / "s.sqlite"))
    assert r.returncode == 2 and "install not attested" in r.stdout
    r = run("tools/desk.py")              # its default folder, from LISTINGASSISTANTS_STATE_DIR
    assert r.returncode != 0 and "install not attested" in (r.stdout + r.stderr)
    assert not marker.exists(), marker.read_text()
    # (the line added to console.py comes after its sys.exit(main()), so it
    # runs only if another program imports console.py before the check)
    r = run("tools/console.py", "session", script(tmp_path))
    assert r.returncode == 2 and "install not attested" in r.stdout
    r = run("tools/console.py", "repair-record")
    assert r.returncode == 2 and "install not attested" in r.stdout
    assert not marker.exists(), marker.read_text()
    assert log.read_text() == before


def test_the_desk_names_a_damaged_record_instead_of_a_traceback(tmp_path):
    # 2026-10-14 third review: the new check read the log and let
    # AuditLogDamaged through as a traceback
    state = tmp_path / "cs"
    console(state, "init")
    with open(state / "console-audit.jsonl", "a", encoding="utf-8") as f:
        f.write('{"kind": "cut off')
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "desk.py"), "--state-dir",
                        str(state), "--port", "0"], capture_output=True, text=True, cwd=ROOT,
                       timeout=60)
    assert r.returncode != 0 and "Traceback" not in r.stderr
    assert "damaged" in (r.stdout + r.stderr)
    assert not (state / "desk.lock").exists()


def test_a_log_from_before_attestation_must_be_attested_once(tmp_path):
    state = tmp_path / "cs"
    console(state, "init")
    old_log = tmp_path / "old" / "console-audit.jsonl"
    old_log.parent.mkdir()
    AuditLog(str(old_log)).append("note", {"x": "an entry written before attestation existed"})
    rc, out = console(state, "session", script(tmp_path), "--audit-log", str(old_log), "--no-state")
    assert rc == 2 and "never attested" in out[-1]["reason"]
    # taking an old log is a recorded step, not a silent first-come claim
    rc, out = console(state, "attest", "--audit-log", str(old_log))
    assert rc == 2 and "attest --new-key" in out[0]["reason"]
    rc, out = console(state, "attest", "--audit-log", str(old_log), "--new-key")
    assert rc == 0
    changed = [json.loads(l) for l in open(old_log, encoding="utf-8")
               if '"boot.key_changed"' in l]
    assert len(changed) == 1 and changed[0]["from_key"] is None
    rc, out = console(state, "session", script(tmp_path), "--audit-log", str(old_log), "--no-state")
    assert rc == 0


def test_another_key_cannot_attest_the_log_and_a_replaced_key_is_a_recorded_step(tmp_path):
    real, stranger = tmp_path / "real", tmp_path / "stranger"
    console(real, "init")
    log = real / "console-audit.jsonl"
    console(stranger, "init")
    before = log.read_text()
    rc, out = console(stranger, "attest", "--audit-log", str(log))
    assert rc == 2 and "last attested with another key" in out[0]["reason"]
    assert log.read_text() == before
    assert console(real, "session", script(tmp_path))[0] == 0      # the operator is not locked out
    # a replaced key: deliberate, and on the chain
    rc, out = console(stranger, "attest", "--audit-log", str(log), "--new-key")
    assert rc == 0
    kinds = [json.loads(l)["kind"] for l in open(log, encoding="utf-8")]
    assert kinds[-2:] == ["boot.key_changed", "boot.attested"]
    rc, out = console(real, "session", script(tmp_path))
    assert rc == 2 and "attested with another key" in out[-1]["reason"]
    assert console(real, "attest", "--new-key")[0] == 0            # and back, also recorded
    assert console(real, "session", script(tmp_path))[0] == 0


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


def test_the_clock_refuses_while_a_desk_holds_an_attested_folder(tmp_path):
    state = tmp_path / "cs"
    console(state, "init")
    sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        (state / "desk.lock").write_text(str(sleeper.pid))
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "run_sweeps.py"),
                            "--audit-log", str(state / "console-audit.jsonl"),
                            "--state-db", str(state / "s.sqlite")],
                           capture_output=True, text=True, cwd=ROOT, timeout=60)
        assert r.returncode == 2 and "Broker Desk is running" in r.stdout
    finally:
        sleeper.kill()
        sleeper.wait()
