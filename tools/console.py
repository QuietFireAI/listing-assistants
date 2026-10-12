#!/usr/bin/env python3
"""console.py - the operator's entry point. No Python required.

Built 2026-07-18 for operational testing: until this existed, feeding
the swarm a lead or a listing meant writing Python against the hub -
fine for tests, wrong for an operator setting up "like anyone else."
This is a thin, honest shim over the same hub the tests run: it builds
real envelopes, signs authority intents with a locally-generated key,
persists swarm state between invocations via each spoke's own state
(reconstructed from the audit log is future work - stated, not faked:
today each console SESSION is one continuous hub, and `--audit-log`
accumulates across sessions so the record survives even though live
spoke state does not).

Commands:
  python tools/console.py init                         # keygen + fresh log
  python tools/console.py session <script.jsonl>       # run a scripted session
  python tools/console.py verify                       # chain + anchor check

A session script is JSON Lines; each line is one action:
  {"do": "config",  "to": "02", "ctx": "setup", "payload": {...}}   # signed
  {"do": "authorize", "to": "05", "ctx": "L1", "payload": {...}}    # signed listing.change.authorized
  {"do": "send", "from": "20", "to": "01", "intent": "lead.signal",
   "ctx": "lead-1", "payload": {...}}                               # spoke/external traffic
  {"do": "sweep", "today": "2026-07-19"}                            # run the clock layer
  {"do": "show", "what": "queues"}     # or "held", "external", "briefing", "eod", "anchor"
  {"do": "release", "ctx": "L1", "intent": "campaign.publish"}      # signed release of held outbound

"send" injects one message as if from the named sender. It is the test
harness's way in: use "external" or "human" where the closed track has
such a route, and a spoke id only to stand in for that agent. The hub
still applies every check (closed track, schema, signatures, holds).

"release" signs one disclosure.authority with your key for EACH held
outbound message matching ctx (required) and intent (optional), the same
call Hub.release_disclosure makes in production. Nothing else releases.

Every item that lands in a human queue (escalations, clarifications,
integrity violations, holds) prints as {"HUMAN_QUEUE": ...} the moment it
lands, the way the SMS notifier would page you.

--config-dir points at a folder holding your ratified config files
(default: the repo's config/). The vendor roster is read from
<config-dir>/vendor_panel.json only when its _status is ratified.

Everything prints as JSON lines so a screen recording captures exactly
what the audit log captured.
"""
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

STATE_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "console-state")
KEY_PATH = os.path.join(STATE_DIR, "operator-key.bin")
AUDIT_PATH = os.path.join(STATE_DIR, "console-audit.jsonl")


def _p(obj):
    print(json.dumps(obj, default=str))


def load_roster(config_dir):
    """Returns (roster, verdict, problems). The roster is Agent 09's format:
    vendor_id -> {kind, license_expiry, insurance_expiry, regulated}. Loaded
    only from a ratified file; an entry with a missing field or a placeholder
    value is skipped and named in problems, never guessed."""
    from dispatcher.config_status import load_ratified_config
    data, verdict = load_ratified_config(os.path.join(config_dir, "vendor_panel.json"))
    if verdict != "loaded":
        return {}, verdict, []
    vendors = data.get("vendors")
    if not isinstance(vendors, dict):
        return {}, "invalid: no 'vendors' object", []
    roster, problems = {}, []
    for vid, v in vendors.items():
        if vid.startswith("<") or not isinstance(v, dict):
            problems.append(f"{vid}: placeholder or not an object")
            continue
        missing = [k for k in ("kind", "license_expiry", "insurance_expiry")
                   if not isinstance(v.get(k), str) or not v.get(k) or v[k].startswith("<")]
        bad_dates = []
        for k in ("license_expiry", "insurance_expiry"):
            if k not in missing:
                try:
                    datetime.date.fromisoformat(v[k])
                except ValueError:
                    bad_dates.append(k)
        if missing or bad_dates:
            problems.append(f"{vid}: missing {missing}" if missing else f"{vid}: bad date {bad_dates}")
            continue
        roster[vid] = {"kind": v["kind"], "license_expiry": v["license_expiry"],
                       "insurance_expiry": v["insurance_expiry"],
                       "regulated": bool(v.get("regulated", True))}
    return roster, verdict, problems


