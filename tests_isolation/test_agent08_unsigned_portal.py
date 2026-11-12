"""Agent 08's "arrived unsigned" question (owner decision D-A11) with every
agent in its own process (found 2026-11-12).

Agent 08 read the hub's queues and the audit log to learn whether the owner
had marked its question done. An agent in its own process or container has
neither: the unsigned document was dead-lettered ("not on the portal menu:
hub.queues"), the request for a signed copy never went and the chase was not
paused. It now asks the dispatcher one narrow question, queue_item_state,
about its own message. The first two tests fail on the code before the
change; the third (no other agent may ask) guards the new menu item."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dispatcher.clock import send_tick  # noqa: E402
from dispatcher.escalation_watch import acknowledge  # noqa: E402
from dispatcher.portal import RemoteError  # noqa: E402
from tests_isolation.test_portal import _env, _entries, _swarm  # noqa: E402


def _from_08(sw, ctx):
    return [e["payload"].get("template") for e in _entries(sw, "envelope.persisted")
            if e.get("client_context_id") == ctx and e["from_agent"] == "08"
            and e["intent"] == "client.message.request"]


def test_unsigned_document_is_handled_and_the_chase_pauses_until_marked_done(tmp_path):
    sw = _swarm(str(tmp_path))
    try:
        sw.hub.send(_env("07", "08", "doc.request", "U-1",
                         {"doc_type": "purchase_agreement", "today": "2026-10-15"}))
        r = sw.hub.send(_env("11", "08", "document.submission", "U-1",
                             {"doc_type": "purchase_agreement", "opens_correctly": True,
                              "signature_expected": True, "signed": False,
                              "content_hash": "pa-1"}))
        assert r["status"] == "ack"                      # was dead.letter
        assert not _entries(sw, "dead.letter")
        assert not _entries(sw, "portal.violation") and "08" not in sw.team.stopped
        assert _from_08(sw, "U-1") == ["document_request", "doc_unsigned_resend"]
        # the daily run does not chase while the owner's question is open
        send_tick(sw.hub, "08", "2026-10-16", "2026-10-16T10:00:00")
        assert _from_08(sw, "U-1") == ["document_request", "doc_unsigned_resend"]
        # the owner marks it done: the next daily run chases again
        assert acknowledge(sw.hub, "clarification.request", "U-1", by="owner")
        send_tick(sw.hub, "08", "2026-10-17", "2026-10-17T10:00:00")
        assert _from_08(sw, "U-1")[-1] == "document_chase_followup"
    finally:
        sw.close()


def test_agent_08_is_told_only_about_its_own_question(tmp_path):
    seen = {}

    def act(peer, env):
        for key, eid in seen["ask"].items():
            seen[key] = peer.call("queue_item_state", {"envelope_id": eid})
    sw = _swarm(str(tmp_path), ("08", act))
    try:
        mine = _env("08", "queue", "clarification.request", "U-2", {"reason": "mine"})
        other = _env("17", "queue", "clarification.request", "U-2", {"reason": "another agent's"})
        sw.hub.send(mine)
        sw.hub.send(other)
        seen["ask"] = {"mine": mine.envelope_id, "other": other.envelope_id, "none": "no-such-id"}
        sw.hub.send(_env("07", "08", "doc.request", "U-2", {"doc_type": "purchase_agreement"}))
        assert (seen["mine"], seen["other"], seen["none"]) == ("open", "not found", "not found")
        acknowledge(sw.hub, "clarification.request", "U-2", by="owner")
        sw.hub.send(_env("07", "08", "doc.request", "U-2", {"doc_type": "purchase_agreement"}))
        assert (seen["mine"], seen["other"]) == ("done", "not found")
        assert not _entries(sw, "portal.violation")
    finally:
        sw.close()


def test_no_other_agent_may_ask(tmp_path):
    seen = {}

    def act(peer, env):
        try:
            seen["answer"] = peer.call("queue_item_state", {"envelope_id": "x"})
        except RemoteError as e:
            seen["answer"] = f"refused: {e}"
    sw = _swarm(str(tmp_path), ("20", act))
    try:
        sw.hub.send(_env("external", "20", "social.mention", "U-3",
                         {"channel": "social", "text": "nice house"}))
        assert str(seen.get("answer")).startswith("refused")
        [v] = _entries(sw, "portal.violation")
        assert v["violation"] == "off_menu" and "20" in sw.team.stopped
    finally:
        sw.close()
