"""Agent 18 - Calendar & Task, built against the full spec.

Personal assistant to the licensed human agent. Also the actual home for
cross-swarm wait-state visibility (agent.status) - so a human can see
what's currently waiting on something before it becomes a missed deadline,
not just after.
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


class Spoke18CalendarTask:
    """DECISIONS.md tuples implemented directly:
      1. event conflict priority rules can't resolve -> human, never
         silently move either. Fixed 2026-07-16: only tuple 5's day-
         capacity check existed - two events at the exact same time on
         the same day would both silently get added with zero conflict
         signal. Now a real time-based conflict check, distinct from
         capacity.
      2. briefing item's source envelope missing -> state the gap. NOT
         implemented - generate_briefing() only aggregates what it has;
         there's no mechanism to know something is missing unless a
         separate system tells it to expect that item. Genuinely
         difficult without an "expected items" tracking layer this
         review won't invent.
      3. human instruction conflicts with contractual deadline -> surface
         both, act on neither until directed. NOT implemented - zero
         code, confirmed by grep. No payload key or handler exists for a
         distinct "human instruction" input at all.
      4. agent asks to move a protected deadline block -> refuse, human
         confirmation only
      5. overloaded day -> propose priority order, human confirms. The
         proposed order (protected blocks first, then by time, the new
         event last) is attached since 2026-10-12; before, the message
         claimed an order and attached none.
      6. two deadline sources disagree -> track both, alert the conflict,
         never pick the friendlier date
      7. owner calendar conflicts with contractual deadline -> deadline
         outranks, propose the move on the soft item
      8. recurring task silently failing (no completion events) -> surface
         the pattern, a quiet calendar is a suspect calendar. SERIOUS GAP
         found 2026-07-16: self.recurring_task_last_seen is never written
         by any real code path anywhere in this class - the existing test
         populated it by directly poking the internal dict
         (spoke.recurring_task_last_seen[...] = ...), not through any
         real message. In actual operation this dict is always empty, so
         check_recurring_task() can never fire - there is no mechanism
         anywhere in the swarm that signals "a recurring task completed."
         Needs a real design decision (what signal, from whom) this
         review won't invent.
      9. timezone ambiguity -> confirm before scheduling

    CRITICAL cross-agent bug found and fixed 2026-07-16, not a tuple:
    Agent 06's and Agent 09's calendar.event sends never included 'day'
    or 'timezone_confirmed' at all. This agent gates on tz_confirmed
    FIRST and keys its entire calendar on 'day' - meaning every single
    real showing confirmation (06) and vendor appointment (09) was
    getting caught at the timezone-ambiguity gate and NEVER reaching the
    calendar, ever. Verified directly: a real showing confirmation
    produced a clarification.request and left self.calendar completely
    empty. In production this agent's calendar, capacity checks, and
    protected-block tracking were all silently non-functional. Fixed in
    both senders.

    Plus: agent.status tracking - the actual fix for real-time HITL
    visibility into what's waiting on what, discussed and decided as a
    push-pattern extension matching how this agent already consumes
    calendar.event/deadline.alert, rather than a pull from 14 (18 has no
    route to query 14 at all, and a briefing "never contains a status the
    system cannot source" - so the signal has to be pushed here directly).
    """

    # TUNABLE (owner-ratified 2026-07-16): max_events_per_day=8.
    # See docs/TUNING_MANUAL.md to change.
    def __init__(self, hub, max_events_per_day: int = 8,
                 no_show_grace_minutes: int = 60):
        self.hub = guard(hub, "18")   # handoff rule (audit TU-2)
        self._sections = None   # set only while a morning briefing is being built
        self.calendar: dict[str, list[dict]] = {}  # day -> events
        self.protected_blocks: dict[str, dict] = {}  # event_id -> {day, source: "07"}
        self.deadline_sources: dict[str, dict[str, dict[str, str]]] = {}  # ctx -> {milestone: {source: date}}
        self.waiting: dict[str, dict] = {}  # (agent, ctx, waiting_on) key -> status record
        self.recurring_task_last_seen: dict[str, str] = {}  # task_id -> last completion date
        self.max_events_per_day = max_events_per_day
        # SKILL.md edge, ratified but unimplemented until 2026-07-17:
        # OUT -> 06 | No-show detected by calendar (missed slot, no
        # confirmation) | showing.no_show. State for that detection:
        self.showings: dict[str, dict] = {}  # ctx -> {time, day}
        self.showing_followup_seen: set[str] = set()  # ctxs where 06 signaled post-showing
        self.no_shows_reported: set[str] = set()  # never report the same slot twice
        # PROVISIONAL, no empirical basis - how long past the slot before
        # silence counts as a calendar-detected no-show. TUNING_MANUAL entry
        # added in the same commit, per standing KPI.
        self.no_show_grace_minutes = no_show_grace_minutes
        self.pending_instructions: dict[str, dict] = {}  # ctx -> instruction held (tuple 3)
        register_spoke(hub, "18", self)
        register_resumer(hub, "18", self._resume)

    def _wait_key(self, agent: str, ctx: str, waiting_on: str) -> str:
        return f"{agent}:{ctx}:{waiting_on}"

    def _not_booked(self, env: Envelope):
        """Owner decision 2026-10-27: Agent 06 confirms a showing to the buyer
        only once it is on the calendar. When a showing from 06 is not added
        (conflict, full day, no day, unconfirmed time zone), 18 tells 06 so;
        the question to the broker above stands as before."""
        if env.from_agent == "06" and env.payload.get("event") == "showing":
            self.hub.send(_env("18", "06", "calendar.conflict", env.client_context_id,
                               {"time": env.payload.get("time"), "day": env.payload.get("day")}))

    def handle(self, env: Envelope):
        if env.intent == "clock.tick":   # daily clock, through the hub (owner rule 2026-10-11)
            from .clock import handle_tick
            return handle_tick(self, "18", env)
        ctx = env.client_context_id
        payload = env.payload

        if env.intent == "report.package":
            # owner decision 8 (2026-10-21): a briefing section, accepted only
            # from the agent that owns it and only while a briefing is built
            name = payload.get("section")
            owner = dict((n, a) for a, n in self.BRIEF_SECTIONS).get(name)
            if self._sections is None or owner != env.from_agent:
                self.hub.ingest_spoke_trace(
                    "18", env.envelope_id,
                    thought=f"briefing section {name!r} from {env.from_agent} arrived "
                            f"with no briefing being built for it from that agent - not used",
                    result="ignored: unrequested section")
                return
            self._sections[name] = payload.get("data")
            return

        if env.intent == "agent.status":
            # Any post-showing signal from 06 (feedback wait opened OR
            # resolved) means 06 processed an outcome for this showing -
            # the calendar-silence no-show detector must not fire for it.
            if env.from_agent == "06" and \
                    payload.get("waiting_on") == "showing_feedback":
                self.showing_followup_seen.add(ctx)
            key = self._wait_key(env.from_agent, ctx, payload.get("waiting_on", ""))
            task_id = payload.get("recurring_task_id") or payload.get("task_id")
            if task_id:
                task_date = (payload.get("completed_at") or payload.get("date") or
                             payload.get("day") or payload.get("since"))
                if task_date:
                    self.recurring_task_last_seen[task_id] = str(task_date)
            if payload.get("resolved"):
                self.waiting.pop(key, None)
                self.hub.ingest_spoke_trace(
                    "18", env.envelope_id,
                    thought=f"{env.from_agent} resolved its wait on "
                            f"{payload.get('waiting_on')!r} for ctx={ctx!r}",
                    result="wait cleared")
            else:
                self.waiting[key] = {"agent": env.from_agent, "ctx": ctx,
                                     "waiting_on": payload.get("waiting_on"),
                                     "since": payload.get("since"),
                                     "wait_id": payload.get("wait_id"),
                                     "reason": payload.get("reason"),
                                     # the envelope this item stands on (tuple 2)
                                     "source_envelope_id": env.envelope_id}
                self.hub.ingest_spoke_trace(
                    "18", env.envelope_id,
                    thought=f"{env.from_agent} is waiting on "
                            f"{payload.get('waiting_on')!r} for ctx={ctx!r} "
                            f"since {payload.get('since')} - tracked for "
                            f"the next briefing",
                    result="wait tracked")
            return

        if env.intent == "calendar.event":
            day = payload.get("day")
            if not day:
                # fixed 2026-10-11 (scene run): an event with no day was
                # filed under None, and the next briefing could not be
                # written to the audit log (mixed None/str keys crash the
                # chain's canonical JSON) - the whole briefing was lost
                self.hub.send(_env("18", "queue", "clarification.request", ctx,
                                   {"reason": "calendar event has no day - not "
                                              "scheduled; name the day",
                                    "event": payload.get("event")}))
                self._not_booked(env)
                return
            if payload.get("recurring_task_id"):
                self.recurring_task_last_seen[payload["recurring_task_id"]] = str(day)
            # Doctrine is unconditional: "deadline blocks originating from
            # 07 are protected" - derived from source, not a trusted flag.
            # A payload could claim protected=False for a 07-sourced block
            # (or omit it) and this must not weaken the actual rule.
            protected = env.from_agent == "07" or payload.get("protected", False)
            # Fail closed: unconfirmed timezone status defaults to NOT
            # confirmed, not assumed fine.
            tz_confirmed = payload.get("timezone_confirmed", False)

            # tuple 9: timezone ambiguity -> confirm before scheduling
            if not tz_confirmed:
                self.hub.send(_env("18", "queue", "clarification.request", ctx,
                                   {"reason": "timezone ambiguity on this "
                                             "event - confirm before "
                                             "scheduling"}))
                self._not_booked(env)
                return

            day_events = self.calendar.setdefault(day, [])

            # tuple 1: event conflict the priority rules cannot resolve ->
            # human, never silently move either. Fixed 2026-07-16: only
            # tuple 5's day-capacity check existed - two events at the
            # exact same time on the same day would both silently get
            # added with zero conflict signal, since only the aggregate
            # day count was ever checked. Distinct from capacity: this is
            # about two specific events actually colliding.
            time = payload.get("time")
            if time and any(e.get("time") == time for e in day_events):
                self.hub.send(_env("18", "queue", "clarification.request", ctx,
                                   {"reason": f"event conflict at {time!r} on "
                                             f"{day!r} - priority rules don't "
                                             f"resolve this, human decides, "
                                             f"never silently moving either"}))
                self._not_booked(env)
                return

            # tuple 5: overloaded day -> propose priority order, human confirms.
            # Fixed 2026-10-12: the message said "proposing priority order"
            # and attached none. The order put forward is the one the rules
            # give - protected (07) blocks first, then by time - with the new
            # event last; the broker confirms or reorders.
            if len(day_events) >= self.max_events_per_day:
                ordered = sorted(day_events, key=lambda e: (not e.get("protected"),
                                                            str(e.get("time") or "")))
                proposed = [e.get("event_id") for e in ordered] + [
                    payload.get("event_id") or payload.get("event")]
                self.hub.send(_env("18", "queue", "clarification.request", ctx,
                                   {"reason": "day is at capacity - the new event "
                                              "was not added; proposed order for "
                                              "your confirmation (protected "
                                              "deadline blocks first, then by time)",
                                    "day": day, "proposed_order": proposed}))
                self._not_booked(env)
                return

            event_id = payload.get("event_id", f"{day}-{len(day_events)}")
            day_events.append({"event_id": event_id, "source": env.from_agent,
                              "protected": protected, "time": time})
            if env.from_agent == "06" and payload.get("event") == "showing":
                self.showings[ctx] = {"time": time, "day": day}
            if protected:
                self.protected_blocks[event_id] = {"day": day, "source": env.from_agent}
            self.hub.send(_env("18", "14", "interaction.log", ctx,
                               {"kind": "calendar_event_logged", "day": day,
                                "event_id": event_id}))
            return

        if env.intent == "deadline.alert":
            milestone = payload.get("milestone")
            deadline = payload.get("deadline")
            # tuple 6: two deadline sources disagree -> track both, alert,
            # never pick the friendlier date. Keyed by source since
            # 2026-10-14 (plumbing): it was keyed by milestone only, so an
            # amended date from the same source read as "two sources", and
            # the briefing listed any context whose milestones fell on
            # different days as a deadline conflict. A source is the
            # sender, or the payload's "source" (Agent 07 sends "artifact"
            # for a date a received document states).
            source = str(payload.get("source") or env.from_agent)
            by_source = self.deadline_sources.setdefault(ctx, {}).setdefault(milestone, {})
            by_source[source] = deadline
            if len(set(by_source.values())) > 1:
                self.hub.send(_env("18", "queue", "clarification.request", ctx,
                                   {"reason": f"conflicting deadline sources "
                                             f"for {milestone!r}: "
                                             + ", ".join(f"{k} says {v!r}" for k, v in sorted(by_source.items()))
                                             + " - tracking both, never picking the "
                                               "friendlier date",
                                    "sources": dict(by_source)}))

            # Doctrine: "deadline blocks originating from 07 are
            # protected." 07 isn't a legal sender of calendar.event at all
            # (only 06/09 are) - this IS the block-creation point. 18
            # creates its own protected block for the deadline, sourced
            # from 07's alert, rather than expecting 07 to send a
            # calendar.event it structurally cannot send.
            block_id = f"deadline-{ctx}-{milestone}" + ("" if source == "07" else f"-{source}")
            day_events = self.calendar.setdefault(deadline, [])
            if not any(e["event_id"] == block_id for e in day_events):
                day_events.append({"event_id": block_id, "source": "07",
                                  "protected": True})
                self.protected_blocks[block_id] = {"day": deadline, "source": "07"}

            # tuple 7: owner calendar conflicts with contractual deadline ->
            # deadline outranks, propose move on the soft item
            conflicting_soft_events = [e for e in self.calendar.get(deadline, [])
                                       if not e["protected"]]
            if conflicting_soft_events:
                self.hub.send(_env("18", "queue", "clarification.request", ctx,
                                   {"reason": f"contractual deadline "
                                             f"{milestone!r} on {deadline!r} "
                                             f"conflicts with soft calendar "
                                             f"items - deadline outranks, "
                                             f"proposing the move on the "
                                             f"soft item(s)",
                                    "soft_events": [e["event_id"]
                                                   for e in conflicting_soft_events]}))
            return

        if env.intent == "config.update" and "schedule_instruction" in payload:
            return self._schedule_instruction(ctx, payload["schedule_instruction"], env)

        if env.intent == "config.update" and "move_protected_block" in payload:
            event_id = payload["move_protected_block"].get("event_id")
            requester = payload["move_protected_block"].get("requester")
            # tuple 4: agent asks to move a protected block -> refuse,
            # human confirmation only. This handler only reachable via a
            # signed config.update (human channel) - an agent itself has
            # no route to request this at all, which is the actual
            # enforcement; this branch handles the human's own request.
            if event_id in self.protected_blocks and requester != "human":
                self.hub.send(_env("18", "queue", "clarification.request", ctx,
                                   {"reason": f"request to move protected "
                                             f"block {event_id!r} from "
                                             f"{requester!r} - refused, "
                                             f"human confirmation only"}))
                return
            if event_id in self.protected_blocks:
                del self.protected_blocks[event_id]
                self.hub.ingest_spoke_trace(
                    "18", env.envelope_id,
                    thought=f"human-confirmed move of protected block {event_id!r} - removed",
                    result="protected block moved")
                return
            self.hub.ingest_spoke_trace(
                "18", env.envelope_id,
                thought=f"move requested for {event_id!r}, which is not a protected "
                        f"block on record - nothing moved",
                result="no such protected block")
            return

    def _schedule_instruction(self, ctx: str, ins, env: Envelope):
        """Tuple 3 (wired 2026-10-15): your signed instruction to put an event
        on the calendar, e.g. {"event": "final walkthrough", "day":
        "2026-10-25", "before_milestone": "closing"}. If the day falls after
        a contractual deadline it must come before, both are surfaced and
        neither is acted on until you decide: continue puts the event where
        you said, cancel drops it. The deadline is never moved."""
        if not isinstance(ins, dict) or not ins.get("event") or not ins.get("day"):
            self.hub.send(_env("18", "queue", "clarification.request", ctx,
                               {"reason": "schedule_instruction needs event and day; nothing done"}))
            return
        m = ins.get("before_milestone")
        dates = sorted(set((self.deadline_sources.get(ctx, {}).get(m) or {}).values())) if m else []
        late = [d for d in dates if d and str(ins["day"]) > str(d)]
        if late:
            self.pending_instructions[ctx] = dict(ins)
            self.hub.ingest_spoke_trace(
                "18", env.envelope_id,
                thought=f"your instruction puts {ins['event']!r} on {ins['day']}, after the "
                        f"{m!r} deadline {late} - surfacing both, acting on neither",
                result="held: instruction vs contractual deadline")
            hold_for_human(self.hub, "18", ctx, "schedule_instruction",
                           f"your instruction puts {ins['event']!r} on {ins['day']}, after the "
                           f"contractual {m!r} deadline ({', '.join(late)}). Continue to put it "
                           f"there anyway (the deadline stays as it is); cancel to drop it.",
                           {"instruction": dict(ins), "deadline": {"milestone": m, "dates": dates}})
            return
        self._add_instructed_event(ctx, ins, env.envelope_id)

    def _add_instructed_event(self, ctx: str, ins: dict, source: str):
        day = str(ins["day"])
        event_id = f"instructed-{ctx}-{ins['event']}"
        self.calendar.setdefault(day, []).append({"event_id": event_id, "source": "human",
                                                  "protected": False, "time": ins.get("time")})
        self.hub.send(_env("18", "14", "interaction.log", ctx,
                           {"kind": "calendar_event_logged", "day": day, "event_id": event_id,
                            "by": "your instruction"}))

    def _resume(self, ws, decision_payload: dict):
        ctx = ws.client_context_id
        d = decision_of(decision_payload)
        ins = self.pending_instructions.pop(ctx, None)
        if ins is None or d == "other":
            if ins is not None:
                self.pending_instructions[ctx] = ins
            return "unchanged"
        if d == "continue":
            self._add_instructed_event(ctx, ins, ws.wait_id)
            return "event placed as instructed; deadline unchanged"
        self.hub.send(_env("18", "14", "interaction.log", ctx,
                           {"kind": "instruction_dropped", "instruction": ins}))
        return "instruction dropped"

    def check_showing_no_show(self, ctx: str, now_iso: str):
        """SKILL.md ratified edge, implemented 2026-07-17 (was a declared
        route with zero code behind it): a showing whose slot passed by
        more than no_show_grace_minutes with NO post-showing signal from
        06 is a calendar-detected no-show. 11's showing.no_show path only
        covers no-shows a client actively mentions; this covers the ones
        nobody mentioned at all. Called by the same scheduler/sweep layer
        as check_recurring_task - 18 never invents the current time.
        Grace elapsed is computed HERE from the stored slot time, never
        pre-computed by the caller (the exact decorative-SLA defect class
        Agent 17's pending_reviews had)."""
        import datetime
        showing = self.showings.get(ctx)
        if showing is None or not showing.get("time"):
            return "no_showing_or_no_time"
        if ctx in self.no_shows_reported:
            return "already_reported"
        if ctx in self.showing_followup_seen:
            return "outcome_already_processed"
        slot = datetime.datetime.fromisoformat(showing["time"])
        now = datetime.datetime.fromisoformat(now_iso)
        elapsed_min = (now - slot).total_seconds() / 60.0
        if elapsed_min < self.no_show_grace_minutes:
            return "within_grace"
        self.no_shows_reported.add(ctx)
        self.hub.ingest_spoke_trace(
            "18", f"no-show-{ctx}",
            thought=f"showing slot {showing['time']!r} passed "
                    f"{elapsed_min:.0f}min ago with no post-showing signal "
                    f"from 06 - calendar-detected no-show, reporting to 06; "
                    f"is_agent_no_show stays False (silence proves absence "
                    f"of confirmation, not who failed to appear)",
            result="showing.no_show sent to 06")
        self.hub.send(_env("18", "06", "showing.no_show", ctx,
                           {"detected_by": "calendar",
                            "today": showing.get("day"),
                            "is_agent_no_show": False}))
        return "reported"

    def check_recurring_task(self, task_id: str, today: str, expected_cadence_days: int):
        """Tuple 8: a recurring task with no completion events is surfaced,
        not assumed fine. Schedule-driven, matching the established
        pattern (07's check_deadlines, etc.)."""
        import datetime
        last_seen = self.recurring_task_last_seen.get(task_id)
        if last_seen is None:
            return None
        gap = (datetime.date.fromisoformat(today) -
              datetime.date.fromisoformat(last_seen)).days
        if gap > expected_cadence_days:
            self.hub.send(_env("18", "queue", "clarification.request", "recurring-task",
                               {"reason": f"recurring task {task_id!r} has "
                                         f"had no completion event in "
                                         f"{gap} days (expected every "
                                         f"{expected_cadence_days}) - a "
                                         f"quiet calendar is a suspect "
                                         f"calendar, surfacing the pattern"}))
            return "surfaced"
        return "on_schedule"

    # owner decision 8 (2026-10-21): the morning briefing's four sections,
    # each asked of the agent that owns the facts (briefing.request) and
    # answered through the hub (report.package)
    BRIEF_SECTIONS = (("14", "overnight_leads"), ("15", "yesterdays_books"),
                      ("19", "prospects_waiting"), ("10", "market_changes"))

    def generate_briefing(self, briefing_type: str = "morning", today: str | None = None):
        """Job component: briefings built ONLY from logged envelopes and
        calendar records - a briefing never contains a status the system
        cannot source. This is where the agent.status tracking actually
        pays off: waiting items are real, sourced facts, not guesses."""
        # tuple 2 (wired 2026-10-15): a briefing item whose source envelope
        # is not on the audit log is stated as a gap, never presented as if
        # it were sourced (a wait restored from saved state whose envelope
        # is gone, or one recorded before sources were kept)
        on_log = {e.get("envelope_id") for e in self.hub.audit.read()
                  if e.get("kind") == "envelope.persisted"}
        gaps = [{"agent": w["agent"], "context": w["ctx"], "waiting_on": w["waiting_on"],
                 "missing_source": w.get("source_envelope_id") or "none recorded"}
                for w in self.waiting.values()
                if w.get("source_envelope_id") not in on_log]
        sections, missing = {}, []
        if briefing_type == "morning":
            self._sections = {}
            for agent, name in self.BRIEF_SECTIONS:
                self.hub.send(_env("18", agent, "briefing.request", "briefing",
                                   {"section": name, "today": today}))
            got, self._sections = self._sections, None
            for agent, name in self.BRIEF_SECTIONS:
                if name in got:
                    sections[name] = got[name]
                else:   # stated, never left out quietly
                    sections[name] = None
                    missing.append({"agent": agent, "section": name,
                                    "missing_source": "no answer to the briefing request"})
        briefing = {
            "briefing_type": briefing_type,
            "today": today,
            "sections": sections,
            "sections_missing": missing,
            "gaps": gaps,
            "calendar_days": {d: [e["event_id"] for e in events]
                             for d, events in self.calendar.items()},
            "currently_waiting": [
                {"agent": w["agent"], "context": w["ctx"],
                 "waiting_on": w["waiting_on"], "since": w["since"]}
                for w in self.waiting.values()],
            "unresolved_decisions_recap": [
                {"agent": w["agent"], "context": w["ctx"],
                 "waiting_on": w["waiting_on"], "since": w["since"],
                 "wait_id": w.get("wait_id"), "reason": w.get("reason")}
                for w in self.waiting.values()
                if "human" in str(w.get("waiting_on", "")).lower()
            ],
            "deadline_conflicts_tracked": {
                ctx: conflicts for ctx, conflicts in (
                    (c, {m: dict(srcs) for m, srcs in ms.items() if len(set(srcs.values())) > 1})
                    for c, ms in self.deadline_sources.items()) if conflicts},
        }
        self.hub.send(_env("18", "human", "report.package", "briefing", briefing))
        return briefing
