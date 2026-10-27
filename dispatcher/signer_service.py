"""signer_service - the operator's key in a room of its own, with two-factor.

Owner decisions 2026-10-26 (agent isolation V1):
  - The key lives in its own container. The dispatcher cannot reach it,
    period: there is no line from the dispatcher to the signer.
  - Signing needs a second factor. V1: the six-digit code from an
    authenticator app, typed on the signer's OWN page. Hardware security
    keys (WebAuthn / FIDO2, e.g. a YubiKey) are built in too and are meant
    to become the default; register two (one on the keyring, one in a safe)
    and turn on the key's PIN.

How a signature travels, with no line between dispatcher and signer:
  1. You press a button on the Desk that needs your signature. The
     dispatcher prepares the message and hands it to YOUR BROWSER.
  2. Your browser opens the signer's page (another port, another room) and
     shows it the message. The signer shows you, in its own words, what
     you are about to sign. The Desk cannot draw on that page.
  3. You type the code (or touch your key). The signer checks it, signs
     that exact message, writes it on its own record, and hands the
     signature back to the Desk page in your browser.
  4. The Desk checks the signature against your public key and carries on.

For settings files and scripts (setup, a playbook run) the same happens in
a batch: `sign-batch` signs a file of prepared messages after one code.

Commands (inside the signer container):

    python -m dispatcher.signer_service init  --dir /signer --out /out --account you@example.com
    python -m dispatcher.signer_service serve --dir /signer --port 8767
    python -m dispatcher.signer_service sign-batch --dir /signer --in unsigned.jsonl --out signed.jsonl
    python -m dispatcher.signer_service attest --dir /signer --out /out

The signer's own record (signer-log.jsonl, hash-chained) holds every
signature it made, every wrong code, every lock and every key added.
"""
from __future__ import annotations

import base64
import datetime
import html
import http.server
import json
import os
import secrets
import sys
import threading
import time
import urllib.parse
from typing import Any, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_FAILURES = 5
LOCK_S = 15 * 60
PENDING_TTL_S = 10 * 60