def build(audit_path, config_dir=None):
    from dispatcher.core import Routes, AuditLog, Envelope  # noqa: F401
    from dispatcher.hub import Hub
    from dispatcher.signatures import Ed25519Signer, Ed25519Verifier
    from dispatcher.listing_spokes import Spoke01LeadCapture, Spoke14CRMPipeline
    from dispatcher.listing_spokes_02 import Spoke02LeadQualification
    from dispatcher.listing_spokes_03 import Spoke03LeadNurture
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
    from dispatcher.listing_spokes_20 import Spoke20SocialMediaMonitoring

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if os.path.exists(KEY_PATH):
        signer = Ed25519Signer(private_key_bytes=open(KEY_PATH, "rb").read())
    else:
        signer = Ed25519Signer()
    verifier = Ed25519Verifier(signer.public_key_bytes())
    hub = Hub(Routes(os.path.join(root, "identity", "routes.json")),
              AuditLog(audit_path),
              signature_verifier=verifier.verifier())
    external = []
    hub.register("external", lambda env: external.append(
        {"intent": env.intent, "ctx": env.client_context_id,
         "payload": env.payload}))
    hub.register("human", lambda env: _p(
        {"DELIVERED_TO_HUMAN": env.intent, "ctx": env.client_context_id,
         "payload": env.payload}))
    # every human-queue landing prints as it happens (the pager, on screen)
    hub.human_notifier = lambda queue, record: _p({"HUMAN_QUEUE": queue, "record": record})
    # Load the vendor roster only when ratified, and say what happened
    # (audit 2026-10-11: a PROPOSED DRAFT roster was loaded silently and any
    # read error was swallowed; scene run 2026-10-11: the console read a
    # "vendors" key the template never had, so even a ratified roster
    # loaded empty).
    config_dir = config_dir or os.path.join(root, "config")
    roster, verdict, problems = load_roster(config_dir)
    hub.audit.append("config.load", {"agent": "console", "file": "vendor_panel.json",
                                     "config_dir": config_dir, "verdict": verdict,
                                     "vendors_loaded": sorted(roster),
                                     "entries_skipped": problems})
    _p({"vendor_roster": verdict, "vendors_loaded": sorted(roster),
        "entries_skipped": problems})
    spokes = {
        "01": Spoke01LeadCapture(hub), "02": Spoke02LeadQualification(hub),
        "03": Spoke03LeadNurture(hub), "04": Spoke04ListingDescription(hub),
        "05": Spoke05MLSListingManagement(hub),
        "06": Spoke06ShowingScheduler(hub),
        "07": Spoke07TransactionCoordinator(hub),
        "08": Spoke08DocumentCollection(hub),
        "09": Spoke09VendorCoordination(hub, roster=roster),
        "10": Spoke10MarketData(hub), "11": Spoke11ClientCommunication(hub),
        "12": Spoke12MarketingCampaign(hub),
        "13": Spoke13BuyerSearchMatch(hub), "14": Spoke14CRMPipeline(hub),
        "15": Spoke15FinancialTracking(hub),
        "16": Spoke16AfterCloseReferral(hub),
        "17": Spoke17ComplianceFairHousing(hub),
        "18": Spoke18CalendarTask(hub), "19": Spoke19Prospecting(hub),
        "20": Spoke20SocialMediaMonitoring(hub),
    }
    hub.on_turn_start()
    return hub, signer, spokes, external


def make_env(frm, to, intent, ctx, payload):
    from dispatcher.core import Envelope
    src = "human" if frm == "human" else \
        ("external" if frm == "external" else f"spoke-{frm}")
    return Envelope(from_agent=frm, to_agent=to, intent=intent,
                    client_context_id=ctx, payload=payload,
                    provenance={"source": src, "captured_at": "runtime",
                                "verbatim_available": True})


def cmd_init(_args):
    from dispatcher.signatures import Ed25519Signer
    os.makedirs(STATE_DIR, exist_ok=True)
    if os.path.exists(AUDIT_PATH):
        _p({"error": f"{AUDIT_PATH} exists - a console log is never "
                     f"silently replaced; move it aside yourself"})
        return 1
    signer = Ed25519Signer()
    with open(KEY_PATH, "wb") as f:
        f.write(signer.private_key_bytes())
    os.chmod(KEY_PATH, 0o600)
    _p({"initialized": STATE_DIR, "operator_key": "generated (0600)",
        "audit_log": AUDIT_PATH,
        "note": "this key signs YOUR authority actions - it stays on "
                "this machine"})
    return 0


