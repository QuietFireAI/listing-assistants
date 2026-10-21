"""Agent 12 - Marketing Campaign, built against the full spec.

Distributes and schedules. Listing creative comes from 04 (already
compliance-cleared through 04's own pipeline) - never rewritten here.
Self-written copy (newsletters, non-listing social, ad copy) goes through
17 before anything publishes. The CCP gate (MLS entry confirmed via 05,
or documented exempt status) is hard and applies to every public
marketing action regardless of content source.
"""
from __future__ import annotations

from .core import Envelope
from .handoff_guard import guard, register as register_spoke

SOURCE_VERIFIED = "source_verified"
STATED_BY_PARTY = "stated_by_party"
UNKNOWN = "unknown"


def _env(frm, to, intent, ctx, payload, confidence=UNKNOWN):
    return Envelope(from_agent=frm, to_agent=to, intent=intent,
                    client_context_id=ctx, payload=payload,
                    confidence=confidence,
                    provenance={"source": f"spoke-{frm}", "captured_at": "runtime",
                                "verbatim_available": True})



def _mentions_amount(content, amount) -> bool:
    """Whether ad content shows a dollar amount, written plain or with
    commas (450000, 450,000, $450,000)."""
    try:
        n = int(amount)
    except (TypeError, ValueError):
        return False
    import json as _json
    text = _json.dumps(content, default=str)
    return str(n) in text or f"{n:,}" in text

