import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dispatcher.notifier import (format_notification_text, send_sms_via_twilio,
                                  sms_human_notifier, DEFAULT_TO_NUMBER)


def test_placeholder_number_is_nanp_fictional_range():
    """555-01xx is NANP's reserved-for-fiction block - guaranteed to never
    route to a real phone, and trivially greppable to replace."""
    assert DEFAULT_TO_NUMBER == "+15555550100"


def test_format_pulls_real_fields_never_invents_them():
    text = format_notification_text("escalation.legal_line", {
        "client_context_id": "ctx-123", "agent": "11",
        "trigger": "client asked for a pricing opinion"})
    assert "escalation.legal_line" in text
    assert "agent=11" in text
    assert "ctx-123" in text
    # the trigger text can carry a client's words; it never leaves in a text
    # (core repair plan 2.4, 2026-10-14)
    assert "client asked for a pricing opinion" not in text


def test_format_handles_missing_fields_gracefully():
    text = format_notification_text("clarification.request", {})
    assert "clarification.request" in text
    assert "ctx=unknown" in text
    assert "agent=?" in text


def test_format_caps_length_for_sms():
    huge_reason = "x" * 1000
    text = format_notification_text("escalation.complaint",
                                    {"reason": huge_reason})
    assert len(text) <= 320


def test_placeholder_credentials_send_nothing_and_say_so(monkeypatch):
    """Until 2026-10-14 this posted to the real Twilio API with the
    placeholder credentials and expected a 401 (the suite depended on
    Twilio). The core notifier now sends nothing while the credentials are
    placeholders, and says so. (This product's own pager is
    dispatcher/pager.py; this is the core notifier it carries.)"""
    import dispatcher.notifier as n
    calls = []
    monkeypatch.setattr(n.urllib.request, "urlopen", lambda *a, **k: calls.append(a))
    for result in (send_sms_via_twilio("wiring check"), n.send_whatsapp_via_twilio("x")):
        assert result["status"] == "failed" and result["error"].startswith("Twilio not configured")
    assert calls == []


def test_human_notifier_signature_matches_hub_expectation(monkeypatch):
    """Confirms sms_human_notifier(queue, record) is call-compatible with
    how Hub.escalate()/the queue-delivery fix actually invoke it, using an
    injected transport so this test doesn't depend on live network."""
    calls = []

    def fake_send(body, to_number=None, timeout=5.0):
        calls.append(body)
        return {"status": "sent", "http_status": 201}

    import dispatcher.notifier as notifier_module
    monkeypatch.setattr(notifier_module, "send_sms_via_twilio", fake_send)

    result = notifier_module.sms_human_notifier(
        "escalation.hot_lead", {"client_context_id": "c-1", "agent": "02"})
    assert result["status"] == "sent"
    assert len(calls) == 1
    assert "escalation.hot_lead" in calls[0]


def test_whatsapp_human_notifier_and_send(monkeypatch):
    calls = []

    def fake_send_wa(body, to_number=None, from_number=None, timeout=5.0):
        calls.append({"body": body, "to": to_number, "from": from_number})
        return {"status": "sent", "http_status": 201, "channel": "whatsapp"}

    import dispatcher.notifier as notifier_module
    monkeypatch.setattr(notifier_module, "send_whatsapp_via_twilio", fake_send_wa)

    result = notifier_module.whatsapp_human_notifier(
        "escalation.wire_warning",
        {"client_context_id": "c-escrow-50", "agent": "07", "reason": "Suspicious wire routing changed"}
    )
    assert result["status"] == "sent"
    assert result["channel"] == "whatsapp"
    assert len(calls) == 1
    assert "c-escrow-50" in calls[0]["body"] and "escalation.wire_warning" in calls[0]["body"]
    assert "Suspicious wire routing changed" not in calls[0]["body"]   # free text stays home


def test_text_command_parser_is_gone():
    """Owner decision J12 (2026-10-12): the unauthenticated SMS/WhatsApp
    APPROVE/REJECT/MODIFY parser was removed from the dispatcher-agents
    core. Broker decisions are signed in the console."""
    import dispatcher.notifier as n
    assert not hasattr(n, "parse_inbound_field_command")