def held_list(hub):
    return [{"held_envelope_id": hid, "intent": e.intent, "from": e.from_agent,
             "to": e.to_agent, "ctx": e.client_context_id, "payload": e.payload}
            for hid, e in hub._absolute_holds.items()]


def release(hub, signer, ctx, intent=None):
    """One signed disclosure.authority per matching held message."""
    from dispatcher.core import Envelope
    out = []
    for hid, held in list(hub._absolute_holds.items()):
        if held.client_context_id != ctx or (intent and held.intent != intent):
            continue
        auth = Envelope(from_agent="human", to_agent=held.from_agent,
                        intent="disclosure.authority", client_context_id=ctx,
                        payload={"held_envelope_id": hid},
                        provenance={"source": "human", "captured_at": "runtime",
                                    "verbatim_available": True})
        signer.sign(auth)
        out.append({"released": hid, "intent": held.intent, "to": held.to_agent,
                    "hub": hub.release_disclosure(auth)})
    return out or {"released": [], "note": f"nothing held for ctx={ctx!r}"
                                           + (f" intent={intent!r}" if intent else "")}


def cmd_session(args):
    hub, signer, spokes, external = build(args.audit_log or AUDIT_PATH,
                                          getattr(args, "config_dir", None))
    from dispatcher.sweep_runner import run_daily_sweeps
    errors = 0
    for lineno, line in enumerate(open(args.script), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            a = json.loads(line)
        except json.JSONDecodeError as e:
            _p({"line": lineno, "error": f"bad JSON: {e}"})
            errors += 1
            continue
        do = a.get("do")
        if do in ("config", "authorize"):
            intent = "config.update" if do == "config" \
                else "listing.change.authorized"
            env = make_env("human", a["to"], intent, a.get("ctx", "console"),
                           a.get("payload", {}))
            signer.sign(env)
            r = hub.send(env)
        elif do == "send":
            env = make_env(a["from"], a["to"], a["intent"],
                           a.get("ctx", "console"), a.get("payload", {}))
            r = hub.send(env)
        elif do == "release":
            if not a.get("ctx"):
                r = {"error": "release needs ctx (and optionally intent)"}
                errors += 1
            else:
                r = release(hub, signer, a["ctx"], a.get("intent"))
        elif do == "sweep":
            r = run_daily_sweeps(hub, spokes, today=a["today"],
                                 now_iso=a.get("now_iso"))
        elif do == "show":
            what = a.get("what")
            if what == "queues":
                r = {k: v for k, v in hub.queues.items() if v}
            elif what in ("briefing", "eod"):
                # through the hub as a clock.tick (owner rule 2026-10-11:
                # no direct calls into an agent)
                from dispatcher.clock import send_tick
                agent, check = ("18", "morning_briefing") if what == "briefing" else ("14", "eod_report")
                day = a.get("today") or datetime.date.today().isoformat()
                out = send_tick(hub, agent, day, checks=[check])
                r = (out["results"][0]["result"] if out["results"]
                     else {"error": f"clock.tick not delivered: {out['hub']}"})
            elif what == "held":
                r = held_list(hub)
            elif what == "external":
                r = external
            elif what == "anchor":
                r = hub.audit.anchor()
            else:
                r = {"error": f"unknown show target {what!r}"}
        else:
            r = {"error": f"unknown action {do!r}"}
            errors += 1
        _p({"line": lineno, "do": do, "result": r})
    _p({"session_complete": True, "errors": errors,
        "chain": hub.audit.verify_chain(), "anchor": hub.audit.anchor(),
        "dead_letters": len(hub.queues["dead.letter"])})
    return 1 if errors else 0


def cmd_verify(args):
    from dispatcher.core import AuditLog
    log = AuditLog(args.audit_log or AUDIT_PATH)
    r = {"chain": log.verify_chain(), "anchor": log.anchor()}
    if args.anchor:
        r["anchor_check"] = log.verify_anchor(json.loads(args.anchor))
    _p(r)
    return 0 if r["chain"]["ok"] else 1


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    s = sub.add_parser("session")
    s.add_argument("script")
    s.add_argument("--audit-log", default=None)
    s.add_argument("--config-dir", default=None,
                   help="folder with your ratified config files (default: config/)")
    v = sub.add_parser("verify")
    v.add_argument("--audit-log", default=None)
    v.add_argument("--anchor", default=None,
                   help="a previously printed anchor JSON to verify against")
    args = ap.parse_args()
    return {"init": cmd_init, "session": cmd_session,
            "verify": cmd_verify}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
