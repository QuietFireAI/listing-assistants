"""The owner's decisions of 2026-10-14, as wired.

1. A phrase-list tagger reads client words at intake; any adverse message
   (angry, negative) goes to the human at once, whatever else it asks; Agent
   11 passes the criteria-change and referral-reward labels on.
2. Compliance is told what the content is and where: the type (from the
   submitter or by which agent sent it), the state (from the listing
   address), and every ad is checked for the brokerage identification, a
   signed setting. A ruleset may list the types it covers and the states
   counsel reviewed; anything else is flagged.
3. Showings read occupancy, status and state from the signed listing record
   for our own listings (an onboarding setting; "requester" is the other
   choice).
4. A signed change to beds, baths, square feet, remarks, address or photos
   is applied and logged.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_playbooks_e2e import build_swarm, persisted, signed, spoke_env  # noqa: E402

from dispatcher.listing_spokes_04 import _state_of  # noqa: E402
from dispatcher.message_tags import tag_message  # noqa: E402


def _for(hub, intent, ctx):
    return [e for e in persisted(hub, intent) if e["client_context_id"] == ctx]


def _reply(ctx, message, **extra):
    return spoke_env("external", "11", "client.reply", ctx, {"message": message, **extra})


def _consent(hub, signer, ctx):
    hub.send(signed(signer, "14", "config.update", ctx,
                    {"consent_record": {"email": "yes", "text": "yes"}}))


# ------------------------------------------------------------- 1. tags
def test_the_tagger_reads_the_words_and_honors_only_a_real_true():
    assert set(tag_message("This is ridiculous")) == {"angry"}
    assert set(tag_message("I'm not thrilled with the pace")) == {"negative_tone"}
    assert set(tag_message("Forget the pool, a garage matters more")) == {"contradicts_stated_criteria"}
    assert set(tag_message("Is there a referral fee?")) == {"mentions_referral_reward"}
    assert tag_message("Worst case we close a week late; still waiting on the lender") == {}
    assert tag_message("hello", {"angry": True}) == {"angry": "explicit"}
    assert tag_message("hello", {"angry": "yes"}) == {}


def test_an_angry_message_that_asks_for_pricing_goes_to_the_human_and_gets_no_hand_off(tmp_path):
    hub, signer, spokes, _ = build_swarm(tmp_path)
    _consent(hub, signer, "A1")
    hub.send(_reply("A1", "This is ridiculous. What's your pricing strategy?"))
    assert [c for c in hub.queues.get("escalation.complaint", []) if c["client_context_id"] == "A1"]
    assert [c for c in hub.queues.get("escalation.legal_line", []) if c["client_context_id"] == "A1"]
    assert not _for(hub, "client.message.send", "A1"), "no automatic note to a complaining client"
    assert "A1" in spokes["11"].complaint_hold


def test_a_neutral_message_is_not_a_complaint(tmp_path):
    hub, signer, spokes, _ = build_swarm(tmp_path)
    _consent(hub, signer, "A2")
    hub.send(_reply("A2", "Worst case we can do Saturday instead.", owning_agent="13"))
    assert not hub.queues.get("escalation.complaint")
    assert "A2" not in spokes["11"].complaint_hold


def test_11_passes_the_criteria_label_to_13(tmp_path):
    hub, signer, spokes, _ = build_swarm(tmp_path)
    hub.send(_reply("A3", "Actually we want a fenced yard instead", owning_agent="13"))
    [r] = _for(hub, "lead.reply", "A3")
    assert r["to_agent"] == "13" and r["payload"]["contradicts_stated_criteria"] is True


# ------------------------------------------------------------- 2. compliance
def test_state_from_address():
    assert _state_of("1 Elm St, Testville, OH") == "OH"
    assert _state_of("1 Elm St, Columbus, OH 43004") == "OH"
    assert _state_of("1 Elm St, Columbus OH") is None
    assert _state_of(None) is None


def test_an_ad_without_the_brokerage_identification_is_flagged(tmp_path):
    hub, signer, spokes, _ = build_swarm(tmp_path)
    hub.send(signed(signer, "17", "config.update", "setup",
                    {"ruleset": {"prohibited_phrases": [], "state_rules": {}}, "version": "t1"}))
    spokes["12"].brokerage_identification = None          # 12 has none to add
    hub.send(signed(signer, "12", "config.update", "C1",
                    {"new_campaign": {"headline": "Open house", "body": "Bright kitchen"}}))
    [v] = _for(hub, "content.verdict", "C1")
    assert v["payload"]["verdict"] == "flagged"
    assert any("brokerage identification missing" in f.get("reason", "") for f in v["payload"]["findings"])


def test_an_ad_with_the_brokerage_identification_is_approved_and_carries_it(tmp_path):
    hub, signer, spokes, external = build_swarm(tmp_path)
    hub.send(signed(signer, "17", "config.update", "setup",
                    {"ruleset": {"prohibited_phrases": [], "state_rules": {}}, "version": "t1"}))
    hub.send(signed(signer, "12", "config.update", "C2",
                    {"new_campaign": {"headline": "Open house", "body": "Bright kitchen"}}))
    [v] = _for(hub, "content.verdict", "C2")
    assert v["payload"]["verdict"] == "approved"
    [r] = _for(hub, "content.review", "C2")
    assert r["payload"]["content_type"] == "advertising"
    assert r["payload"]["campaign"]["brokerage_identification"] == "Synth Realty, Testville OH"


def test_12_holds_an_approved_asset_until_a_brokerage_identification_is_set(tmp_path):
    hub, signer, spokes, external = build_swarm(tmp_path)
    s12 = spokes["12"]
    s12.brokerage_identification = None
    hub.send(spoke_env("05", "12", "status.update", "H1", {"status": "active"}))
    hub.send(spoke_env("04", "12", "asset.release", "H1", {"draft": {"facts": []}}))
    assert "H1" in s12.held_for_brokerage_id and "H1" not in s12.published
    assert any("no brokerage identification" in c["payload"]["reason"]
               for c in _for(hub, "clarification.request", "H1"))
    hub.send(signed(signer, "12", "config.update", "setup",
                    {"brokerage_identification": "Synth Realty"}))
    assert "H1" in s12.published and not s12.held_for_brokerage_id
    assert s12.published["H1"]["content"]["brokerage_identification"] == "Synth Realty"


def test_ruleset_covers_and_states_reviewed_are_validated(tmp_path):
    hub, signer, spokes, _ = build_swarm(tmp_path)
    hub.send(signed(signer, "17", "config.update", "setup",
                    {"ruleset": {"prohibited_phrases": [], "covers": []}, "version": "bad"}))
    assert spokes["17"].ruleset_version != "bad"


def test_template_class_preapproval_is_refused(tmp_path):
    hub, signer, spokes, _ = build_swarm(tmp_path)
    hub.send(signed(signer, "17", "config.update", "P1", {"preapprove_template_class": "open houses"}))
    assert any("pre-approval refused" in c["payload"]["reason"]
               for c in _for(hub, "clarification.request", "P1"))


# ------------------------------------------------------------- 3. showing facts
def _showing(ctx, listing_id, when, **extra):
    return spoke_env("11", "06", "showing.request", ctx,
                     {"requested_time": when, "listing_id": listing_id,
                      "buyer_agreement_on_file": True, "requester_identity_verified": True,
                      **extra})


def test_06_reads_occupancy_and_status_from_the_listing_record(tmp_path):
    hub, signer, spokes, _ = build_swarm(tmp_path)
    hub.send(spoke_env("05", "06", "listing.data", "L1",
                       {"listing_id": "L1", "status": "active", "occupancy": "occupied", "state": "OH"}))
    # the requester claims vacant and plenty of notice; the record wins
    hub.send(_showing("B1", "L1", "2026-10-15T15:00:00", sent_at="2026-10-15T10:00:00",
                      property_occupied=False))
    assert any(m["payload"].get("template") == "next_legal_slot_offer"
               for m in _for(hub, "client.message.request", "B1"))
    assert not _for(hub, "calendar.event", "B1")


def test_06_uses_the_requesters_facts_for_a_listing_that_is_not_ours(tmp_path):
    hub, signer, spokes, _ = build_swarm(tmp_path)
    hub.send(_showing("B2", "OTHER-9", "2026-10-20T15:00:00"))
    assert _for(hub, "calendar.event", "B2"), "another brokerage's listing: requester facts, as before"


def test_the_requester_setting_ignores_the_listing_record(tmp_path):
    hub, signer, spokes, _ = build_swarm(tmp_path)
    hub.send(signed(signer, "06", "config.update", "setup", {"showing_facts_source": "requester"}))
    hub.send(spoke_env("05", "06", "listing.data", "L2",
                       {"listing_id": "L2", "status": "active", "occupancy": "occupied"}))
    hub.send(_showing("B3", "L2", "2026-10-20T15:00:00"))
    assert _for(hub, "calendar.event", "B3")
    hub.send(signed(signer, "06", "config.update", "setup", {"showing_facts_source": "nobody"}))
    assert spokes["06"].showing_facts_source == "requester"


def test_05_answers_a_status_request_by_the_listing_not_the_buyer(tmp_path):
    hub, signer, spokes, _ = build_swarm(tmp_path)
    spokes["05"].mls_records["L3"] = {"status": "pending"}
    hub.send(spoke_env("06", "05", "status.request", "B4", {"listing_id": "L3"}))
    [r] = _for(hub, "status.response", "B4")
    assert r["payload"]["status"] == "pending"


# ------------------------------------------------------------- 4. MLS fields
def _change(signer, ctx, **payload):
    return signed(signer, "05", "listing.change.authorized", ctx, payload)


def test_a_signed_sqft_change_is_applied_logged_and_redrafted(tmp_path):
    hub, signer, spokes, _ = build_swarm(tmp_path)
    s05 = spokes["05"]
    s05.mls_records["M1"] = {"status": "active", "sqft": 1800}
    s05.property_data["M1"] = {"address": "1 Elm St, Testville, OH", "sqft": 1800, "beds": 3}
    hub.send(_change(signer, "M1", field="sqft", value=1850))
    assert s05.mls_records["M1"]["sqft"] == 1850
    [log] = [e for e in _for(hub, "interaction.log", "M1") if e["payload"].get("kind") == "mls_field_changed"]
    assert log["payload"]["prior"] == 1800 and log["payload"]["value"] == 1850
    redraft = [e for e in _for(hub, "listing.data", "M1") if e["to_agent"] == "04"]
    assert redraft and redraft[-1]["payload"]["sqft"] == 1850


def test_a_remarks_change_is_applied_without_a_redraft(tmp_path):
    hub, signer, spokes, _ = build_swarm(tmp_path)
    spokes["05"].property_data["M2"] = {"address": "2 Elm St, Testville, OH"}
    hub.send(_change(signer, "M2", field="remarks", value="Sunny ranch."))
    assert spokes["05"].mls_records["M2"]["remarks"] == "Sunny ranch."
    assert not [e for e in _for(hub, "listing.data", "M2") if e["to_agent"] == "04"]


def test_a_change_with_no_value_changes_nothing(tmp_path):
    hub, signer, spokes, _ = build_swarm(tmp_path)
    hub.send(_change(signer, "M3", field="beds"))
    assert "beds" not in spokes["05"].mls_records.get("M3", {})
    assert any("carries no value" in c["payload"]["reason"]
               for c in _for(hub, "clarification.request", "M3"))
