"""Real spokes for the listing (real-estate) vertical, rebuilt against the
FULL ratified spec - not the simplified P11 demo versions.

The P11 demo's Spoke01LeadCapture/Spoke14CRM (in dispatcher-agents proper)
implement roughly 2 of 01's 16 decision tuples and omit the Legal Line
escalation entirely. This file replaces that scope with the real spec.
"""
from __future__ import annotations

from .core import Envelope
from .handoff_guard import guard, register as register_spoke
from .human_holds import hold_for_human, decision_of, register_resumer
from .drawer_filing import file_record

SOURCE_VERIFIED = "source_verified"
STATED_BY_PARTY = "stated_by_party"
UNKNOWN = "unknown"

CHANNEL_RANK = {"call": 3, "text": 2, "web_form": 1}

# Legal-line trigger phrases (01 SKILL.md S3): fiduciary pricing advice,
# contract negotiation, legal opinions. Conservative/broad per "if
# classification is uncertain, treat it as over the line."
_LEGAL_LINE_WORDS = ("what should i offer", "should i list at", "negotiate",
                    "contract language", "legal opinion", "is this legal",
                    "represent me in", "counter their offer")

# tuple 3: caller demands a human now, escalate immediately (capture what's
# already given, don't drop it). Fixed 2026-07-17 - zero code existed for
# this at all.
_DEMANDS_HUMAN_WORDS = ("speak to a human", "talk to a human", "talk to a "
                       "person", "speak to a person", "get me a person",
                       "real person", "speak to someone", "human agent",
                       "not a robot", "let me talk to someone", "human now")


def _env(frm, to, intent, ctx, payload, confidence=UNKNOWN, escalation_flag=False):
    return Envelope(from_agent=frm, to_agent=to, intent=intent,
                    client_context_id=ctx, payload=payload,
                    confidence=confidence, escalation_flag=escalation_flag,
                    provenance={"source": f"spoke-{frm}", "captured_at": "runtime",
                                "verbatim_available": True})



def _phone_key(phone) -> str | None:
    """A phone as its digits (7 or more). An 11-digit number starting with
    1 is the North American country code plus a 10-digit number and is
    keyed as the 10 digits, so +1 216 555 0101 and (216) 555-0101 are the
    same number (2026-10-14: the synthetic sample run found them treated
    as two people)."""
    if not isinstance(phone, str):
        return None
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return "phone:" + digits if len(digits) >= 7 else None


def _contact_identifiers(payload: dict) -> list[str]:
    """Normalized identity keys for the cross-context duplicate check and
    the do-not-contact check: phone as _phone_key, email lower-cased.
    Nothing else."""
    out = []
    key = _phone_key(payload.get("phone"))
    if key:
        out.append(key)
    email = payload.get("email")
    if isinstance(email, str) and "@" in email:
        out.append("email:" + email.strip().lower())
    return out


def _dnc_identifiers(entries) -> set[str]:
    """The do-not-contact list in the same normalized form: an entry with
    an @ is an email, anything else a phone."""
    out = set()
    for entry in entries:
        if not isinstance(entry, str):
            continue
        if "@" in entry:
            out.add("email:" + entry.strip().lower())
        else:
            key = _phone_key(entry)
            if key:
                out.add(key)
    return out

