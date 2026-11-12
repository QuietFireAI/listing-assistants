#!/usr/bin/env python3
"""Watch the listing swarm take a new listing live - a real run, not a
slideshow. One property, signed authorization to a live, marketed,
fair-housing-cleared listing, against the real hub, real Ed25519
signatures, and the real hash-chained audit log.

  Act 1  Signed listing authorization -> setup: photography ordered from
         the vetted roster, seller onboarded, agreement logged. The PRICE
         is the human's - the swarm never touches it.
  Act 2  Photos delivered -> the production gate opens: description agent
         drafts from property facts, compliance reviews EVERY asset before
         anything markets.
  Act 3  Fair-housing gate LIVE: a steering phrase in the data is FLAGGED
         and never releases - marketing cannot proceed on flagged copy.
  Act 4  Clean assets approved -> go-live: MLS active (live-verified, not
         a push log), Clear Cooperation satisfied, campaign publishes,
         buyer feeds updated, seller told "you're live".
  Act 5  A pricing question from any party -> escalation.legal_line. The
         swarm does not answer money/price questions - ever.
  Act 6  Chain verification - every event, hash-linked, tamper-evident.

Run it:  python3 tools/run_demo.py

Every stage below is checked. The run ends with a count and exits with
code 1 if any stage did not happen (2026-11-11: before, the script printed
False for the go-live and still exited 0, because it never gave the
broker's release for the photographer booking that Act 2 waits on).

Three lines are sent by the script in an agent's name, to stand in for work
that happens outside this one listing: the listing agreement logged by
Agent 07, the seller onboarding request from Agent 06, and the listing data
that carries the steering phrase in Act 3. Each is marked "(stand-in)".
"""
import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dispatcher.core import Envelope, Routes, AuditLog
from dispatcher.hub import Hub
from dispatcher.signatures import Ed25519Signer, Ed25519Verifier
from dispatcher.listing_spokes import Spoke01LeadCapture, Spoke14CRMPipeline
from dispatcher.listing_spokes_02 import Spoke02LeadQualification
from dispatcher.listing_spokes_04 import Spoke04ListingDescription
from dispatcher.listing_spokes_05 import Spoke05MLSListingManagement
from dispatcher.listing_spokes_06 import Spoke06ShowingScheduler
from dispatcher.listing_spokes_07 import Spoke07TransactionCoordinator
from dispatcher.listing_spokes_08 import Spoke08DocumentCollection
from dispatcher.listing_spokes_09 import Spoke09VendorCoordination
from dispatcher.listing_spokes_10 import Spoke10MarketData
from dispatcher.listing_spokes_11 import Spoke11ClientCommunication
from dispatcher.listing_spokes_12 import Spoke12MarketingCampaign
from dispatcher.listing_spokes_13 import Spoke13BuyerSearchMatch
from dispatcher.listing_spokes_15 import Spoke15FinancialTracking
from dispatcher.listing_spokes_16 import Spoke16AfterCloseReferral
from dispatcher.listing_spokes_17 import Spoke17ComplianceFairHousing
from dispatcher.listing_spokes_18 import Spoke18CalendarTask
from dispatcher.listing_spokes_19 import Spoke19Prospecting

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BROKERAGE_ID = "Synth Realty, Testville OH"
RULESET = {"prohibited_phrases": [
    {"phrase": "perfect for families", "rule_id": "FH-STEER-1"}],
    "state_rules": {}}


def say(s=""): print(s)
def act(n, t): say(); say("=" * 68); say(f"  ACT {n}: {t}"); say("=" * 68)


def build():
    signer = Ed25519Signer()
    verifier = Ed25519Verifier(signer.public_key_bytes())
    path = os.path.join(tempfile.mkdtemp(), "audit.jsonl")
    hub = Hub(Routes(os.path.join(ROOT, "identity", "routes.json")),
              AuditLog(path), signature_verifier=verifier.verifier())
    ext = []
    hub.register("external", lambda e: ext.append(e))
    hub.register("human", lambda e: None)
    s = {
        "01": Spoke01LeadCapture(hub, brokerage_scope={"L1", "MLS-1"}),
        "02": Spoke02LeadQualification(hub),
        "04": Spoke04ListingDescription(hub),
        "05": Spoke05MLSListingManagement(hub),
        "06": Spoke06ShowingScheduler(hub),
        "07": Spoke07TransactionCoordinator(hub),
        "08": Spoke08DocumentCollection(hub, expected_senders={}),
        "09": Spoke09VendorCoordination(hub, roster={
            "v-photo": {"kind": "photography",
                        "license_expiry": "2027-01-01",
                        "insurance_expiry": "2027-01-01",
                        "regulated": False}}),
        "10": Spoke10MarketData(hub),
        "11": Spoke11ClientCommunication(hub),
        # every ad carries the brokerage identification (owner decision
        # 2026-10-14); without it Agent 12 asks a human instead of publishing
        "12": Spoke12MarketingCampaign(hub, brokerage_identification=BROKERAGE_ID),
        "13": Spoke13BuyerSearchMatch(hub),
        "14": Spoke14CRMPipeline(hub),
        "15": Spoke15FinancialTracking(hub),
        "16": Spoke16AfterCloseReferral(hub),
        "17": Spoke17ComplianceFairHousing(hub, brokerage_identification=BROKERAGE_ID),
        "18": Spoke18CalendarTask(hub),
        "19": Spoke19Prospecting(hub),
    }
    hub.on_turn_start()
    return hub, signer, s, ext, path


