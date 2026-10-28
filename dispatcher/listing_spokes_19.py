"""Agent 19 - Prospecting, built against the full spec.

Discovers and reports. Never initiates contact, never queues outbound
messages. Every opportunity record carries representation status and
DNC-registry status as decision-support fields - the human decides
outreach, the record makes the legal posture visible first.
"""
from __future__ import annotations

from .core import Envelope
from .handoff_guard import guard, register as register_spoke

SOURCE_VERIFIED = "source_verified"
STATED_BY_PARTY = "stated_by_party"
UNKNOWN = "unknown"


def _env(frm, to, intent, ctx, payload, confidence=UNKNOWN, in_reply_to=None):
    return Envelope(from_agent=frm, to_agent=to, intent=intent,
                    client_context_id=ctx, payload=payload,
                    confidence=confidence, in_reply_to=in_reply_to,
                    provenance={"source": f"spoke-{frm}", "captured_at": "runtime",
                                "verbatim_available": True})


class Spoke19Prospecting:
    """DECISIONS.md tuples implemented directly:
      1. representation status unclear -> mark unknown with source,
         human decides posture
      2. discovery source's rule-compliance unclear -> exclude the
         source + flag
      3. opportunity matches an existing client context -> flag the
         relationship, no outreach implication
      4. expired listing relists with another broker -> update the
         record, opportunity closed
      5. bulk-outreach instruction arrives unsigned -> require signed
         config, chat is not authority
      6. expired listing surfaced -> human + compliance gate before ANY
         contact
      7. FSBO surfaced -> same gate
      8. prospect appears on DNC -> suppress, log; the miss goes in the
         books as suppressed-by-rule
      9. ranking rationale weaker than threshold -> present unranked
         with data, a confident-looking rank without basis is fabrication
      10. neighbor data requested for farm outreach -> aggregate level
          only, individual household inferences refused
    """

    def __init__(self, hub):
        self.hub = guard(hub, "19")   # handoff rule (audit TU-2)
        self.zip_codes: set[str] = set()  # human-configured monitoring targets
        self.approved_sources: set[str] = set()  # human-configured, MLS-rule-compliant
        self.dnc_list: set[str] = set()
        self.known_client_contexts: set[str] = set()  # for tuple 3 matching
        self.opportunities: dict[str, dict] = {}  # listing_id -> record
        # owner decision 8 (2026-10-21): prospects you marked handled (signed
        # config.update {"prospects_handled": [listing ids]}) leave the
        # morning briefing's "prospects waiting" section
        self.prospects_handled: set[str] = set()
        register_spoke(hub, "19", self)

    def request_market_context(self, listing_id: str):
        """Job component: market context for opportunity records via 10.
        Called when an opportunity needs enrichment (schedule/on-demand
        driven, matching the established pattern), not envelope-triggered."""
        record = self.opportunities.get(listing_id)
        if record is None:
            return
        # D-A16 (owner decision 2026-10-28, finding AW): Agent 10 builds a
        # package only from the comps it is handed and has no data source of
        # its own; this request handed it none, so every package came back
        # empty ("thin", 0 comps) and looked like a real result. Nothing is
        # requested now and no wait is opened; the record says plainly that
        # no comp source is connected.
        record["market_context"] = "none - no comp source connected"

    def handle(self, env: Envelope):
        ctx = env.client_context_id
        payload = env.payload

        if env.intent == "config.update":
            if "zip_codes" in payload:
                self.zip_codes.update(payload["zip_codes"])
                return
            if "approved_sources" in payload:
                self.approved_sources.update(payload["approved_sources"])
                return
            if "dnc_entries" in payload:
                self.dnc_list.update(payload["dnc_entries"])
                return
            if "known_client_contexts" in payload:
                self.known_client_contexts.update(payload["known_client_contexts"])
                return
            if "prospects_handled" in payload:
                ids = payload["prospects_handled"]
                if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
                    self.hub.send(_env("19", "queue", "clarification.request", ctx,
                                       {"reason": "prospects_handled must be a list of "
                                                  "listing ids; nothing changed"}))
                    return
                self.prospects_handled.update(ids)
                return
            if "bulk_outreach_instruction" in payload:
                # tuple 5: this handler only reachable via a signed
                # config.update (the hub's own signature gate on
                # authority intents already enforces this structurally -
                # an unsigned attempt never reaches here at all)
                self.hub.ingest_spoke_trace(
                    "19", env.envelope_id,
                    thought="signed bulk-outreach instruction received - "
                            "still discovery-only, this agent never "
                            "initiates contact regardless of instruction",
                    result="noted, no outreach action taken")
                return
            if "farm_data_request" in payload:
                # tuple 10: neighbor data for farm outreach -> aggregate
                # level only, individual household inferences refused
                request = payload["farm_data_request"]
                if request.get("individual_level"):
                    self.hub.escalate("escalation.legal_line",
                                      {"client_context_id": ctx,
                                       "trigger": "farm outreach request for "
                                                 "individual household-level "
                                                 "data - refused, aggregate "
                                                 "only",
                                       "agent": "19"})
                    return
                # D-A16 (2026-10-28): no neighborhood data source is
                # connected, so there is nothing to aggregate; the owner is
                # told once, instead of an empty package and an open wait
                self.hub.send(_env("19", "queue", "clarification.request", ctx,
                                   {"reason": "farm data request: no neighborhood data source "
                                              "connected; nothing to aggregate"}))
                return
            return

        if env.intent == "discovery.feed":
            listing_id = payload.get("listing_id")
            zip_code = payload.get("zip_code")
            source = payload.get("source")
            status = payload.get("status")  # "new" / "expired" / "fsbo"

            if zip_code not in self.zip_codes:
                # outside monitored zips, not this agent's concern - recorded,
                # never silent (silent-handler sweep 2026-10-11)
                self.hub.ingest_spoke_trace(
                    "19", env.envelope_id,
                    thought=f"discovery {listing_id!r} in zip {zip_code!r} is outside "
                            f"the monitored zips {sorted(self.zip_codes)} - not recorded",
                    result="ignored: outside monitored zips")
                return

            # tuple 2: source's rule-compliance unclear -> exclude + flag
            if status in ("expired", "fsbo") and source not in self.approved_sources:
                self.hub.send(_env("19", "queue", "clarification.request", ctx,
                                   {"reason": f"discovery source {source!r} "
                                             f"is not on the approved, "
                                             f"MLS-rule-compliant list - "
                                             f"excluded, flagged rather "
                                             f"than used"}))
                return

            # tuple 4: expired listing relists with another broker ->
            # update the record, opportunity closed
            existing = self.opportunities.get(listing_id)
            if existing and existing.get("status_at_retrieval") == "expired" and \
                    payload.get("relisted_with_broker"):
                existing["status_at_retrieval"] = "closed_relisted"
                self.hub.send(_env("19", "14", "interaction.log", ctx,
                                   {"kind": "opportunity_closed",
                                    "listing_id": listing_id,
                                    "reason": "relisted with another broker"}))
                return

            # representation status - tuple 1: unclear -> mark unknown w/ source
            rep_status = payload.get("representation_status")
            if rep_status not in ("listed", "expired", "fsbo", "unknown"):
                rep_status = "unknown"

            # tuple 8: DNC suppression
            # Normalized since 2026-10-14 (tuple runs), the same fix Agent 01
            # got the same day: exact text missed "330-555-0190" against a
            # list entry "(330) 555-0190".
            from .listing_spokes import _dnc_identifiers
            contact = payload.get("owner_contact")
            on_dnc = bool(contact) and (contact in self.dnc_list or bool(
                _dnc_identifiers([contact]) & _dnc_identifiers(self.dnc_list)))

            record = {"listing_id": listing_id, "zip_code": zip_code,
                     "source": source, "retrieval_timestamp": payload.get("today"),
                     "status_at_retrieval": status,
                     "representation_status": rep_status,
                     "dnc_status": "on_dnc" if on_dnc else "not_on_dnc"}

            # Real bug found on re-review: this record only ever carried
            # meta/compliance fields - never the actual property data
            # (price, beds, area, etc.) that 13's matching logic needs to
            # do real filtering. Verified directly: a match "succeeded"
            # with zero actual price comparison, because price was never
            # present to compare against a buyer's budget at all. Forward
            # whatever property facts the discovery feed actually
            # supplied, verbatim - never invented, only passed through.
            _PROPERTY_FIELDS = ("price", "beds", "baths", "area", "sqft",
                               "equipment", "garage", "colleague_listing",
                               "data_anomaly")
            for f in _PROPERTY_FIELDS:
                if f in payload:
                    record[f] = payload[f]

            # tuple 9: ranking rationale weaker than threshold -> present
            # unranked with data; a confident-looking rank without basis
            # is fabrication. Only include a rank at all if a real basis
            # strength clears the threshold.
            rank_score = payload.get("rank_score")
            rank_basis_strength = payload.get("rank_basis_strength", 0)
            rank_threshold = payload.get("rank_threshold", 0.5)
            if rank_score is not None:
                if rank_basis_strength >= rank_threshold:
                    record["rank_score"] = rank_score
                    record["ranked"] = True
                else:
                    record["ranked"] = False
                    record["rank_omitted_reason"] = (
                        "ranking basis strength below threshold - "
                        "presented unranked, a confident-looking rank "
                        "without basis is fabrication")

            self.opportunities[listing_id] = record

            if on_dnc:
                self.hub.send(_env("19", "14", "interaction.log", ctx,
                                   {"kind": "suppressed_by_rule",
                                    "listing_id": listing_id,
                                    "reason": "DNC registry match"}))

            # tuple 6/7: expired/FSBO -> human + compliance gate before
            # ANY contact (this agent never contacts regardless - the
            # gate is enforced structurally by this agent's own zero-
            # outreach design, but still explicitly flagged for the human)
            if status in ("expired", "fsbo"):
                self.hub.escalate("escalation.legal_line",
                                  {"client_context_id": ctx,
                                   "trigger": f"{status} listing surfaced - "
                                             f"human + compliance gate "
                                             f"required before any contact",
                                   "agent": "19"})

            # tuple 3: matches an existing client context -> flag the
            # relationship, no outreach implication
            matching_ctx = payload.get("matches_client_context")
            if matching_ctx and matching_ctx in self.known_client_contexts:
                self.hub.send(_env("19", "queue", "clarification.request", ctx,
                                   {"reason": f"opportunity matches existing "
                                             f"client context "
                                             f"{matching_ctx!r} - flagged, "
                                             f"no outreach implication"}))

            # Market context for every recorded opportunity (owner decision
            # 7c, 2026-10-11), set BEFORE the prospect goes to you so it
            # reaches you once (P24 walkthrough, 2026-10-21). Since D-A16
            # (2026-10-28) nothing is requested from Agent 10: no comp source
            # is connected, and the record says so ("none - no comp source
            # connected") instead of carrying an empty package.
            # Never characterized, never sent to the property owner.
            record["surfaced"] = False
            self.request_market_context(listing_id)
            record["surfaced"] = True
            out = {k: v for k, v in record.items() if k != "surfaced"}
            if "market_context" not in out:
                out["market_context"] = None
            self.hub.send(_env("19", "human", "prospect.opportunity", ctx,
                               out, confidence=SOURCE_VERIFIED))
            if payload.get("buyer_profile_match_ctx"):
                self.hub.send(_env("19", "13", "prospect.opportunity",
                                   payload["buyer_profile_match_ctx"], out,
                                   confidence=SOURCE_VERIFIED))
            self.hub.send(_env("19", "14", "interaction.log", ctx,
                               {"kind": "opportunity_discovered",
                                "listing_id": listing_id}))
            return

        if env.intent == "briefing.request":
            # owner decision 8 (2026-10-21): prospects waiting, for 18
            waiting = [{k: r.get(k) for k in ("listing_id", "zip_code", "source",
                                              "status_at_retrieval", "dnc_status",
                                              "retrieval_timestamp")}
                       for lid, r in self.opportunities.items()
                       if lid not in self.prospects_handled]
            self.hub.send(_env("19", "18", "report.package", ctx,
                               {"section": "prospects_waiting",
                                "data": {"count": len(waiting), "prospects": waiting,
                                         "basis": "recorded prospects you have not "
                                                  "marked handled"}},
                               confidence=SOURCE_VERIFIED))
            return

        # data.package from Agent 10: removed 2026-10-28 with the route
        # (owner decision D-A16): 19 no longer asks 10 for anything
