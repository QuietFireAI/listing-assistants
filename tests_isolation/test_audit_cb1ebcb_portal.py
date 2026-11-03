"""The portal fixes from the outside audit of cb1ebcb (2026-11-03): items
37 (allow_external is the broker's signed setting, held by the dispatcher),
38 (an agent files only for the client whose message it is handling) and
39 (agents cannot write the drawer lines on the record). Each test fails on
the code before the fix."""
import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dispatcher.portal import RemoteError  # noqa: E402
from dispatcher.portal_dispatcher import (RemoteSpoke, allow_external_on_record,  # noqa: E402
                                          process_launcher)
from dispatcher.signatures import Ed25519Signer, Ed25519Verifier  # noqa: E402
from dispatcher.swarm import build_swarm  # noqa: E402
from tests_isolation.test_portal import _env, _entries, _kinds, _rogue  # noqa: E402

import threading  # noqa: E402

LEAD = {"channel": "web_form", "name": "N", "budget": 900000, "timeline_days": 7,
        "financing_progress": "preapproved", "preapproval_status": "yes",
        "today": "2026-10-12", "consent": {"call": "yes", "text": "yes", "email": "yes"}}


def _swarm(tmp, rogue, signer=None):
    short = tempfile.mkdtemp(prefix="la-a-")
    real = process_launcher(sys.executable, ROOT)

    def launch(aid, path):
        if aid == rogue[0]:
            t = threading.Thread(target=_rogue, args=(path, aid, rogue[1]), daemon=True)
            t.start()
            return t
        return real(aid, path)
    kw = {}
    if signer is not None:
        kw["verifier"] = Ed25519Verifier(signer.public_key_bytes()).verifier()
    return build_swarm(os.path.join(tmp, "audit.jsonl"),
                       portal={"sockets_dir": short, "launcher": launch}, **kw)


def _try(seen, key, fn):
    try:
        seen[key] = fn()
    except RemoteError as e:
        seen[key] = f"refused: {e}"


# ------------------------------------------------------------ audit 39
def test_audit39_an_agent_cannot_write_a_drawer_line_on_the_record(tmp_path):
    seen = {}

    def act(peer, env):
        _try(seen, "note", lambda: peer.call("log_note", {
            "kind": "drawer.filed", "data": {"agent": "20", "client_context_id": "M-1",
                                             "category": "documents", "filename": "x.json",
                                             "sha256": "0" * 64}}))
    sw = _swarm(str(tmp_path), ("20", act))
    try:
        sw.hub.send(_env("external", "20", "social.mention", "M-1",
                         {"channel": "social", "text": "nice house"}))
        assert str(seen.get("note")).startswith("refused")
        [v] = _entries(sw, "portal.violation")
        assert v["violation"] == "record_kind"
        assert "drawer.filed" not in _kinds(sw)
    finally:
        sw.close()


# ------------------------------------------------------------ audit 38
@pytest.mark.parametrize("file_for,violation", [("A", None), ("B", "drawer_context")])
def test_audit38_an_agent_files_only_for_the_client_it_is_handling(tmp_path, file_for, violation):
    seen = {}

    def act(peer, env):
        _try(seen, "filed", lambda: peer.call("file_record", {
            "agent_id": "14", "ctx": file_for, "category": "interactions", "name": "n",
            "record": {"x": 1}}))
    sw = _swarm(str(tmp_path), ("14", act))
    try:
        sw.hub.send(_env("13", "14", "interaction.log", "A", {"kind": "note", "text": "t"}))
        if violation is None:
            assert seen["filed"]["filed"] is True
            assert not _entries(sw, "portal.violation")
        else:
            assert str(seen.get("filed")).startswith("refused")
            [v] = _entries(sw, "portal.violation")
            assert v["violation"] == violation and "'B'" in v["detail"]
            assert "14" in sw.team.stopped
            assert not _entries(sw, "drawer.filed")
    finally:
        sw.close()


# ------------------------------------------------------------ audit 37
def test_audit37_an_agent_cannot_widen_allow_external(tmp_path):
    seen = {}

    def act(peer, env):
        _try(seen, "decide", lambda: peer.call("decision_status", {"allow_external": True}))
    sw = _swarm(str(tmp_path), ("02", act))
    try:
        sw.hub.send(_env("01", "02", "lead.captured", "L-1", LEAD))
        assert str(seen.get("decide")).startswith("refused")
        [v] = _entries(sw, "portal.violation")
        assert v["violation"] == "unsigned_setting"
        assert "02" in sw.team.stopped
    finally:
        sw.close()


def test_audit37_the_brokers_signed_setting_lets_it_through_and_is_kept_on_the_record(tmp_path):
    signer = Ed25519Signer()
    seen = {}

    def act(peer, env):
        if env.intent == "config.update":
            _try(seen, "after_signed", lambda: peer.call("decision_status", {"allow_external": True}))
        else:
            _try(seen, "narrowed", lambda: peer.call("decision_status", {"allow_external": False}))
    sw = _swarm(str(tmp_path), ("02", act), signer=signer)
    try:
        sw.hub.send(_env("01", "02", "lead.captured", "L-1", LEAD))
        assert isinstance(seen["narrowed"], dict)             # narrowing is always allowed
        assert sw.team.allow_external is False
        cfg = _env("human", "02", "config.update", "cfg", {"decision_engine": {"allow_external": True}})
        signer.sign(cfg)
        sw.hub.send(cfg)
        assert isinstance(seen["after_signed"], dict)
        assert sw.team.allow_external is True
        assert not _entries(sw, "portal.violation")
        # after a restart the dispatcher reads it back from the record
        assert allow_external_on_record(sw.hub.audit) is True
        # an unsigned or malformed setting changes nothing
        bad = _env("human", "02", "config.update", "cfg", {"decision_engine": {"allow_external": "yes"}})
        signer.sign(bad)
        sw.hub.send(bad)
        assert allow_external_on_record(sw.hub.audit) is True
    finally:
        sw.close()
