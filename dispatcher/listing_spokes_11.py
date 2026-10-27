"""Agent 11 - Client Communication, built against the full spec.

Single voice for routine client updates. Reports facts, never
characterizations. Routes inbound replies to the owning agent BY CONTENT
- this is the actual implementation of the "routed by content" mechanism
referenced across the swarm (lead.reply, document.submission,
showing.no_show, showing.feedback_response all originate here).
"""
from __future__ import annotations

from .core import Envelope
from .handoff_guard import guard, register as register_spoke
from .human_holds import hold_for_human, decision_of, register_resumer

SOURCE_VERIFIED = "source_verified"
STATED_BY_PARTY = "stated_by_party"
UNKNOWN = "unknown"

_ADVICE_WORDS = ("what would you do", "should i offer", "what's it worth",
                 "negotiate", "legal opinion", "pricing strategy")
_WIRE_WORDS = ("wire instructions", "wiring details", "wire transfer",
              "updated wire", "routing number")

# Agents whose handlers process lead.reply. 04 and 12 were route receivers
# with no handler (the hub acked and the reply was dropped); per the owner's
# decision of 2026-10-11 they now have handlers that log the reply and hold
# it for the human. A reply naming any other owner (07, an unknown id) goes
# to clarification.request with the client's words (audit OPS-1).
LEAD_REPLY_HANDLERS = frozenset({"03", "04", "12", "13", "16", "20"})


# the fields Agent 08 reads from a document.submission
_DOCUMENT_FIELDS = ("doc_type", "submitting_party", "opens_correctly", "open_error",
                    "content_hash", "artifact_ref", "today", "partial", "signed",
                    "signature_expected", "version_conflict_key", "wrong_context",
                    "sale_price", "commission_amount", "appraised_value",
                    "contract_price", "repair_requests_present", "exception_found",
                    "exception_text", "receipt_confirmed", "stated_deadline")

def _env(frm, to, intent, ctx, payload, confidence=UNKNOWN, in_reply_to=None):
    return Envelope(from_agent=frm, to_agent=to, intent=intent,
                    client_context_id=ctx, payload=payload,
                    confidence=confidence, in_reply_to=in_reply_to,
                    provenance={"source": f"spoke-{frm}", "captured_at": "runtime",
                                "verbatim_available": True})


def _flatten_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _flatten_strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _flatten_strings(v)