class SignerRefused(Exception):
    """Not signed, with the reason shown to you."""


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def _unb64u(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class SignerStore:
    """The signer's folder: the key, the authenticator secret, the security
    keys, its record. Nothing here ever leaves the signer except the public
    key and signatures."""

    def __init__(self, folder: str):
        self.folder = folder
        self.key_path = os.path.join(folder, "operator-key.bin")
        self.totp_path = os.path.join(folder, "totp.json")
        self.keys_path = os.path.join(folder, "security-keys.json")
        self.lock = threading.RLock()
        from .core import AuditLog
        self.log = AuditLog(os.path.join(folder, "signer-log.jsonl"))

    # ------------------------------------------------------------ files
    def _read(self, path: str, default):
        if not os.path.exists(path):
            return default
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _write(self, path: str, obj) -> None:
        from .private_file import write_private
        write_private(path, json.dumps(obj, indent=1).encode("utf-8"))

    def signer(self):
        from .signatures import Ed25519Signer
        if not os.path.exists(self.key_path):
            raise SignerRefused("no key: run `init` first")
        with open(self.key_path, "rb") as f:
            return Ed25519Signer(private_key_bytes=f.read())

    def public_key(self) -> bytes:
        return self.signer().public_key_bytes()

    def fingerprint(self) -> str:
        from .boot_attest import fingerprint
        return fingerprint(self.public_key())

    def totp(self) -> dict:
        t = self._read(self.totp_path, None)
        if not t:
            raise SignerRefused("no authenticator set up: run `init` first")
        return t

    def security_keys(self) -> list:
        return self._read(self.keys_path, [])

    # ------------------------------------------------------------ factors
    def check_code(self, code: str, purpose: str) -> None:
        """Raises SignerRefused unless the code is right, new and the signer
        is not locked. Five wrong codes lock it for 15 minutes."""
        from . import totp as tp
        with self.lock:
            t = self.totp()
            if t.get("locked_until", 0) > time.time():
                left = int(t["locked_until"] - time.time()) // 60 + 1
                raise SignerRefused(f"locked after {MAX_FAILURES} wrong codes; try again in "
                                    f"{left} minute(s)")
            step = tp.verify(t["secret"], code, int(t.get("last_counter", -1)))
            if step is None:
                t["failures"] = int(t.get("failures", 0)) + 1
                locked = t["failures"] >= MAX_FAILURES
                if locked:
                    t["locked_until"] = time.time() + LOCK_S
                    t["failures"] = 0
                self._write(self.totp_path, t)
                self.log.append("signer.locked" if locked else "signer.wrong_code",
                                {"purpose": purpose})
                raise SignerRefused("locked: too many wrong codes" if locked
                                    else "that code is not right (or was already used)")
            t["last_counter"], t["failures"] = step, 0
            self._write(self.totp_path, t)

    # ------------------------------------------------------------ signing
    def check_request(self, record: dict) -> Any:
        """The message must be yours to sign: from 'human', an authority
        intent of this identity. Returns the Envelope."""
        from .core import Envelope, Routes
        from .hub import is_authority
        if not isinstance(record, dict):
            raise SignerRefused("not a message")
        fields = ("envelope_id", "from_agent", "to_agent", "intent", "client_context_id",
                  "payload", "provenance")
        if any(k not in record for k in fields):
            raise SignerRefused("the message is missing a field")
        if record["from_agent"] != "human":
            raise SignerRefused("only messages from you are signed here")
        routes = Routes(os.path.join(ROOT, "identity", "routes.json"))
        if not is_authority(record["intent"], routes.signed_intents):
            raise SignerRefused(f"{record['intent']} is not something that needs your signature")
        keep = {k: record.get(k) for k in ("envelope_id", "from_agent", "to_agent", "intent",
                                           "in_reply_to", "client_context_id", "payload",
                                           "provenance", "confidence", "escalation_flag")}
        keep["confidence"] = keep.get("confidence") or "unknown"
        keep["escalation_flag"] = bool(keep.get("escalation_flag"))
        return Envelope(**keep)

    def sign_record(self, record: dict, factor: str) -> dict:
        env = self.check_request(record)
        sig = self.signer().sign(env)
        self.log.append("signer.signed", {
            "envelope_id": env.envelope_id, "intent": env.intent, "to_agent": env.to_agent,
            "client_context_id": env.client_context_id, "factor": factor,
            "payload_keys": sorted((env.payload or {}).keys())})
        return {**env.to_record(), "signature": sig}


# ----------------------------------------------------------------- the page
def summary(record: dict) -> list[tuple[str, str]]:
    """What you are about to sign, in plain words, built by the signer from
    the message itself (not from anything the Desk says about it)."""
    import re
    names = {}
    for d in sorted(os.listdir(ROOT)):          # each agent's name, from its SKILL.md
        p = os.path.join(ROOT, d, "SKILL.md")
        if d[:2].isdigit() and d[2:3] == "-" and os.path.isfile(p):
            m = re.search(r"^# Agent \d\d - (.+?)(?: Agent)?\s*$", open(p, encoding="utf-8").read(), re.M)
            names[d[:2]] = m.group(1) if m else d[3:]
    what = {"disclosure.authority": "Release (or decline) a held message",
            "hitl.decision.authority": "Your decision on a paused item",
            "config.update": "A setting for an agent",
            "listing.change.authorized": "A listing you authorize"}.get(record.get("intent"),
                                                                       record.get("intent"))
    if record.get("intent") == "disclosure.authority":
        what = ("Do NOT send a held message (decline it)"
                if (record.get("payload") or {}).get("decision") == "decline"
                else "Send a held message")
    to = record.get("to_agent")
    rows = [("What", what), ("To", f"Agent {to} ({names.get(to, '')})".replace(" ()", "")),
            ("Client", str(record.get("client_context_id")))]

    def flat(prefix, v):
        if isinstance(v, dict):
            for k, x in v.items():
                yield from flat(f"{prefix}{k}." if prefix else f"{k}.", x)
        else:
            yield prefix.rstrip("."), json.dumps(v) if not isinstance(v, str) else v
    for k, v in flat("", record.get("payload") or {}):
        rows.append((k.replace("_", " "), v))
    rows.append(("Message id", str(record.get("envelope_id"))))
    return rows


PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ListingAssistants signer</title>
<style>
body{{font:16px/1.45 system-ui,sans-serif;margin:0;background:#f6f8fa;color:#1f2328}}
main{{max-width:560px;margin:24px auto;padding:20px;background:#fff;border:1px solid #d0d7de;border-radius:10px}}
h1{{font-size:20px;margin:0 0 4px}} .sub{{color:#57606a;margin:0 0 16px}}
table{{border-collapse:collapse;width:100%;margin:12px 0}} td{{border-top:1px solid #eaeef2;padding:6px 4px;vertical-align:top}}
td:first-child{{color:#57606a;width:34%}} input{{font-size:22px;letter-spacing:4px;width:9em;padding:6px}}
button{{font-size:16px;padding:8px 14px;border-radius:6px;border:1px solid #1f6feb;background:#1f6feb;color:#fff;cursor:pointer}}
button.alt{{background:#fff;color:#1f6feb}} .err{{color:#cf222e;font-weight:600}} .ok{{color:#1a7f37;font-weight:600}}
.fp{{font-family:ui-monospace,monospace;color:#57606a;font-size:13px}}
</style></head><body><main>{body}</main>{script}</body></html>"""


def page(body: str, script: str = "", nonce: str = "") -> str:
    tag = f'<script nonce="{nonce}">{script}</script>' if script else ""
    return PAGE.format(body=body, script=tag)


class SignerServer:
    """The signer's own page. Origins and ports come from the environment
    of the signer container (docker/compose.yml)."""

    def __init__(self, store: SignerStore, signer_origin: str, desk_origin: str):
        self.store = store
        self.signer_origin = signer_origin.rstrip("/")
        self.desk_origin = desk_origin.rstrip("/")
        u = urllib.parse.urlsplit(self.signer_origin)
        self.rp_id = u.hostname or "localhost"
        self.port = u.port
        self.pending: dict[str, dict] = {}
        self.challenges: dict[str, bytes] = {}

    def _clean(self) -> None:
        cutoff = time.time() - PENDING_TTL_S
        for n in [n for n, p in self.pending.items() if p["at"] < cutoff]:
            self.pending.pop(n, None)

    # ---------------------------------------------------------------- views
    def view_home(self) -> str:
        st = self.store
        keys = st.security_keys()
        rows = "".join(f"<tr><td>{html.escape(k.get('label') or 'key')}</td>"
                       f"<td>added {html.escape(k.get('added_at', ''))}</td></tr>" for k in keys)
        body = (f"<h1>Your signer</h1><p class='sub'>Your key lives here and nowhere else.</p>"
                f"<p class='fp'>Key fingerprint {html.escape(st.fingerprint())}</p>"
                f"<p>Authenticator app: set up. Security keys: {len(keys)}.</p>"
                f"<table>{rows}</table><p><a href='/keys'>Add a security key</a></p>")
        return page(body)

    def view_sign(self, request_json: str) -> str:
        try:
            req = json.loads(request_json)
            record = req["envelope"]
            self.store.check_request(record)
        except (ValueError, KeyError, TypeError, SignerRefused) as e:
            msg = str(e) if isinstance(e, SignerRefused) else "not a signing request"
            return page(f"<h1>Not signed</h1><p class='err'>{html.escape(msg)}</p>")
        self._clean()
        nonce = secrets.token_urlsafe(18)
        self.pending[nonce] = {"id": str(req.get("id", "")), "record": record, "at": time.time()}
        rows = "".join(f"<tr><td>{html.escape(k)}</td><td>{html.escape(v)}</td></tr>"
                       for k, v in summary(record))
        about = req.get("about") if isinstance(req.get("about"), dict) else {}
        if about:
            rows += ("<tr><td colspan='2'><b>What your Desk says this is</b> "
                     "<span class='fp'>(from the Desk; the signer signs only the lines above)</span></td></tr>")
            rows += "".join(f"<tr><td>{html.escape(str(k))}</td><td>{html.escape(str(v))[:400]}</td></tr>"
                            for k, v in list(about.items())[:12])
        key_btn = "<p><button class='alt' id='usekey' type='button'>Use my security key</button></p>"
        body = (f"<h1>Sign this?</h1><p class='sub'>Read it here, on your signer's own page.</p>"
                f"<table>{rows}</table>"
                f"<form method='post' action='/sign/confirm'>"
                f"<input type='hidden' name='nonce' value='{nonce}'>"
                f"<p>Code from your authenticator app:<br>"
                f"<input name='code' inputmode='numeric' autocomplete='one-time-code' maxlength='6' autofocus>"
                f" <button type='submit'>Sign</button></p></form>{key_btn}"
                f"<p id='msg' class='err'></p>"
                f"<p class='fp'>Signing with key {html.escape(self.store.fingerprint())}</p>")
        csp = secrets.token_urlsafe(12)
        return page(body, self._key_script(nonce), csp), csp

    def _key_script(self, nonce: str) -> str:
        return ("""
const b64u = b => btoa(String.fromCharCode(...new Uint8Array(b))).replace(/\\+/g,'-').replace(/\\//g,'_').replace(/=+$/,'');
const unb = s => Uint8Array.from(atob(s.replace(/-/g,'+').replace(/_/g,'/') + '==='.slice((s.length+3)%4)), c => c.charCodeAt(0));
document.getElementById('usekey').onclick = async () => {
  const msg = document.getElementById('msg');
  try {
    const o = await (await fetch('/sign/key-options', {method:'POST', headers:{'Content-Type':'application/json'},
                     body: JSON.stringify({nonce: '__NONCE__'})})).json();
    if (o.error) { msg.textContent = o.error; return; }
    o.challenge = unb(o.challenge);
    o.allowCredentials = (o.allowCredentials||[]).map(c => ({...c, id: unb(c.id)}));
    const a = await navigator.credentials.get({publicKey: o});
    const cred = {id: a.id, rawId: b64u(a.rawId), type: a.type, response: {
      clientDataJSON: b64u(a.response.clientDataJSON), authenticatorData: b64u(a.response.authenticatorData),
      signature: b64u(a.response.signature), userHandle: a.response.userHandle ? b64u(a.response.userHandle) : null}};
    const r = await (await fetch('/sign/key-confirm', {method:'POST', headers:{'Content-Type':'application/json'},
                     body: JSON.stringify({nonce: '__NONCE__', credential: cred})})).json();
    if (r.error) { msg.textContent = r.error; return; }
    document.querySelector('main').innerHTML = '<h1>Signed</h1><p class="ok">Signed with your security key ' +
      'and handed back to your Desk.</p><p>You can close this window.</p>';
    if (window.opener) { window.opener.postMessage(r.message, __DESK__); setTimeout(() => window.close(), 800); }
  } catch (e) { msg.textContent = 'Security key: ' + e; }
};""".replace("__NONCE__", nonce).replace("__DESK__", json.dumps(self.desk_origin)))

    def _done(self, pend: dict, signed: dict) -> tuple[str, str]:
        csp = secrets.token_urlsafe(12)
        msg = {"type": "la-signed", "id": pend["id"], "envelope_id": signed["envelope_id"],
               "signature": signed["signature"]}
        script = (f"if (window.opener) {{ window.opener.postMessage({json.dumps(msg)}, "
                  f"{json.dumps(self.desk_origin)}); setTimeout(() => window.close(), 800); }}")
        body = ("<h1>Signed</h1><p class='ok'>Signed and handed back to your Desk.</p>"
                f"<p class='fp'>Message {html.escape(signed['envelope_id'])}</p>"
                "<p>You can close this window.</p>")
        return page(body, script, csp), csp

    def confirm_code(self, nonce: str, code: str) -> tuple[str, str]:
        pend = self.pending.get(nonce)
        if pend is None:
            return page("<h1>Not signed</h1><p class='err'>This request expired. "
                        "Press the button on your Desk again.</p>"), ""
        try:
            self.store.check_code(code, "sign")
            signed = self.store.sign_record(pend["record"], "authenticator code")
        except SignerRefused as e:
            return page(f"<h1>Not signed</h1><p class='err'>{html.escape(str(e))}</p>"
                        f"<p><a href='javascript:history.back()'>Try again</a></p>"), ""
        self.pending.pop(nonce, None)
        return self._done(pend, signed)

    # ------------------------------------------------------------ webauthn
    def key_options_for_sign(self, nonce: str) -> dict:
        from webauthn import generate_authentication_options, options_to_json
        from webauthn.helpers.structs import PublicKeyCredentialDescriptor, UserVerificationRequirement
        if nonce not in self.pending:
            return {"error": "this request expired"}
        keys = self.store.security_keys()
        if not keys:
            return {"error": "no security key is registered yet; use the code, or add a key at /keys"}
        opts = generate_authentication_options(
            rp_id=self.rp_id,
            allow_credentials=[PublicKeyCredentialDescriptor(id=_unb64u(k["id"])) for k in keys],
            user_verification=UserVerificationRequirement.PREFERRED)
        self.challenges["sign:" + nonce] = opts.challenge
        return json.loads(options_to_json(opts))

    def key_confirm_sign(self, nonce: str, credential: dict) -> dict:
        from webauthn import verify_authentication_response
        pend = self.pending.get(nonce)
        challenge = self.challenges.pop("sign:" + nonce, None)
        if pend is None or challenge is None:
            return {"error": "this request expired"}
        with self.store.lock:
            keys = self.store.security_keys()
            k = next((k for k in keys if k["id"] == credential.get("id")), None)
            if k is None:
                self.store.log.append("signer.unknown_key", {"purpose": "sign"})
                return {"error": "that security key is not registered here"}
            try:
                v = verify_authentication_response(
                    credential=credential, expected_challenge=challenge, expected_rp_id=self.rp_id,
                    expected_origin=self.signer_origin, credential_public_key=_unb64u(k["public_key"]),
                    credential_current_sign_count=int(k.get("sign_count", 0)))
            except Exception as e:
                self.store.log.append("signer.key_refused", {"purpose": "sign",
                                                             "reason": f"{type(e).__name__}: {e}"[:200]})
                return {"error": "the security key's answer did not check out"}
            k["sign_count"] = v.new_sign_count
            self.store._write(self.store.keys_path, keys)
        try:
            signed = self.store.sign_record(pend["record"], f"security key {k.get('label') or ''}".strip())
        except SignerRefused as e:
            return {"error": str(e)}
        self.pending.pop(nonce, None)
        return {"message": {"type": "la-signed", "id": pend["id"], "envelope_id": signed["envelope_id"],
                            "signature": signed["signature"]}}

    def key_options_for_register(self, code: str, label: str) -> dict:
        from webauthn import generate_registration_options, options_to_json
        from webauthn.helpers.structs import (AuthenticatorSelectionCriteria,
                                              PublicKeyCredentialDescriptor,
                                              ResidentKeyRequirement, UserVerificationRequirement)
        try:
            self.store.check_code(code, "add security key")
        except SignerRefused as e:
            return {"error": str(e)}
        account = self.store.totp().get("account", "operator")
        opts = generate_registration_options(
            rp_id=self.rp_id, rp_name="ListingAssistants signer", user_name=account,
            exclude_credentials=[PublicKeyCredentialDescriptor(id=_unb64u(k["id"]))
                                 for k in self.store.security_keys()],
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.DISCOURAGED,
                user_verification=UserVerificationRequirement.PREFERRED))
        token = secrets.token_urlsafe(18)
        self.challenges["reg:" + token] = opts.challenge
        self.pending["reg:" + token] = {"label": (label or "security key")[:40], "at": time.time()}
        return {"token": token, "options": json.loads(options_to_json(opts))}

    def key_register(self, token: str, credential: dict) -> dict:
        from webauthn import verify_registration_response
        challenge = self.challenges.pop("reg:" + token, None)
        meta = self.pending.pop("reg:" + token, None)
        if challenge is None or meta is None:
            return {"error": "this request expired"}
        try:
            v = verify_registration_response(credential=credential, expected_challenge=challenge,
                                             expected_rp_id=self.rp_id,
                                             expected_origin=self.signer_origin)
        except Exception as e:
            self.store.log.append("signer.key_refused", {"purpose": "register",
                                                         "reason": f"{type(e).__name__}: {e}"[:200]})
            return {"error": "the security key's answer did not check out"}
        with self.store.lock:
            keys = self.store.security_keys()
            keys.append({"id": _b64u(v.credential_id), "public_key": _b64u(v.credential_public_key),
                         "sign_count": v.sign_count, "label": meta["label"], "added_at": _now()})
            self.store._write(self.store.keys_path, keys)
        self.store.log.append("signer.key_added", {"label": meta["label"], "keys": len(keys)})
        return {"ok": True, "keys": len(keys)}

    def view_keys(self) -> tuple[str, str]:
        csp = secrets.token_urlsafe(12)
        body = ("<h1>Add a security key</h1>"
                "<p class='sub'>Register two: one for your keyring, one for a safe. "
                "Turn on the key's PIN if it has one.</p>"
                "<p>Code from your authenticator app:<br><input id='code' inputmode='numeric' maxlength='6'></p>"
                "<p>Name for this key: <input id='label' style='font-size:16px;letter-spacing:0;width:12em' "
                "value='keyring'></p><p><button id='add' type='button'>Add the key</button></p>"
                "<p id='msg' class='err'></p>")
        script = """
const b64u = b => btoa(String.fromCharCode(...new Uint8Array(b))).replace(/\\+/g,'-').replace(/\\//g,'_').replace(/=+$/,'');
const unb = s => Uint8Array.from(atob(s.replace(/-/g,'+').replace(/_/g,'/') + '==='.slice((s.length+3)%4)), c => c.charCodeAt(0));
document.getElementById('add').onclick = async () => {
  const msg = document.getElementById('msg');
  try {
    const o = await (await fetch('/keys/options', {method:'POST', headers:{'Content-Type':'application/json'},
       body: JSON.stringify({code: document.getElementById('code').value, label: document.getElementById('label').value})})).json();
    if (o.error) { msg.textContent = o.error; return; }
    const p = o.options; p.challenge = unb(p.challenge); p.user.id = unb(p.user.id);
    p.excludeCredentials = (p.excludeCredentials||[]).map(c => ({...c, id: unb(c.id)}));
    const c = await navigator.credentials.create({publicKey: p});
    const cred = {id: c.id, rawId: b64u(c.rawId), type: c.type, response: {
      clientDataJSON: b64u(c.response.clientDataJSON), attestationObject: b64u(c.response.attestationObject)}};
    const r = await (await fetch('/keys/register', {method:'POST', headers:{'Content-Type':'application/json'},
       body: JSON.stringify({token: o.token, credential: cred})})).json();
    if (r.error) { msg.textContent = r.error; return; }
    msg.className = 'ok'; msg.textContent = 'Added. Security keys registered: ' + r.keys;
  } catch (e) { msg.textContent = 'Security key: ' + e; }
};"""
        return page(body, script, csp), csp


def make_handler(server: SignerServer):
    allowed_hosts = {f"localhost:{server.port}", f"127.0.0.1:{server.port}"}

    class H(http.server.BaseHTTPRequestHandler):
        server_version = "la-signer"

        def log_message(self, *a):
            pass

        def _host_ok(self) -> bool:
            return (self.headers.get("Host") or "") in allowed_hosts

        def _send(self, code: int, body: str, ctype: str = "text/html; charset=utf-8",
                  csp_nonce: str = "") -> None:
            data = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "same-origin")
            script = f"'nonce-{csp_nonce}'" if csp_nonce else "'none'"
            self.send_header("Content-Security-Policy",
                             f"default-src 'none'; style-src 'unsafe-inline'; script-src {script}; "
                             f"connect-src 'self'; form-action 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def _json(self, obj: dict, code: int = 200) -> None:
            self._send(code, json.dumps(obj), "application/json")

        def _body(self) -> bytes:
            n = int(self.headers.get("Content-Length") or 0)
            if n > 256 * 1024:
                raise SignerRefused("request too large")
            return self.rfile.read(n)

        def do_GET(self):
            if not self._host_ok():
                return self._send(403, "wrong host")
            path = urllib.parse.urlsplit(self.path).path
            if path == "/":
                return self._send(200, server.view_home())
            if path == "/keys":
                pg, csp = server.view_keys()
                return self._send(200, pg, csp_nonce=csp)
            return self._send(404, "not found")

        def do_POST(self):
            if not self._host_ok():
                return self._send(403, "wrong host")
            path = urllib.parse.urlsplit(self.path).path
            origin = (self.headers.get("Origin") or "").rstrip("/")
            try:
                raw = self._body()
            except SignerRefused as e:
                return self._send(413, str(e))
            with server.store.lock:
                if path == "/sign":
                    # the Desk page posts the prepared message here; the
                    # signer shows it and asks for your code
                    if origin not in (server.desk_origin, server.signer_origin):
                        return self._send(403, "not from your Desk")
                    form = urllib.parse.parse_qs(raw.decode("utf-8"))
                    out = server.view_sign((form.get("request") or [""])[0])
                    pg, csp = out if isinstance(out, tuple) else (out, "")
                    return self._send(200, pg, csp_nonce=csp)
                if origin != server.signer_origin:
                    return self._send(403, "only the signer's own page")
                if path == "/sign/confirm":
                    form = urllib.parse.parse_qs(raw.decode("utf-8"))
                    pg, csp = server.confirm_code((form.get("nonce") or [""])[0],
                                                  (form.get("code") or [""])[0])
                    return self._send(200, pg, csp_nonce=csp)
                if (self.headers.get("Content-Type") or "").split(";")[0] != "application/json":
                    return self._send(415, "json only")
                try:
                    body = json.loads(raw or b"{}")
                except ValueError:
                    return self._json({"error": "bad json"}, 400)
                if path == "/sign/key-options":
                    return self._json(server.key_options_for_sign(str(body.get("nonce", ""))))
                if path == "/sign/key-confirm":
                    return self._json(server.key_confirm_sign(str(body.get("nonce", "")),
                                                              body.get("credential") or {}))
                if path == "/keys/options":
                    return self._json(server.key_options_for_register(str(body.get("code", "")),
                                                                      str(body.get("label", ""))))
                if path == "/keys/register":
                    return self._json(server.key_register(str(body.get("token", "")),
                                                          body.get("credential") or {}))
            return self._send(404, "not found")
    return H


# ----------------------------------------------------------------- commands
def cmd_init(folder: str, out: str, account: str) -> int:
    """Makes the key and the authenticator secret, hands over the public key
    and a signed record of what is installed. Prints the authenticator
    setup once; add it to your app now."""
    from . import totp as tp
    from .private_file import write_private
    from .signatures import Ed25519Signer
    os.makedirs(folder, exist_ok=True)
    os.makedirs(out, exist_ok=True)
    store = SignerStore(folder)
    if os.path.exists(store.key_path):
        print(json.dumps({"error": f"{store.key_path} exists; a key is never replaced silently"}))
        return 1
    signer = Ed25519Signer()
    write_private(store.key_path, signer.private_key_bytes())
    secret = tp.new_secret()
    store._write(store.totp_path, {"secret": secret, "account": account, "last_counter": -1,
                                   "failures": 0, "made_at": _now()})
    _handover(store, out)
    store.log.append("signer.initialized", {"key_fingerprint": store.fingerprint(),
                                            "account": account})
    print(json.dumps({"signer": "ready", "key_fingerprint": store.fingerprint(),
                      "public_key": os.path.join(out, "operator-public.bin"),
                      "attestation": os.path.join(out, "signer-attestation.json"),
                      "authenticator": {"add_to_your_app": tp.otpauth_uri(secret, account),
                                        "or_type_this_key": secret},
                      "note": "add the authenticator now; this setup is shown once"}))
    return 0


def _handover(store: SignerStore, out: str) -> None:
    """The only things that leave the signer: the public key, and the
    signed list of installed files (the dispatcher checks it and records it)."""
    from .boot_attest import canonical, current_manifest, fingerprint
    from .private_file import write_private
    pub = store.public_key()
    manifest = current_manifest(ROOT)
    doc = {"manifest": manifest, "signature": store.signer().sign_bytes(canonical(manifest)),
           "key_fingerprint": fingerprint(pub), "attested_on": _now()}
    write_private(os.path.join(out, "operator-public.bin"), pub)
    write_private(os.path.join(out, "signer-attestation.json"),
                  json.dumps(doc, indent=1, sort_keys=True).encode("utf-8"))
    for name in ("operator-public.bin", "signer-attestation.json"):
        os.chmod(os.path.join(out, name), 0o644)   # read by the dispatcher's user, never written


def cmd_attest(folder: str, out: str, code: Optional[str]) -> int:
    store = SignerStore(folder)
    try:
        store.check_code(code if code is not None else input("Code from your authenticator app: "),
                         "attest")
    except SignerRefused as e:
        print(json.dumps({"error": str(e)}))
        return 1
    _handover(store, out)
    store.log.append("signer.attested", {"files": len(json.load(open(
        os.path.join(out, "signer-attestation.json"), encoding="utf-8"))["manifest"])})
    print(json.dumps({"attested": os.path.join(out, "signer-attestation.json")}))
    return 0


def cmd_sign_batch(folder: str, src: str, dst: str, code: Optional[str]) -> int:
    store = SignerStore(folder)
    records = [json.loads(ln) for ln in open(src, encoding="utf-8") if ln.strip()]
    for r in records:
        rows = summary(r)
        print(" | ".join(f"{k}: {v}" for k, v in rows[:6]), file=sys.stderr)
    try:
        store.check_code(code if code is not None else input(
            f"Sign these {len(records)} message(s)? Code from your authenticator app: "), "batch")
        signed = [store.sign_record(r, "authenticator code (batch)") for r in records]
    except SignerRefused as e:
        print(json.dumps({"error": str(e), "signed": 0}))
        return 1
    with open(dst, "w", encoding="utf-8") as f:
        for s in signed:
            f.write(json.dumps(s) + "\n")
    print(json.dumps({"signed": len(signed), "out": dst}))
    return 0


def cmd_serve(folder: str, port: int) -> int:
    store = SignerStore(folder)
    store.totp()                                   # refuse to start without the second factor
    signer_origin = os.environ.get("LISTINGASSISTANTS_SIGNER_ORIGIN", f"http://localhost:{port}")
    desk_origin = os.environ.get("LISTINGASSISTANTS_DESK_ORIGIN", "http://127.0.0.1:8765")
    server = SignerServer(store, signer_origin, desk_origin)
    if server.port is None:
        server.port = port
    host = "0.0.0.0" if os.environ.get("LISTINGASSISTANTS_IN_CONTAINER") == "1" else "127.0.0.1"
    httpd = http.server.ThreadingHTTPServer((host, port), make_handler(server))
    print(json.dumps({"signer": f"{signer_origin}/", "key_fingerprint": store.fingerprint(),
                      "desk": desk_origin}), flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def main(argv=None) -> int:
    import argparse
    if os.name != "nt":
        os.umask(0o077)
    ap = argparse.ArgumentParser(description="The operator's signer")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("init", "serve", "sign-batch", "attest"):
        p = sub.add_parser(name)
        p.add_argument("--dir", required=True)
        if name in ("init", "attest"):
            p.add_argument("--out", required=True)
        if name == "init":
            p.add_argument("--account", required=True)
        if name == "serve":
            p.add_argument("--port", type=int, default=8767)
        if name == "sign-batch":
            p.add_argument("--in", dest="src", required=True)
            p.add_argument("--out", dest="dst", required=True)
        if name in ("sign-batch", "attest"):
            p.add_argument("--code", default=None, help="the authenticator code (else asked)")
    a = ap.parse_args(argv)
    if a.cmd == "init":
        return cmd_init(a.dir, a.out, a.account)
    if a.cmd == "serve":
        return cmd_serve(a.dir, a.port)
    if a.cmd == "sign-batch":
        return cmd_sign_batch(a.dir, a.src, a.dst, a.code)
    return cmd_attest(a.dir, a.out, a.code)


if __name__ == "__main__":
    sys.exit(main())
