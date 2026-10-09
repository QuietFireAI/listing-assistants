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
    assert "client asked for a pricing opinion" in text


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


def test_real_network_call_reaches_actual_twilio_endpoint():
    """Proves this is real wiring, not a stub - with placeholder
    credentials this genuinely fails with Twilio's own 401, not a local
    mock or a DNS/connection error. That specific failure mode IS the
    proof the request is correctly formed and actually reaching Twilio."""
    result = send_sms_via_twilio("wiring check")
    assert result["status"] == "failed"
    assert result["http_status"] == 401
    assert "Authentication Error" in result["body"] or "20003" in result["body"]


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
    assert "Suspicious wire routing changed" in calls[0]["body"]


def test_parse_inbound_field_command():
    from dispatcher.notifier import parse_inbound_field_command

    # 1. Approve
    res = parse_inbound_field_command("APPROVE wait-123456")
    assert res["action"] == "APPROVE"
    assert res["wait_id"] == "wait-123456"

    # 2. Escalate to support
    res = parse_inbound_field_command("ESCALATE wait-987654 client disputing earnest deposit")
    assert res["action"] == "ESCALATE_TO_SUPPORT"
    assert res["wait_id"] == "wait-987654"
    assert "client disputing earnest deposit" in res["user_notes"]

    # 3. Reject
    res = parse_inbound_field_command("REJECT wait-111 buyer refused addendum")
    assert res["action"] == "REJECT"
    assert res["wait_id"] == "wait-111"
    assert "buyer refused addendum" in res["user_notes"]

    # 4. Modify with key-value pairs
    res = parse_inbound_field_command("MODIFY wait-222 credit=2500 closing_date=2026-11-15")
    assert res["action"] == "MODIFY"
    assert res["wait_id"] == "wait-222"
    assert res["payload"]["credit"] == "2500"
    assert res["payload"]["closing_date"] == "2026-11-15"

    # 5. Status query
    res = parse_inbound_field_command("STATUS ctx-oak-100")
    assert res["action"] == "STATUS"
    assert res["target"] == "ctx-oak-100"

    # 6. Hermes prompt query
    res = parse_inbound_field_command("QUERY What showings are scheduled for today?")
    assert res["action"] == "QUERY"
    assert "showings are scheduled" in res["prompt"]

    # 7. Natural conversational prompt
    res = parse_inbound_field_command("Give me a summary of the inspection report on Elm Street")
    assert res["action"] == "NATURAL_QUERY"
    assert "inspection report on Elm Street" in res["prompt"]
