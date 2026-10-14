"""Three tuple gaps the synthetic sample run found (2026-10-14).

1. Agent 02's tuple "(lead is an agent shopping for a client, flag
   agent-to-agent; ...)" could not fire on a lead that came through intake:
   Agent 01 never forwarded is_agent_shopping. The sample lead scored HOT.
2. The same person written with the country code (+1 216 555 0101) was not
   matched against (216) 555-0101, so the duplicate tuple missed it.
3. The do-not-contact list was compared as exact text on one contact only:
   "330-555-0190" missed a list entry "(330) 555-0190", and a listed email
   was missed whenever the lead also gave a phone.
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dispatcher.core import AuditLog, Envelope, Routes  # noqa: E402
from dispatcher.hub import Hub  # noqa: E402
from dispatcher.listing_spokes import (Spoke01LeadCapture, Spoke14CRMPipeline,  # noqa: E402
                                       _contact_identifiers, _dnc_identifiers)
from dispatcher.listing_spokes_02 import Spoke02LeadQualification  # noqa: E402

ROUTES = os.path.join(os.path.dirname(__file__), "..", "identity", "routes.json")
RUBRIC = {"budget_threshold": 400000, "budget_weight": 40, "timeline_days_threshold": 30,
          "timeline_weight": 40, "financing_weight": 20, "hot_threshold": 70,
          "warm_threshold": 40}


def make(tmp_path, dnc=None, with_02=False):
    hub = Hub(Routes(ROUTES), AuditLog(os.path.join(str(tmp_path), f"a-{uuid.uuid4().hex[:6]}.jsonl")))
    Spoke14CRMPipeline(hub)
    Spoke01LeadCapture(hub, dnc_list=set(dnc or ()))
    q = None
    if with_02:
        q = Spoke02LeadQualification(hub)
        q.rubric, q.rubric_version = dict(RUBRIC), "t1"
    hub.on_turn_start()
    return hub, q


def inbound(ctx, payload):
    return Envelope(from_agent="external", to_agent="01", intent="lead.inbound",
                    client_context_id=ctx, payload=payload,
                    provenance={"source": "external-channel-system", "captured_at": "runtime",
                                "verbatim_available": True})


def persisted(hub, intent):
    return [e for e in hub.audit.read() if e["kind"] == "envelope.persisted" and e["intent"] == intent]


C3 = {"call": "yes", "text": "yes", "email": "yes"}


# ------------------------------------------------------------ 1. agent shopping
def test_an_agent_shopping_lead_reaches_agent_02s_tuple(tmp_path):
    hub, _ = make(tmp_path, with_02=True)
    hub.send(inbound("AS-1", {"channel": "web_form", "name": "Sage Synth", "phone": "(216) 555-0121",
                              "budget": 700000, "timeline_days": 10, "financing_progress": "preapproved",
                              "is_agent_shopping": True, "consent": C3, "today": "2026-10-15"}))
    captured = persisted(hub, "lead.captured")
    assert captured and captured[0]["payload"]["is_agent_shopping"] is True
    clar = [e for e in persisted(hub, "clarification.request") if e["client_context_id"] == "AS-1"]
    # (this bare harness has no Agent 18, so 01's status messages dead-letter;
    # only the agent-to-agent flag matters here)
    assert "agent-to-agent inquiry" in [c["payload"]["reason"] for c in clar]
    assert not hub.queues.get("escalation.hot_lead"), "an agent-to-agent lead is not scored HOT"


def test_a_consumer_lead_carries_no_agent_shopping_flag(tmp_path):
    hub, _ = make(tmp_path, with_02=True)
    for flag in (None, False, "yes"):
        p = {"channel": "web_form", "name": "Avery Synth", "phone": f"(216) 555-01{len(str(flag)):02d}",
             "budget": 700000, "timeline_days": 10, "financing_progress": "preapproved",
             "consent": C3, "today": "2026-10-15"}
        if flag is not None:
            p["is_agent_shopping"] = flag      # only a real True is forwarded
        hub.send(inbound(f"C-{flag}", p))
    assert all("is_agent_shopping" not in e["payload"] for e in persisted(hub, "lead.captured"))


# ------------------------------------------------------------ 2. same person, +1
def test_phone_with_country_code_is_the_same_number():
    assert _contact_identifiers({"phone": "+12165550101"}) == ["phone:2165550101"]
    assert _contact_identifiers({"phone": "1-216-555-0101"}) == ["phone:2165550101"]
    assert _contact_identifiers({"phone": "(216) 555-0101"}) == ["phone:2165550101"]
    assert _contact_identifiers({"phone": "555-0101"}) == ["phone:5550101"]      # 7 digits stay
    assert _contact_identifiers({"phone": "12345"}) == []                        # too short
    assert _contact_identifiers({"phone": "22165550101"}) == ["phone:22165550101"]  # 11, not 1-led


def test_the_same_person_with_the_country_code_is_held_as_a_duplicate(tmp_path):
    hub, _ = make(tmp_path)
    hub.send(inbound("P-1", {"channel": "web_form", "name": "Avery Synth", "phone": "(216) 555-0101",
                             "consent": C3, "today": "2026-10-15"}))
    hub.send(inbound("P-2", {"channel": "call", "name": "Avery Synth", "phone": "+12165550101",
                             "consent": C3, "today": "2026-10-16"}))
    held = [c for c in persisted(hub, "clarification.request")
            if c["client_context_id"] == "P-2" and "held" in c["payload"]]
    assert held and held[0]["payload"]["held"]["possible_duplicate_of"] == ["P-1"]
    assert [e["client_context_id"] for e in persisted(hub, "lead.captured")] == ["P-1"]


# ------------------------------------------------------------ 3. do-not-contact
def test_dnc_entries_normalize_like_contacts():
    assert _dnc_identifiers(["(330) 555-0190", "DNC.One@Example.test ", "+13305550191", 7, ""]) == {
        "phone:3305550190", "email:dnc.one@example.test", "phone:3305550191"}


def _dnc_hit(hub, ctx):
    return any("DNC" in str(e.get("trigger", "")) and e.get("client_context_id") == ctx
               for e in hub.queues.get("escalation.legal_line", []))


def test_a_listed_phone_in_another_format_is_on_the_list(tmp_path):
    hub, _ = make(tmp_path, dnc={"(330) 555-0190"})
    hub.send(inbound("D-1", {"channel": "call", "name": "Emery Synth", "phone": "330-555-0190",
                             "consent": C3, "today": "2026-10-15"}))
    assert _dnc_hit(hub, "D-1")
    assert persisted(hub, "lead.captured")[0]["payload"]["dnc"] is True


def test_a_listed_email_is_on_the_list_even_when_a_phone_is_given(tmp_path):
    hub, _ = make(tmp_path, dnc={"dnc.one@example.test"})
    hub.send(inbound("D-2", {"channel": "web_form", "name": "Finn Synth", "phone": "(216) 555-0150",
                             "email": "DNC.One@example.test", "consent": C3, "today": "2026-10-15"}))
    assert _dnc_hit(hub, "D-2")
    assert persisted(hub, "lead.captured")[0]["payload"]["dnc"] is True


def test_a_lead_not_on_the_list_is_not_suppressed(tmp_path):
    hub, _ = make(tmp_path, dnc={"(330) 555-0190", "dnc.one@example.test"})
    hub.send(inbound("D-3", {"channel": "web_form", "name": "Gale Synth", "phone": "(330) 555-0191",
                             "email": "gale@example.test", "consent": C3, "today": "2026-10-15"}))
    assert not _dnc_hit(hub, "D-3")
    assert persisted(hub, "lead.captured")[0]["payload"]["dnc"] is False
