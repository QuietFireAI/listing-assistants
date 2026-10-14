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
  python tools/console.py onboard                      # who you are (asked once, after init)
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
  {"do": "decline", "ctx": "L1", "intent": "campaign.publish", "reason": "wrong photos"}  # signed: never send it
  {"do": "decide", "ctx": "L1", "decision": "continue"}             # signed continue/cancel on a hold
  {"do": "decide", "ctx": "L1", "decision": "continue", "route_to": "13"}   # a hold that asks for an agent

"send" injects one message as if from the named sender. It is the test
harness's way in: use "external" or "human" where the closed track has
such a route, and a spoke id only to stand in for that agent. The hub
still applies every check (closed track, schema, signatures, holds).

"release" signs one disclosure.authority with your key for EACH held
outbound message matching ctx (required) and intent (optional), the same
call Hub.release_disclosure makes in production. Nothing else releases.
"decline" signs the same key with decision "decline": the held message is
removed unsent (Hub.decline_disclosure) and the decline, with your reason,
goes on the audit log.

Every item that lands in a human queue (escalations, clarifications,
integrity violations, holds) prints as {"HUMAN_QUEUE": ...} the moment it
lands, the way the SMS notifier would page you.

--config-dir points at a folder holding your ratified config files
(default: the repo's config/). The vendor roster is read from
<config-dir>/vendor_panel.json only when its _status is ratified.

Everything prints as JSON lines so a screen recording captures exactly
what the audit log captured.

The Broker Desk (tools/desk.py) runs actions through the same
apply_action(); while a desk holds a state folder, `session` refuses to
start against it (desk_running()).
"""
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# LISTINGASSISTANTS_STATE_DIR moves the whole console state (key, operator,
# pager, log, state store) - used by the tests; default console-state/.
STATE_DIR = os.environ.get("LISTINGASSISTANTS_STATE_DIR") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "console-state")
KEY_PATH = os.path.join(STATE_DIR, "operator-key.bin")
AUDIT_PATH = os.path.join(STATE_DIR, "console-audit.jsonl")


def _p(obj):
    print(json.dumps(obj, default=str))


STATE_DB = os.path.join(STATE_DIR, "swarm-state.sqlite")


def _notify_human(queue, record, pager):
    """The console's human_notifier. Prints the landing, then reports to the
    hub what happened (repair plan 1.1, owner decision D3, 2026-10-13):
      pager on  -> the pager's own result: {"status": "sent"} records
                   human.notified; {"status": "failed", ...} records
                   human.notify_failed, because the channel you chose to be
                   reached on did not reach you.
      pager off -> {"status": "shown", "channel": "screen"}: printed on the
                   session's screen; under the Broker Desk the item is on the
                   desk's queue list. "shown" means put in front of you, not
                   that anyone read it - only the pager reaches you away
                   from the screen.
    Before this the lambda returned a tuple, which the hub could not read."""
    _p({"HUMAN_QUEUE": queue, "record": record})
    if pager:
        return pager(queue, record)
    return {"status": "shown", "channel": "screen"}


def build(audit_path, config_dir=None, state_db=None, model=None, pager=None, enforce=True):
    """The console's swarm: dispatcher/swarm.py with this operator's key.
    Returns (swarm, signer). State is restored from state_db (default
    console-state/swarm-state.sqlite) when the audit chain vouches for it."""
    from dispatcher.signatures import Ed25519Signer, Ed25519Verifier
    from dispatcher.swarm import build_swarm
    from dispatcher.boot_attest import AttestationRefused
    if not os.path.exists(KEY_PATH):
        # 2026-10-14: the install is attested with the operator key, so
        # there is nothing to check it against without one
        raise AttestationRefused(f"no operator key at {KEY_PATH}: run "
                                 f"`python tools/console.py init` first")
    signer = Ed25519Signer(private_key_bytes=open(KEY_PATH, "rb").read())
    verifier = Ed25519Verifier(signer.public_key_bytes())
    from dispatcher.boot_attest import fingerprint
    sw = build_swarm(
        audit_path, state_db=state_db, config_dir=config_dir,
        verifier=verifier.verifier(),
        # refuse to start unless the install is what this key attested and
        # the log agrees (MANNERS.md §Re-injection; owner decision
        # 2026-10-14). enforce=False only for the showcase desk.
        attestation=({"state_dir": os.path.dirname(KEY_PATH),
                      "verify_bytes": verifier.verify_bytes,
                      "key_fingerprint": fingerprint(signer.public_key_bytes())}
                     if enforce else None),
        # every human-queue landing prints as it happens; with the pager on it
        # also texts you, and the hub records what the notifier says happened
        human_notifier=lambda queue, record: _notify_human(queue, record, pager),
        human_sink=lambda env: _p({"DELIVERED_TO_HUMAN": env.intent,
                                   "ctx": env.client_context_id, "payload": env.payload}),
        model_client=(model or {}).get("client"), model_name=(model or {}).get("name"))
    _p({"vendor_roster": sw.roster_info["verdict"],
        "vendors_loaded": sw.roster_info["vendors_loaded"],
        "entries_skipped": sw.roster_info["entries_skipped"],
        "state": ("restored" if sw.restored is not None else
                  "fresh" if sw.store is not None else "this process only"),
        "model_drafting": sw.hub.drafting.gate(),
        "sms_pager": "on" if pager else "off"})
    if pager:
        pager.audit = sw.hub.audit
    return sw, signer


def desk_running(state_dir):
    """The pid of a Broker Desk (tools/desk.py) holding this state folder,
    or None. The desk keeps the swarm open; a second process on the same
    files would fork the state, so console sessions and the daily clock
    refuse to start while a desk runs. A lock left by a desk that died is
    ignored (its pid is gone)."""
    path = os.path.join(state_dir, "desk.lock")
    try:
        pid = int(open(path, encoding="utf-8").read().strip())
    except (OSError, ValueError):
        return None
    if pid == os.getpid():
        return None
    return pid if _pid_alive(pid) else None


def _pid_alive(pid):
    """Whether a process is running. On Windows os.kill(pid, 0) would END
    the process (it calls TerminateProcess), so ask the kernel instead."""
    if os.name == "nt":
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, pid)      # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
        k32.CloseHandle(h)
        return bool(ok) and code.value == 259         # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except (PermissionError, OSError):
        return True
    return True


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
    from dispatcher.private_file import write_private, is_private
    signer = Ed25519Signer()
    # private from the first byte, on Linux, macOS and Windows alike
    write_private(KEY_PATH, signer.private_key_bytes())
    # the install you just set up is the one you attest (2026-10-14)
    from dispatcher.boot_attest import attest
    att = attest(STATE_DIR, signer, audit_path=AUDIT_PATH)
    _p({"initialized": STATE_DIR,
        "operator_key": "generated, private: " + is_private(KEY_PATH)[1],
        "audit_log": AUDIT_PATH,
        "attested": {"files": att["files"], "file": att["path"]},
        "note": "this key signs YOUR authority actions - it stays on "
                "this machine"})
    return 0


def held_list(hub):
    return [{"held_envelope_id": hid, "intent": e.intent, "from": e.from_agent,
             "to": e.to_agent, "ctx": e.client_context_id, "payload": e.payload}
            for hid, e in hub._absolute_holds.items()]


def _answer_held(hub, signer, ctx, intent, decision, reason=None):
    """One signed disclosure.authority per held message matching ctx (and
    intent). decision "release" sends it; "decline" removes it unsent. The
    decision is inside the signed payload, so one can never stand in for
    the other."""
    from dispatcher.core import Envelope
    out = []
    verb = "released" if decision == "release" else "declined"
    for hid, held in list(hub._absolute_holds.items()):
        if held.client_context_id != ctx or (intent and held.intent != intent):
            continue
        payload = {"held_envelope_id": hid}
        if decision != "release":
            payload["decision"] = decision
            if reason:
                payload["reason"] = reason
        auth = Envelope(from_agent="human", to_agent=held.from_agent,
                        intent="disclosure.authority", client_context_id=ctx,
                        payload=payload,
                        provenance={"source": "human", "captured_at": "runtime",
                                    "verbatim_available": True})
        signer.sign(auth)
        call = hub.release_disclosure if decision == "release" else hub.decline_disclosure
        out.append({verb: hid, "intent": held.intent, "to": held.to_agent,
                    "hub": call(auth)})
    return out or {verb: [], "note": f"nothing held for ctx={ctx!r}"
                                     + (f" intent={intent!r}" if intent else "")}


def release(hub, signer, ctx, intent=None):
    """One signed disclosure.authority per matching held message."""
    return _answer_held(hub, signer, ctx, intent, "release")


def decline(hub, signer, ctx, intent=None, reason=None):
    """One signed decline per matching held message: removed, never sent."""
    return _answer_held(hub, signer, ctx, intent, "decline", reason)


def decide(sw, signer, a):
    """Signs one hitl.decision.authority for the pending hold on ctx (and
    agent, if given) and applies it through the HITL manager."""
    from dispatcher.core import Envelope
    from dispatcher.hitl_protocol import HITLAuthorizationError
    waits = [w for w in sw.hitl.get_pending_waits(a.get("ctx"))
             if not a.get("agent") or w["agent_id"] == a["agent"]]
    if len(waits) != 1:
        return {"error": f"{len(waits)} pending holds match ctx={a.get('ctx')!r}"
                         f"{' agent=' + repr(a['agent']) if a.get('agent') else ''} - "
                         f"name the agent so exactly one matches",
                "pending": [{"wait_id": w["wait_id"], "agent": w["agent_id"]} for w in waits]}
    w = waits[0]
    choice = str(a.get("decision", "")).lower()
    if choice == "continue":
        payload = {"wait_id": w["wait_id"], "decision": "APPROVE"}
        if a.get("route_to") is not None:
            payload = {"wait_id": w["wait_id"], "decision": "APPROVE_WITH_OVERRIDE",
                       "updated_fields": {"route_to": str(a["route_to"])}}
    elif choice == "cancel":
        payload = {"wait_id": w["wait_id"], "decision": "REJECT_AND_ABORT"}
    else:
        return {"error": "decision must be continue or cancel"}
    auth = Envelope(from_agent="human", to_agent=w["agent_id"],
                    intent="hitl.decision.authority", client_context_id=w["client_context_id"],
                    payload=payload, provenance={"source": "human", "captured_at": "runtime",
                                                 "verbatim_available": True})
    signer.sign(auth)
    try:
        return sw.hitl.resume_operation(auth)
    except (HITLAuthorizationError, ValueError) as e:
        return {"error": str(e)}


OPERATOR_PATH = os.path.join(STATE_DIR, "operator.json")
PAGER_PATH = os.path.join(STATE_DIR, "pager.json")


def load_pager(state_dir):
    """The text pager for the swarm on this state folder, or None when it is
    off (no pager.json). A pager.json that is there but unusable raises
    ValueError naming what is wrong: a pager that is on must page. Used by
    console sessions, the Broker Desk and the daily clock (2026-10-13: the
    desk showed "Text pager to you: on" while its swarm paged nobody)."""
    from dispatcher import pager as pg
    cfg = pg.load_config(os.path.join(state_dir, "pager.json"))
    return pg.Pager(cfg) if cfg else None


def cmd_pager(args):
    """Turns the text-message pager on (asks for the Twilio details once,
    after onboarding), sends a test page, or turns it off (owner decision
    #10 / J8). Pages carry the queue name and client context id only."""
    from dispatcher import pager as pg
    if args.off:
        existed = os.path.exists(PAGER_PATH)
        if existed:
            os.remove(PAGER_PATH)
        _p({"pager": "off", "details_removed": existed})
        return 0
    if args.test:
        try:
            cfg = pg.load_config(PAGER_PATH)
        except ValueError as e:
            _p({"error": str(e)})
            return 1
        if cfg is None:
            _p({"error": "the pager is off - run `python tools/console.py pager` first"})
            return 1
        res = pg.send_page(cfg, "ListingAssistants: test page. If you can read this, paging works.")
        _p({"test_page": res})
        return 0 if res["status"] == "sent" else 1
    if _operator() is None:
        _p({"error": "onboard first (`python tools/console.py onboard`) - the pager is set up "
                     "after you are recorded as the operator"})
        return 1
    import getpass
    cfg = {"account_sid": args.account_sid or input("Twilio account SID: ").strip(),
           "auth_token": (open(args.auth_token_file, encoding="utf-8").read().strip() if args.auth_token_file
                          else getpass.getpass("Twilio auth token (not shown): ").strip()),
           "from_number": args.from_number or input("Twilio number to send from (+1...): ").strip(),
           "to_number": args.to_number or input("Your mobile number (+1...): ").strip()}
    if args.api_base:
        cfg["api_base"] = args.api_base
    problems = pg.validate(cfg)
    if problems:
        _p({"error": "pager details rejected; nothing saved", "problems": problems})
        return 1
    pg.save_config(PAGER_PATH, cfg)
    from dispatcher.private_file import is_private
    _p({"pager": "on", "saved_to": PAGER_PATH, "private": is_private(PAGER_PATH)[1],
        "pages_carry": "the queue name and client context id only",
        "next": "python tools/console.py pager --test"})
    return 0


def cmd_onboard(args):
    """Asks once, after init, who the operator is, and records it next to
    the key. Signed console actions then carry that login in their
    provenance. Credentials for anything else are asked for when a feature
    first needs them; nothing in the console needs one today."""
    import hashlib
    if not os.path.exists(KEY_PATH):
        _p({"error": "run `python tools/console.py init` first - there is no key to bind"})
        return 1
    name = args.name or input("Your name (broker of record): ").strip()
    login = args.login or input("Your login (email you sign as): ").strip()
    if not name or not login or "@" not in login:
        _p({"error": "a name and an email-style login are both required; nothing saved"})
        return 1
    from dispatcher.signatures import Ed25519Signer
    pub = Ed25519Signer(private_key_bytes=open(KEY_PATH, "rb").read()).public_key_bytes()
    rec = {"name": name, "login": login,
           "key_fingerprint": hashlib.sha256(pub).hexdigest()[:16],
           "onboarded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    with open(OPERATOR_PATH, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=1)
    _p({"onboarded": rec,
        "not_armed": {"signer_registry": "config/authority_signers.json binds signers to an "
                                         "identity provider with MFA; no identity provider is "
                                         "connected, so the hub checks your key's signature and "
                                         "records that the login binding is off",
                      "sms_pager": "off - `python tools/console.py pager` asks for your Twilio "
                                   "details and turns it on; pages carry the queue name and "
                                   "client context id only; the console always prints pages "
                                   "on screen"}})
    return 0


def _operator():
    try:
        with open(OPERATOR_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def apply_action(sw, signer, operator, a, external=None):
    """Runs one session action (the JSON-line format above) and returns
    (result, error). The console's session loop and the Broker Desk
    (tools/desk.py) both run actions through here, so a click on the Desk
    and a line in a session script do exactly the same thing."""
    hub, spokes = sw.hub, sw.spokes
    external = sw.external if external is None else external
    from dispatcher.sweep_runner import run_daily_sweeps
    error = False
    do = a.get("do")
    if do in ("config", "authorize"):
        intent = "config.update" if do == "config" \
            else "listing.change.authorized"
        env = make_env("human", a["to"], intent, a.get("ctx", "console"),
                       a.get("payload", {}))
        if operator:
            env.provenance["operator"] = operator["login"]
        signer.sign(env)
        r = hub.send(env)
    elif do == "send":
        env = make_env(a["from"], a["to"], a["intent"],
                       a.get("ctx", "console"), a.get("payload", {}))
        r = hub.send(env)
    elif do == "release":
        if not a.get("ctx"):
            r = {"error": "release needs ctx (and optionally intent)"}
            error = True
        else:
            r = release(hub, signer, a["ctx"], a.get("intent"))
    elif do == "decline":
        if not a.get("ctx"):
            r = {"error": "decline needs ctx (and optionally intent, reason)"}
            error = True
        else:
            r = decline(hub, signer, a["ctx"], a.get("intent"), a.get("reason"))
    elif do == "decide":
        r = decide(sw, signer, a)
        if isinstance(r, dict) and r.get("error"):
            error = True
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
            if what == "eod" and isinstance(r, dict):
                # the plain-language ledger, built from the chain (2026-10-12)
                led = sw.write_eod(a.get("ledger_date"))
                r = {**r, "readable_ledger": {"file": led["report_file"],
                                              "events": led["total_events"],
                                              "chain_ok": (led["integrity"]["chain"] or {}).get("ok")}}
        elif what == "held":
            r = held_list(hub)
        elif what == "waits":
            r = [{k: w[k] for k in ("wait_id", "client_context_id", "agent_id",
                                    "paused_intent", "reason", "required_decision")}
                 for w in sw.hitl.get_pending_waits()]
        elif what == "external":
            r = external
        elif what == "anchor":
            r = hub.audit.anchor()
        else:
            r = {"error": f"unknown show target {what!r}"}
    else:
        r = {"error": f"unknown action {do!r}"}
        error = True
    return r, error


def damaged_record_error(e, audit_path):
    """What every entry point prints when the audit record cannot be used
    (dispatcher.core.AuditLogDamaged; repair plan 1.2, owner decision D4).
    Nothing was written. A write cut off at the end is repaired by a person
    with `console.py repair-record`; anything else is for a person to look at.
    Also covers AuditLogBusy (third review): another program held the
    record's lock for longer than the wait."""
    from dispatcher.core import AuditLogBusy
    if isinstance(e, AuditLogBusy):
        return {"error": "the record (audit log) is in use by another program - nothing was done",
                "file": audit_path, "reason": str(e),
                "action": "wait a moment and try again; if it stays busy, stop the other program "
                          "using this folder (a desk, a console session or the daily clock)"}
    out = {"error": "the record (audit log) is damaged - nothing was started or written",
           "file": audit_path, "line": e.line, "reason": e.reason,
           "cut_off_last_write": e.torn_tail}
    if e.torn_tail:
        out["action"] = ("the last write was cut off part-way (a crash or power loss). "
                         "Stop anything else using this folder, then run: python tools/console.py "
                         f"repair-record --audit-log \"{audit_path}\" - it moves the partial line "
                         "to a side file, keeps every complete entry, and records the repair")
    else:
        out["action"] = ("a line before the end is damaged or was edited - this is not a "
                         "cut-off write and is not repaired automatically. Keep a copy of the "
                         "file and have someone look at that line before running again")
    return out


def cmd_session(args):
    from dispatcher.core import AuditLogBusy, AuditLogDamaged
    from dispatcher.state_snapshot import StateIntegrityError
    from dispatcher.boot_attest import AttestationRefused
    folder = os.path.dirname(os.path.abspath(args.audit_log or AUDIT_PATH))
    other = desk_running(folder)
    if other:
        _p({"error": f"the Broker Desk is running on {folder} (pid {other}) - stop it, or "
                     f"do this from the desk; two processes on the same state would fork it"})
        return 2
    model = None
    if getattr(args, "model_url", None):
        if not args.model_name:
            _p({"error": "--model-url needs --model-name"})
            return 2
        from dispatcher.model_drafting import OpenAICompatibleClient
        try:
            model = {"client": OpenAICompatibleClient(args.model_url,
                                                      allow_remote=args.allow_remote_model),
                     "name": args.model_name}
        except ValueError as e:
            _p({"error": str(e)})
            return 2
    try:
        pager = load_pager(os.path.dirname(PAGER_PATH))
    except ValueError as e:
        _p({"error": str(e)})
        return 2
    try:
        sw, signer = build(args.audit_log or AUDIT_PATH, getattr(args, "config_dir", None),
                           None if args.no_state else (args.state_db or STATE_DB), model, pager)
    except StateIntegrityError as e:
        _p({"error": "saved state refused", "reason": str(e),
            "action": "nothing was restored or changed; move the state file aside "
                      "yourself after checking it, or run with --no-state"})
        return 2
    except (AuditLogDamaged, AuditLogBusy) as e:
        _p(damaged_record_error(e, args.audit_log or AUDIT_PATH))
        return 2
    except AttestationRefused as e:
        _p({"error": "install not attested", "reason": str(e),
            "action": "nothing was written; review the install, then run "
                      "`python tools/console.py attest`"})
        return 2
    hub, spokes, external = sw.hub, sw.spokes, sw.external
    operator = _operator()
    if operator is None:
        _p({"note": "not onboarded - run `python tools/console.py onboard` to record who "
                    "signs; signed actions still carry your key's signature"})
    errors = 0
    for lineno, line in enumerate(open(args.script, encoding="utf-8"), 1):
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
        try:
            r, err = apply_action(sw, signer, operator, a, external)
        except (AuditLogDamaged, AuditLogBusy) as e:
            # the record changed or broke under this session, or stayed busy: stop here,
            # write nothing more (no state save either), and say where
            _p({**damaged_record_error(e, args.audit_log or AUDIT_PATH),
                "script_line": lineno, "do": do,
                "stopped": "the session stopped at this script line; earlier lines were done"})
            return 2
        if err:
            errors += 1
        _p({"line": lineno, "do": do, "result": r})
    saved = sw.save_state()
    _p({"session_complete": True, "errors": errors, "state_saved": saved,
        "readable_log": sw.readable.stream_path,
        "readable_log_errors": len(hub.audit.mirror_errors),
        "chain": hub.audit.verify_chain(), "anchor": hub.audit.anchor(),
        "dead_letters": len(hub.queues["dead.letter"])})
    return 1 if errors else 0


def cmd_verify(args):
    from dispatcher.core import AuditLog
    path = args.audit_log or AUDIT_PATH
    # check_file reads only and names the first bad line; it never raises on
    # damage (2026-10-13: a cut-off last line used to crash verify itself)
    from dispatcher.core import AuditLogBusy
    try:
        r = {"chain": AuditLog.check_file(path)}
    except AuditLogBusy as e:
        _p(damaged_record_error(e, path))
        return 2
    if r["chain"]["ok"]:
        log = AuditLog(path)
        r["anchor"] = log.anchor()
        if args.anchor:
            r["anchor_check"] = log.verify_anchor(json.loads(args.anchor))
    elif r["chain"].get("torn_tail"):
        r["action"] = f"the last write was cut off - run: python tools/console.py repair-record --audit-log \"{path}\""
    _p(r)
    return 0 if r["chain"]["ok"] else 1


def cmd_repair_record(args):
    """Repairs a write cut off at the end of the record, and nothing else
    (owner decision D4: a person runs this; nothing repairs on its own).
    The partial line goes to <log>.torn-<UTC time>-<sha12> next to the log,
    every complete entry stays, and an audit.tail_quarantined entry records
    the repair on the chain. Any other damage is refused, unchanged."""
    from dispatcher.core import AuditLog, AuditLogBusy, AuditLogDamaged
    path = args.audit_log or AUDIT_PATH
    folder = os.path.dirname(os.path.abspath(path))
    other = desk_running(folder)
    if other:
        _p({"error": f"the Broker Desk is running on {folder} (pid {other}) - stop it first"})
        return 2
    if not os.path.exists(path):
        _p({"error": f"{path}: no such file"})
        return 2
    if args.check:
        r = AuditLog.check_file(path)
        _p({"chain": r})
        return 0 if r["ok"] else 1
    # a repair writes to the chain: only from an attested install (2026-10-14).
    # The log is not read for this check - it is the damaged thing.
    from dispatcher.boot_attest import AttestationRefused, check, fingerprint
    from dispatcher.signatures import Ed25519Signer, Ed25519Verifier
    try:
        if not os.path.exists(KEY_PATH):
            raise AttestationRefused(f"no operator key at {KEY_PATH}: run "
                                     f"`python tools/console.py init` first")
        key = Ed25519Signer(private_key_bytes=open(KEY_PATH, "rb").read()).public_key_bytes()
        check(os.path.dirname(KEY_PATH), Ed25519Verifier(key).verify_bytes, fingerprint(key))
    except AttestationRefused as e:
        _p({"repaired": False, "changed": "nothing", "refused": f"install not attested: {e}"})
        return 2
    try:
        rec = AuditLog.repair_torn_tail(path)
    except (AuditLogDamaged, AuditLogBusy, ValueError) as e:
        _p({"repaired": False, "refused": str(e), "changed": "nothing"})
        return 2
    except OSError as e:     # e.g. Windows: another program holds the record open
        _p({"repaired": False, "changed": "nothing",
            "refused": f"the repaired record could not replace the old one ({e!r}); "
                       f"stop every program using this folder and run this again"})
        return 2
    out = {"repaired": True, **rec, "chain": AuditLog.check_file(path)}
    # the plain-language log is a view the swarm writes as it appends; the
    # repair is not a swarm append, so it is written to the view here
    try:
        from dispatcher.readable_audit import describe
        from dispatcher.readable_logger import HumanReadableLogger
        cat, msg, _, _ = describe("audit.tail_quarantined", rec)
        HumanReadableLogger(log_root=os.path.join(folder, "readable"),
                            drawers_root=None).log_event(cat, msg)
    except Exception as e:   # the view failing never undoes the repair; said, not hidden
        out["readable_log_error"] = f"{type(e).__name__}: {e}"
    _p(out)
    return 0


def cmd_attest(args):
    """Sign what is installed now, after you have reviewed a change (an
    offline update, a core sync). Names what changed since the last
    attestation. The console, the Broker Desk and the daily clock refuse to
    start until the install matches what you attested (2026-10-14)."""
    from dispatcher.signatures import Ed25519Signer
    from dispatcher.boot_attest import attest
    if not os.path.exists(KEY_PATH):
        _p({"error": f"no operator key at {KEY_PATH}: run `python tools/console.py init` first"})
        return 2
    signer = Ed25519Signer(private_key_bytes=open(KEY_PATH, "rb").read())
    from dispatcher.core import AuditLogBusy, AuditLogDamaged
    try:
        result = attest(STATE_DIR, signer, audit_path=args.audit_log or AUDIT_PATH)
    except (AuditLogDamaged, AuditLogBusy) as e:
        _p({**damaged_record_error(e, args.audit_log or AUDIT_PATH),
            "attested": False, "note": "nothing was signed; the record must take the entry first"})
        return 2
    _p({"attested": result,
        "note": "you signed what is installed now; the console, the Broker Desk and "
                "the daily clock start only while it stays exactly this"})
    return 0


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from fresh_bytecode import use_fresh_bytecode
    use_fresh_bytecode()            # only attested source runs (2026-10-14)
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    at = sub.add_parser("attest", help="sign what is installed now, after reviewing a change")
    at.add_argument("--audit-log", default=None,
                    help="the audit log this attestation is recorded on (default: the console's)")
    o = sub.add_parser("onboard")
    o.add_argument("--name", default=None)
    o.add_argument("--login", default=None)
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
    s.add_argument("--model-url", default=None,
                   help="OpenAI-style endpoint of a locally served model for Agent 04's "
                        "optional model-written remarks (e.g. http://localhost:11434/v1)")
    s.add_argument("--model-name", default=None, help="the served model's name")
    s.add_argument("--allow-remote-model", action="store_true",
                   help="allow a model endpoint that is not this machine (listing data leaves it)")
    pg = sub.add_parser("pager")
    pg.add_argument("--off", action="store_true", help="forget the Twilio details; pages stop")
    pg.add_argument("--test", action="store_true", help="send one test page")
    pg.add_argument("--account-sid", default=None)
    pg.add_argument("--auth-token-file", default=None,
                    help="read the auth token from this file instead of asking")
    pg.add_argument("--from-number", default=None)
    pg.add_argument("--to-number", default=None)
    pg.add_argument("--api-base", default=None, help=argparse.SUPPRESS)
    v = sub.add_parser("verify")
    v.add_argument("--audit-log", default=None)
    v.add_argument("--anchor", default=None,
                   help="a previously printed anchor JSON to verify against")
    rr = sub.add_parser("repair-record",
                        help="repair a write cut off at the end of the record (nothing else)")
    rr.add_argument("--audit-log", default=None)
    rr.add_argument("--check", action="store_true", help="check only; change nothing")
    args = ap.parse_args()
    try:
        return {"init": cmd_init, "attest": cmd_attest, "onboard": cmd_onboard,
                "session": cmd_session,
                "verify": cmd_verify, "pager": cmd_pager,
                "repair-record": cmd_repair_record}[args.cmd](args)
    except EOFError:
        # onboard and pager ask questions; with no terminal attached there
        # is nobody to answer them
        _p({"error": f"`{args.cmd}` asks for answers and none could be read - run it in "
                     f"a terminal, or pass every answer as an option (see --help)"})
        return 1


if __name__ == "__main__":
    sys.exit(main())
