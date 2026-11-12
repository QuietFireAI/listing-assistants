"""The hub's answer to "has the owner marked my question done"
(queue_item_state, 2026-11-12), and Agent 08's use of it for the
"arrived unsigned" pause (owner decision D-A11).

Agent 08 used to read the hub's queues and audit log itself, which an agent
in its own container cannot do (tests_isolation/
test_agent08_unsigned_portal.py runs the same path that way)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dispatcher.escalation_watch import acknowledge
from dispatcher.listing_spokes_08 import Spoke08DocumentCollection
from tests_listing.test_owner_decisions_2026_10_28 import env, make_hub


def test_queue_item_state_is_open_then_done_and_not_found_for_anything_else(tmp_path):
    hub = make_hub(tmp_path)
    hub.on_turn_start()
    q = env("08", "queue", "clarification.request", "qs-1", {"reason": "a question"})
    hub.send(q)
    assert hub.queue_item_state(q.envelope_id) == "open"
    assert hub.queue_item_state("no-such-envelope") == "not found"
    assert hub.queue_item_state("") == "not found"
    acknowledge(hub, "clarification.request", "qs-1", by="owner")
    assert hub.queue_item_state(q.envelope_id) == "done"


def test_a_question_that_is_not_on_the_owners_list_does_not_pause_the_chase(tmp_path):
    """Before, a question 08 could not find on the list paused the chase for
    good (the flag was set to True and nothing lifted it)."""
    hub = make_hub(tmp_path)
    s08 = Spoke08DocumentCollection(hub)
    hub.on_turn_start()
    hub.send(env("07", "08", "doc.request", "qs-2",
                 {"doc_type": "purchase_agreement", "today": "2026-10-15"}))
    pending = s08.pending_requests["qs-2"]["purchase_agreement"]
    for stale in (True, "0123456789abcdef"):       # an older saved state's values
        pending["unsigned_question"] = stale
        assert s08.check_chase_timeout("qs-2", "purchase_agreement") == "chased"
        assert "unsigned_question" not in pending