class Spoke14CRMPipeline:
    """System of record. Append-only; consent flags are authoritative HERE.

    DECISIONS.md tuples:
      - conflicting facts for one event -> both stand, flagged (never
        merged). Fixed 2026-07-17: "both stand" was trivially true
        (append-only never overwrites) but nothing was ever actually
        flagged - zero code existed. _append() now compares a new entry
        against the most recent PRIOR entry of the same kind for the same
        context; any differing overlapping field is flagged on the entry
        itself (conflicts_with_prior), not silently left for a reader to
        notice or not.
      - merge candidate w/ unconfirmed identity -> no merge (vacuously
        true: this class has no merge mechanism of any kind, so nothing
        auto-merges; see the next tuple for the ACTIVE detection half)
      - report over a known logging gap -> state the gap, never smooth.
        Fixed 2026-07-17: generate_report() now detects contexts with
        side-channel state (consent/property interests/buyer agreement/
        identity verification) but NO backing log entry at all, and names
        them explicitly (logging_gaps) rather than presenting whatever
        exists as a complete picture.
      - consent flags conflict across channels -> most restrictive wins, per channel
      - record deletion request -> escalate to human (retention is jurisdiction)
      - merge candidates detected -> propose w/ evidence, never auto-merge.
        Fixed 2026-07-17: zero detection logic existed, and the data it
        would need (contact info) wasn't even being sent here by Agent 01
        until that was fixed too. Since 2026-10-11 the match is made at
        capture: the dedupe lookup compares phone/email across contexts
        and 01 holds a match for the broker (continue or cancel) - the
        uncalled check_merge_candidates() sweep was removed.
      - record edit erasing history -> append-correct, never overwrite
        (structurally true: no edit/overwrite method exists anywhere in
        this class, only _append)
      - external import conflicts w/ log-derived state -> log wins,
        flagged. Fixed 2026-07-17 by the same _append() conflict-check
        that fixed the first tuple above - one mechanism serves both,
        since they're the same underlying comparison (a new fact for an
        existing context disagreeing with what's already on record).
      - context requested outside a routed intent -> refuse. Corrected
        2026-07-17: this is NOT a missing local check - record.request's
        legal senders (01, 11, 13, 15 - verified directly against
        routes.json, not assumed) are already enforced by the hub before
        this class's handle() is ever called; there is no alternate path
        to request a context that bypasses this. The prior comment
        claiming "this is the redundant local check named in the tuple"
        was misleading (implied distinct code that didn't exist) - fixed
        to describe what's actually true.
      - retention/deletion request -> freeze + escalate to owner
    """

    def __init__(self, hub):
        self.hub = guard(hub, "14")   # handoff rule (audit TU-2)
        self.records: dict[str, list[dict]] = {}
        # canonical consent state per context, per channel - authoritative
        self.consent: dict[str, dict[str, str]] = {}
        # canonical property-interest list per context - authoritative,
        # same reason: 01 must never rebuild this from its own memory
        # across completed round trips (MANNERS #9).
        self.property_interests: dict[str, list[dict]] = {}
        # authoritative buyer-agent-relationship facts - 14 is system of
        # record for these, updated by whoever confirms them (13 signs
        # the agreement, an identity-verification process confirms
        # identity), queried by anyone who needs the current fact (06 via
        # 11, directly) rather than each requester inventing or omitting it.
        self.buyer_agreement: dict[str, bool] = {}
        self.identity_verified: dict[str, bool] = {}
        # Contexts frozen by a retention/deletion request. Fixed
        # 2026-07-18: "frozen" used to be a WORD ON A TRACE - nothing
        # mechanically blocked further writes, so a "frozen" record kept
        # accumulating entries while supposedly held for the owner.
        # Doctrine: instruction < detection < structural impossibility.
        self.frozen: set[str] = set()
        self._entry_seq = 0
        # P13 client dates, broker-signed per context: event_type -> "MM-DD"
        # (every year) or "YYYY-MM-DD" (once). Read by the daily clock.
        self.client_dates: dict[str, dict[str, str]] = {}
        self._dates_fired: set = set()
        # P19 Property Access Custody (J3, 2026-10-12): broker-signed access
        # grants per listing context - who has access and until when. The
        # code, combination or key itself is never recorded or sent.
        self.access_grants: dict[str, list[dict]] = {}
        # Owner decision 8 (2026-10-21): leads already reported in a morning
        # briefing (entry ids), so "overnight leads" is every lead captured
        # since the last briefing, each reported once.
        self.briefed_leads: set[str] = set()
        register_spoke(hub, "14", self)

    def _new_entry_id(self) -> str:
        self._entry_seq += 1
        return f"E{self._entry_seq:06d}"

    def _append(self, ctx: str, kind: str, env: Envelope) -> str:
        if ctx in self.frozen:
            # Structural freeze: no new entries while a retention/deletion
            # question is with the owner. The attempted write is DECLARED
            # (audit + human queue), never silently dropped and never
            # silently admitted - a frozen record that quietly kept
            # growing was the defect.
            self.hub.ingest_spoke_trace(
                "14", env.envelope_id,
                thought=f"write attempt ({kind!r}) on FROZEN ctx={ctx!r} - "
                        f"record is held pending the owner's retention "
                        f"decision; refusing the append and declaring it",
                result="refused: record_frozen")
            self.hub.send(_env("14", "queue", "clarification.request", ctx,
                               {"reason": f"write attempted on frozen record "
                                         f"({kind}) - held for owner's "
                                         f"retention decision"}))
            return "FROZEN"
        entry_id = self._new_entry_id()
        entry = {"entry_id": entry_id, "kind": kind,
                 "envelope_id": env.envelope_id, "from_agent": env.from_agent,
                 "payload": env.payload}
        # tuples 1 & 8: two agents logged conflicting facts for one event
        # (both stand, flagged) / external import conflicts with log-
        # derived state (log wins, differences flagged). Fixed 2026-07-17:
        # zero implementing code existed for either - "both stand" was
        # trivially true (append-only never overwrites) but nothing was
        # ever actually flagged. Compares against the most recent prior
        # entry of the SAME kind for this context; any overlapping key
        # with a differing value is a conflict, named on the new entry
        # itself so a later reader sees it without re-deriving it.
        prior_same_kind = [e for e in self.records.get(ctx, []) if e["kind"] == kind]
        # interaction.log carries many kinds of event (payload "kind":
        # lead_captured, client_touch, ...). Fixed 2026-10-14 (tuple runs):
        # every log entry was compared with whatever log entry came before
        # it, so two different events (a campaign log after a status log)
        # were flagged as "conflicting" on the kind field itself, and the
        # flag meant nothing. Facts conflict only within one kind of event.
        if kind == "interaction.log" and isinstance(env.payload, dict):
            prior_same_kind = [e for e in prior_same_kind
                               if e["payload"].get("kind") == env.payload.get("kind")]
        conflicts = {}
        if prior_same_kind:
            prior_payload = prior_same_kind[-1]["payload"]
            for k, v in env.payload.items():
                if (k in prior_payload and prior_payload[k] != v
                        and isinstance(v, (str, int, float, bool))):
                    conflicts[k] = {"prior": prior_payload[k], "new": v,
                                    "prior_entry_id": prior_same_kind[-1]["entry_id"]}
        if conflicts:
            entry["conflicts_with_prior"] = conflicts
            self.hub.ingest_spoke_trace(
                "14", env.envelope_id,
                thought=f"ctx={ctx!r} kind={kind!r}: conflicting values vs "
                        f"the prior {kind} entry for {sorted(conflicts)} - "
                        f"both stand, log-derived state wins over this new "
                        f"one for now, difference flagged on the entry "
                        f"itself, never silently overwritten",
                result=f"conflict_flagged={sorted(conflicts)}")
        self.records.setdefault(ctx, []).append(entry)
        # the client's drawer gets its own copy of every CRM entry (2026-10-12)
        name = env.payload.get("name") if isinstance(env.payload, dict) else None
        file_record(self.hub, "14", ctx, "interactions", f"{entry_id}_{env.envelope_id[:8]}",
                    {**entry, "client_context_id": ctx},
                    identity={"client_name": name} if isinstance(name, str) else None)
        return entry_id

    _SECRET_WORDS = ("code", "combo", "combination", "password", "pin", "passcode")

    def _access_record(self, ctx: str, env: Envelope):
        """P19 (J3, 2026-10-12). {"access_grant": {"party", "window_end",
        "custody_ref"}} records who may enter and until when;
        {"access_closed": {"party"}} records that the key came back or the
        code was changed. Any field beyond those, or a value that looks like
        it carries the secret itself, is rejected whole: access secrets never
        ride a message (playbook P19)."""
        import datetime
        p = env.payload
        problems = []
        if "access_grant" in p:
            g = p["access_grant"]
            if not isinstance(g, dict) or set(g) != {"party", "window_end", "custody_ref"}:
                problems.append("access_grant takes exactly party, window_end, custody_ref")
            else:
                try:
                    datetime.date.fromisoformat(str(g["window_end"]))
                except ValueError:
                    problems.append("window_end must be YYYY-MM-DD")
                import re as _re
                if any(_re.search(rf"\b{w}\b", str(v).lower())
                       for v in g.values() for w in self._SECRET_WORDS):
                    problems.append("a value looks like it names the access secret - "
                                    "never send the code or key itself")
        if "access_closed" in p:
            c = p["access_closed"]
            if not isinstance(c, dict) or set(c) != {"party"}:
                problems.append("access_closed takes exactly party")
        if problems:
            self.hub.send(_env("14", "queue", "clarification.request", ctx,
                               {"reason": "access record rejected; nothing changed",
                                "problems": problems}))
            return
        if "access_grant" in p:
            self.access_grants.setdefault(ctx, []).append(
                {**p["access_grant"], "closed": False, "flagged": False})
        if "access_closed" in p:
            for g in self.access_grants.get(ctx, []):
                if g["party"] == p["access_closed"]["party"]:
                    g["closed"] = True
        self._append(ctx, "config.update", env)
        self.hub.ingest_spoke_trace("14", env.envelope_id,
                                    thought=f"broker-signed access record for {ctx!r} "
                                            f"(no secret recorded)",
                                    result="access record kept")

    def check_access_custody(self, ctx: str, today: str):
        """Daily clock check, P19 (J3, 2026-10-12): an access grant whose
        window has ended and that the broker has not closed is flagged once."""
        flagged = []
        for g in self.access_grants.get(ctx, []):
            if g["closed"] or g["flagged"] or str(g["window_end"]) >= today:
                continue
            g["flagged"] = True
            flagged.append(g["party"])
            self.hub.send(_env("14", "queue", "clarification.request", ctx,
                               {"reason": f"access window for {g['party']!r} ended "
                                          f"{g['window_end']} and is not closed - confirm the "
                                          f"key is back or the code was changed, then sign "
                                          f"access_closed",
                                "custody_ref": g["custody_ref"]}))
        return f"flagged:{flagged}" if flagged else "none_due"

    def _update_consent(self, ctx: str, new_flags: dict):
        """Most-restrictive-per-channel tuple: a channel already marked
        'no' never gets upgraded to 'yes' by a later, less-restrictive claim
        without an explicit new confirmation event - only downgrades
        (yes->no) or first-time-sets are applied automatically."""
        current = self.consent.setdefault(ctx, {})
        for channel, val in (new_flags or {}).items():
            if channel not in current or val == "no" or current[channel] == "unknown":
                current[channel] = val
            # current[channel] == "yes" and val == "yes": no-op, unchanged
            # current[channel] == "no": stays "no" regardless of new claim
            # (most restrictive wins) UNLESS the new event is itself an
            # explicit reconfirmation, which callers signal separately.

    def check_client_dates(self, ctx: str, today: str):
        """Daily clock check (added 2026-10-11): P13's date triggers for one
        client, from the broker-signed client_dates. Before this, nothing in
        production ever called check_date_triggers, so P13 never ran."""
        return self.check_date_triggers(today, {ctx: self.client_dates.get(ctx, {})})

    def check_date_triggers(self, today: str, client_dates: dict[str, dict[str, str]]):
        """Job component: emit date triggers (birthday, holiday, purchase/
        move-in anniversary) to 16, per the human-supplied client list.
        Per P13: schedule-driven (owner-configured daily check), not
        envelope-triggered - there is no inbound routed intent for this,
        matching the playbook's own framing ('consumed by Agent 00').
        Precondition (P13): contact must be on the supplied list AND pass
        consent - no list entry, no touch."""
        fired = []
        for ctx, dates in client_dates.items():
            consent = self.consent.get(ctx, {})
            if not any(v == "yes" for v in consent.values()):
                continue  # no consent on file, no touch - P13 precondition
            for event_type, date_str in dates.items():
                # "MM-DD" recurs every year; "YYYY-MM-DD" fires on that day
                due = date_str == today or (len(date_str) == 5 and date_str == today[5:])
                if due and (ctx, event_type, today) not in self._dates_fired:
                    self._dates_fired.add((ctx, event_type, today))
                    self.hub.send(_env("14", "16", "date.trigger", ctx,
                                       {"event_type": event_type, "date": today}))
                    fired.append((ctx, event_type))
        return fired

    def overnight_leads(self) -> dict:
        """Owner decision 8 (2026-10-21): the morning briefing's lead
        section - every lead captured since the last briefing, from the
        CRM's own entries, each reported once."""
        leads = []
        for ctx, entries in self.records.items():
            tier = None
            for e in entries:
                if e["kind"] == "interaction.log" and "tier" in e["payload"]:
                    tier = e["payload"]["tier"]
            for e in entries:
                if (e["kind"] == "interaction.log"
                        and e["payload"].get("kind") == "lead.captured"
                        and e["entry_id"] not in self.briefed_leads):
                    self.briefed_leads.add(e["entry_id"])
                    leads.append({"context": ctx, "entry_id": e["entry_id"],
                                  "captured": e["payload"].get("today"),
                                  "tier": tier})
        return {"count": len(leads), "leads": leads,
                "basis": "lead.captured entries not in an earlier briefing"}

    def generate_report(self, report_type: str = "eod", today: str | None = None):
        """Job component: pipeline reports from stored data only - a
        report never contains a figure that cannot be traced to records.
        Per P17: scheduled daily close, not envelope-triggered. Owner
        decision 9 (2026-10-21): the end-of-day books run on the evening
        clock and go to Agent 15, which adds the day's figures and sends
        you one report."""
        interaction_count = sum(len(v) for v in self.records.values())
        tiers = {}
        for ctx, entries in self.records.items():
            for e in entries:
                if e["kind"] == "interaction.log" and "tier" in e["payload"]:
                    tiers[ctx] = e["payload"]["tier"]  # last write wins, traced to entry_id

        # tuple 3: report requested over a known logging gap -> state the
        # gap, never smooth. Fixed 2026-07-17 - zero gap-detection existed;
        # the report just presented whatever data existed as if it were
        # complete. Real, detectable gap: side-channel state (consent,
        # property interests, buyer agreement, identity verification) that
        # exists for a context with NO backing log entry at all - meaning
        # something happened for that context that this log never captured.
        contexts_with_side_state = (set(self.consent) | set(self.property_interests)
                                    | set(self.buyer_agreement) | set(self.identity_verified))
        logging_gaps = sorted(ctx for ctx in contexts_with_side_state
                              if not self.records.get(ctx))

        report = {
            "report_type": report_type,
            "traced_to_entries": True,
            "total_interactions": interaction_count,
            "contexts_covered": len(self.records),
            "tier_snapshot": tiers,
            "logging_gaps": logging_gaps,
            "today": today,
        }
        if report_type == "eod":
            self.hub.send(_env("14", "15", "report.package", "eod-report", report))
        else:   # any other report (a listing's activity, P23) comes straight to you
            self.hub.send(_env("14", "human", "report.package", "eod-report", report))
        return report

    def handle(self, env: Envelope):
        if env.intent == "clock.tick":   # daily clock, through the hub (owner rule 2026-10-11)
            from .clock import handle_tick
            return handle_tick(self, "14", env)
        ctx = env.client_context_id

        if env.intent == "briefing.request":
            # owner decision 8 (2026-10-21): 18 asks for the morning section
            section = self.overnight_leads()
            self.hub.send(_env("14", "18", "report.package", ctx,
                               {"section": "overnight_leads", "data": section},
                               confidence=SOURCE_VERIFIED))
            return

        if env.intent == "record.request":
            requester_scope = env.payload.get("requester_scope")
            dedupe_key = env.payload.get("dedupe_key")
            entries = self.records.get(ctx, [])

            if dedupe_key is not None:
                known = any(e["kind"] == "interaction.log"
                           and e["payload"].get("kind") == "lead.captured"
                           for e in entries)
                # same phone/email under ANOTHER context: reported, never
                # merged here (01 flags it for a human)
                ids = set(env.payload.get("identifiers") or [])
                possible = sorted(
                    other for other, other_entries in self.records.items()
                    if other != ctx and ids and any(
                        e["kind"] == "interaction.log"
                        and e["payload"].get("kind") == "lead.captured"
                        and ids & set(e["payload"].get("identifiers") or [])
                        for e in other_entries))
                consent = dict(self.consent.get(ctx, {}))
                interests = list(self.property_interests.get(ctx, []))
                self.hub.ingest_spoke_trace(
                    "14", env.envelope_id,
                    thought=f"dedupe lookup ctx={ctx!r}: "
                            f"{'HIT - prior lead.captured exists' if known else 'MISS'}; "
                            f"returning current consent + interest state "
                            f"(authoritative here, never held by 01 across turns)",
                    result=f"known={known}")
                self.hub.send(_env("14", env.from_agent, "record.response",
                                   ctx, {"known": known, "consent": consent,
                                        "property_interests": interests,
                                        "possible_duplicate_of": possible},
                                   confidence=SOURCE_VERIFIED))
                return

            # Need-to-know: a record.request is the only legitimate way to
            # ask for a context. Corrected 2026-07-17: this used to claim
            # "this is the redundant local check named in the tuple," which
            # was misleading - no distinct check exists in this class. The
            # real enforcement is the hub's own routing legality, verified
            # directly against routes.json: record.request's only legal
            # senders are 01, 11, 13, 15, and handle() is never reached by
            # anything else. There is no alternate path that bypasses this.
            entries_out = list(entries)
            self.hub.ingest_spoke_trace(
                "14", env.envelope_id,
                thought=f"record.request ctx={ctx!r}: {len(entries_out)} "
                        f"entries returned verbatim, no interpretation",
                result=f"returned={len(entries_out)}")
            self.hub.send(_env("14", env.from_agent, "record.response", ctx,
                               {"entries": entries_out, "absent": not entries_out,
                                "consent": dict(self.consent.get(ctx, {})),
                                "buyer_agreement_on_file": self.buyer_agreement.get(ctx, False),
                                "requester_identity_verified": self.identity_verified.get(ctx, False)},
                               confidence=SOURCE_VERIFIED))
            return

        if env.intent == "interaction.log":
            payload = env.payload
            entry_id = self._append(ctx, "interaction.log", env)
            if "consent" in payload:
                self._update_consent(ctx, payload["consent"])
            if "property_interests" in payload:
                self.property_interests[ctx] = list(payload["property_interests"])
            if "buyer_agreement_on_file" in payload:
                self.buyer_agreement[ctx] = bool(payload["buyer_agreement_on_file"])
            if "requester_identity_verified" in payload:
                self.identity_verified[ctx] = bool(payload["requester_identity_verified"])
            self.hub.ingest_spoke_trace(
                "14", env.envelope_id,
                thought=(f"append-only interaction entry {entry_id}; "
                         if entry_id != "FROZEN" else
                         # 2026-10-14 (tuple runs): this used to read
                         # "appended=FROZEN" when nothing was appended
                         "record frozen, NO entry appended; ")
                        + f"consent updated per most-restrictive-per-channel "
                        f"rule if present in payload; property interests "
                        f"list replaced with the caller's full current list",
                result=(f"appended={entry_id}" if entry_id != "FROZEN"
                        else "not appended: record_frozen; side state updated"))
            return

        if env.intent in ("transaction.closed", "status.update"):
            entry_id = self._append(ctx, env.intent, env)
            self.hub.ingest_spoke_trace(
                "14", env.envelope_id,
                thought=f"audit receiver: {env.intent} appended as "
                        f"{entry_id}; log-derived state wins over any "
                        f"conflicting external import, flagged if conflict",
                result=f"appended={entry_id}")
            return

        if env.intent == "config.update" and ("access_grant" in env.payload
                                              or "access_closed" in env.payload):
            return self._access_record(ctx, env)

        if env.intent == "config.update" and "consent_record" in env.payload:
            # Owner decision 2026-10-12: Agent 11 sends nothing to a client
            # without consent on record here. Leads get theirs from 01 at
            # capture; for any other client (a seller, a buyer, a party to a
            # deal) the broker records it with this signed setting, e.g.
            # {"consent_record": {"email": "yes", "text": "no"}}. A channel
            # the client opted out of stays "no" unless the setting says the
            # client reconfirmed ("reconfirmed_by_client": true).
            rec = env.payload["consent_record"]
            extra = sorted(set(env.payload) - {"consent_record", "reconfirmed_by_client"})
            ok = (isinstance(rec, dict) and rec and not extra
                  and all(k in ("call", "text", "email") and v in ("yes", "no")
                          for k, v in rec.items())
                  and isinstance(env.payload.get("reconfirmed_by_client", False), bool))
            if not ok:
                self.hub.send(_env("14", "queue", "clarification.request", ctx,
                                   {"reason": "consent_record rejected; nothing changed - "
                                              "expected {\"consent_record\": {\"call\"|\"text\"|"
                                              "\"email\": \"yes\"|\"no\"}} and optionally "
                                              "\"reconfirmed_by_client\": true"}))
                return
            current = self.consent.setdefault(ctx, {})
            kept_no = sorted(ch for ch, v in rec.items()
                             if v == "yes" and current.get(ch) == "no"
                             and not env.payload.get("reconfirmed_by_client"))
            for ch, v in rec.items():
                if ch not in kept_no:
                    current[ch] = v
            self._append(ctx, "config.update", env)
            if kept_no:
                self.hub.send(_env("14", "queue", "clarification.request", ctx,
                                   {"reason": "the client opted out on these channels; they stay "
                                              "\"no\" until the setting says the client reconfirmed",
                                    "channels": kept_no}))
            self.hub.ingest_spoke_trace("14", env.envelope_id,
                                        thought=f"broker-signed consent for {ctx!r}: {dict(current)}"
                                                + (f"; kept 'no' on {kept_no}" if kept_no else ""),
                                        result="consent recorded")
            return

        if env.intent == "config.update" and "client_dates" in env.payload:
            # P13 dates for this client (broker-signed). Validated whole.
            import re as _re
            d = env.payload["client_dates"]
            ok = isinstance(d, dict) and d and all(
                isinstance(k, str) and isinstance(v, str)
                and (_re.fullmatch(r"\d{2}-\d{2}", v) or _re.fullmatch(r"\d{4}-\d{2}-\d{2}", v))
                for k, v in d.items())
            if not ok:
                self.hub.send(_env("14", "queue", "clarification.request", ctx,
                                   {"reason": "client_dates rejected; nothing changed - "
                                              "event name -> MM-DD (yearly) or YYYY-MM-DD (once)"}))
                return
            self.client_dates[ctx] = dict(d)
            self.hub.ingest_spoke_trace("14", env.envelope_id,
                                        thought=f"broker-signed client dates for {ctx!r}: {sorted(d)}",
                                        result="client dates set")
            return

        if env.intent == "config.update" and ("buyer_agreement_on_file" in env.payload
                                              or "requester_identity_verified" in env.payload):
            # The broker's signed record that a buyer representation
            # agreement is on file / the requester's identity is verified.
            # Added 2026-10-11 (real-traffic check): nothing in the swarm
            # ever recorded either fact, so every client showing request
            # stopped at "no buyer agreement" - P06/P07 only worked from
            # hand-built test logs. Both must be true/false, nothing else.
            p = env.payload
            bad = [k for k in ("buyer_agreement_on_file", "requester_identity_verified")
                   if k in p and not isinstance(p[k], bool)]
            if bad:
                self.hub.send(_env("14", "queue", "clarification.request", ctx,
                                   {"reason": "record update rejected; nothing changed",
                                    "problems": [f"{k} must be true or false" for k in bad]}))
                return
            if "buyer_agreement_on_file" in p:
                self.buyer_agreement[ctx] = p["buyer_agreement_on_file"]
            if "requester_identity_verified" in p:
                self.identity_verified[ctx] = p["requester_identity_verified"]
            self._append(ctx, "config.update", env)
            self.hub.ingest_spoke_trace(
                "14", env.envelope_id,
                thought=f"broker-signed record for ctx={ctx!r}: buyer agreement="
                        f"{self.buyer_agreement.get(ctx, False)}, identity verified="
                        f"{self.identity_verified.get(ctx, False)}",
                result="record updated")
            return

        if env.intent == "config.update" and env.payload.get("action") == "release_record_freeze":
            # The owner's signed resolution of a retention question - the
            # ONLY unfreeze path, and config.update is signature-gated at
            # the hub before it ever reaches here.
            self.frozen.discard(ctx)
            self.hub.ingest_spoke_trace(
                "14", env.envelope_id,
                thought=f"owner released the freeze on ctx={ctx!r} - "
                        f"appends resume",
                result="unfrozen")
            return

        if env.intent == "config.update" and env.payload.get("action") == "delete_record":
            # retention/deletion is never a spoke decision - freeze + escalate
            self.frozen.add(ctx)
            self.hub.ingest_spoke_trace(
                "14", env.envelope_id,
                thought="deletion/retention request - freeze the record, "
                        "escalate to human/owner; retention rules are "
                        "jurisdiction, never a spoke judgment call",
                result="frozen, escalated")
            self.hub.escalate("escalation.legal_line",
                              {"client_context_id": ctx,
                               "trigger": "record deletion/retention request",
                               "agent": "14"})
            return