class Spoke11ClientCommunication:
    """DECISIONS.md tuples implemented directly:
      1. reply mixes routine + advice -> answer neither, split and route
         both. Soft finding, not resolved here: the "split" is a label
         (split="routine_only") on the lead.reply sent to the owning
         agent, not an actual text extraction - the full raw message
         (including the advice portion) is what's forwarded. Real
         sentence-splitting would be invented NLP logic this review
         won't guess at; flagging rather than pretending it's done.
      2. client is angry -> amended 2026-10-12 (owner decision): straight
         to the human (escalation.complaint, verbatim), logged to 14,
         outbound held (P14 step 2); nothing is sent to the client. The
         tuple used to say acknowledge, which conflicted with P14's
         human-only response; the owner resolved it for P14.
      3. two agents report conflicting statuses -> send nothing,
         clarification. Fixed 2026-07-16: the conflict-detection logic
         only ran for status.update - deadline.alert and
         client.message.request shared the same outer branch but had no
         equivalent check, despite the tuple being written generically
         and covering any of the three update types this agent receives.
      4. urgent alert inside quiet hours -> send only if config marks that
         class exempt, otherwise wake human not client
      5. 'what would you do?' -> escalation.legal_line, verbatim
      6. pricing/strategy question -> Legal Line, template ack + human handoff
      7. message would go out after legal contact hours -> queue for next
         window, urgency claim requires human override
      8. template variable unresolved -> does not send, blank-fill is
         fabrication
      9. client references an off-log conversation -> acknowledge + ask
         for particulars, never pretend recall
      10. negative-tone reply -> route P14 complaint intake, never
          freestyle de-escalation. Fixed 2026-07-16: this never actually
          escalated via escalation.complaint at all - it only tagged a
          lead.reply to the owning business agent, which has no
          relationship to P14's real mechanism. Checked the playbook
          directly (see tuple 2's note): step 1 is escalation.complaint
          verbatim, step 2 is the outbound hold. Both now real.
      11. contact-channel change request -> honor immediately, record via
          14, confirm once
    """

    # TUNABLE (owner-ratified 2026-07-16): quiet_hours=(21, 8).
    # See docs/TUNING_MANUAL.md to change.
    def __init__(self, hub, quiet_hours: tuple[int, int] = (21, 8),
                 exempt_alert_classes: set[str] | None = None):
        self.hub = guard(hub, "11")   # handoff rule (audit TU-2)
        self.quiet_hours = quiet_hours  # (start_hour, end_hour), wraps midnight
        self.exempt_alert_classes = exempt_alert_classes or set()
        self.pending_conflict: dict[str, list] = {}  # ctx -> conflicting statuses
        self.pending_showing_requests: dict[str, dict] = {}  # ctx -> held request
        self.awaiting_human_response: dict[str, bool] = {}  # ctx -> escalated, awaiting human
        # P14 (Complaint Response playbook) step 2: "Outbound HOLD for that
        # client context - no scheduled touches fire" once a complaint is
        # open. Was missing entirely - neither tuple 2 (angry) nor tuple 10
        # (negative tone) implemented this half of the playbook.
        self.complaint_hold: set[str] = set()
        # client replies held for the broker (owner decision #6)
        self.held_replies: dict[str, dict] = {}
        # consent as 14 last reported it, per context (opt-out check before
        # every client send - 2026-10-12 doc review: none existed)
        self.consent_seen: dict[str, dict] = {}
        self.no_consent_reported: set[str] = set()   # broker told once per client
        self._consent_check_open: str | None = None
        self._last_block = None   # why the last client message did not go (P11, 2026-10-21)
        register_spoke(hub, "11", self)
        register_resumer(hub, "11", self._resume)

    def _in_quiet_hours(self, hour: int) -> bool:
        start, end = self.quiet_hours
        if start > end:  # wraps midnight, e.g. 21 -> 8
            return hour >= start or hour < end
        return start <= hour < end

    def _advice_hit(self, text: str) -> str | None:
        low = text.lower()
        for w in _ADVICE_WORDS:
            if w in low:
                return text.strip()
        return None

    def _wire_hit(self, payload: dict) -> bool:
        text = " ".join(_flatten_strings(payload)).lower()
        return any(w in text for w in _WIRE_WORDS)

    def _route_lead_reply(self, ctx: str, owner, body: dict, env: Envelope | None) -> dict:
        """Sends lead.reply to the owning agent only when the reply names
        one and that agent has a lead.reply handler. Otherwise the whole
        thread holds for the broker (owner decision 2026-10-11, #6): no
        default owner is guessed (it used to be 13), and nothing moves until
        a signed continue naming the agent (route_to) or a cancel."""
        eid = env.envelope_id if env else "internal"
        if owner is None or str(owner) not in LEAD_REPLY_HANDLERS:
            why = ("names no owning agent" if owner is None else
                   f"names owning_agent {str(owner)!r}, which has no lead.reply handler")
            self.hub.ingest_spoke_trace(
                "11", eid,
                thought=f"client reply {why} - holding the thread for the broker, "
                        f"never guessing an owner",
                result="held: lead_reply_owner")
            self.held_replies[ctx] = dict(body)
            return hold_for_human(
                self.hub, "11", ctx, "lead.reply",
                f"client reply {why}. Continue with route_to = one of "
                f"{sorted(LEAD_REPLY_HANDLERS)} to deliver it there; cancel to "
                f"close the thread (the reply stays on the record).",
                {"route_to": None, "verbatim": body.get("message"), "lead_reply": body})
        # a reject / dead.letter is handled by HandoffGuard (handoff.failed +
        # clarification.request with the failed envelope, which carries the
        # client's message)
        return self.hub.send(_env("11", str(owner), "lead.reply", ctx, body))

    def _resume(self, ws, decision_payload: dict):
        """The broker's signed decision on a held client reply."""
        ctx = ws.client_context_id
        d = decision_of(decision_payload)
        if ctx not in self.held_replies or d == "other":
            self.hub.ingest_spoke_trace("11", ws.wait_id,
                                        thought=f"decision {decision_payload.get('decision')!r} for "
                                                f"{ctx!r}: nothing held or not continue/cancel - unchanged",
                                        result="unchanged")
            return "unchanged"
        if d == "continue":
            route_to = (decision_payload.get("updated_fields") or {}).get("route_to") \
                or ws.original_payload.get("route_to")
            if str(route_to) not in LEAD_REPLY_HANDLERS:
                self.hub.ingest_spoke_trace("11", ws.wait_id,
                                            thought=f"continue named route_to={route_to!r}, which "
                                                    f"has no lead.reply handler - still held",
                                            result="still held")
                hold_for_human(self.hub, "11", ctx, "lead.reply",
                               f"continue named route_to={route_to!r}; it must be one of "
                               f"{sorted(LEAD_REPLY_HANDLERS)}",
                               {"route_to": None, "verbatim": self.held_replies[ctx].get("message"),
                                "lead_reply": self.held_replies[ctx]})
                return "still held: bad route_to"
            body = self.held_replies.pop(ctx)
            self.hub.send(_env("11", str(route_to), "lead.reply", ctx, body))
            return f"delivered to {route_to}"
        body = self.held_replies.pop(ctx)
        self.hub.ingest_spoke_trace("11", ws.wait_id,
                                    thought=f"broker cancelled the held reply thread {ctx!r}",
                                    result="cancelled")
        self.hub.send(_env("11", "14", "interaction.log", ctx,
                           {"kind": "reply_thread_cancelled", "verbatim": body.get("message")}))
        return "cancelled"

    def _send_client_message(self, ctx: str, template: str, variables: dict,
                             hour: int, alert_class: str | None = None,
                             env: Envelope | None = None):
        # P14 hold, every send (2026-10-14): only scheduled touches were held,
        # so a client who wrote angrily and also asked a pricing question got
        # the automatic hand-off note. The opt-out confirmation still goes.
        if ctx in self.complaint_hold and template != "opt_out_confirmed":
            self.hub.ingest_spoke_trace(
                "11", env.envelope_id if env else "internal",
                thought=f"complaint hold open for {ctx!r} - {template!r} not sent; "
                        f"the response to this client is the human's",
                result="held: complaint_hold")
            self.hub.send(_env("11", "14", "interaction.log", ctx,
                               {"kind": "touch_held_complaint_hold", "template": template}))
            self._last_block = "complaint_hold"
            return False
        # tuple 8: unresolved template variable -> does not send
        unresolved = [k for k, v in variables.items() if v is None]
        if unresolved:
            self.hub.ingest_spoke_trace(
                "11", env.envelope_id if env else "internal",
                thought=f"template {template!r} has unresolved variables "
                        f"{unresolved} - a blank filled by guess is a "
                        f"fabrication to a client, not sending",
                result="held: unresolved_template_variable")
            self.hub.send(_env("11", "queue", "clarification.request", ctx,
                               {"reason": f"unresolved template variables: "
                                         f"{unresolved}"}))
            self._last_block = "unresolved_variables"
            return False

        # tuple 4/7: quiet hours / legal contact hours gate
        if self._in_quiet_hours(hour) and alert_class not in self.exempt_alert_classes:
            self.hub.ingest_spoke_trace(
                "11", env.envelope_id if env else "internal",
                thought=f"send would land inside quiet hours (hour={hour}) "
                        f"and alert_class={alert_class!r} is not config-"
                        f"exempt - queuing for the next window, waking the "
                        f"human instead of the client",
                result="queued: quiet_hours")
            self.hub.send(_env("11", "queue", "clarification.request", ctx,
                               {"reason": "send queued - quiet hours, "
                                         "human notified instead"}))
            self._last_block = "quiet_hours"
            return False

        # consent check against 14, the system of record for consent.
        # Owner decision 2026-10-12: a client message needs consent on
        # record - at least one channel marked "yes" at 14. No consent on
        # record, or an opt-out on every channel, blocks the send; each
        # blocked send is logged to 14 and the broker is told once per
        # client. The one opt-out confirmation (01's tuple 15) still goes.
        if template != "opt_out_confirmed":
            self.consent_seen.pop(ctx, None)
            self._consent_check_open = ctx
            try:
                self.hub.send(_env("11", "14", "record.request", ctx,
                                   {"purpose": "consent_check"}))
            finally:
                self._consent_check_open = None
            consent = self.consent_seen.pop(ctx, None) or {}
            if not any(v == "yes" for v in consent.values()):
                opted_out = bool(consent) and all(v == "no" for v in consent.values())
                why = "opted_out" if opted_out else "no_consent"
                self.hub.ingest_spoke_trace(
                    "11", env.envelope_id if env else "internal",
                    thought=f"14 records {'an opt-out on every channel' if opted_out else 'no consent on any channel'} "
                            f"for {ctx!r} - {template!r} is not sent",
                    result=f"blocked: {why}")
                self.hub.send(_env("11", "14", "interaction.log", ctx,
                                   {"kind": f"send_blocked_{why}", "template": template}))
                if why == "no_consent" and ctx not in self.no_consent_reported:
                    self.no_consent_reported.add(ctx)
                    self.hub.send(_env("11", "queue", "clarification.request", ctx,
                                       {"reason": "client messages are not being sent - no "
                                                  "consent on record at 14; record the client's "
                                                  "consent with a signed consent_record",
                                        "first_blocked_template": template}))
                self._last_block = why
                return False
        self.hub.send(_env("11", "external", "client.message.send", ctx,
                           {"template": template, "variables": variables}))
        self.hub.send(_env("11", "14", "interaction.log", ctx,
                           {"kind": "client_touch", "template": template}))
        return True

    def _tell_not_sent(self, env: Envelope, why: str):
        """P11 sign-off (2026-10-21): a nurture touch that did not go out is
        reported back to Agent 03, so it is not counted as sent; 03 tries
        it again on its next clock check (or stops the sequence on an
        opt-out). Before, 03 counted every touch it handed over as sent."""
        p = env.payload or {}
        if env.from_agent != "03" or p.get("template") != "sequence_touch":
            return
        self.hub.send(_env("11", "03", "client.message.not_sent", env.client_context_id,
                           {"template": "sequence_touch",
                            "touch": (p.get("content") or {}).get("touch"),
                            "reason": why}))

    def _consent_from_14(self, ctx: str) -> dict:
        """Consent as Agent 14 records it now (the same in-step answer the
        consent check before every send uses)."""
        self.consent_seen.pop(ctx, None)
        self._consent_check_open = ctx
        try:
            self.hub.send(_env("11", "14", "record.request", ctx,
                               {"purpose": "consent_check"}))
        finally:
            self._consent_check_open = None
        return self.consent_seen.pop(ctx, None) or {}

    # request_market_update() and the data.package -> client branch were
    # removed 2026-10-12 (owner decision J5): the request asked Agent 10 for
    # NEIGHBORHOOD data (the same steering risk as Agent 13's path removed in
    # 7b), nothing called it, and any market package that reached 11 was
    # forwarded to the client - including comps a broker had asked for to
    # make a pricing decision. Market data now goes only to the broker
    # (human) and to Agent 19 (owner decision 7c).

    def handle(self, env: Envelope):
        ctx = env.client_context_id
        payload = env.payload

        if env.intent == "config.update":
            resolved_ctx = payload.get("resolve_advice_response")
            if resolved_ctx:
                self.awaiting_human_response.pop(resolved_ctx, None)
                self.hub.send(_env("11", "18", "agent.status", resolved_ctx,
                                   {"waiting_on": "human_advice_response",
                                    "resolved": True}))
            resolved_complaint_ctx = payload.get("resolve_complaint_hold")
            if resolved_complaint_ctx:
                # P14: "hold released only on human direction"
                self.complaint_hold.discard(resolved_complaint_ctx)
                self.hub.send(_env("11", "14", "interaction.log",
                                   resolved_complaint_ctx,
                                   {"kind": "complaint_hold_released"}))
            return

        if env.intent in ("status.update", "deadline.alert", "client.message.request"):
            if payload.get("template") == "__p14_complaint_hold__":
                # Reserved P14 control (see 20's complaint branch) - arms
                # the outbound hold, renders NOTHING, sends NOTHING to any
                # client. Released only by the human's
                # resolve_complaint_hold, same as the 11-sourced path.
                self.complaint_hold.add(ctx)
                self.hub.ingest_spoke_trace(
                    "11", env.envelope_id,
                    thought=f"complaint hold armed for ctx={ctx!r} from a "
                            f"20-sourced escalation - all scheduled touches "
                            f"for this context hold until human release",
                    result="complaint_hold_armed")
                self.hub.send(_env("11", "14", "interaction.log", ctx,
                                   {"kind": "complaint_hold_armed",
                                    "source": "20"}))
                return
            if env.intent == "client.message.request" and "template" not in payload:
                # A request with no template is not a message to send: it is
                # a client's own question that needs a person's answer (03's
                # substantive drip reply, tuple 03-11: "a gated
                # human-reviewed reply"). Fixed 2026-10-27 (found writing the
                # tuple procedure pages): the template defaulted to the
                # intent name and the client's own question went back out to
                # the client with no person in between. Now nothing is sent;
                # the broker gets the question to answer.
                verbatim = payload.get("verbatim", "")
                self.hub.ingest_spoke_trace(
                    "11", env.envelope_id,
                    thought=f"no template from {env.from_agent} for {ctx!r} - a question "
                            f"for a person to answer; nothing sent to the client",
                    result="held for the broker: reply needed")
                self.hub.send(_env("11", "queue", "clarification.request", ctx,
                                   {"reason": "reply needed: the client asked a question "
                                              "that needs your answer; nothing was sent",
                                    "from_agent": env.from_agent,
                                    "why": payload.get("reason", ""),
                                    "verbatim": verbatim}))
                self.hub.send(_env("11", "14", "interaction.log", ctx,
                                   {"kind": "reply_needed_from_broker",
                                    "verbatim": verbatim}))
                return
            hour = payload.get("hour", 12)
            alert_class = payload.get("alert_class")

            # P14 step 2: outbound hold - no scheduled touches fire while a
            # complaint is open for this context.
            if ctx in self.complaint_hold:
                self.hub.ingest_spoke_trace(
                    "11", env.envelope_id,
                    thought=f"ctx={ctx!r} has an open complaint hold (P14) - "
                            f"no scheduled touches fire until the human "
                            f"releases it",
                    result="held: complaint_hold")
                self.hub.send(_env("11", "14", "interaction.log", ctx,
                                   {"kind": "touch_held_complaint_hold"}))
                self._tell_not_sent(env, "complaint_hold")
                return

            # tuple 3: two agents report conflicting statuses -> send
            # nothing, clarification. Fixed 2026-07-16: this only ran for
            # status.update - deadline.alert and client.message.request
            # shared the same outer branch (any of the three can report on
            # the same milestone from a different agent) but had no
            # equivalent check at all.
            existing = self.pending_conflict.setdefault(ctx, [])
            conflict_key = payload.get("conflict_key")
            if conflict_key:
                prior = [s for s in existing if s.get("conflict_key") == conflict_key]
                if prior and prior[-1]["value"] != payload.get("value"):
                    self.hub.send(_env("11", "queue", "clarification.request",
                                       ctx, {"reason": "conflicting statuses "
                                                       "for the same milestone "
                                                       "- sending nothing"}))
                    existing.append({"conflict_key": conflict_key,
                                    "value": payload.get("value")})
                    return
                existing.append({"conflict_key": conflict_key,
                                "value": payload.get("value")})

            template = payload.get("template", env.intent)
            variables = payload.get("variables", {k: v for k, v in payload.items()
                                                  if k not in ("hour", "alert_class",
                                                              "template")})
            self._last_block = None
            if not self._send_client_message(ctx, template, variables, hour,
                                             alert_class, env):
                self._tell_not_sent(env, self._last_block or "not_sent")
            return

        if env.intent == "client.reply":
            message = str(payload.get("message", ""))
            low = message.lower()

            # Tags (owner decision 2026-10-14): set here from the client's
            # words (dispatcher/message_tags.py), or honored when an upstream
            # classifier sent the label. Any adverse message goes to the
            # human at once, before and whatever else it asks: the complaint
            # escalation and the outbound hold come first, and the other
            # rules below (wire, access, advice) still run.
            from .message_tags import tag_message, ADVERSE, FORWARDED
            tags = tag_message(message, payload)
            angry = "angry" in tags
            negative = "negative_tone" in tags
            if angry or negative:
                self.complaint_hold.add(ctx)  # P14 step 2: outbound hold
                self.hub.escalate("escalation.complaint",
                                  {"client_context_id": ctx,
                                   "trigger": "angry client contact" if angry
                                   else "negative-tone reply",
                                   "verbatim": message,
                                   "tags": {k: v for k, v in tags.items() if k in ADVERSE}})
                self.hub.send(_env("11", "14", "interaction.log", ctx,
                                   {"kind": "complaint_received", "verbatim": message,
                                    "routed_to": "escalation.complaint"}))
            forward = {k: True for k in FORWARDED if k in tags}

            # wire fraud line - checked first, any channel
            if self._wire_hit(payload):
                self.hub.escalate("escalation.legal_line",
                                  {"client_context_id": ctx,
                                   "trigger": f"client message contains wire "
                                             f"topic: {message!r}",
                                   "agent": "11"})
                return

            # access is the line (Agent 06 tuples 3 and 6). 2026-10-14 (tuple
            # runs): a client asking to "just let them in" or for a lockbox
            # combination reached nobody with that meaning - Agent 06 checks
            # its own showing requests, but a client's words come here and
            # were never forwarded. Same phrase list as Agent 06.
            from .listing_spokes_06 import _ACCESS_REQUEST_WORDS
            access = next((w for w in _ACCESS_REQUEST_WORDS if w in low), None)
            if access:
                self.hub.escalate("escalation.legal_line",
                                  {"client_context_id": ctx,
                                   "trigger": f"client message asks for property access "
                                             f"({access!r}) - never granted or transmitted "
                                             f"by an agent: {message!r}",
                                   "agent": "11"})
                self.hub.send(_env("11", "14", "interaction.log", ctx,
                                   {"kind": "access_request_refused", "verbatim": message}))
                return

            # tuple 5: "what would you do" -> legal line, verbatim
            if "what would you do" in low:
                self.hub.escalate("escalation.legal_line",
                                  {"client_context_id": ctx,
                                   "trigger": message, "agent": "11"})
                return

            advice_hit = self._advice_hit(message)
            # Unlike the license_scope/opens_correctly/receipt_confirmed
            # class of fix, this one doesn't gate whether real protective
            # action happens - both branches escalate to Legal Line either
            # way. The doctrine also structures these as two distinct
            # tuples: advice-only (6) is the general case, "mixed" (1) is
            # the specific exception requiring its own detected condition.
            # Defaulting to "assume mixed" would invert that relationship.
            routine_present = payload.get("has_routine_component", False)

            # tuple 1: mixes routine + advice -> answer neither, split+route both
            if advice_hit and routine_present:
                self.hub.escalate("escalation.legal_line",
                                  {"client_context_id": ctx,
                                   "trigger": advice_hit, "agent": "11"})
                self._route_lead_reply(ctx, payload.get("owning_agent"),
                                       {"message": message, "split": "routine_only",
                                        **forward}, env)
                return

            # tuple 6: pricing/strategy question -> legal line, template ack
            if advice_hit:
                self.hub.escalate("escalation.legal_line",
                                  {"client_context_id": ctx,
                                   "trigger": advice_hit, "agent": "11"})
                self.awaiting_human_response[ctx] = True
                self.hub.send(_env("11", "18", "agent.status", ctx,
                                   {"waiting_on": "human_advice_response",
                                    "since": payload.get("hour_date")}))
                self._send_client_message(ctx, "advice_ack_handoff", {},
                                          payload.get("hour", 12), env=env)
                return

            # tuple 2, amended 2026-10-12 (owner decision): an angry client
            # goes to the human at once and is logged; no message is sent to
            # the client (the acknowledgement was removed - P14: the entire
            # response is human). The escalation and log happen at the top
            # of this branch since 2026-10-14.
            if angry:
                return

            # tuple 10: negative tone -> route P14 complaint intake, never
            # freestyle de-escalation. P14 step 1 (escalation.complaint,
            # verbatim) and step 2 (the hold) happen at the top of this
            # branch; the reply also goes to the owning agent marked for P14.
            if negative:
                self._route_lead_reply(ctx, payload.get("owning_agent"),
                                       {"message": message, "route": "P14_complaint_intake",
                                        **forward}, env)
                return

            # tuple 11: contact-channel change -> honor, record, confirm once
            if payload.get("requests_channel_change"):
                new_channel = payload.get("new_channel")
                # A client explicitly asking to be reached via a channel
                # clearly implies consent for it - log the event AND
                # update 14's authoritative consent record, or a system
                # reading consent later would still see it as
                # unknown/no despite the client's explicit request.
                self.hub.send(_env("11", "14", "interaction.log", ctx,
                                   {"kind": "channel_change",
                                    "new_channel": new_channel,
                                    "consent": {new_channel: "yes"} if new_channel else {}}))
                # 2026-10-14 (plumbing, finding on 14-04): 14 keeps a "no"
                # the client gave earlier until you record a reconfirmation
                # (Agent 14 tuple 14), but the client was still told the
                # change was made. Confirm only what 14 now records.
                now = self._consent_from_14(ctx)
                if new_channel and now.get(new_channel) != "yes":
                    self.hub.send(_env("11", "14", "interaction.log", ctx,
                                       {"kind": "channel_change_not_confirmed",
                                        "new_channel": new_channel,
                                        "consent_on_record": now.get(new_channel)}))
                    self.hub.send(_env("11", "queue", "clarification.request", ctx,
                                       {"reason": f"client asked to be reached by {new_channel!r}, "
                                                  f"which they opted out of earlier; the opt-out "
                                                  f"stands and nothing was confirmed to the client. "
                                                  f"To honor the request, record a signed "
                                                  f"consent_record with reconfirmed_by_client: true",
                                        "verbatim": message}))
                    return
                self._send_client_message(ctx, "channel_change_confirmed", {},
                                          payload.get("hour", 12), env=env)
                return

            # tuple 9: references an off-log conversation -> acknowledge +
            # ask for particulars, never pretend recall
            if payload.get("references_unlogged_conversation"):
                self._send_client_message(ctx, "ask_for_particulars", {},
                                          payload.get("hour", 12), env=env)
                return

            # client-requested showing -> query 14 for the facts 06
            # requires (buyer_agreement_on_file, requester_identity_
            # verified - 14 is system of record for these, same pattern as
            # consent), then send a genuinely complete showing.request
            # directly to 06 - using 11's own documented edge for real,
            # not routing around the problem.
            if payload.get("requests_showing"):
                self.pending_showing_requests[ctx] = {
                    "requested_time": payload.get("requested_time"),
                    # fixed 2026-10-11: the listing never reached 06, so
                    # showings of one property by two buyers could not
                    # conflict
                    "listing_id": payload.get("listing_id") or payload.get("requested_listing_id"),
                    "protected_deadline": payload.get("protected_deadline", False),
                    # when the client wrote: Agent 06 measures notice from it
                    # (2026-10-14)
                    "sent_at": payload.get("sent_at")}
                self.hub.send(_env("11", "14", "record.request", ctx, {}))
                return

            # showing-related reply -> route to 06
            if payload.get("about_showing"):
                if payload.get("no_show"):
                    self.hub.send(_env("11", "06", "showing.no_show", ctx,
                                       {"message": message}))
                else:
                    self.hub.send(_env("11", "06", "showing.feedback_response",
                                       ctx, {"message": message}))
                return

            # document submission -> route to 08
            if payload.get("document_attached"):
                # Forward every document field Agent 08 reads, verbatim and
                # only when present. Fixed 2026-10-11 (real-traffic check):
                # only four fields were forwarded, so a settlement statement's
                # sale price, signature status and date never reached 08 - and
                # the commission was computed from nothing. The tests had sent
                # document.submission to 08 directly with every field filled.
                self.hub.send(_env("11", "08", "document.submission", ctx,
                                   {k: payload[k] for k in _DOCUMENT_FIELDS
                                    if k in payload}))
                return

            # routine reply -> route to owning agent (by content, per the
            # swarm-wide "routed by content" convention this agent
            # implements for real)
            self._route_lead_reply(ctx, payload.get("owning_agent"),
                                   {"message": message, **forward}, env)
            return

        if env.intent == "record.response":
            if getattr(self, "_consent_check_open", None) == ctx:
                # the answer to the consent check before a client send
                self.consent_seen[ctx] = dict(payload.get("consent") or {})
                return
            pending = self.pending_showing_requests.pop(ctx, None)
            if pending is None:
                return
            buyer_agreement = payload.get("buyer_agreement_on_file", False)
            identity_verified = payload.get("requester_identity_verified", False)
            if not buyer_agreement:
                # 14 doesn't have this on file - not 11's call to schedule
                # around it; route to 13 (which owns getting it signed)
                # rather than send an incomplete request 06 would bounce.
                self.hub.send(_env("11", "13", "lead.reply", ctx,
                                   {"reason": "showing requested, no buyer "
                                             "agreement on file yet",
                                    "requested_time": pending["requested_time"]}))
                return
            # lead tier relayed from 14's record (02 logged it there), the
            # same relay 13 uses - never taken from the client's message
            tier = None
            for e in payload.get("entries", []):
                t = (e.get("payload") or {}).get("tier")
                if t:
                    tier = t
            self.hub.send(_env("11", "06", "showing.request", ctx,
                               {"requested_time": pending["requested_time"],
                                "listing_id": pending.get("listing_id"),
                                "protected_deadline": pending.get("protected_deadline", False),
                                "sent_at": pending.get("sent_at"),
                                "lead_tier": tier,
                                "buyer_agreement_on_file": buyer_agreement,
                                "requester_identity_verified": identity_verified}))
            return