def signed(signer, to, intent, ctx, payload, frm="human"):
    e = Envelope(from_agent=frm, to_agent=to, intent=intent,
                 client_context_id=ctx, payload=payload,
                 provenance={"source": frm, "captured_at": "runtime",
                             "verbatim_available": True})
    signer.sign(e)
    return e


def spoke_env(frm, to, intent, ctx, payload):
    return Envelope(from_agent=frm, to_agent=to, intent=intent,
                    client_context_id=ctx, payload=payload,
                    provenance={"source": f"spoke-{frm}",
                                "captured_at": "runtime",
                                "verbatim_available": True})


def main():
    hub, signer, s, ext, path = build()
    ctx = "demo-listing-1"
    failed = []

    def check(label, ok, shown=None):
        """Print one stage and remember it if it did not happen."""
        mark = "ok    " if ok else "FAILED"
        say(f"  [{mark}] {label}" + (f": {shown}" if shown is not None else ""))
        if not ok:
            failed.append(label)

    def seen(intent):
        return [e for e in hub.audit.read()
                if e["kind"] == "envelope.persisted" and e["intent"] == intent]

    def ext_has(intent):
        return any(e.intent == intent for e in ext)

    def held_now(intent):
        return [hid for hid, h in hub._absolute_holds.items() if h.intent == intent]

    def release(intent, to_agent):
        """The broker's key: a signed disclosure.authority for each held
        message of this kind. Returns how many were released."""
        n = 0
        for hid in held_now(intent):
            h = hub._absolute_holds[hid]
            auth = Envelope(from_agent="human", to_agent=to_agent,
                            intent="disclosure.authority",
                            client_context_id=h.client_context_id,
                            payload={"held_envelope_id": hid},
                            provenance={"source": "human", "captured_at": "runtime",
                                        "verbatim_available": True})
            signer.sign(auth)
            hub.release_disclosure(auth)
            n += 1
        return n

    hub.send(signed(signer, "17", "config.update", ctx,
                    {"ruleset": RULESET, "version": "r1"}))

    act(1, "SIGNED AUTHORIZATION -> SETUP (the price is the human's)")
    hub.send(signed(signer, "05", "listing.change.authorized", ctx,
                    {"new_listing": {"beds": 3, "sqft": 2000, "price": 500_000,
                                     "features": ["garage"],
                                     "photo_detected_features": ["garage"]},
                     "authorize_go_live": True, "today": "2026-07-01"}))
    hub.send(spoke_env("07", "14", "interaction.log", ctx,     # (stand-in)
                       {"kind": "listing_agreement",
                        "consent": {"call": "yes", "text": "yes",
                                    "email": "yes"}}))
    v = s["09"].scheduled.get(ctx, {}).get("photography", {}).get("vendor_id")
    check("photography ordered from the vetted roster", v == "v-photo", v)
    vheld = any(e["kind"] == "absolute_signal.hold"
                and e["intent"] == "vendor.schedule" for e in hub.audit.read())
    check("vendor booking (a COUNTERPARTY) held, not sent on its own",
          vheld and not ext_has("vendor.schedule"))
    say("  the roster PICK happened inside the swarm; reaching OUT to the "
        "vendor waits for a human's release. Scheduling != disclosing.")
    n_vendor = release("vendor.schedule", "09")
    check("broker signs the release for the photographer booking",
          n_vendor >= 1, f"{n_vendor} released")
    check("booking sent to the photographer after the release",
          ext_has("vendor.schedule"))
    hub.send(spoke_env("06", "11", "client.message.request", ctx,  # (stand-in)
                       {"template": "seller_onboarding", "hour": 10}))
    check("seller onboarding message sent", ext_has("client.message.send"))
    say("  NOTE: $500,000 list price came in on the signed envelope. No "
        "agent set it, no agent will change it.")

    act(2, "PHOTOS DELIVERED -> PRODUCTION GATE OPENS")
    hub.send(spoke_env("external", "09", "vendor.event", ctx,
                       {"kind": "photography",
                        "event_kind": "deliverable_report",
                        "doc_type": "photo_package",
                        "proof_artifact_present": True,
                        "content_hash": "photos-hash"}))
    check("photo deliverable verified present-and-opens",
          bool(seen("deliverable.release")))
    check("description drafted, submitted to compliance",
          bool(seen("content.review")))
    verd = [e for e in seen("content.verdict") if e["client_context_id"] == ctx]
    verdict = verd[-1]["payload"]["verdict"] if verd else "none"
    check("compliance verdict on the clean draft is approved",
          verdict == "approved", verdict)
    rel = {r["to_agent"] for r in seen("asset.release")
           if r["client_context_id"] == ctx}
    check("approved assets released to both MLS (05) and marketing (12)",
          {"05", "12"} <= rel, sorted(rel))

    act(3, "FAIR-HOUSING GATE LIVE -> A STEERING PHRASE IS FLAGGED")
    fctx = "demo-flag"
    hub.send(spoke_env("05", "04", "listing.data", fctx,       # (stand-in)
                       {"beds": 2, "features": ["perfect for families"],
                        "today": "2026-07-05"}))
    fv = [e["payload"]["verdict"] for e in seen("content.verdict")
          if e["client_context_id"] == fctx]
    check("data carrying a prohibited steering phrase is flagged first",
          bool(fv) and fv[0] == "flagged", fv)
    leaked = any("perfect for families" in str(r["payload"])
                 for r in seen("asset.release")
                 if r["client_context_id"] == fctx)
    check("the flagged phrase never reached a marketing release", not leaked)
    say("  The gate is a hard stop: flagged copy cannot market. Period.")

    act(4, "GO-LIVE -> MLS ACTIVE, CLEAR COOPERATION, THE ABSOLUTE SIGNAL")
    su = {e["to_agent"] for e in seen("status.update")
          if e["client_context_id"] == ctx
          and e["payload"].get("status") == "active"}
    check("status.update(active) reached 11, 12 and 14",
          {"11", "12", "14"} <= su, sorted(su))
    # THE ABSOLUTE SIGNAL, live: the campaign is a PUBLIC send. It does not
    # auto-publish - it HOLDS until a human authorizes THIS message.
    held = [e for e in hub.audit.read()
            if e["kind"] == "absolute_signal.hold"
            and e["intent"] == "campaign.publish"]
    check("campaign to the PUBLIC held by the Absolute Signal", bool(held),
          f"audience={held[0]['audience'] if held else '-'}")
    check("nothing published before the broker's key",
          not ext_has("campaign.publish"))
    n_released = release("campaign.publish", "12")
    check("broker signs the release for the campaign", n_released >= 1,
          f"{n_released} released")
    check("campaign published after the broker's key",
          ext_has("campaign.publish"))
    feeds = any(e["to_agent"] == "13" and e["client_context_id"] == ctx
                for e in seen("listing.data"))
    check("listing pushed into buyer-match feeds (agent 13)", feeds)
    sends = [e for e in ext if e.intent == "client.message.send"
             and e.client_context_id == ctx]
    check("seller told 'you're live' (a second message to the seller)",
          len(sends) >= 2, f"{len(sends)} messages to the seller")

    act(5, "A PRICING QUESTION -> ESCALATION, NEVER AN ANSWER")
    pctx = "demo-price"
    before = len(hub.queues.get("escalation.legal_line", []))
    # a seller asks the comms agent directly: should we drop the price?
    hub.send(spoke_env("external", "11", "client.reply", pctx,
                       {"message": "what's your pricing strategy - should "
                                   "we drop to 480k?"}))
    after = len(hub.queues.get("escalation.legal_line", []))
    raised = [e for e in hub.audit.read()
              if e["kind"] == "escalation.raised"
              and e.get("queue") == "escalation.legal_line"]
    escalated = (after > before) and bool(raised)
    answered = any(e.intent == "client.message.send"
                   and e.client_context_id == pctx
                   and "480" in str(e.payload) for e in ext)
    check("pricing question escalated to the legal line", escalated)
    check("no agent answered the price question", not answered)
    say("  Price is fiduciary. The swarm routes it to a human, always.")

    act(6, "THE CHAIN")
    r = hub.audit.verify_chain()
    say(f"  audit entries: {len(hub.audit.read())}")
    check("verify_chain()", bool(r["ok"]), f"ok={r['ok']}")
    check("no dead letters", len(hub.queues["dead.letter"]) == 0,
          len(hub.queues["dead.letter"]))
    say(f"  log file: {path}")
    say()
    say("  Tamper with any line and verify_chain() names it. "
        "Not trust us - check us.")
    say()
    say("=" * 68)
    if failed:
        say(f"  DEMO DID NOT COMPLETE: {len(failed)} stage(s) did not happen:")
        for label in failed:
            say(f"    - {label}")
        say("=" * 68)
        return 1
    say("  DEMO COMPLETE: every stage above happened.")
    say("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