class Spoke01LeadCapture:
    """Front-of-funnel intake. Captures; never qualifies, scores, or advises.

    Rebuilt against all 16 DECISIONS.md tuples - the P11 demo version
    implemented roughly two of these and inverted the consent-refusal
    behavior (dropped the lead instead of capturing it with outreach
    suppressed). Fixed here.
    """

    # TUNABLE (added 2026-07-17): record_response_timeout_days=1.
    # See docs/TUNING_MANUAL.md to change.
    def __init__(self, hub, brokerage_scope: set[str] | None = None,
                 dnc_list: set[str] | None = None,
                 record_response_timeout_days: int = 1):
        self.hub = guard(hub, "01")   # handoff rule (audit TU-2)
        self.pending: dict[str, dict] = {}
        # addresses/listing-IDs this brokerage actually lists (tuple: property
        # outside scope -> log + human, never redirect). None/empty = nothing
        # configured yet = everything is out of scope until set (fail closed,
        # same discipline as freight's service_scope).
        self.brokerage_scope = brokerage_scope or set()
        # the brokerage's own listings, as Agent 05 records them (P04
        # walkthrough 2026-10-21): kept apart from the signed scope, so a
        # signed scope that replaces the set never drops a listing we hold
        self.own_listings: set[str] = set()
        # phone/email already on the do-not-call/do-not-contact list
        self.dnc_list = dnc_list or set()
        self.record_response_timeout_days = record_response_timeout_days
        # tuple 16: record.response never returns -> retry once, then hold
        # with handoff.failed. Fixed 2026-07-17 - zero code existed for
        # this at all; a non-answering 14 left pending[ctx] stuck forever
        # with no timeout, no retry, no signal.
        self.retry_count: dict[str, int] = {}
        # possible-duplicate leads held for the broker (owner decision #3)
        self.held_duplicates: dict[str, dict] = {}
        register_spoke(hub, "01", self)
        register_resumer(hub, "01", self._resume)

    def _legal_line_hit(self, payload: dict) -> str | None:
        note = str(payload.get("message", "")) + " " + str(payload.get("request", ""))
        low = note.lower()
        for w in _LEGAL_LINE_WORDS:
            if w in low:
                return note.strip()
        return None

    def _demands_human_hit(self, payload: dict) -> str | None:
        note = str(payload.get("message", "")) + " " + str(payload.get("request", ""))
        low = note.lower()
        for w in _DEMANDS_HUMAN_WORDS:
            if w in low:
                return note.strip()
        return None

    def handle(self, env: Envelope):
        if env.intent == "clock.tick":   # daily clock, through the hub (owner rule 2026-10-11)
            from .clock import handle_tick
            return handle_tick(self, "01", env)
        if env.intent == "listing.data" and env.from_agent == "05":
            for k in ("listing_id", "address"):
                if env.payload.get(k):
                    self.own_listings.add(env.payload[k])
            return
        if env.intent == "config.update" and ("brokerage_scope" in env.payload
                                              or "dnc_add" in env.payload):
            # Broker-signed (config.update is signature-gated at the hub).
            # Added 2026-10-11 (scene run): scope and the do-not-contact list
            # could only be passed to the constructor, so a running swarm
            # treated every listing inquiry as out of scope and had no way
            # to add a number to DNC. brokerage_scope REPLACES the set (a
            # listing you no longer hold must be removable); dnc_add only
            # adds - nothing here removes a DNC entry. Validated whole.
            p, ctx = env.payload, env.client_context_id
            problems = []
            for key in ("brokerage_scope", "dnc_add"):
                if key in p and (not isinstance(p[key], list) or not all(
                        isinstance(x, str) and x.strip() for x in p[key])):
                    problems.append(f"{key} must be a list of non-empty strings")
            if problems:
                self.hub.send(_env("01", "queue", "clarification.request", ctx,
                                   {"reason": "lead-capture config rejected; nothing changed",
                                    "problems": problems}))
                return
            if "brokerage_scope" in p:
                self.brokerage_scope = set(p["brokerage_scope"])
            if "dnc_add" in p:
                self.dnc_list |= set(p["dnc_add"])
            self.hub.ingest_spoke_trace(
                "01", env.envelope_id,
                thought=f"broker-signed config: scope={sorted(self.brokerage_scope)}, "
                        f"dnc entries={len(self.dnc_list)}",
                result="lead-capture config applied")
            return
        if env.intent in ("lead.signal", "lead.inbound"):
            payload = env.payload
            ctx = env.client_context_id

            # --- Minor-safety protocol: absolute, checked before anything
            # else. Capture NOTHING beyond the fact of contact. ---
            if payload.get("apparent_minor"):
                self.hub.ingest_spoke_trace(
                    "01", env.envelope_id,
                    thought="apparent minor inquiring - capture nothing "
                            "beyond the fact of contact per hard rule; "
                            "human immediately, not a judgment call",
                    result="escalated: minor_safety, no data captured")
                self.hub.escalate("escalation.legal_line",
                                  {"client_context_id": ctx,
                                   "trigger": "apparent minor inquiry - fact "
                                             "of contact only, no data captured",
                                   "agent": "01"})
                return

            # --- Legal line: fiduciary advice / negotiation / legal opinion ---
            trigger = self._legal_line_hit(payload)
            if trigger:
                self.hub.ingest_spoke_trace(
                    "01", env.envelope_id,
                    thought=f"request crosses the legal line: {trigger!r} - "
                            f"not this agent's territory; escalating "
                            f"verbatim, not answering or approximating",
                    result="escalated: legal_line")
                self.hub.escalate("escalation.legal_line",
                                  {"client_context_id": ctx,
                                   "trigger": trigger, "agent": "01"})
                return

            # --- Abusive contact: stay professional, close politely, log
            # verbatim, escalate as a complaint - but STILL capture what's
            # already been given (doesn't return early). ---
            abusive = bool(payload.get("abusive"))
            if abusive:
                self.hub.escalate("escalation.complaint",
                                  {"client_context_id": ctx,
                                   "trigger": "abusive contact",
                                   "verbatim": payload.get("message", "")})

            # --- tuple 3: caller demands a human now -> escalate
            # immediately, but still capture what's already given (doesn't
            # return early, same as abusive above). Fixed 2026-07-17 - zero
            # code existed for this tuple at all. ---
            demands_human = self._demands_human_hit(payload)
            if demands_human:
                self.hub.ingest_spoke_trace(
                    "01", env.envelope_id,
                    thought=f"caller demands a human now: {demands_human!r} - "
                            f"escalating immediately, still capturing what's "
                            f"already been given rather than dropping it",
                    result="escalated: demands_human")
                self.hub.escalate("escalation.legal_line",
                                  {"client_context_id": ctx,
                                   "trigger": f"caller demands a human now: "
                                             f"{demands_human!r}",
                                   "agent": "01"})

            # --- DNC check: the list wins over the opportunity. Still
            # captured (source + suppression), never silently dropped.
            # 2026-10-14: compared in normalized form, and on every contact
            # the lead gave. Before, only the phone (or, with no phone, the
            # email) was checked, as exact text: "330-555-0190" did not
            # match a list entry "(330) 555-0190", and a listed email was
            # missed whenever the lead also gave a phone. ---
            contact = payload.get("phone") or payload.get("email")
            on_dnc = bool(set(_contact_identifiers(payload)) & _dnc_identifiers(self.dnc_list))

            # --- Property scope check ---
            interest = payload.get("property_interest", {})
            addr_or_listing = interest.get("address") or interest.get("listing_id")
            out_of_scope = (addr_or_listing is not None
                           and addr_or_listing not in self.brokerage_scope
                           and addr_or_listing not in self.own_listings)
            if out_of_scope:
                self.hub.ingest_spoke_trace(
                    "01", env.envelope_id,
                    thought=f"inquiry about {addr_or_listing!r} - not in "
                            f"this brokerage's configured listing scope; "
                            f"log + human, never redirect to another "
                            f"brokerage unprompted",
                    result="escalated: out_of_scope_property, logged")
                self.hub.escalate("escalation.legal_line",
                                  {"client_context_id": ctx,
                                   "trigger": f"inquiry outside brokerage "
                                             f"scope: {addr_or_listing}",
                                   "agent": "01"})
                # still fall through to capture the contact - the tuple says
                # log + human, not "discard the lead"

            # --- Consent, captured regardless of the answer (tuple: refusal
            # captures the lead, marks no-consent; it does not drop it) ---
            consent_raw = payload.get("consent")  # e.g. {"call":"yes","text":"no","email":"unknown"}
            if consent_raw is None:
                consent_raw = {"call": "unknown", "text": "unknown", "email": "unknown"}
            # "stop contacting me" mid-capture -> immediate blanket suppression
            # + confirmation once (tuple 15). Fixed 2026-07-17: this agent had
            # no route to 11 at all before, so no confirmation could ever be
            # sent - suppression fired but nothing told the client it worked.
            if payload.get("revoke_all_contact"):
                consent_raw = {k: "no" for k in ("call", "text", "email")}
                self.hub.send(_env("01", "11", "client.message.request", ctx,
                                   {"template": "opt_out_confirmed"}))

            # tuple 7: caller refuses consent to RECORDING (distinct from
            # tuple 2's messaging consent) -> contact info only, mark
            # no-consent, NO nurture entry. Fixed 2026-07-17 - zero code
            # existed for this tuple; only messaging consent (tuple 2) was
            # ever checked.
            recording_consent_refused = payload.get("recording_consent") == "no"
            if recording_consent_refused:
                self.hub.ingest_spoke_trace(
                    "01", env.envelope_id,
                    thought="caller refuses consent to recording - contact "
                            "info only, marking no-consent, no nurture "
                            "entry per this tuple specifically (distinct "
                            "from the general messaging-consent tuple)",
                    result="recording_consent_refused: contact-only capture")
                # "human informed" half of the tuple (2026-10-12 doc review:
                # the trace was the only record, nobody was told)
                self.hub.send(_env("01", "queue", "clarification.request", ctx,
                                   {"reason": "caller refused consent to recording - "
                                              "contact captured only, no nurture entry, "
                                              "no messaging"}))

            # --- Multiple near-simultaneous inbounds for the same context:
            # merge by channel priority (call > text > web_form), drop
            # nothing - accumulate into a list, don't overwrite. ---
            existing = self.pending.get(ctx)
            channel = payload.get("channel", "web_form")
            raw_inputs = (existing["raw_inputs"] if existing else []) + [
                {"channel": channel, "payload": dict(payload)}]

            def _pick(field):
                """Highest channel-rank source for this field, across all
                raw inputs seen so far for this context - never drops a
                lower-rank input, just orders precedence on conflict."""
                candidates = [(CHANNEL_RANK.get(r["channel"], 0), r["payload"].get(field))
                             for r in raw_inputs if r["payload"].get(field) not in (None, "")]
                if not candidates:
                    return None
                candidates.sort(key=lambda t: -t[0])
                return candidates[0][1]

            name = _pick("name")
            timeline = _pick("timeline")
            budget = _pick("budget")
            preapproval = payload.get("preapproval_status", "unknown")
            if preapproval not in ("yes", "no", "unknown"):
                preapproval = "unknown"  # never inferred

            # low-confidence transcription -> mark unknown, never tier on it.
            # Fixed 2026-07-17: only name was nulled before - timeline/budget/
            # preapproval could be equally garbled from the same transcription
            # and were being tiered on regardless.
            low_confidence = payload.get("transcription_confidence") == "low"
            if low_confidence and channel == "call":
                name = None
                timeline = None
                budget = None
                preapproval = "unknown"

            # obviously-false contact data: pass through an explicit
            # upstream signal, never guess at "obviously false" ourselves
            contact_valid_flag = payload.get("contact_data_suspect")

            # volunteered info beyond schema -> verbatim notes, never parsed
            notes = existing["notes"] if existing else []
            if payload.get("notes"):
                notes = notes + [str(payload["notes"])]

            # same person, two property interests -> one context, both
            # interests recorded, never two contexts
            interests = (existing["property_interests"] if existing else [])
            if interest and interest not in interests:
                interests = interests + [interest]

            captured = {
                "name": ({"value": name, "source": STATED_BY_PARTY} if name
                        and not recording_consent_refused else None),
                "contact": {"value": contact, "source": STATED_BY_PARTY,
                           "suspect": contact_valid_flag},
                "property_interests": interests,
                "timeline": ({"value": timeline, "source": STATED_BY_PARTY}
                            if timeline and not recording_consent_refused else None),
                "budget": ({"value": budget, "source": STATED_BY_PARTY}
                          if budget and not recording_consent_refused else None),
                "preapproval_status": (UNKNOWN if recording_consent_refused
                                      else preapproval),
                "consent": ({k: "no" for k in ("call", "text", "email")}
                           if recording_consent_refused else consent_raw),
                "no_nurture_entry": recording_consent_refused,
                "dnc": on_dnc,
                "notes_verbatim": notes,
                "prior_relationship_claim": payload.get("prior_relationship_claim"),
            }
            # Contract fix, found by the first END-TO-END playbook run
            # (2026-07-18): 02's rubric reads timeline_days,
            # financing_progress, stated_urgency and preapproval_doc -
            # none of which this capture schema ever forwarded, so with
            # REAL 01 traffic 02 could never score on them (its own tests
            # fed flat hand-built payloads that real traffic never
            # produces). Pass-through VERBATIM when the inbound supplied
            # them - same discipline as 19's property-fields fix: never
            # derived (turning "2 weeks" into 14 would be the
            # interpretation tuple 4 forbids), only forwarded.
            for f in ("timeline_days", "financing_progress",
                      "stated_urgency", "preapproval_doc"):
                if f in payload and not recording_consent_refused:
                    captured[f] = payload[f]
            # Agent 02's tuple "(lead is an agent shopping for a client, flag
            # agent-to-agent; ...)" reads is_agent_shopping, which this
            # capture never forwarded, so the tuple could not fire on a lead
            # that arrived through intake (found by the synthetic sample run,
            # 2026-10-14). Forwarded verbatim, never inferred here.
            if payload.get("is_agent_shopping") is True:
                captured["is_agent_shopping"] = True
            if low_confidence and channel == "call":
                for f in ("timeline_days", "financing_progress",
                          "stated_urgency", "preapproval_doc"):
                    captured.pop(f, None)  # garbled transcript: never tier on it

            # tuple 10: prior relationship claimed -> captured as stated_by_
            # party (done above), AND human confirms before any history is
            # assumed. Fixed 2026-07-17 - the claim was stored but nothing
            # ever actively asked a human to confirm it.
            if payload.get("prior_relationship_claim"):
                self.hub.escalate("escalation.legal_line",
                                  {"client_context_id": ctx,
                                   "trigger": f"prior relationship claimed: "
                                             f"{payload['prior_relationship_claim']!r} "
                                             f"- human confirmation required "
                                             f"before any history is assumed",
                                   "agent": "01"})
            # the day this capture happened, forwarded so 02's waits carry a
            # real "since" (scene run 2026-10-11: briefings showed since=null)
            if payload.get("today"):
                captured["today"] = payload["today"]
            # and the time it arrived, when the source gives one: Agent 03
            # sends the day-0 touch at once inside contact hours by it
            # (owner decision 7, 2026-10-21)
            if payload.get("now_iso"):
                captured["now_iso"] = payload["now_iso"]
            self.pending[ctx] = {**captured, "raw_inputs": raw_inputs, "notes": notes,
                                 "property_interests": interests,
                                 "requested_at": payload.get("today"),
                                 "identifiers": _contact_identifiers(payload)}

            if on_dnc:
                self.hub.escalate("escalation.legal_line",
                                  {"client_context_id": ctx,
                                   "trigger": "lead on DNC list - source "
                                             "logged, outreach suppressed",
                                   "agent": "01"})

            self.hub.ingest_spoke_trace(
                "01", env.envelope_id,
                thought=f"tender captured via {channel}; dedupe against CRM "
                        f"(14) before creating a new lead object - never "
                        f"merge unconfirmed identity",
                result="record.request issued")
            # SKILL.md edge, ratified: OUT -> 18 | Wait-state signal (dedupe
            # pending) | agent.status. Gap found 2026-07-17; ORDERING bug in
            # that fix found 2026-07-18 by the operator console's first
            # smoke run: the wait used to open AFTER the record.request -
            # but 14 answers synchronously inside hub.send, so the resolve
            # fired before the open and a permanently-waiting ghost sat in
            # 18's briefing forever. Open BEFORE asking; a wait that can
            # resolve before it exists isn't a wait.
            self.hub.send(_env("01", "18", "agent.status", ctx,
                               {"waiting_on": "crm_dedupe_response",
                                "since": payload.get("today")}))
            self.hub.send(_env("01", "14", "record.request", ctx,
                               {"dedupe_key": ctx,
                                "identifiers": self.pending[ctx]["identifiers"]}))
            return

        if env.intent == "record.response":
            ctx = env.client_context_id
            pending = self.pending.get(ctx)
            if pending is None:
                self.hub.ingest_spoke_trace(
                    "01", env.envelope_id,
                    thought=f"record.response for ctx={ctx!r} has no "
                            f"matching pending capture - cannot correlate, "
                            f"flagging rather than guessing",
                    result="flagged: uncorrelated response")
                self.hub.send(_env("01", "queue", "clarification.request",
                                   ctx, {"reason": "uncorrelated record.response"}))
                return
            self.retry_count.pop(ctx, None)
            # Wait opened at record.request time is now over - clear it so
            # 18's briefing never shows a resolved dedupe as still pending.
            self.hub.send(_env("01", "18", "agent.status", ctx,
                               {"waiting_on": "crm_dedupe_response",
                                "resolved": True}))
            payload = dict(pending)
            raw_inputs = payload.pop("raw_inputs")
            notes = payload.pop("notes")
            identifiers = payload.pop("identifiers", [])
            known = env.payload["known"]
            # tuple: possible duplicate identity, unconfirmed -> new context
            # + flag, never merge. Added 2026-10-11 (scene run): 14 only
            # matched the context id, so the same person arriving under a
            # new context was never flagged at all.
            possible_dupes = list(env.payload.get("possible_duplicate_of") or [])
            if possible_dupes:
                payload["possible_duplicate_of"] = possible_dupes
            prior_consent = env.payload.get("consent", {})
            prior_interests = env.payload.get("property_interests", [])
            payload["duplicate"] = known

            # Consent: most-restrictive-per-channel against 14's
            # AUTHORITATIVE prior state (never against 01's own memory -
            # MANNERS #9, never rebuild state from memory of prior turns).
            merged_consent = dict(prior_consent)
            for ch, val in payload["consent"].items():
                if ch not in merged_consent or val == "no" or merged_consent[ch] == "unknown":
                    merged_consent[ch] = val
                # merged_consent[ch] == "no" and val != "no": stays "no"
            payload["consent"] = merged_consent

            # Same-person-two-properties: merge against 14's authoritative
            # prior interest list, same reason.
            merged_interests = list(prior_interests)
            for i in payload["property_interests"]:
                if i not in merged_interests:
                    merged_interests.append(i)
            payload["property_interests"] = merged_interests

            self.pending.pop(ctx, None)
            captured = {"payload": payload, "known": known, "identifiers": identifiers,
                        "possible_duplicate_of": possible_dupes}

            if possible_dupes:
                # Owner decision 2026-10-11 (#3): the same phone/email already on
                # record under another context -> the WHOLE thread holds for the
                # broker. Nothing is scored, paged or logged as a lead until the
                # broker signs continue (a separate person) or cancel.
                self.held_duplicates[ctx] = captured
                self.hub.ingest_spoke_trace(
                    "01", env.envelope_id,
                    thought=f"same phone/email already on record under "
                            f"{possible_dupes}; identity unconfirmed - holding "
                            f"{ctx!r} for the broker, never merging and never "
                            f"scoring until a signed continue",
                    result="held: possible duplicate identity")
                hold_for_human(self.hub, "01", ctx, "lead.captured",
                               f"possible duplicate person: same phone or email as "
                               f"{', '.join(possible_dupes)}. Continue = a separate "
                               f"person, scored as a new lead. Cancel = this thread "
                               f"closes, nothing merged.",
                               {"possible_duplicate_of": possible_dupes,
                                "contact": payload.get("contact"),
                                "name": payload.get("name")})
                return
            self._forward_captured(ctx, captured, env.envelope_id)
            return

    def _forward_captured(self, ctx: str, captured: dict, eid: str) -> None:
        payload = captured["payload"]
        self.hub.ingest_spoke_trace(
            "01", eid,
            thought=f"dedupe answer known={captured['known']}; consent and "
                    f"property interests merged against 14's "
                    f"authoritative state; forwarding complete lead "
                    f"object to Lead Qualification (02)",
            result="lead.captured issued")
        # Recorded first, then forwarded (2026-10-21, decision 7): the CRM
        # holds the lead and its consent before anything downstream acts.
        # Since the day-0 nurture touch goes at once, 02 -> 03 -> 11 can
        # reach a client inside this same send; in the old order 11 found
        # no consent on record yet and blocked the touch.
        self.hub.send(_env("01", "14", "interaction.log", ctx,
                           {"kind": "lead.captured", "duplicate": captured["known"],
                            "identifiers": captured["identifiers"],
                            "possible_duplicate_of": captured["possible_duplicate_of"],
                            "consent": payload["consent"],
                            "property_interests": payload["property_interests"],
                            "contact": payload.get("contact")}))
        self.hub.send(_env("01", "02", "lead.captured", ctx, payload,
                           confidence=STATED_BY_PARTY))

    def _resume(self, ws, decision_payload: dict):
        """The broker's signed decision on a held possible-duplicate lead.
        Only continue or cancel act; any other decision leaves it held."""
        ctx = ws.client_context_id
        d = decision_of(decision_payload)
        if ctx not in self.held_duplicates:
            self.hub.ingest_spoke_trace("01", ws.wait_id,
                                        thought=f"decision for {ctx!r} but nothing is held there",
                                        result="no held lead")
            return "nothing_held"
        if d == "other":
            self.hub.ingest_spoke_trace("01", ws.wait_id,
                                        thought=f"decision {decision_payload.get('decision')!r} is "
                                                f"neither continue nor cancel - {ctx!r} stays held",
                                        result="still held")
            return "unsupported decision - still held"
        captured = self.held_duplicates.pop(ctx)
        if d == "continue":
            self._forward_captured(ctx, captured, ws.wait_id)
            return "continued: scored as a separate person"
        self.hub.ingest_spoke_trace(
            "01", ws.wait_id,
            thought=f"broker cancelled the possible-duplicate thread {ctx!r}; nothing "
                    f"merged, nothing scored",
            result="cancelled")
        self.hub.send(_env("01", "14", "interaction.log", ctx,
                           {"kind": "duplicate_thread_cancelled",
                            "possible_duplicate_of": captured["possible_duplicate_of"],
                            "contact": captured["payload"].get("contact")}))
        return "cancelled"

    def check_record_response_timeout(self, ctx: str, today: str):
        """Tuple 16: record.response never returns -> retry once, then hold
        the lead in pending with handoff.failed - never tier undeduped.
        Called by a scheduler/sweep, matching Agent 07's check_deadlines
        and Agent 08's document-chase pattern - this agent had no
        equivalent sweep at all before 2026-07-17."""
        import datetime
        pending = self.pending.get(ctx)
        if pending is None or not pending.get("requested_at"):
            return "no_pending_or_no_timestamp"
        requested = datetime.date.fromisoformat(pending["requested_at"])
        elapsed_days = (datetime.date.fromisoformat(today) - requested).days
        if elapsed_days < self.record_response_timeout_days:
            return "within_timeout"

        retries = self.retry_count.get(ctx, 0)
        if retries == 0:
            self.retry_count[ctx] = 1
            self.hub.ingest_spoke_trace(
                "01", f"timeout-retry-{ctx}",
                thought=f"ctx={ctx!r}: record.response never returned "
                        f"after {elapsed_days}d - retrying record.request "
                        f"once before giving up, per this tuple",
                result="retried: record.request resent")
            self.hub.send(_env("01", "14", "record.request", ctx,
                               {"dedupe_key": ctx}))
            return "retried"

        # already retried once and STILL nothing - hold, never tier undeduped
        self.hub.ingest_spoke_trace(
            "01", f"timeout-failed-{ctx}",
            thought=f"ctx={ctx!r}: retried once, still no record.response "
                    f"after {elapsed_days}d - holding in pending with "
                    f"handoff.failed, never tiering an undeduped lead",
            result="held: handoff.failed")
        self.hub.send(_env("01", "queue", "clarification.request", ctx,
                           {"reason": "record.response never returned after "
                                     "a retry - handoff.failed, lead held "
                                     "undeduped"}))
        # The wait state moves from "pending" to "escalated" - clear it in
        # 18 so the same stuck lead isn't reported twice through two
        # different channels (wait briefing AND clarification queue).
        self.hub.send(_env("01", "18", "agent.status", ctx,
                           {"waiting_on": "crm_dedupe_response",
                            "resolved": True}))
        return "handoff.failed"
