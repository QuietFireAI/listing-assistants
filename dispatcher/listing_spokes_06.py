"""Agent 06 - Showing Scheduler, built against the full spec.

Schedules people; never authorizes access. Access requests of any kind
are an absolute Legal Line, not a judgment call.
"""
from __future__ import annotations

from .core import Envelope
from .handoff_guard import guard, register as register_spoke
from .human_holds import hold_for_human, decision_of, register_resumer

_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

SOURCE_VERIFIED = "source_verified"
STATED_BY_PARTY = "stated_by_party"
UNKNOWN = "unknown"

_ACCESS_REQUEST_WORDS = ("let them in", "access code", "lockbox combo",
                        "gate code", "just let", "combo for the")


def _env(frm, to, intent, ctx, payload, confidence=UNKNOWN):
    return Envelope(from_agent=frm, to_agent=to, intent=intent,
                    client_context_id=ctx, payload=payload,
                    confidence=confidence,
                    provenance={"source": f"spoke-{frm}", "captured_at": "runtime",
                                "verbatim_available": True})


class Spoke06ShowingScheduler:
    """DECISIONS.md tuples implemented directly:
      1. calendar double-booking -> protected deadline wins; otherwise
         first-confirmed wins, alternatives offered. Fixed 2026-07-16:
         "protected deadline wins" used to mean "ignore the conflict
         check and schedule anyway" - both showings ended up marked
         confirmed, and the bumped party got no notification at all. Now
         the displaced showing is actually removed and its party notified.
      2. requester identity cannot be verified -> cancel the access-bearing
         appointment, no exceptions
      3. 'just let them in' -> refuse + escalation.legal_line, access is
         the line
      4. no-show -> log + feedback request, no reproach messaging
      5. same-day request on occupied property -> minimum-notice rules
         still apply, occupancy never squeezed
      6. access code/lockbox combo requested in a message -> never
         transmit, routes through custody protocol only
      7. request inside occupied-home notice window -> offer first legal
         slot, never ask seller to waive notice unprompted
      8. agent no-shows twice -> flag pattern to human before third confirm
      9. overlapping showings -> sequence with buffer, never double-book
         and hope. Fixed 2026-07-16: the conflict check was exact-time-
         match only - buffer_minutes rode along in the calendar.event
         payload as pure data, never compared against anything. Two
         showings 15 minutes apart with buffer_minutes=30 produced zero
         conflict detection. Now a real buffer-aware overlap check.
      10. feedback unanswered after two asks -> stop asking
      11. request for a property under contract -> confirm show-ability
          via 05 first, never assume active

    Open question, not resolved here: tuple 1's "alternatives offered"
    and tuples 5/7's "offer first legal slot" send a template name and a
    supporting number (required_notice_hours) to 11, not a computed
    alternative time - this may be intentional division of labor (11's
    template layer computes the real slot) rather than a gap. Not
    changed without confirming which it is.
    """

    # TUNABLE (owner-ratified 2026-07-16): feedback_ask_cap=2,
    # no_show_pattern_threshold=2. See docs/TUNING_MANUAL.md to change.
    def __init__(self, hub, min_notice_hours: dict[str, int] | None = None,
                 feedback_ask_cap: int = 2, no_show_pattern_threshold: int = 2):
        self.hub = guard(hub, "06")   # handoff rule (audit TU-2)
        # Where a showing's facts come from (owner decision 2026-10-14; an
        # onboarding setting): "listing_record" (default) reads occupancy,
        # status and state from Agent 05's signed listing record when the
        # listing is ours; "requester" takes them from the request.
        self.showing_facts_source = "listing_record"
        self.listing_facts: dict[str, dict] = {}   # listing_id -> facts pushed by 05
        self.feedback_ask_cap = feedback_ask_cap
        self.no_show_pattern_threshold = no_show_pattern_threshold
        self.confirmed_showings: dict[str, list[dict]] = {}  # ctx -> showings
        self.showing_agent_no_shows: dict[str, int] = {}  # requester_id -> count
        self.feedback_asks: dict[str, int] = {}  # showing_id -> ask count
        self.pending_status_checks: dict[str, dict] = {}  # ctx -> held request
        self.pending_bumps: dict[str, dict] = {}  # ctx -> held protected-bump request
        # per-state or per-property minimum notice hours for occupied homes
        self.min_notice_hours = min_notice_hours or {"default": 24}
        # P18 Seller Weekly Report (J3, 2026-10-12). Broker-signed:
        # {"weekday": 0-6, "listings": {listing_id: seller context}}. None = off.
        self.seller_reports: dict | None = None
        self.seller_report_weeks: dict[str, str] = {}   # listing_id -> ISO week reported
        self.held_reports: dict[str, dict] = {}         # seller ctx -> report awaiting the broker
        self.open_houses: dict[str, dict] = {}          # listing ctx -> the scheduled open house (P04)
        register_spoke(hub, "06", self)
        register_resumer(hub, "06", self._resume)

    def _schedule_open_house(self, ctx: str, env: Envelope) -> None:
        """P04 (built 2026-10-20; before, no entry scheduled an open house and
        the playbook could not start). The broker signs {"open_house":
        {"start": "2026-10-25T13:00", "end": "2026-10-25T15:00"}} on the
        listing. Held for the broker, nothing scheduled, when the listing is
        not active on the record Agent 05 pushed, or the times are not
        readable. Otherwise: the event goes on the calendar (18), signage is
        ordered through the vendor roster (09) and the schedule is logged
        (14). Promotion is the broker's signed campaign through Agent 12;
        walk-ins arrive as inquiries through Agent 01."""
        import datetime
        oh = env.payload.get("open_house")
        lid = (oh or {}).get("listing_id") or ctx if isinstance(oh, dict) else ctx
        problems = []
        if not isinstance(oh, dict) or not oh.get("start") or not oh.get("end"):
            problems.append("open_house takes start and end (YYYY-MM-DDTHH:MM)")
        else:
            try:
                if datetime.datetime.fromisoformat(oh["end"]) <= datetime.datetime.fromisoformat(oh["start"]):
                    problems.append("end must be after start")
            except ValueError:
                problems.append("start and end must be YYYY-MM-DDTHH:MM")
        facts = self.listing_facts.get(lid)
        if not problems and (facts is None or facts.get("status") != "active"):
            problems.append(f"listing {lid!r} is not active on the MLS record "
                            f"(status {(facts or {}).get('status')!r}) - an open house "
                            f"markets the property to the public")
        if problems:
            self.hub.send(_env("06", "queue", "clarification.request", ctx,
                               {"reason": "open house not scheduled; nothing changed",
                                "problems": problems}))
            return
        self.open_houses[ctx] = {"listing_id": lid, "start": oh["start"], "end": oh["end"],
                                 "status": "scheduled"}
        self.hub.send(_env("06", "18", "calendar.event", ctx,
                           {"event": "open_house", "time": oh["start"], "end": oh["end"],
                            "day": oh["start"][:10], "timezone_confirmed": True,
                            "buffer_minutes": 0}))
        self.hub.send(_env("06", "09", "vendor.request", ctx,
                           {"kind": "open_house_signage", "today": oh["start"][:10]}))
        self.hub.send(_env("06", "14", "interaction.log", ctx,
                           {"kind": "open_house_scheduled", "listing_id": lid,
                            "start": oh["start"], "end": oh["end"]}))
        self.hub.ingest_spoke_trace("06", env.envelope_id,
                                    thought=f"broker-signed open house for {lid!r} {oh['start']} to "
                                            f"{oh['end']}; listing active on the record",
                                    result="open house scheduled")

    def _record_open_house(self, ctx: str, env: Envelope) -> None:
        """P04's close: the broker signs {"open_house_result": {"attendees":
        12, "feedback": ["light traffic"]}} after the event; it is logged to
        Agent 14 as the open house event. Walk-ins are leads in their own
        right (Agent 01), not part of this record."""
        r = env.payload.get("open_house_result")
        oh = self.open_houses.get(ctx)
        if oh is None or not isinstance(r, dict) or not isinstance(r.get("attendees"), int) \
                or isinstance(r.get("attendees"), bool):
            self.hub.send(_env("06", "queue", "clarification.request", ctx,
                               {"reason": "open house result not recorded; nothing changed - "
                                          + ("no open house is scheduled for this listing"
                                             if oh is None else
                                             "attendees must be a whole number")}))
            return
        oh["status"] = "held"
        oh["attendees"] = r["attendees"]
        self.hub.send(_env("06", "14", "interaction.log", ctx,
                           {"kind": "open_house_event", "listing_id": oh["listing_id"],
                            "attendees": r["attendees"],
                            "feedback": [str(x) for x in r.get("feedback", [])]}))

    def _configure_seller_reports(self, env: Envelope) -> None:
        cfg = env.payload.get("seller_reports")
        problems = []
        if not isinstance(cfg, dict) or set(cfg) != {"weekday", "listings"}:
            problems.append('expected {"weekday": "<day>", "listings": {"<listing_id>": "<seller context>"}}')
        else:
            if str(cfg["weekday"]).lower() not in _WEEKDAYS:
                problems.append(f"weekday {cfg['weekday']!r} is not a day name")
            lst = cfg["listings"]
            if not isinstance(lst, dict) or not lst or not all(
                    isinstance(k, str) and k and isinstance(v, str) and v for k, v in lst.items()):
                problems.append("listings must map each listing id to the seller's context id")
        if problems:
            self.hub.send(_env("06", "queue", "clarification.request", env.client_context_id,
                               {"reason": "seller_reports setting rejected", "problems": problems}))
            return
        self.seller_reports = {"weekday": _WEEKDAYS.index(str(cfg["weekday"]).lower()),
                               "listings": dict(cfg["listings"])}
        self.hub.ingest_spoke_trace(
            "06", env.envelope_id,
            thought=f"weekly seller reports set by the broker's signature: "
                    f"{cfg['weekday']} for {sorted(cfg['listings'])}",
            result="seller_reports configured")

    def weekly_seller_reports(self, today: str):
        """Daily clock check, P18 (J3, 2026-10-12). On the broker's chosen
        weekday, for each listing in the signed setting: counts the showings
        confirmed for that listing in the 7 days ending today and how many of
        them have feedback, and holds the report for the broker. Continue
        sends it to the seller through Agent 11 (template
        seller_weekly_report); cancel skips this week. Numbers only - no
        free text - so there is nothing for Agent 17 to screen."""
        import datetime
        if not self.seller_reports:
            return "not_configured"
        day = datetime.date.fromisoformat(today)
        if day.weekday() != self.seller_reports["weekday"]:
            return "not_today"
        iso = day.isocalendar()
        week = f"{iso[0]}-W{iso[1]:02d}"
        start = day - datetime.timedelta(days=7)
        held = []
        for listing_id, seller_ctx in sorted(self.seller_reports["listings"].items()):
            if self.seller_report_weeks.get(listing_id) == week:
                continue
            shown = []
            for showings in self.confirmed_showings.values():
                for s in showings:
                    if s.get("listing_id") != listing_id or not s.get("time"):
                        continue
                    try:
                        d = datetime.date.fromisoformat(str(s["time"])[:10])
                    except ValueError:
                        continue
                    if start < d <= day:
                        shown.append(s)
            report = {"listing_id": listing_id, "week_ending": today,
                      "showings": len(shown),
                      "feedback_received": sum(1 for s in shown if s.get("feedback_received"))}
            self.seller_report_weeks[listing_id] = week
            self.held_reports[seller_ctx] = report
            hold_for_human(self.hub, "06", seller_ctx, "client.message.request",
                           f"weekly seller report for {listing_id}: {report['showings']} "
                           f"showing(s), {report['feedback_received']} with feedback. "
                           f"Continue = send it to the seller; cancel = skip this week.",
                           {"report": report})
            held.append(listing_id)
        return f"held:{held}" if held else "none_due"

    def _resume(self, ws, decision_payload: dict):
        """The broker's signed decision on a held weekly seller report."""
        ctx = ws.client_context_id
        d = decision_of(decision_payload)
        report = self.held_reports.get(ctx)
        if report is None or d == "other":
            return "nothing held for this context" if report is None else "decision not continue/cancel"
        self.held_reports.pop(ctx)
        if d == "cancel":
            self.hub.send(_env("06", "14", "interaction.log", ctx,
                               {"kind": "seller_report_skipped", **report}))
            return "cancelled: report not sent"
        self.hub.send(_env("06", "11", "client.message.request", ctx,
                           {"template": "seller_weekly_report", "variables": report}))
        return "continued: report sent to 11"

    def _with_listing_facts(self, payload: dict, env: Envelope) -> dict:
        """Owner decision 2026-10-14 (tuples 5, 7, 11): occupancy, status and
        state come from the signed listing record for a listing that is
        ours; for any other listing (a buyer touring another brokerage's
        listing) they come from the request, as before. Notice hours are
        measured from when the client wrote (sent_at) to the requested
        time; with no sent_at, the request's own figure (or none) stands."""
        import datetime
        lid = payload.get("listing_id")
        facts = self.listing_facts.get(lid) if lid else None
        if self.showing_facts_source == "listing_record" and facts is not None:
            occ = facts.get("occupancy")
            # unknown occupancy on our own listing is treated as occupied:
            # the notice rule protects whoever may live there
            payload["property_occupied"] = occ != "vacant"
            payload["possibly_under_contract"] = facts.get("status") != "active"
            if facts.get("state"):
                payload["state"] = facts["state"]
            self.hub.ingest_spoke_trace(
                "06", env.envelope_id,
                thought=f"showing facts for {lid!r} from the listing record: occupancy "
                        f"{occ!r}, status {facts.get('status')!r}, state {facts.get('state')!r}",
                result="facts: listing_record")
        if payload.get("sent_at") and payload.get("requested_time"):
            try:
                hours = (datetime.datetime.fromisoformat(payload["requested_time"]) -
                         datetime.datetime.fromisoformat(payload["sent_at"])).total_seconds() / 3600
                payload["hours_notice"] = hours
            except (TypeError, ValueError):
                pass
        return payload

    def _access_request_hit(self, text: str) -> str | None:
        low = text.lower()
        for w in _ACCESS_REQUEST_WORDS:
            if w in low:
                return text.strip()
        return None

    def request_showing_feedback(self, ctx: str, today: str | None = None):
        """Tuple 10: feedback unanswered after two asks, stop asking. This
        was previously a declared dict (feedback_asks) that nothing ever
        read or incremented - the tuple was never actually implemented.
        Schedule-driven re-ask, matching the established pattern."""
        count = self.feedback_asks.get(ctx, 0)
        if count >= self.feedback_ask_cap:
            self.hub.ingest_spoke_trace(
                "06", "internal", thought=f"feedback unanswered after "
                f"{count} asks for ctx={ctx!r} - stopping, per tuple 10",
                result="stopped: ask_cap_reached")
            self.hub.send(_env("06", "18", "agent.status", ctx,
                               {"waiting_on": "showing_feedback",
                                "resolved": True}))
            return "stopped"
        self.feedback_asks[ctx] = count + 1
        self.hub.send(_env("06", "11", "client.message.request", ctx,
                           {"template": "feedback_request",
                            "tone": "neutral_no_reproach"}))
        if count == 0 and today:
            self.hub.send(_env("06", "18", "agent.status", ctx,
                               {"waiting_on": "showing_feedback",
                                "since": today}))
        return "asked"

    def clock_showing_feedback(self, ctx: str, today: str):
        """Daily clock entry for showing feedback. 2026-10-14 (tuple runs):
        the clock called request_showing_feedback directly, so feedback was
        asked for on the day a showing was booked, before it happened. It
        asks only once a confirmed showing's date has passed."""
        dates = [str(s.get("time") or "")[:10] for s in self.confirmed_showings.get(ctx, [])]
        if not any(d and d < today for d in dates):
            return "not_yet_shown"
        return self.request_showing_feedback(ctx, today)

    def handle(self, env: Envelope):
        if env.intent == "clock.tick":   # daily clock, through the hub (owner rule 2026-10-11)
            from .clock import handle_tick
            return handle_tick(self, "06", env)
        ctx = env.client_context_id

        if env.intent == "config.update" and "seller_reports" in env.payload:
            self._configure_seller_reports(env)
            return

        if env.intent == "config.update" and "open_house" in env.payload:
            self._schedule_open_house(ctx, env)
            return

        if env.intent == "config.update" and "open_house_result" in env.payload:
            self._record_open_house(ctx, env)
            return

        if env.intent == "config.update" and "confirm_protected_bump" in env.payload:
            # Human's confirmation of a held protected-deadline bump - the
            # only path that ever executes it. config.update reaches this
            # handler only via the hub's signed-authority pipeline.
            held = self.pending_bumps.pop(ctx, None)
            if held is None:
                self.hub.ingest_spoke_trace(
                    "06", env.envelope_id,
                    thought=f"bump confirmation for ctx={ctx!r}, but no bump is "
                            f"held for this context - nothing moved",
                    result="no held bump")
                return
            if not env.payload["confirm_protected_bump"]:
                self.hub.ingest_spoke_trace(
                    "06", env.envelope_id,
                    thought=f"broker declined the bump for ctx={ctx!r} - the "
                            f"confirmed showing(s) stand",
                    result="bump declined")
                return
            # the displaced showings may belong to other buyers (same listing)
            for other_ctx, time in held.get("displaced", [(ctx, None)]):
                showings = self.confirmed_showings.get(other_ctx, [])
                for bumped in [s for s in showings
                               if (time is not None and s.get("time") == time)
                               or (time is None and self._time_conflict(
                                   s.get("time"), held["requested_time"],
                                   held["buffer_minutes"]))]:
                    showings.remove(bumped)
                    self.hub.send(_env("06", "11", "client.message.request", other_ctx,
                                       {"template": "showing_bumped_notice",
                                        "original_time": bumped["time"],
                                        "reason": "protected_deadline_priority"}))
                    self.hub.send(_env("06", "14", "interaction.log", other_ctx,
                                       {"kind": "showing_bumped",
                                        "time": bumped["time"]}))
            self._schedule(ctx, held["payload"], env)
            return

        if env.intent == "vendor.cancellation_notice":
            # A vendor relevant to this context cancelled late (09's
            # direct, immediate signal - tuple 1 on 09's side). This
            # agent has no existing state linking a specific vendor to a
            # specific confirmed showing, so it can't automatically judge
            # which showing (if any) is affected - flagging for human
            # review rather than guessing, matching the ambiguity
            # protocol (section 6).
            self.hub.send(_env("06", "14", "interaction.log", ctx,
                               {"kind": "vendor_cancellation_received",
                                "vendor_kind": env.payload.get("vendor_kind")}))
            self.hub.send(_env("06", "queue", "clarification.request", ctx,
                               {"reason": f"vendor "
                                         f"{env.payload.get('vendor_kind')!r} "
                                         f"cancelled late - human should "
                                         f"check whether a confirmed showing "
                                         f"depends on this vendor's work"}))
            return

        if env.intent == "listing.data":
            # facts pushed by Agent 05 from the signed listing record
            lid = env.payload.get("listing_id") or ctx
            self.listing_facts[lid] = {k: env.payload.get(k)
                                       for k in ("status", "occupancy", "state")}
            return

        if env.intent == "config.update" and "showing_facts_source" in env.payload:
            src = env.payload["showing_facts_source"]
            if src not in ("listing_record", "requester"):
                self.hub.send(_env("06", "queue", "clarification.request", ctx,
                                   {"reason": "showing_facts_source rejected; nothing changed - "
                                              "\"listing_record\" or \"requester\""}))
                return
            self.showing_facts_source = src
            self.hub.ingest_spoke_trace("06", env.envelope_id,
                                        thought=f"broker-signed: showing facts come from {src}",
                                        result="showing facts source set")
            return

        if env.intent == "showing.request":
            payload = self._with_listing_facts(dict(env.payload), env)

            trigger = self._access_request_hit(str(payload.get("message", "")))
            if trigger:
                self.hub.ingest_spoke_trace(
                    "06", env.envelope_id,
                    thought=f"request contains an access request: "
                            f"{trigger!r} - access is the legal line, not "
                            f"a judgment call, refusing and escalating",
                    result="escalated: legal_line (access request)")
                self.hub.escalate("escalation.legal_line",
                                  {"client_context_id": ctx,
                                   "trigger": trigger, "agent": "06"})
                return

            # tuple 6: access code/lockbox combo requested -> never
            # transmit, regardless of who's asking
            if payload.get("requests_access_code"):
                self.hub.escalate("escalation.legal_line",
                                  {"client_context_id": ctx,
                                   "trigger": "access code/lockbox combo "
                                             "requested - never transmitted, "
                                             "custody protocol only",
                                   "agent": "06"})
                return

            # job component: buyer-agreement-on-file flag (set by 13),
            # absent = hold and escalate (NAR 8/17/24 rule)
            if not payload.get("buyer_agreement_on_file"):
                self.hub.ingest_spoke_trace(
                    "06", env.envelope_id,
                    thought="buyer-agreement-on-file flag absent - written "
                            "buyer agreement is required before touring "
                            "(NAR settlement, 8/17/24); holding, not "
                            "scheduling",
                    result="held: no buyer agreement on file")
                self.hub.escalate("escalation.legal_line",
                                  {"client_context_id": ctx,
                                   "trigger": "showing requested without "
                                             "buyer-agreement-on-file flag",
                                   "agent": "06"})
                return

            # job component: verify requester identity per configured
            # procedure before confirming any access-bearing appointment
            if not payload.get("requester_identity_verified"):
                # tuple 2: cannot verify -> cancel the appointment, no
                # exceptions (not merely hold - cancel outright)
                self.hub.ingest_spoke_trace(
                    "06", env.envelope_id,
                    thought="requester identity could not be verified - "
                            "cancelling the access-bearing appointment, no "
                            "exceptions (vacant-property fraud pattern)",
                    result="cancelled: identity unverified")
                self.hub.send(_env("06", "14", "interaction.log", ctx,
                                   {"kind": "showing_cancelled",
                                    "reason": "identity_unverified"}))
                return

            # tuple 11: property under contract -> confirm show-ability via
            # 05 first, never assume active. Hold this request pending the
            # status.response round trip.
            if payload.get("possibly_under_contract"):
                self.pending_status_checks[ctx] = payload
                self.hub.ingest_spoke_trace(
                    "06", env.envelope_id,
                    thought="property may be under contract - confirming "
                            "show-ability via MLS (05) before scheduling, "
                            "never assuming active",
                    result="status.request issued, holding")
                self.hub.send(_env("06", "05", "status.request", ctx,
                                   {"listing_id": payload.get("listing_id")}))
                return

            self._schedule(ctx, payload, env)
            return

        if env.intent == "status.response":
            payload = self.pending_status_checks.pop(ctx, None)
            if payload is None:
                return
            status = env.payload.get("status")
            if status not in ("active",):
                self.hub.ingest_spoke_trace(
                    "06", env.envelope_id,
                    thought=f"MLS status is {status!r}, not active - "
                            f"show-ability not confirmed, holding and "
                            f"escalating rather than scheduling",
                    result="held: not show-able")
                self.hub.send(_env("06", "queue", "clarification.request", ctx,
                                   {"reason": f"property status {status!r} "
                                             f"is not show-able"}))
                return
            self._schedule(ctx, payload, env)
            return

        if env.intent == "showing.feedback_response":
            self.feedback_asks.pop(ctx, None)
            for s in self.confirmed_showings.get(ctx, []):   # P18 counts these
                s["feedback_received"] = True
            self.hub.send(_env("06", "18", "agent.status", ctx,
                               {"waiting_on": "showing_feedback",
                                "resolved": True}))
            self.hub.send(_env("06", "14", "interaction.log", ctx,
                               {"kind": "feedback_received",
                                "response": env.payload.get("response")}))
            return

        if env.intent == "showing.no_show":
            agent_id = env.payload.get("showing_agent_id")
            was_buyer_agent = env.payload.get("is_agent_no_show", False)
            # tuple 4: no-show -> log + feedback request, NO reproach messaging
            self.hub.send(_env("06", "14", "interaction.log", ctx,
                               {"kind": "no_show"}))
            self.request_showing_feedback(ctx, env.payload.get("today"))
            if was_buyer_agent and agent_id:
                self.showing_agent_no_shows[agent_id] = \
                    self.showing_agent_no_shows.get(agent_id, 0) + 1
                # tuple 8: agent no-shows twice -> flag pattern before third
                if self.showing_agent_no_shows[agent_id] >= self.no_show_pattern_threshold:
                    self.hub.send(_env("06", "queue", "clarification.request",
                                       ctx, {"reason": f"showing agent "
                                                       f"{agent_id!r} has "
                                                       f"{self.showing_agent_no_shows[agent_id]} "
                                                       f"no-shows - human review "
                                                       f"before third confirmation"}))
            return

    def _time_conflict(self, existing_time_str, requested_time_str,
                       buffer_minutes) -> bool:
        """Was: exact-match only (s.get('time') == requested_time), so
        buffer_minutes rode along in the calendar.event payload as pure
        data - nothing ever compared it against anything. Two showings
        15 minutes apart with buffer_minutes=30 produced zero conflict
        detection. Fixed: real buffer-aware overlap check."""
        import datetime
        if not existing_time_str or not requested_time_str:
            return False
        try:
            existing_dt = datetime.datetime.fromisoformat(existing_time_str)
            requested_dt = datetime.datetime.fromisoformat(requested_time_str)
        except (ValueError, TypeError):
            # unparseable - fail toward the exact-match check rather than
            # silently treating an unparseable time as never conflicting
            return existing_time_str == requested_time_str
        delta_minutes = abs((requested_dt - existing_dt).total_seconds()) / 60
        return delta_minutes < buffer_minutes

    def _schedule(self, ctx: str, payload: dict, env: Envelope):
        # tuple 5/7: minimum-notice rules for occupied properties always
        # apply, never squeezed for same-day requests
        if payload.get("property_occupied"):
            requested_hours_notice = payload.get("hours_notice", 0)
            required = self.min_notice_hours.get(
                payload.get("state"), self.min_notice_hours["default"])
            if requested_hours_notice < required:
                self.hub.ingest_spoke_trace(
                    "06", env.envelope_id,
                    thought=f"occupied property requires {required}h "
                            f"minimum notice, request gives "
                            f"{requested_hours_notice}h - offering first "
                            f"legal slot instead, never asking seller to "
                            f"waive notice unprompted",
                    result="offered first legal slot")
                self.hub.send(_env("06", "11", "client.message.request", ctx,
                                   {"template": "next_legal_slot_offer",
                                    "required_notice_hours": required}))
                return

        # tuple 9: overlapping showings -> sequence with buffer, never
        # double-book and hope. Fixed 2026-10-11 (scene run): only this
        # context's own showings were checked, and the context is the BUYER,
        # so two buyers could be booked into the same property at the same
        # time. Showings of the same listing now conflict across buyers.
        requested_time = payload.get("requested_time")
        buffer_minutes = payload.get("buffer_minutes", 30)
        listing_id = payload.get("listing_id")
        conflicting_pairs = [
            (c, s) for c, showings in self.confirmed_showings.items()
            for s in showings
            if (c == ctx or (listing_id is not None and s.get("listing_id") == listing_id))
            and self._time_conflict(s.get("time"), requested_time, buffer_minutes)]
        conflicting = [s for _c, s in conflicting_pairs]
        if conflicting:
            protected = payload.get("protected_deadline", False)
            if not protected:
                self.hub.send(_env("06", "queue", "clarification.request", ctx,
                                   {"reason": "calendar conflict within "
                                             f"{buffer_minutes}min buffer - "
                                             "sequencing required",
                                    "conflicting_times": [s["time"] for s in conflicting]}))
                return
            # Owner decision 2026-07-17 + #2 refinement 2026-07-18:
            # protected_deadline is a CALLER-WRITABLE payload flag - any
            # requester claiming it used to auto-bump confirmed showings.
            # Now, two gates before a bump can even be OFFERED:
            #   1. lead_tier (spoke-relayed by 13 from 14's CRM records,
            #      where 02 logged it - never client-writable) must be
            #      HOT. Not hot, or unknown, fails closed: plain
            #      sequencing clarification, no bump offer at all.
            #   2. A hot claim still only HOLDS for human confirmation -
            #      the bump executes solely on the human's signed
            #      config.update (confirm_protected_bump), never on the
            #      claim.
            tier = str(payload.get("lead_tier") or "").upper()
            if tier != "HOT":
                self.hub.ingest_spoke_trace(
                    "06", env.envelope_id,
                    thought=f"protected-deadline claim with lead_tier="
                            f"{payload.get('lead_tier')!r} (not HOT, or "
                            f"unknown) - bump offer declined, falls back "
                            f"to plain conflict sequencing; hotness is "
                            f"read from the CRM relay, never the claim",
                    result="bump_offer_declined_tier_gate")
                self.hub.send(_env("06", "queue", "clarification.request",
                                   ctx,
                                   {"reason": "calendar conflict within "
                                             f"{buffer_minutes}min buffer - "
                                             "sequencing required "
                                             "(protected-deadline claim "
                                             "present but lead tier not "
                                             "HOT - no bump offered)",
                                    "conflicting_times":
                                        [s["time"] for s in conflicting]}))
                return
            self.hub.ingest_spoke_trace(
                "06", env.envelope_id,
                thought=f"protected-deadline claim at {requested_time!r} "
                        f"conflicts with confirmed showing(s) "
                        f"{[s['time'] for s in conflicting]} - the claim is "
                        f"caller-writable, so the bump goes to human "
                        f"confirmation, never executed on the claim alone",
                result="held: bump_requires_human_confirmation")
            self.pending_bumps[ctx] = {"requested_time": requested_time,
                                       "buffer_minutes": buffer_minutes,
                                       "payload": payload,
                                       "displaced": [(c, s["time"]) for c, s in conflicting_pairs],
                                       "conflicting_times":
                                           [s["time"] for s in conflicting]}
            self.hub.send(_env("06", "queue", "clarification.request", ctx,
                               {"reason": "protected-deadline claim would "
                                         "bump confirmed showing(s) - human "
                                         "confirmation required, the claim "
                                         "alone never bumps",
                                "requested_time": requested_time,
                                "conflicting_times":
                                    [s["time"] for s in conflicting]}))
            return

        # Real bug found in Agent 18's review 2026-07-16: this send never
        # included 'day' or 'timezone_confirmed' - Agent 18 keys its
        # entire calendar on 'day' and gates on tz_confirmed FIRST, so
        # every real showing confirmation was getting caught at the
        # timezone-ambiguity gate and never reaching the calendar at all.
        # timezone_confirmed=True is correct here: by this point
        # requested_time is already a fully resolved ISO datetime (not an
        # ambiguous conversational time like "let's say 10") - that
        # ambiguity, if any, is resolved before a showing reaches
        # confirmation, not after.
        self.hub.send(_env("06", "18", "calendar.event", ctx,
                           {"event": "showing", "time": requested_time,
                            "day": requested_time.split("T")[0] if requested_time else None,
                            "timezone_confirmed": True,
                            "buffer_minutes": buffer_minutes}))

        # job component: open house RSVP logistics - an open house (unlike
        # an individual buyer showing) needs event vendor support
        # (signage/staging), ordered via 09.
        if payload.get("is_open_house"):
            self.hub.send(_env("06", "09", "vendor.request", ctx,
                               {"kind": "open_house_signage"}))

        showing = {"time": requested_time, "confirmed": True,
                   "listing_id": listing_id}
        self.confirmed_showings.setdefault(ctx, []).append(showing)
        self.hub.ingest_spoke_trace(
            "06", env.envelope_id,
            thought="all gates cleared (buyer agreement on file, identity "
                    "verified, show-ability confirmed, no unresolved "
                    "conflict) - confirming showing",
            result="showing confirmed")
        self.hub.send(_env("06", "11", "client.message.request", ctx,
                           {"template": "showing_confirmation"}))
        self.hub.send(_env("06", "14", "interaction.log", ctx,
                           {"kind": "showing_confirmed", "time": requested_time}))