class Spoke12MarketingCampaign:
    """DECISIONS.md tuples implemented directly:
      1. platform-forced truncation -> that's an edit, back through 17
      2. platform rejects an ad -> log raw rejection + human, never tweak
         targeting to pass a filter
      3. engagement numbers conflict between sources -> report both, named
      4. CCP status unclear -> no publish, the gate is hard
      5. trending-topic tie-in -> human approval first, reputational surface
      6. asset references specifics not in listing.data -> pull it,
         marketing never outruns the MLS record
      7. fair-housing verdict pending -> nothing publishes, verdict is a
         gate not a race
      8. campaign targets a geography -> farm rules apply; demographic
         targeting parameters refused outright. Only the demographic-
         refusal half is implemented. NOT implemented: "farm rules apply"
         for geography-based targeting has no code at all, because there
         is no ratified farm-area boundary config anywhere in this
         identity to check a targeted geography against. Same class of
         gap as Agent 05's syndication tuples and Agent 10's scrape-
         source tuple - honestly flagged as structurally unbuilt, not
         guessed at.
      9. published asset found factually stale -> correct or retract,
         same day, log the delta. Fixed 2026-07-16: only "correct"
         (reopen verdict_locked for revision) existed - there was no path
         that actually retracted (pulled down) a stale asset at all.
         Whoever detects the staleness now signals which applies via
         retract_requested; defaults to correct (the non-destructive
         option) when absent, matching the tuple's "or" as a real choice
         rather than one silently-always path.
      10. budget change requested verbally -> signed budget stands until
          config.update
    """

    def __init__(self, hub, brokerage_identification: str | None = None):
        self.hub = guard(hub, "12")   # handoff rule (audit TU-2)
        self.mls_confirmed: dict[str, bool] = {}
        self.exempt_status: dict[str, dict] = {}  # ctx -> {exempt, disclosure_on_file}
        # P12 farm campaigns (2026-10-20): general geographic marketing that
        # names no listing. The Clear Cooperation gate is about publicly
        # marketing a property, so it does not hold these; until this date a
        # farm campaign waited forever for an MLS confirmation that no farm
        # ever gets. OWNER TO CONFIRM (docs/TUNING_MANUAL.md).
        self.farm_campaigns: set[str] = set()
        self.approved_assets: dict[str, dict] = {}  # ctx -> asset from 04
        self.pending_review: dict[str, dict] = {}  # ctx -> content awaiting 17
        self.published: dict[str, dict] = {}  # ctx -> {content, verdict_locked}
        self.approved_awaiting_ccp: dict[str, dict] = {}  # ctx -> approved content, gate not yet clear
        self.signed_budgets: dict[str, float] = {}  # ctx -> current signed budget
        self.engagement_sources: dict[str, dict[str, dict]] = {}  # ctx -> source -> metrics
        # The brokerage identification every ad must carry (Agent 17 tuple 7,
        # owner decision 2026-10-14): a signed setting, appended to every ad.
        # None until the broker sets it; no ad publishes without it.
        self.brokerage_identification: str | None = brokerage_identification
        self.held_for_brokerage_id: dict[str, dict] = {}  # ctx -> {campaign, source}
        register_spoke(hub, "12", self)

    def _ccp_gate_clear(self, ctx: str) -> bool:
        if self.mls_confirmed.get(ctx) or ctx in self.farm_campaigns:
            return True
        exempt = self.exempt_status.get(ctx, {})
        return bool(exempt.get("exempt") and exempt.get("disclosure_on_file"))

    def _with_brokerage_id(self, campaign):
        if isinstance(campaign, dict):
            return {**campaign, "brokerage_identification": self.brokerage_identification}
        return {"content": campaign, "brokerage_identification": self.brokerage_identification}

    def _publish_approved(self, ctx: str, campaign, source: str):
        if not self.brokerage_identification:
            # no exceptions for format constraints (Agent 17 tuple 7)
            first = ctx not in self.held_for_brokerage_id
            self.held_for_brokerage_id[ctx] = {"campaign": campaign, "source": source}
            self.hub.ingest_spoke_trace(
                "12", "internal",
                thought=f"approved ad for {ctx!r} held: no brokerage identification "
                        f"on file, and every ad must carry it",
                result="held: brokerage_identification")
            if first:
                self.hub.send(_env("12", "queue", "clarification.request", ctx,
                                   {"reason": "an approved ad is held: no brokerage "
                                              "identification is on file and every ad "
                                              "must carry it. Set it with a signed "
                                              "brokerage_identification setting to Agent 12 "
                                              "and Agent 17; the held ad then publishes"}))
            return
        campaign = self._with_brokerage_id(campaign)
        publish = _env("12", "external", "campaign.publish", ctx,
                       {"content": campaign, "source": source})
        self.published[ctx] = {"content": campaign, "verdict_locked": True,
                               "envelope_id": publish.envelope_id}
        res = self.hub.send(publish)
        # 2026-10-14 (tuple runs): the hub holds a campaign.publish for the
        # broker's signed release (counterparty audience), yet the record said
        # "campaign_published" before anything left. The log now names what
        # happened, the same fix the retraction got on 2026-10-12.
        held = isinstance(res, dict) and res.get("status") == "held"
        self.hub.send(_env("12", "14", "interaction.log", ctx,
                           {"kind": "campaign_publish_held" if held else "campaign_published",
                            "source": source}))

    def _check_awaiting_ccp(self, ctx: str):
        """Called whenever the CCP gate might have just cleared (MLS
        confirmation or exempt status arriving) - publishes anything that
        was approved earlier but held on the gate, instead of it being
        silently lost. Real bug found on re-review: previously, an
        approved campaign was popped from tracking and never stored
        anywhere else if the gate wasn't clear yet - it would never
        publish even after the gate cleared."""
        pending = self.approved_awaiting_ccp.pop(ctx, None)
        if pending is not None and self._ccp_gate_clear(ctx):
            self._publish_approved(ctx, pending["campaign"], pending["source"])
            self.hub.send(_env("12", "18", "agent.status", ctx,
                               {"waiting_on": "ccp_gate", "resolved": True}))
        elif pending is not None:
            self.approved_awaiting_ccp[ctx] = pending  # gate still not clear

    def handle(self, env: Envelope):
        ctx = env.client_context_id

        if env.intent == "lead.reply":
            # Client reply routed here by Agent 11 (owner decision 2026-10-11:
            # 12 gets a lead.reply handler instead of leaving the route
            # unhandled). No ratified tuple yet says how 12 acts on client
            # feedback about marketing, so per the root rule it changes nothing
            # itself: it logs the reply to 14 and holds it for the human with
            # the client's words and 12's current state for that client.
            message = env.payload.get("message")
            self.hub.ingest_spoke_trace(
                "12", env.envelope_id,
                thought=f"client reply about marketing for ctx={ctx!r}; no tuple covers "
                        f"acting on it - logging and holding for the human, nothing changed",
                result="held: client_reply_needs_human")
            self.hub.send(_env("12", "14", "interaction.log", ctx,
                               {"kind": "client_reply_received", "verbatim": message}))
            self.hub.send(_env("12", "queue", "clarification.request", ctx,
                               {"reason": "client reply about marketing - no tuple covers acting "
                                          "on it; human decides",
                                "verbatim": message, "agent": "12",
                                "agent_state": {"published": ctx in self.published, "pending_review": ctx in self.pending_review}}))
            return
        payload = env.payload

        if env.intent == "status.update":
            if payload.get("status") == "active":
                self.mls_confirmed[ctx] = True
                self._check_awaiting_ccp(ctx)
                return
            if "status" not in payload:
                # A field change, not a status change (P02, found by the
                # playbook runs 2026-10-20): Agent 05 sends {"price": ...}
                # after a signed price change, and this handler read the
                # missing status as "not active" and halted every live ad.
                # A price change keeps the listing marketed. Walkthrough
                # 2026-10-21: the broker is asked only when the ad itself
                # shows the old price, and told whether that ad is live or
                # still held for release.
                fields = sorted(k for k in payload if not k.startswith("prior_"))
                self.hub.send(_env("12", "14", "interaction.log", ctx,
                                   {"kind": "listing_change_received", "fields": fields}))
                prior = payload.get("prior_price")
                pub = self.published.get(ctx)
                if pub is not None and prior is not None and _mentions_amount(pub.get("content"), prior):
                    state = (self.hub.outbound_state(pub["envelope_id"])
                             if pub.get("envelope_id") else "sent")
                    where = "held for your release" if state == "held" else "live"
                    self.hub.send(_env("12", "queue", "clarification.request", ctx,
                                       {"reason": f"the ad for this listing ({where}) shows the old "
                                                  f"price {prior}; the price is now "
                                                  f"{payload.get('price')}. Nothing was changed: "
                                                  f"decline or replace the ad",
                                        "agent": "12"}))
                return
            # P05 step 1b / P03 step 1b, ratified but ZERO code until
            # 2026-07-18 (found by the first end-to-end P05 run): this
            # handler only reacted to "active" - a withdrawn/expired/
            # pending status was silently ignored, so marketing for a
            # dead or under-contract listing just kept running. Now: any
            # non-active status halts every published campaign for the
            # context, per platform, with the halt LEAVING the swarm
            # (campaign.publish action=halt) and going in the books.
            # A halt for a listing with nothing published is a no-op,
            # logged as such - never an error, never invented work.
            new_status = payload.get("status")
            self.mls_confirmed[ctx] = False
            if ctx in self.published:
                halted = self.published.pop(ctx)
                self.approved_awaiting_ccp.pop(ctx, None)
                self.hub.ingest_spoke_trace(
                    "12", env.envelope_id,
                    thought=f"status.update {new_status!r} consumed - "
                            f"halting ALL marketing for this context; a "
                            f"live ad for a {new_status} listing is a "
                            f"compliance exposure and a seller wound",
                    result="marketing_halted")
                self.hub.send(_env("12", "external", "campaign.publish", ctx,
                                   {"action": "halt",
                                    "reason": f"listing_status_{new_status}"}))
                self.hub.send(_env("12", "14", "interaction.log", ctx,
                                   {"kind": "marketing_halted",
                                    "status": new_status}))
            else:
                self.approved_awaiting_ccp.pop(ctx, None)
                self.hub.ingest_spoke_trace(
                    "12", env.envelope_id,
                    thought=f"status.update {new_status!r} consumed - "
                            f"nothing published for this context, nothing "
                            f"to halt; held approvals cleared",
                    result="no_active_marketing")
            return

        if env.intent == "asset.release":
            draft = payload.get("draft", {})
            # tuple 6: asset references specifics not in listing.data ->
            # pull it, marketing never outruns the MLS record
            if payload.get("references_unconfirmed_data"):
                self.hub.send(_env("12", "queue", "clarification.request", ctx,
                                   {"reason": "asset references specifics "
                                             "not in listing.data - pulled, "
                                             "marketing never outruns the "
                                             "MLS record"}))
                return
            self.approved_assets[ctx] = draft
            if not self._ccp_gate_clear(ctx):
                # tuple 4: CCP status unclear -> no publish, hard gate.
                # Same bug fixed here as the content.verdict path: store
                # for automatic publish once the gate clears, don't lose it.
                self.approved_awaiting_ccp[ctx] = {"campaign": draft,
                                                   "source": "04_asset"}
                self.hub.ingest_spoke_trace(
                    "12", env.envelope_id,
                    thought="asset received from 04, but CCP gate not "
                            "clear (no MLS confirmation, no documented "
                            "exempt status) - holding, will publish "
                            "automatically once the gate clears",
                    result="held: ccp_gate")
                return
            self._publish_approved(ctx, draft, "04_asset")
            return

        if env.intent == "config.update":
            if "brokerage_identification" in payload:
                text = payload["brokerage_identification"]
                if not isinstance(text, str) or not text.strip():
                    self.hub.send(_env("12", "queue", "clarification.request", ctx,
                                       {"reason": "brokerage_identification rejected; nothing "
                                                  "changed - it must be the text every ad carries"}))
                    return
                self.brokerage_identification = text.strip()
                self.hub.ingest_spoke_trace("12", env.envelope_id,
                                            thought="broker-signed brokerage identification set",
                                            result="brokerage identification set")
                for held_ctx, held in list(self.held_for_brokerage_id.items()):
                    self.held_for_brokerage_id.pop(held_ctx)
                    self._publish_approved(held_ctx, held["campaign"], held["source"])
                return
            if "exempt_status" in payload:
                self.exempt_status[ctx] = payload["exempt_status"]
                self._check_awaiting_ccp(ctx)
                return
            if "new_campaign" in payload:
                campaign = payload["new_campaign"]
                # tuple 8: geography targeting -> farm rules apply;
                # demographic targeting refused outright
                if campaign.get("targeting_demographic"):
                    self.hub.escalate("escalation.legal_line",
                                      {"client_context_id": ctx,
                                       "trigger": "demographic targeting "
                                                 "parameter requested - "
                                                 "refused outright, not a "
                                                 "workaround",
                                       "agent": "12"})
                    return
                # tuple 5: trending-topic tie-in -> human approval first
                if campaign.get("trending_topic_tie_in"):
                    self.hub.send(_env("12", "queue", "clarification.request",
                                       ctx, {"reason": "trending-topic tie-in "
                                                       "- human approval "
                                                       "required first, "
                                                       "reputational surface"}))
                    return
                aud = campaign.get("audience") if isinstance(campaign, dict) else None
                if isinstance(aud, dict) and aud.get("geography") and not campaign.get("listing_id"):
                    if aud.get("targeting", "general") != "general":
                        self.hub.escalate("escalation.legal_line", {
                            "client_context_id": ctx, "agent": "12",
                            "trigger": f"farm campaign with targeting {aud.get('targeting')!r} - "
                                       f"farm marketing is general only (P12, Article 16)"})
                        return
                    self.farm_campaigns.add(ctx)
                # every ad carries the brokerage identification when one is on
                # file; Agent 17 checks it is there (tuple 7, 2026-10-14)
                if self.brokerage_identification:
                    campaign = self._with_brokerage_id(campaign)
                self.pending_review[ctx] = campaign
                # wait opened BEFORE the review (17 answers inside hub.send;
                # fixed 2026-10-11 - a resolved review stayed open forever)
                self.hub.send(_env("12", "18", "agent.status", ctx,
                                   {"waiting_on": "compliance_review",
                                    "since": payload.get("today")}))
                self.hub.send(_env("12", "17", "content.review", ctx,
                                   {"campaign": campaign, "content_type": "advertising",
                                    "state": campaign.get("state") if isinstance(campaign, dict) else None}))
                return
            if "budget_change_verbal" in payload:
                # tuple 10: verbal budget change -> signed budget stands
                # until config.update actually carries the new figure
                self.hub.ingest_spoke_trace(
                    "12", env.envelope_id,
                    thought="verbal budget change reported - current "
                            "signed budget stands until a real "
                            "config.update carries the new figure",
                    result="held: signed_budget_stands")
                return
            if "signed_budget" in payload:
                self.signed_budgets[ctx] = payload["signed_budget"]
                return
            return

        if env.intent == "content.verdict":
            verdict = payload.get("verdict")
            campaign = self.pending_review.pop(ctx, None)
            self.hub.send(_env("12", "18", "agent.status", ctx,
                               {"waiting_on": "compliance_review",
                                "resolved": True}))
            if verdict == "approved":
                if not self._ccp_gate_clear(ctx):
                    # tuple 4/7: gate is hard, verdict is a gate not a race.
                    # Real bug fixed on re-review: this used to just hold
                    # and lose the campaign - nothing published it even
                    # after the gate later cleared. Now stored for
                    # _check_awaiting_ccp to pick up.
                    self.approved_awaiting_ccp[ctx] = {"campaign": campaign,
                                                       "source": "self_written"}
                    self.hub.send(_env("12", "18", "agent.status", ctx,
                                       {"waiting_on": "ccp_gate",
                                        "since": payload.get("today")}))
                    self.hub.ingest_spoke_trace(
                        "12", env.envelope_id,
                        thought="compliance approved, but CCP gate not "
                                "clear - nothing publishes until MLS "
                                "confirms or exempt status is documented; "
                                "held for automatic publish once it does",
                        result="held: ccp_gate")
                    return
                self._publish_approved(ctx, campaign, "self_written")
                return
            if verdict == "flagged":
                findings = payload.get("findings", [])
                self.hub.ingest_spoke_trace(
                    "12", env.envelope_id,
                    thought=f"compliance flagged: {findings} - nothing "
                            f"publishes, fair-housing verdict pending",
                    result="held: flagged")
                # the broker started this campaign, so the broker is told
                # (2026-10-12 doc review: the hold was silent)
                self.hub.send(_env("12", "queue", "clarification.request", ctx,
                                   {"reason": "Compliance (17) flagged the campaign copy - "
                                              "nothing publishes; send corrected copy as a "
                                              "new signed new_campaign",
                                    "findings": findings}))
                return
            self.hub.send(_env("12", "queue", "clarification.request", ctx,
                               {"reason": f"unrecognized verdict "
                                         f"{verdict!r}"}))
            return

        if env.intent == "platform.metrics" and payload.get("event_kind") == "truncated":
            # tuple 1: platform-forced truncation IS an edit - never
            # silently accepted, goes back through 17 like any other
            # change to an already-approved asset.
            truncated_content = payload.get("truncated_content")
            self.hub.send(_env("12", "17", "content.review", ctx,
                               {"campaign": truncated_content,
                                "content_type": "advertising",
                                "reason": "platform-forced truncation - "
                                         "truncation is an edit"}))
            self.hub.ingest_spoke_trace(
                "12", env.envelope_id,
                thought="platform truncated approved content before "
                        "publishing - that's an edit to a verdict-locked "
                        "asset, back through 17, never accepted as-is",
                result="resubmitted for review: truncation")
            return

        if env.intent == "platform.metrics" and payload.get("event_kind") == "rejection":
            # tuple 2: platform rejects an ad -> log raw rejection + human,
            # never tweak targeting to pass a filter
            self.hub.send(_env("12", "14", "interaction.log", ctx,
                               {"kind": "platform_rejection",
                                "raw_rejection": payload.get("raw_rejection")}))
            self.hub.send(_env("12", "queue", "clarification.request", ctx,
                               {"reason": f"platform rejected ad: "
                                         f"{payload.get('raw_rejection')!r} - "
                                         f"never tweaking targeting to pass "
                                         f"a filter"}))
            return

        if env.intent == "platform.metrics" and payload.get("event_kind") == "stale_detected":
            # tuple 9: correct OR retract, same day, log the delta. Fixed
            # 2026-07-16: only "correct" (reopen verdict_locked for
            # revision) existed - there was no path that actually pulled a
            # stale asset down at all. Whoever detects the staleness
            # signals which one applies via retract_requested; defaults to
            # correct (the safer, non-destructive option) when absent.
            # 2026-10-12 doc review: this used to log "stale_asset_corrected"
            # before anything was corrected and say "pulled from the platform"
            # while the retraction sat in the hub's hold. The log now names
            # what happened, and the broker is told either way.
            published = self.published.get(ctx)
            if payload.get("retract_requested"):
                if published:
                    published["retracted"] = True
                res = self.hub.send(_env("12", "external", "campaign.publish", ctx,
                                         {"action": "retract"}))
                state = (res or {}).get("status") if isinstance(res, dict) else None
                kind = "stale_asset_retraction_held" if state == "held" else "stale_asset_retracted"
                self.hub.send(_env("12", "14", "interaction.log", ctx,
                                   {"kind": kind, "delta": payload.get("delta")}))
                self.hub.send(_env("12", "queue", "clarification.request", ctx,
                                   {"reason": "published asset is stale - a retraction is "
                                              + ("held for your signed release" if state == "held"
                                                 else f"sent ({state})"),
                                    "delta": payload.get("delta")}))
                self.hub.ingest_spoke_trace(
                    "12", env.envelope_id,
                    thought=f"stale asset: retraction sent to the platform route, hub "
                            f"answered {state!r}; delta logged",
                    result=kind)
            else:
                if published:
                    published["verdict_locked"] = False
                self.hub.send(_env("12", "14", "interaction.log", ctx,
                                   {"kind": "stale_asset_reopened_for_correction",
                                    "delta": payload.get("delta")}))
                self.hub.send(_env("12", "queue", "clarification.request", ctx,
                                   {"reason": "published asset is stale - reopened for "
                                              "correction; corrected copy goes back through "
                                              "17 and your release",
                                    "delta": payload.get("delta")}))
                self.hub.ingest_spoke_trace(
                    "12", env.envelope_id,
                    thought="stale asset reopened for correction - "
                            "verdict_locked cleared, delta logged",
                    result="reopened for correction")
            return

        if env.intent == "platform.metrics":
            source = payload.get("platform")
            value = payload.get("engagement_value")
            entry = self.engagement_sources.setdefault(ctx, {})
            entry[source] = {"value": value, "source": source}

            # tuple 3: conflicting engagement numbers -> report both, named
            if len(entry) > 1 and len({v["value"] for v in entry.values()}) > 1:
                self.hub.send(_env("12", "14", "interaction.log", ctx,
                                   {"kind": "engagement_conflict",
                                    "sources": dict(entry)}))
                self.hub.send(_env("12", "queue", "clarification.request", ctx,
                                   {"reason": f"engagement numbers conflict "
                                             f"between sources: "
                                             f"{dict(entry)} - reporting "
                                             f"both, named"}))
                return

            self.hub.send(_env("12", "14", "interaction.log", ctx,
                               {"kind": "engagement_metric", "platform": source,
                                "value": value}))

            # spike feeds back into nurture, per 12's own legal edge to 03
            spike_threshold = payload.get("spike_threshold", 50)
            if value is not None and value >= spike_threshold:
                signal = {"engagement_score": value, "spike_threshold": spike_threshold}
                if payload.get("today"):
                    signal["today"] = payload["today"]   # lets 03 count the timeline down
                self.hub.send(_env("12", "03", "behavioral.signal", ctx, signal))
            return
