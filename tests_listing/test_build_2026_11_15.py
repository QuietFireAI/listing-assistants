"""Parts of the playbooks' success statements that the product did not do,
built from 2026-11-15 on the owner's instruction ("build the 16 and wire it
up correctly"). Each test runs the swarm the way production builds it
(dispatcher/swarm.py) and fails on the code before its build."""
from tests_listing.test_owner_decisions_2026_10_27 import _ask, _buyer, _confirmations
from tests_listing.test_repairs_2026_10_11 import _decide, _env, _persisted, _signed, _swarm


# ---------------------------------------------------------------- B1 (P07)
# "confirmations to every party": the seller of one of our own listings is
# told when a showing is booked, and when a booked one is taken off.

def _our_listing(sw, signer, lid, consent=True):
    """A listing Agent 05 has pushed facts for, with its seller's consent."""
    if consent:
        sw.hub.send(_signed(signer, "14", lid, {"consent_record": {"email": "yes", "text": "yes"}}))
    sw.hub.send(_env("05", "06", "listing.data", lid,
                     {"listing_id": lid, "status": "active", "occupancy": "vacant", "state": "OH"}))


def _to_seller(sw, lid, intent="client.message.send"):
    return [e["payload"] for e in _persisted(sw, intent, lid)
            if "seller" in str(e["payload"].get("template"))]


def test_b1_the_seller_of_our_own_listing_is_told_a_showing_is_booked(tmp_path):
    sw, signer = _swarm(tmp_path)
    sw.hub.send(_signed(signer, "11", "setup", {"template_signed": "showing_booked_seller"}))
    _our_listing(sw, signer, "L1")
    _buyer(sw, signer, "B1")
    _ask(sw, "B1", "L1", "2026-10-20T14:00:00")
    assert len(_confirmations(sw, "B1")) == 1                       # the buyer, as before
    [sent] = _to_seller(sw, "L1")                                   # and now the seller
    assert sent == {"template": "showing_booked_seller",
                    "variables": {"listing_id": "L1", "time": "2026-10-20T14:00:00"}}
    assert "B1" not in str(sent)                                    # nothing about the buyer
    assert [e for e in _persisted(sw, "interaction.log", "L1")
            if e["payload"].get("kind") == "seller_showing_notice_requested"]


def test_b1_the_wording_is_yours_nothing_goes_until_you_sign_it(tmp_path):
    sw, signer = _swarm(tmp_path)
    _our_listing(sw, signer, "L1")
    _buyer(sw, signer, "B1")
    _ask(sw, "B1", "L1", "2026-10-20T14:00:00")
    assert len(_to_seller(sw, "L1", "client.message.request")) == 1  # asked for
    assert _to_seller(sw, "L1") == []                                # not sent
    assert [e for e in _persisted(sw, "interaction.log", "L1")
            if e["payload"].get("kind") == "send_blocked_template_not_signed"]


def test_b1_a_listing_that_is_not_ours_has_no_seller_to_tell(tmp_path):
    sw, signer = _swarm(tmp_path)
    sw.hub.send(_signed(signer, "11", "setup", {"template_signed": "showing_booked_seller"}))
    _buyer(sw, signer, "B1")
    _ask(sw, "B1", "SYN-L001", "2026-10-20T14:00:00")
    assert len(_confirmations(sw, "B1")) == 1
    assert _to_seller(sw, "SYN-L001", "client.message.request") == []


def test_b1_a_seller_who_opted_out_is_not_messaged(tmp_path):
    sw, signer = _swarm(tmp_path)
    sw.hub.send(_signed(signer, "11", "setup", {"template_signed": "showing_booked_seller"}))
    _our_listing(sw, signer, "L1", consent=False)
    _buyer(sw, signer, "B1")
    _ask(sw, "B1", "L1", "2026-10-20T14:00:00")
    assert len(_to_seller(sw, "L1", "client.message.request")) == 1
    assert _to_seller(sw, "L1") == []


def test_b1_a_showing_the_broker_continued_past_a_conflict_also_tells_the_seller(tmp_path):
    sw, signer = _swarm(tmp_path)
    sw.hub.send(_signed(signer, "11", "setup", {"template_signed": "showing_booked_seller"}))
    _our_listing(sw, signer, "L1")
    _our_listing(sw, signer, "L2")
    _buyer(sw, signer, "B1")
    _buyer(sw, signer, "B2")
    _ask(sw, "B1", "L1", "2026-10-20T14:00:00")
    _ask(sw, "B2", "L2", "2026-10-20T14:00:00")           # the calendar refuses this one
    assert _to_seller(sw, "L2") == []
    _decide(sw, signer, "B2", "APPROVE")
    assert [m["variables"]["listing_id"] for m in _to_seller(sw, "L2")] == ["L2"]


# ---------------------------------------------------------------- B3 (P05)
# "the seller hears it from you in your words": a signed status or price
# change may carry note_to_seller; it reaches the seller word for word.

NOTE = "Pat - we are pulling the listing today as we discussed. I will call you at 4. - Jeff"


def _listed(sw, signer, lid):
    """A listing on the record at status active (set directly; the go-live
    path is the P01 run's subject, not this test's)."""
    sw.hub.send(_signed(signer, "14", lid, {"consent_record": {"email": "yes", "text": "yes"}}))
    s05 = sw.spokes["05"]
    s05.mls_records[lid] = {"status": "active", "price": 450000}
    s05.property_data[lid] = {"address": f"{lid} Synthetic Ln, Testville, OH"}


def _change(sw, signer, lid, **payload):
    sw.hub.send(_signed(signer, "05", lid, payload, intent="listing.change.authorized"))


def _seller_notices(sw, lid):
    return [e["payload"] for e in _persisted(sw, "client.message.send", lid)
            if e["payload"].get("template") == "status.update"]


def test_b3_your_note_reaches_the_seller_word_for_word(tmp_path):
    sw, signer = _swarm(tmp_path)
    _listed(sw, signer, "L5")
    _change(sw, signer, "L5", field="status", value="withdrawn", human_confirmation_ref="w-1",
            live_verified=True, today="2026-10-16", note_to_seller=NOTE)
    [sent] = _seller_notices(sw, "L5")
    assert sent["variables"] == {"status": "withdrawn", "your_words": NOTE}
    assert [e for e in _persisted(sw, "interaction.log", "L5")
            if e["payload"].get("kind") == "seller_note_from_broker"
            and e["payload"]["chars"] == len(NOTE)]
    assert not _persisted(sw, "content.review", "L5")        # your words are not reviewed or rewritten


def test_b3_without_a_note_the_notice_is_as_before(tmp_path):
    sw, signer = _swarm(tmp_path)
    _listed(sw, signer, "L5")
    _change(sw, signer, "L5", field="status", value="withdrawn", human_confirmation_ref="w-1",
            live_verified=True, today="2026-10-16")
    [sent] = _seller_notices(sw, "L5")
    assert sent["variables"] == {"status": "withdrawn"}


def test_b3_a_note_that_is_not_text_is_not_guessed_at(tmp_path):
    sw, signer = _swarm(tmp_path)
    _listed(sw, signer, "L5")
    _change(sw, signer, "L5", field="status", value="withdrawn", human_confirmation_ref="w-1",
            live_verified=True, today="2026-10-16", note_to_seller={"text": NOTE})
    [sent] = _seller_notices(sw, "L5")
    assert sent["variables"] == {"status": "withdrawn"}
    assert any("note_to_seller was not text" in q["payload"].get("reason", "")
               for q in sw.hub.queues["clarification.request"])
