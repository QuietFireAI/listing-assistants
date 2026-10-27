"""Owner decisions 2026-10-27 (found writing the Operating Procedures):
a showing is confirmed to the buyer only once the calendar has it. When
Agent 18 does not add a showing, it tells Agent 06 (calendar.conflict),
and 06 holds it for the broker: continue confirms it, cancel sends
nothing. Built the way production builds the swarm (dispatcher/swarm.py)."""
from tests_listing.test_repairs_2026_10_11 import _swarm, _env, _signed, _decide, _persisted


def _buyer(sw, signer, ctx):
    sw.hub.send(_signed(signer, "14", ctx, {"consent_record": {"email": "yes", "text": "yes"}}))
    sw.hub.send(_signed(signer, "14", ctx, {"buyer_agreement_on_file": True,
                                            "requester_identity_verified": True}))


def _ask(sw, ctx, listing, when):
    sw.hub.send(_env("external", "11", "client.reply", ctx,
                     {"message": f"Can we see {listing} at {when[11:16]}?", "requests_showing": True,
                      "listing_id": listing, "requested_time": when,
                      "sent_at": "2026-10-15T09:00:00"}))


def _confirmations(sw, ctx):
    return [e for e in _persisted(sw, "client.message.request", ctx)
            if e["payload"].get("template") == "showing_confirmation"]


def _two_at_once(tmp_path):
    sw, signer = _swarm(tmp_path)
    _buyer(sw, signer, "B1")
    _buyer(sw, signer, "B2")
    _ask(sw, "B1", "SYN-L001", "2026-10-20T14:00:00")
    _ask(sw, "B2", "SYN-L002", "2026-10-20T14:00:00")
    return sw, signer


def test_a_showing_the_calendar_refuses_is_not_confirmed_and_waits_for_the_broker(tmp_path):
    sw, signer = _two_at_once(tmp_path)
    assert len(_confirmations(sw, "B1")) == 1
    assert _confirmations(sw, "B2") == []
    assert _persisted(sw, "calendar.conflict", "B2")
    [w] = sw.hitl.get_pending_waits("B2")
    assert w["agent_id"] == "06"


def test_continue_confirms_the_held_showing(tmp_path):
    sw, signer = _two_at_once(tmp_path)
    _decide(sw, signer, "B2", "APPROVE")
    assert len(_confirmations(sw, "B2")) == 1


def test_cancel_sends_the_buyer_nothing(tmp_path):
    sw, signer = _two_at_once(tmp_path)
    _decide(sw, signer, "B2", "REJECT_AND_ABORT")
    assert _confirmations(sw, "B2") == []
    logs = [e for e in _persisted(sw, "interaction.log", "B2")
            if e["payload"].get("kind") == "showing_not_confirmed"]
    assert logs
