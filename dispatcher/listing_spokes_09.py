"""Agent 09 - Vendor Coordination, built against the full spec.

Manages the service provider network. Schedules only roster vendors with
current credentials. RESPA Section 8 (referral compensation with
settlement service providers) is human/counsel territory, absolute.
"""
from __future__ import annotations

from .core import Envelope
from .handoff_guard import guard, register as register_spoke
from .human_holds import hold_for_human, decision_of, register_resumer

SOURCE_VERIFIED = "source_verified"
STATED_BY_PARTY = "stated_by_party"
UNKNOWN = "unknown"


def _env(frm, to, intent, ctx, payload, confidence=UNKNOWN):
    return Envelope(from_agent=frm, to_agent=to, intent=intent,
                    client_context_id=ctx, payload=payload,
                    confidence=confidence,
                    provenance={"source": f"spoke-{frm}", "captured_at": "runtime",
                                "verbatim_available": True})


class Spoke09VendorCoordination:
    """DECISIONS.md tuples implemented directly:
      1. vendor cancels late -> notify 07/06 immediately + roster
         alternatives; regulated roles never auto-rebooked without human.
         Fixed 2026-07-16: 09 had no route to 06 at all, and the
         "immediate" notification to 07 was actually the 7-day holdup
         timer - built for silence/non-response, the wrong mechanism for
         a definitive cancellation. Added a real, direct
         vendor.cancellation_notice route to both.
      2. credential expires mid-engagement -> flag before any next scheduling
      3. vendor proposes rate change mid-job -> halt + human, RESPA-adjacent
      4. deliverable arrives partial -> report partial truthfully, never
         mark collected
      5. two agents request same vendor slot -> deadline-driven request
         wins, ties to human
      6. vendor not on approved list -> refuse to schedule, propose
         addition to human; urgency creates no approval
      7. vendor requests property access codes -> custody protocol only,
         never ride vendor messages
      8. completion claimed without proof artifact -> status stays open
      9. invoice differs from quote -> log both, human; never approve
         variances
      10. vendor no-show on deadline-critical job -> escalate + offer next
          approved vendor to human, never self-substitute
      11. work scope grows on-site -> stop-work message per template,
          scope changes are human-approved

    Tuples 1 and 10 (2026-10-12): the hold and the cancellation notices
    carry the roster's other vendors of the same kind (credentials checked
    when the event carries a date) as roster_alternatives; the broker
    picks, nothing is booked by this agent.
    """

    def __init__(self, hub, roster: dict[str, dict] | None = None):
        self.hub = guard(hub, "09")   # handoff rule (audit TU-2)
        # roster: vendor_id -> {kind, license_expiry, insurance_expiry,
        #                        regulated (bool)}. Human-approved additions
        # only - empty/unset means nothing is approved yet (fail closed).
        self.roster = roster or {}
        self.scheduled: dict[str, dict[str, dict]] = {}  # ctx -> milestone -> {vendor_id, time}
        self.slot_holds: dict[str, str] = {}  # (property, time) key -> ctx holding it
        # deliveries held because the booking never reached the vendor
        # (2026-10-21): ctx -> kind -> the vendor's report, until you decide
        self.held_deliveries: dict[str, dict[str, dict]] = {}
        register_spoke(hub, "09", self)
        register_resumer(hub, "09", self._resume)

    def _credentials_current(self, vendor_id: str, today: str) -> bool:
        v = self.roster.get(vendor_id)
        if not v:
            return False
        import datetime
        today_d = datetime.date.fromisoformat(today)
        for field in ("license_expiry", "insurance_expiry"):
            exp = v.get(field)
            if not exp or datetime.date.fromisoformat(exp) < today_d:
                return False
        return True

    def _roster_alternatives(self, kind, exclude, today) -> dict:
        """Tuples 1 and 10 (offer roster alternatives / the next approved
        vendor to the human; added 2026-10-12): the other roster vendors of
        the same kind. With a date their credentials are checked and only
        current ones are listed; without one they are listed unchecked and
        the record says so. The human picks; nothing is booked here."""
        others = sorted(vid for vid, v in self.roster.items()
                        if v.get("kind") == kind and vid != exclude)
        if today:
            others = [vid for vid in others if self._credentials_current(vid, today)]
        return {"vendors": others, "credentials_checked_on": today or None}

    def _accept_delivery(self, ctx: str, kind, payload: dict, source_id: str):
        """A verified, proven delivery goes on: photos to 05, documents to 08."""
        target = "05" if kind == "photography" else "08"
        self.hub.send(_env("09", "18", "agent.status", ctx,
                           {"waiting_on": f"vendor_deliverable:{kind}",
                            "resolved": True}))
        self.hub.send(_env("09", target, "deliverable.release", ctx,
                           {"doc_type": payload.get("doc_type"),
                            "opens_correctly": True,
                            "content_hash": payload.get("content_hash"),
                            "appraised_value": payload.get("appraised_value"),
                            "contract_price": payload.get("contract_price"),
                            "repair_requests_present":
                                payload.get("repair_requests_present"),
                            "exception_found": payload.get("exception_found"),
                            "exception_text": payload.get("exception_text")},
                           confidence=SOURCE_VERIFIED))
        self.hub.ingest_spoke_trace(
            "09", source_id,
            thought=f"{kind!r} deliverable verified present and opens - "
                    f"routing to {target}",
            result=f"deliverable.release -> {target}")

    def _resume(self, ws, decision_payload: dict):
        """Your decision on a delivery whose booking never reached the vendor."""
        ctx = ws.client_context_id
        kind = (ws.original_payload or {}).get("kind")
        d = decision_of(decision_payload)
        held = (self.held_deliveries.get(ctx) or {}).get(kind)
        if held is None or d == "other":
            return "nothing held" if held is None else "decision not continue/cancel"
        self.held_deliveries[ctx].pop(kind)
        if d == "continue":
            self._accept_delivery(ctx, kind, held, ws.wait_id)
            return f"{kind} delivery accepted on your decision"
        self.hub.send(_env("09", "14", "interaction.log", ctx,
                           {"kind": "delivery_not_accepted", "vendor_kind": kind,
                            "reason": "the booking never reached the vendor; you declined it"}))
        return f"{kind} delivery not accepted"

    def handle(self, env: Envelope):
        ctx = env.client_context_id
        payload = env.payload

        if env.intent == "vendor.request":
            vendor_id = payload.get("vendor_id")
            kind = payload.get("kind")
            today = payload.get("today")
            # Fail closed (fixed 2026-10-11, scene run): 05 and 07 sent
            # vendor.request with no date, and every credential check below
            # is skipped when there is no date - so in real traffic an
            # expired license or lapsed insurance was never caught. No date
            # = credentials cannot be checked = nothing is booked.
            if not today:
                self.hub.send(_env("09", "queue", "clarification.request", ctx,
                                   {"reason": f"vendor.request for {kind!r} has no "
                                              f"date - credentials cannot be "
                                              f"checked, nothing scheduled"}))
                return

            # Real fail-open, found 2026-07-17 by reading (invisible to the
            # .get-default sweeps): a vendor.request with NO vendor_id
            # skipped the roster gate AND the credential gate below (both
            # guarded by `if vendor_id ...`) and confirmed scheduling with
            # vendor_id=None - and that is exactly what P01 Phase 1b sends
            # ({"kind": "photography"}). Tuple 6's own doctrine: empty/
            # unset roster means nothing is approved yet, fail closed.
            # Now: no vendor named -> select from the approved roster by
            # kind (credentials current where checkable); no approved
            # vendor of that kind -> clarification, never a None booking.
            if not vendor_id:
                candidates = [vid for vid, v in self.roster.items()
                              if v.get("kind") == kind
                              and (not today or self._credentials_current(vid, today))]
                lapsed = sorted(vid for vid, v in self.roster.items()
                                if v.get("kind") == kind and vid not in candidates)
                if not candidates and lapsed:
                    # tuple 2 (found 2026-10-14, tuple runs): requesters never
                    # name a vendor, so the credential gate below was never
                    # reached. A roster whose only vendors of this kind have
                    # lapsed credentials was reported as "no approved vendor",
                    # hiding the expiry the tuple says to flag.
                    self.hub.escalate("escalation.legal_line",
                                      {"client_context_id": ctx,
                                       "trigger": f"roster vendor(s) {lapsed} for kind {kind!r} "
                                                  f"have credentials expired or missing - "
                                                  f"flagged before scheduling, nothing scheduled",
                                       "agent": "09"})
                    return
                if not candidates:
                    self.hub.send(_env("09", "queue", "clarification.request",
                                       ctx, {"reason": f"no approved roster "
                                                       f"vendor for kind "
                                                       f"{kind!r} - nothing "
                                                       f"scheduled, urgency "
                                                       f"does not create "
                                                       f"approval"}))
                    return
                vendor_id = sorted(candidates)[0]  # deterministic pick

            # tuple 6: not on approved list -> refuse, propose addition to
            # human; urgency creates no approval
            if vendor_id and vendor_id not in self.roster:
                self.hub.send(_env("09", "queue", "clarification.request", ctx,
                                   {"reason": f"vendor {vendor_id!r} not on "
                                             f"the approved roster - "
                                             f"proposing addition to human, "
                                             f"urgency does not create "
                                             f"approval"}))
                return

            # tuple 2/credential gate: expired or missing = flag before
            # scheduling
            if vendor_id and today and not self._credentials_current(vendor_id, today):
                self.hub.escalate("escalation.legal_line",
                                  {"client_context_id": ctx,
                                   "trigger": f"vendor {vendor_id!r} "
                                             f"credentials expired or "
                                             f"missing - flagged before "
                                             f"scheduling",
                                   "agent": "09"})
                return

            # tuple 5: same slot requested by two agents -> deadline-driven
            # wins, ties to human. Compare against the ACTUAL stored
            # priority of whoever holds the slot, not an externally-
            # supplied field a second requester couldn't legitimately know.
            slot_key = payload.get("slot_key")
            if slot_key:
                held = self.slot_holds.get(slot_key)
                incoming_priority = payload.get("deadline_priority", 0)
                if held and held["ctx"] != ctx:
                    existing_priority = held["priority"]
                    if incoming_priority == existing_priority:
                        self.hub.send(_env("09", "queue", "clarification.request",
                                           ctx, {"reason": "vendor slot "
                                                           "contention, tied "
                                                           "priority - human "
                                                           "decides"}))
                        return
                    if incoming_priority <= existing_priority:
                        self.hub.send(_env("09", "queue", "clarification.request",
                                           ctx, {"reason": "vendor slot "
                                                           "already held by "
                                                           "a higher/equal "
                                                           "priority request"}))
                        return
                self.slot_holds[slot_key] = {"ctx": ctx, "priority": incoming_priority}

            booking = _env("09", "external", "vendor.schedule", ctx,
                           {"vendor_id": vendor_id, "kind": kind})
            self.scheduled.setdefault(ctx, {})[kind] = {
                "vendor_id": vendor_id, "confirmed": True,
                "booking_envelope": booking.envelope_id}
            self.hub.send(booking)
            if today:
                self.hub.send(_env("09", "18", "agent.status", ctx,
                                   {"waiting_on": f"vendor_deliverable:{kind}",
                                    "since": today}))
            # Real bug found in Agent 18's review 2026-07-16: this send
            # never included 'day' or 'timezone_confirmed' at all - same
            # class of gap as Agent 06's identical fix. Uses 'today' as
            # the day value since vendor.request has no distinct future
            # appointment-date field of its own yet (a separate, smaller
            # gap - vendor appointments aren't currently tracked against
            # a specific future date, only the day the request was made).
            self.hub.send(_env("09", "18", "calendar.event", ctx,
                               {"event": f"vendor_{kind}", "vendor_id": vendor_id,
                                "day": today, "timezone_confirmed": True}))
            self.hub.ingest_spoke_trace(
                "09", env.envelope_id,
                thought=f"vendor {vendor_id!r} ({kind}) on roster, "
                        f"credentials current - scheduled",
                result="scheduled")
            return

        if env.intent == "vendor.event" and payload.get("event_kind") == "cancellation":
            kind = payload.get("kind")
            vendor_id = payload.get("vendor_id")
            # Derive from OWNED roster state, not the incoming event's own
            # claim - 09 already knows which roles are regulated; trusting
            # a self-reported flag on the cancellation event itself is the
            # same class of bug as trusting an echoed doc_type in Agent 08.
            regulated = self.roster.get(vendor_id, {}).get("regulated", True)
            alternatives = self._roster_alternatives(kind, vendor_id, payload.get("today"))
            # tuple 1: notify 07/06 IMMEDIATELY - not the 7-day holdup
            # timer (built for silence/non-response, the wrong mechanism
            # for a definitive cancellation) and not silence for 06
            # (previously unreachable - no route existed at all).
            self.hub.send(_env("09", "07", "vendor.cancellation_notice", ctx,
                               {"vendor_kind": kind, "vendor_id": vendor_id,
                                "roster_alternatives": alternatives}))
            self.hub.send(_env("09", "06", "vendor.cancellation_notice", ctx,
                               {"vendor_kind": kind, "vendor_id": vendor_id,
                                "roster_alternatives": alternatives}))
            self.hub.send(_env("09", "14", "interaction.log", ctx,
                               {"kind": "vendor_cancelled_late",
                                "vendor_kind": kind}))
            if regulated:
                # regulated roles never auto-rebooked without human
                self.hub.send(_env("09", "queue", "clarification.request", ctx,
                                   {"reason": f"regulated vendor role "
                                             f"{kind!r} cancelled late - "
                                             f"human picks the replacement, "
                                             f"never auto-rebooked",
                                    "roster_alternatives": alternatives}))
            return

        if env.intent == "vendor.event" and payload.get("event_kind") == "rate_change":
            self.hub.escalate("escalation.legal_line",
                              {"client_context_id": ctx,
                               "trigger": "vendor proposed a rate change "
                                         "mid-job - RESPA-adjacent "
                                         "territory, halted for human",
                               "agent": "09"})
            return

        if env.intent == "vendor.event" and payload.get("event_kind") == "access_code_request":
            # tuple 7: never rides vendor messages, custody protocol only
            self.hub.escalate("escalation.legal_line",
                              {"client_context_id": ctx,
                               "trigger": "vendor requested property access "
                                         "codes - custody protocol only, "
                                         "never transmitted via vendor "
                                         "messages",
                               "agent": "09"})
            return

        if env.intent == "vendor.event" and payload.get("event_kind") == "deliverable_report":
            kind = payload.get("kind")
            proof_present = payload.get("proof_artifact_present", False)
            partial = payload.get("partial", False)

            if not proof_present:
                # tuple 8: completion claimed without proof -> status stays
                # open, deliverable.release requires the proof
                self.hub.ingest_spoke_trace(
                    "09", env.envelope_id,
                    thought=f"{kind!r} completion claimed without a proof "
                            f"artifact - status stays open, no "
                            f"deliverable.release without proof",
                    result="not released: no_proof")
                return

            if partial:
                # tuple 4: partial -> report truthfully, never mark collected
                target = "05" if kind == "photography" else "08"
                self.hub.send(_env("09", target, "deliverable.release", ctx,
                                   {"doc_type": payload.get("doc_type"),
                                    "partial": True}))
                return

            # P01 review (2026-10-21): a delivery for a booking that never
            # reached the vendor (still held for your release, or declined)
            # is not accepted on its own: the booking must have gone out
            booked = (self.scheduled.get(ctx) or {}).get(kind) or {}
            if booked.get("booking_envelope"):
                state = self.hub.outbound_state(booked["booking_envelope"])
                if state != "sent":
                    self.held_deliveries.setdefault(ctx, {})[kind] = dict(payload)
                    why = ("is still waiting for your release" if state == "held"
                           else "was never sent to the vendor")
                    self.hub.ingest_spoke_trace(
                        "09", env.envelope_id,
                        thought=f"{kind!r} delivery arrived but our booking message {why} - "
                                f"not accepting it on my own",
                        result="held: booking not sent")
                    hold_for_human(self.hub, "09", ctx, "deliverable.release",
                                   f"A {kind} delivery arrived for {ctx}, but the booking message "
                                   f"to the vendor {why}. Continue = accept the delivery (the "
                                   f"booking was made some other way); cancel = do not accept it.",
                                   {"kind": kind, "booking_state": state,
                                    "content_hash": payload.get("content_hash")})
                    return
            self._accept_delivery(ctx, kind, payload, env.envelope_id)
            return

        if env.intent == "vendor.event" and payload.get("event_kind") == "invoice":
            quote = payload.get("quote_amount")
            invoice = payload.get("invoice_amount")
            if quote is not None and invoice is not None and quote != invoice:
                # tuple 9: differs from quote -> log both, human, never
                # approve variances
                self.hub.send(_env("09", "14", "interaction.log", ctx,
                                   {"kind": "invoice_variance",
                                    "quote": quote, "invoice": invoice}))
                self.hub.escalate("escalation.legal_line",
                                  {"client_context_id": ctx,
                                   "trigger": f"invoice {invoice} differs "
                                             f"from quote {quote} - human, "
                                             f"never auto-approved",
                                   "agent": "09"})
            return

        if env.intent == "vendor.event" and payload.get("event_kind") == "no_show":
            # Fail closed: unknown criticality is treated as critical, not
            # dismissed - same reasoning as the other two fixes here.
            deadline_critical = payload.get("deadline_critical", True)
            if deadline_critical:
                # tuple 10: escalate + offer next approved vendor to human,
                # never self-substitute
                self.hub.send(_env("09", "queue", "clarification.request", ctx,
                                   {"reason": "vendor no-show on a "
                                             "deadline-critical job - human "
                                             "picks the next approved "
                                             "vendor, never self-substituted",
                                    "roster_alternatives": self._roster_alternatives(
                                        payload.get("kind") or self.roster.get(
                                            payload.get("vendor_id"), {}).get("kind"),
                                        payload.get("vendor_id"), payload.get("today"))}))
            else:
                self.hub.send(_env("09", "14", "interaction.log", ctx,
                                   {"kind": "vendor_no_show",
                                    "deadline_critical": False}))
            return

        if env.intent == "vendor.event" and payload.get("event_kind") == "scope_change":
            # tuple 11: stop-work message per template, human-approved only.
            # Until the 2026-10-12 doc review the broker was told "stop work
            # order issued" while nothing was sent. The message now goes to
            # the vendor's channel; the hub holds it (counterparty audience)
            # until the broker signs its release.
            vendor_id = payload.get("vendor_id")
            res = self.hub.send(_env("09", "external", "vendor.schedule", ctx,
                                     {"vendor_id": vendor_id, "template": "stop_work_order",
                                      "kind": payload.get("kind")}))
            self.hub.send(_env("09", "queue", "clarification.request", ctx,
                               {"reason": "work scope grew on-site - a stop-work message to "
                                          "the vendor is "
                                          + ("held for your signed release"
                                             if isinstance(res, dict) and res.get("status") == "held"
                                             else f"not sent ({(res or {}).get('status')})")
                                          + "; scope changes are human-approved only",
                                "vendor_id": vendor_id}))
            return
