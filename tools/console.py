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


STATE_DB = os.path.join(STATE_DIR, "swarm-state.sqlite")


def build(audit_path, config_dir=None, state_db=None):
    """The console's swarm: dispatcher/swarm.py with this operator's key.
    Returns (swarm, signer). State is restored from state_db (default
    console-state/swarm-state.sqlite) when the audit chain vouches for it."""
    from dispatcher.signatures import Ed25519Signer, Ed25519Verifier
    from dispatcher.swarm import build_swarm
    if os.path.exists(KEY_PATH):
        signer = Ed25519Signer(private_key_bytes=open(KEY_PATH, "rb").read())
    else:
        signer = Ed25519Signer()
    verifier = Ed25519Verifier(signer.public_key_bytes())
    sw = build_swarm(
        audit_path, state_db=state_db, config_dir=config_dir,
        verifier=verifier.verifier(),
        # every human-queue landing prints as it happens (the pager, on screen)
        human_notifier=lambda queue, record: _p({"HUMAN_QUEUE": queue, "record": record}),
        human_sink=lambda env: _p({"DELIVERED_TO_HUMAN": env.intent,
                                   "ctx": env.client_context_id, "payload": env.payload}))
    _p({"vendor_roster": sw.roster_info["verdict"],
        "vendors_loaded": sw.roster_info["vendors_loaded"],
        "entries_skipped": sw.roster_info["entries_skipped"],
        "state": ("restored" if sw.restored is not None else
                  "fresh" if sw.store is not None else "this process only")})
    return sw, signer


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
    from dispatcher.state_snapshot import StateIntegrityError
    try:
        sw, signer = build(args.audit_log or AUDIT_PATH, getattr(args, "config_dir", None),
                           None if args.no_state else (args.state_db or STATE_DB))
    except StateIntegrityError as e:
        _p({"error": "saved state refused", "reason": str(e),
            "action": "nothing was restored or changed; move the state file aside "
                      "yourself after checking it, or run with --no-state"})
        return 2
    hub, spokes, external = sw.hub, sw.spokes, sw.external
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
    saved = sw.save_state()
    _p({"session_complete": True, "errors": errors, "state_saved": saved,
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
    s.add_argument("--state-db", default=None,
                   help="SQLite file holding the swarm's state between sessions "
                        "(default: console-state/swarm-state.sqlite)")
    s.add_argument("--no-state", action="store_true",
                   help="do not restore or save state (one self-contained session)")
    v = sub.add_parser("verify")
    v.add_argument("--audit-log", default=None)
    v.add_argument("--anchor", default=None,
                   help="a previously printed anchor JSON to verify against")
    args = ap.parse_args()
    return {"init": cmd_init, "session": cmd_session,
            "verify": cmd_verify}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
