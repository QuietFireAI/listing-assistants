"""Agent 20 - Social Media Monitoring, built against the full spec.

Monitors, classifies, routes. Never posts a public reply autonomously -
a wrong public reply is a permanent public artifact. Drafts go to the
human via 17's review; publication is a human act, always.
"""
from __future__ import annotations

from .core import Envelope
from .handoff_guard import guard, register as register_spoke
from .human_holds import hold_for_human, decision_of, register_resumer

SOURCE_VERIFIED = "source_verified"
STATED_BY_PARTY = "stated_by_party"
UNKNOWN = "unknown"

_PRICING_LEGAL_WORDS = ("the price is", "we can offer", "contract terms",
                       "legal advice", "guarantee")


def _env(frm, to, intent, ctx, payload, confidence=UNKNOWN, in_reply_to=None):
    return Envelope(from_agent=frm, to_agent=to, intent=intent,
                    client_context_id=ctx, payload=payload,
                    confidence=confidence, in_reply_to=in_reply_to,
                    provenance={"source": f"spoke-{frm}", "captured_at": "runtime",
                                "verbatim_available": True})


class Spoke20SocialMediaMonitoring:
    """DECISIONS.md tuples implemented directly (5 active; a 6th entry
    in DECISIONS.md is an owner deferral note, not a decision - not
    implemented as a tuple, since there is nothing to implement):
      1. sentiment genuinely mixed -> classify at complaint priority,
         protective default
      2. mention may involve a client, identity unconfirmed -> route
         without confirming identity anywhere, including the
         clarification itself
      3. negative thread going viral -> escalation.complaint at
         priority, no drafts
      4. praise post detected -> log only, no auto-engagement
      5. question via DM vs public -> both route to 01, channel recorded
         in provenance
    """

    def __init__(self, hub):
        self.hub = guard(hub, "20")   # handoff rule (audit TU-2)
        self.monitored_channels: set[str] = set()
        self.pending_drafts: dict[str, dict] = {}  # envelope_id-keyed via in_reply_to
        # broker-signed reply templates by sentiment (owner decision 7d):
        # drafted only from these, reviewed by 17, then held for the broker
        self.reply_templates: dict[str, str] = {}
        self.drafts_for_approval: dict[str, dict] = {}   # ctx -> draft held for the broker
        register_spoke(hub, "20", self)
        register_resumer(hub, "20", self._resume)

    # behavioral.signal: Agent 20 is no longer a sender on the closed track
    # (owner decision 7e, 2026-10-11). A social mention carries no engagement
    # measure to decide when it should pause nurture; Agent 12 (ad metrics)
    # remains the sender of that signal to 03.

    def _pricing_legal_hit(self, text: str) -> str | None:
        low = text.lower()
        for w in _PRICING_LEGAL_WORDS:
            if w in low:
                return text.strip()
        return None

    def handle(self, env: Envelope):
        ctx = env.client_context_id
        payload = env.payload

        if env.intent == "config.update":
            if "reply_templates" in payload:
                t = payload["reply_templates"]
                bad = (not isinstance(t, dict) or not t or
                       any(k not in ("question", "praise") or not isinstance(v, str) or not v.strip()
                           for k, v in t.items()))
                if bad:
                    self.hub.send(_env("20", "queue", "clarification.request", ctx,
                                       {"reason": "reply_templates rejected; nothing changed - "
                                                  "keys question and/or praise, each a non-empty text"}))
                    return
                self.reply_templates = dict(t)
                self.hub.ingest_spoke_trace(
                    "20", env.envelope_id,
                    thought=f"broker-signed reply templates for {sorted(t)}",
                    result="reply templates set")
            if "monitored_channels" in payload:
                self.monitored_channels.update(payload["monitored_channels"])
            return

        if env.intent == "content.verdict":
            # Drafts never auto-publish regardless of verdict - this
            # agent has no publish capability at all. Verdict is logged
            # for the human's eventual review, nothing more.
            draft = self.pending_drafts.pop(env.in_reply_to, None)
            self.hub.send(_env("20", "18", "agent.status", ctx,
                               {"waiting_on": "draft_compliance_review",
                                "resolved": True}))
            self.hub.send(_env("20", "14", "interaction.log", ctx,
                               {"kind": "draft_verdict_received",
                                "verdict": payload.get("verdict")}))
            if draft is None:
                return
            if payload.get("verdict") != "approved":
                # flagged by compliance: never offered for posting
                self.hub.send(_env("20", "queue", "clarification.request", ctx,
                                   {"reason": "draft social reply flagged by compliance - "
                                              "discarded, not offered for posting",
                                    "draft": draft["text"],
                                    "findings": payload.get("findings")}))
                return
            # owner decision 7d: an approved draft holds for the broker.
            # The swarm never posts it; continue = approved for the broker
            # to post, cancel = discarded.
            self.drafts_for_approval[ctx] = dict(draft)
            hold_for_human(self.hub, "20", ctx, "social.reply.draft",
                           "draft social reply cleared by compliance - continue to "
                           "approve it for you to post (the swarm never posts), "
                           "cancel to discard",
                           {"draft": draft["text"], "source_mention_id": draft.get("source_mention_id")})
            return

        if env.intent == "social.mention":
            channel = payload.get("channel")
            if channel not in self.monitored_channels:
                # not a monitored channel - recorded, never silent
                # (silent-handler sweep 2026-10-11)
                self.hub.ingest_spoke_trace(
                    "20", env.envelope_id,
                    thought=f"mention on {channel!r}, which is not a monitored "
                            f"channel {sorted(self.monitored_channels)} - not acted on",
                    result="ignored: unmonitored channel")
                return

            text = payload.get("text", "")
            sentiment = payload.get("sentiment")  # question/complaint/lead_signal/praise/noise/mixed
            is_viral = payload.get("is_viral", False)
            may_involve_client = payload.get("may_involve_client_unconfirmed", False)

            # tuple 1: genuinely mixed sentiment -> classify at complaint
            # priority, protective default
            effective_sentiment = "complaint" if sentiment == "mixed" else sentiment

            self.hub.send(_env("20", "14", "interaction.log", ctx,
                               {"kind": "mention_classified",
                                "sentiment": effective_sentiment,
                                "channel": channel, "text_verbatim": text},
                              confidence=SOURCE_VERIFIED))

            if effective_sentiment == "complaint":
                # tuple 3: negative thread going viral -> escalate at
                # priority, no drafts - viral or not, complaints never
                # get an autonomous draft either way (this agent never
                # publishes; but "no drafts" for viral means don't even
                # prepare one for human review, escalate raw instead)
                escalation_payload = {"client_context_id": ctx,
                                      "trigger": text, "agent": "20",
                                      "channel": channel}
                if is_viral:
                    escalation_payload["priority"] = "viral"
                # tuple 2: identity unconfirmed -> route without
                # confirming identity anywhere, including here - the
                # escalation never asserts client status either way
                if may_involve_client:
                    escalation_payload["note"] = ("may relate to an "
                                                  "existing matter - "
                                                  "identity not confirmed "
                                                  "or asserted")
                self.hub.escalate("escalation.complaint", escalation_payload)
                # P14 step 2, ratified but unwired for the 20-sourced case
                # until 2026-07-18 (found by the first end-to-end P14
                # run): only 11's OWN angry-client path armed the
                # outbound hold - a complaint arriving via social left
                # every scheduled touch still firing at the complaining
                # party. Armed here over the existing legal 20->11 lane
                # as a RESERVED CONTROL TEMPLATE (never rendered, never
                # sent to a client - 11 intercepts it before the
                # outbound path). Flagged in the review: the cleaner
                # long-term wiring is a ratified 20->11 hold intent,
                # owner's call.
                self.hub.send(_env("20", "11", "client.message.request", ctx,
                                   {"template": "__p14_complaint_hold__",
                                    "reason": "complaint escalated from "
                                              "social monitoring"}))
                return

            if effective_sentiment == "question":
                # tuple 5: DM vs public both route to 01, channel
                # recorded in provenance. If it may involve an existing
                # client, route to 11 instead - but never assert/confirm
                # identity in the routing itself either way (tuple 2).
                if may_involve_client:
                    # Real bug found on the deep pass: client.message.request
                    # is universally treated by 11 as an OUTBOUND send
                    # instruction (template + variables), not a way to
                    # forward an inbound question. Sending {"verbatim":...}
                    # with no "template" key would have made 11 attempt to
                    # send a nonsensical message using the intent name
                    # itself as the template. Fixed: a real template
                    # ("team_will_follow_up", matching the Restricted-Speed
                    # doctrine's own framing) with the verbatim question as
                    # a variable for the human to see when they follow up.
                    self.hub.send(_env("20", "11", "client.message.request",
                                       ctx, {"template": "team_will_follow_up",
                                            "variables": {"channel": channel},
                                            "hour": payload.get("hour", 12),
                                            "inbound_verbatim": text,
                                            "note": "may relate to an "
                                                    "existing matter - "
                                                    "identity not "
                                                    "confirmed or asserted"}))
                else:
                    self.hub.send(_env("20", "01", "lead.signal", ctx,
                                       {"channel": channel, "message": text,
                                        "consent": {"call": "unknown",
                                                   "text": "unknown",
                                                   "email": "unknown"}},
                                      confidence=STATED_BY_PARTY))
                if self.reply_templates.get("question"):
                    self.draft_response(ctx, self.reply_templates["question"], env.envelope_id)
                return

            if effective_sentiment == "praise":
                # tuple 4: logged above as mention_classified, no
                # auto-engagement. A draft only from the broker's own
                # template, held for the broker - the swarm never posts
                # (owner decision 7d, 2026-10-11)
                if self.reply_templates.get("praise"):
                    self.draft_response(ctx, self.reply_templates["praise"], env.envelope_id)
                else:
                    self.hub.ingest_spoke_trace(
                        "20", env.envelope_id,
                        thought="praise mention logged; no broker reply template for "
                                "praise, so no draft",
                        result="logged: praise")
                return

            if effective_sentiment == "lead_signal":
                self.hub.send(_env("20", "01", "lead.signal", ctx,
                                   {"channel": channel, "message": text,
                                    "consent": {"call": "unknown",
                                               "text": "unknown",
                                               "email": "unknown"}},
                                  confidence=STATED_BY_PARTY))
                return

            # "noise" or unrecognized sentiment - no suitable tuple, per
            # root rule: STOP and ask, never guess
            self.hub.send(_env("20", "queue", "clarification.request", ctx,
                               {"reason": f"unrecognized sentiment "
                                         f"classification {sentiment!r} - "
                                         f"no suitable tuple, holding"}))
            return

        if env.intent == "lead.reply":
            # existing-client (or prospect) reply routed back through 11 -
            # this agent's job here is discovery/classification, not
            # ongoing conversation. Logged with the client's words and held
            # for the broker (owner rule 2026-10-11: no reply vanishes).
            self.hub.send(_env("20", "14", "interaction.log", ctx,
                               {"kind": "reply_received", "agent": "20",
                                "verbatim": payload.get("message")}))
            self.hub.send(_env("20", "queue", "clarification.request", ctx,
                               {"reason": "reply routed to social monitoring needs a human",
                                "verbatim": payload.get("message")}))
            return

    def draft_response(self, ctx: str, draft_text: str, source_mention_id: str):
        """Optionally draft a suggested response - clearly labeled DRAFT,
        never published by this agent. Job component: never state/imply
        pricing, legal, or contractual content, never confirm client
        relationship. Checked BEFORE ever submitting for review - this
        agent doesn't even draft that content, let alone publish it."""
        hit = self._pricing_legal_hit(draft_text)
        if hit:
            self.hub.escalate("escalation.legal_line",
                              {"client_context_id": ctx,
                               "trigger": f"drafted response would state/"
                                         f"imply pricing/legal/contractual "
                                         f"content: {hit!r} - never drafted, "
                                         f"let alone published",
                               "agent": "20"})
            return "refused"
        env = _env("20", "17", "content.review", ctx,
                  {"draft": {"text": draft_text, "label": "DRAFT"},
                   "source_mention_id": source_mention_id})
        # wait and pending draft recorded BEFORE the review: 17 answers
        # inside hub.send (same ordering fix as 04/12/15/19)
        self.pending_drafts[env.envelope_id] = {"text": draft_text,
                                                "source_mention_id": source_mention_id}
        self.hub.send(_env("20", "18", "agent.status", ctx,
                           {"waiting_on": "draft_compliance_review"}))
        self.hub.send(env)
        return "submitted_for_review"

    def _resume(self, ws, decision_payload: dict):
        """The broker's signed decision on a draft held for approval."""
        ctx = ws.client_context_id
        d = decision_of(decision_payload)
        if ctx not in self.drafts_for_approval or d == "other":
            return "unchanged"
        draft = self.drafts_for_approval.pop(ctx)
        kind = "draft_approved_for_broker_to_post" if d == "continue" else "draft_discarded_by_broker"
        self.hub.ingest_spoke_trace("20", ws.wait_id,
                                    thought=f"broker decision on draft for {ctx!r}: {kind}; "
                                            f"the swarm posts nothing", result=kind)
        self.hub.send(_env("20", "14", "interaction.log", ctx,
                           {"kind": kind, "draft": draft["text"]}))
        return kind
