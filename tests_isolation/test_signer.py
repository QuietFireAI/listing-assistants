"""The signer in a room of its own, with two-factor (owner decisions
2026-10-26). The dispatcher holds the public key only; every signature is
made by the signer after the code from an authenticator app or a touch of
a security key, on the signer's own page.

Real pieces throughout: the signer's commands and its web page, the
console with no key in its state folder, the Broker Desk, and, for the
browser flows, Chromium driven by Playwright with a virtual security key
(Chrome's WebAuthn test authenticator) standing in for a YubiKey.
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import pytest

if os.name == "nt":
    pytest.skip("the signer runs in its own Linux container", allow_module_level=True)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests_listing"))
sys.path.insert(0, os.path.join(ROOT, "synth", "tuples"))

from dispatcher import totp  # noqa: E402
from dispatcher.core import Envelope  # noqa: E402
from dispatcher.remote_signer import NeedsSignature, RemoteSigner  # noqa: E402
from dispatcher.signer_service import (SignerRefused, SignerServer, SignerStore,  # noqa: E402
                                       make_handler)


# ----------------------------------------------------------------- the code
def test_authenticator_codes_match_rfc_6238():
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"          # "12345678901234567890"
    assert totp.code_at(secret, 59 // 30) == "287082"
    assert totp.code_at(secret, 1111111109 // 30) == "081804"
    assert totp.code_at(secret, 1234567890 // 30) == "005924"


def test_a_code_works_once_and_only_near_now():
    s = totp.new_secret()
    t = 1_800_000_000.0
    c = totp.code_at(s, totp.counter_now(t))
    step = totp.verify(s, c, -1, t)
    assert step == totp.counter_now(t)
    assert totp.verify(s, c, step, t) is None                       # used once
    assert totp.verify(s, totp.code_at(s, totp.counter_now(t) - 5), -1, t) is None   # too old
    assert totp.verify(s, "12345", -1, t) is None and totp.verify(s, "abcdef", -1, t) is None


def _signer(tmp):
    folder, out = os.path.join(tmp, "signer"), os.path.join(tmp, "out")
    r = subprocess.run([sys.executable, "-m", "dispatcher.signer_service", "init", "--dir", folder,
                        "--out", out, "--account", "jeff@example.test"],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    info = json.loads(r.stdout)
    secret = json.load(open(os.path.join(folder, "totp.json")))["secret"]
    assert info["authenticator"]["or_type_this_key"] == secret
    return folder, out, secret


def _code(secret, ahead=0):
    return totp.code_at(secret, totp.counter_now() + ahead)


def test_five_wrong_codes_lock_the_signer(tmp_path):
    folder, _, secret = _signer(str(tmp_path))
    store = SignerStore(folder)
    for _ in range(4):
        with pytest.raises(SignerRefused, match="not right"):
            store.check_code("000000" if _code(secret) != "000000" else "111111", "test")
    with pytest.raises(SignerRefused, match="locked"):
        store.check_code("000000" if _code(secret) != "000000" else "111111", "test")
    with pytest.raises(SignerRefused, match="locked"):
        store.check_code(_code(secret), "test")                   # even the right one, for 15 min
    kinds = [e["kind"] for e in store.log.read()]
    assert kinds.count("signer.wrong_code") == 4 and "signer.locked" in kinds


def test_the_signer_signs_only_your_authority_messages(tmp_path):
    folder, _, _ = _signer(str(tmp_path))
    store = SignerStore(folder)
    base = {"envelope_id": "e1", "to_agent": "05", "client_context_id": "L1", "payload": {},
            "provenance": {"source": "human", "captured_at": "runtime"}}
    with pytest.raises(SignerRefused, match="only messages from you"):
        store.check_request({**base, "from_agent": "05", "intent": "config.update"})
    with pytest.raises(SignerRefused, match="does not need your signature|not something"):
        store.check_request({**base, "from_agent": "human", "intent": "lead.inbound"})
    assert store.check_request({**base, "from_agent": "human", "intent": "config.update"})


def test_the_dispatcher_side_has_no_key_and_checks_every_signature(tmp_path):
    folder, out, secret = _signer(str(tmp_path))
    pub = open(os.path.join(out, "operator-public.bin"), "rb").read()
    rs = RemoteSigner(pub)
    env = Envelope(from_agent="human", to_agent="17", intent="config.update", client_context_id="setup",
                   payload={"brokerage_identification": "Test"},
                   provenance={"source": "human", "captured_at": "runtime"})
    with pytest.raises(NeedsSignature):
        rs.sign(env)
    store = SignerStore(folder)
    store.check_code(_code(secret), "test")
    signed = store.sign_record(env.to_record(), "test")
    with pytest.raises(ValueError):
        rs.supply({**signed, "payload": {"brokerage_identification": "Changed"}})
    rs.supply(signed)
    again = Envelope(from_agent="human", to_agent="17", intent="config.update", client_context_id="setup",
                     payload={"brokerage_identification": "Test"},
                     provenance={"source": "human", "captured_at": "later"})
    rs.sign(again)
    assert again.envelope_id == env.envelope_id and again.signature == signed["signature"]
    with pytest.raises(NeedsSignature):
        rs.sign(again)                                           # one signature, one use
    with pytest.raises(RuntimeError):
        rs.sign_bytes(b"anything")


# ----------------------------------------------------------------- the page
def _serve(folder, desk_origin):
    from test_desk import free_port
    import http.server
    port = free_port()
    server = SignerServer(SignerStore(folder), f"http://localhost:{port}", desk_origin)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), make_handler(server))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, port


def _post(url, data, headers):
    req = urllib.request.Request(url, data=data, method="POST", headers=headers)
    try:
        r = urllib.request.urlopen(req)
        return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def test_the_signers_page_shows_the_message_and_signs_after_the_code(tmp_path):
    folder, out, secret = _signer(str(tmp_path))
    httpd, port = _serve(folder, "http://127.0.0.1:9999")
    try:
        env = Envelope(from_agent="human", to_agent="09", intent="disclosure.authority",
                       client_context_id="L1", payload={"held_envelope_id": "abc"},
                       provenance={"source": "human", "captured_at": "runtime"})
        req = urllib.parse.urlencode({"request": json.dumps({"id": "r1", "envelope": env.to_record()})}).encode()
        form = {"Content-Type": "application/x-www-form-urlencoded", "Host": f"localhost:{port}"}
        code, _ = _post(f"http://127.0.0.1:{port}/sign", req, {**form, "Origin": "http://evil.test"})
        assert code == 403
        code, page = _post(f"http://127.0.0.1:{port}/sign", req, {**form, "Origin": "http://127.0.0.1:9999"})
        assert code == 200 and "Send a held message" in page and "Agent 09" in page
        nonce = page.split("name='nonce' value='")[1].split("'")[0]
        mine = {**form, "Origin": f"http://localhost:{port}"}
        code, page = _post(f"http://127.0.0.1:{port}/sign/confirm",
                           urllib.parse.urlencode({"nonce": nonce, "code": "000000"}).encode(), mine)
        assert "Not signed" in page
        code, page = _post(f"http://127.0.0.1:{port}/sign/confirm",
                           urllib.parse.urlencode({"nonce": nonce, "code": _code(secret)}).encode(), mine)
        assert "Signed" in page and "postMessage" in page and '"http://127.0.0.1:9999"' in page
        sig = page.split('"signature": "')[1].split('"')[0]
        from dispatcher.signatures import Ed25519Verifier, _canonical
        pub = open(os.path.join(out, "operator-public.bin"), "rb").read()
        assert Ed25519Verifier(pub).verify_bytes(_canonical(env), sig)
        code, _ = _post(f"http://127.0.0.1:{port}/sign", req,
                        {**form, "Origin": "http://127.0.0.1:9999", "Host": "evil.test"})
        assert code == 403                                       # another host name: refused
    finally:
        httpd.shutdown()


# ----------------------------------------------------------------- a whole run

def _office(tmp):
    """A broker's office with the key in the signer: the signer made, the
    state folder holding only the public key, playbook P01 run up to the
    photographer booking that waits for the broker's signed release."""
    import run_tuples
    folder, out, secret = _signer(tmp)
    state = os.path.join(tmp, "state")
    env = {**os.environ, "LISTINGASSISTANTS_STATE_DIR": state}
    env.pop("LISTINGASSISTANTS_PORTAL", None)

    def console(*a):
        r = subprocess.run([sys.executable, "tools/console.py", *a], cwd=ROOT, env=env,
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
        return r.stdout
    console("init", "--from-signer", out)
    console("onboard", "--name", "Jeff", "--login", "jeff@example.test")
    assert not os.path.exists(os.path.join(state, "operator-key.bin"))
    [spec] = run_tuples.load_specs(["P01"], spec_set="playbooks")
    lines = run_tuples.session_lines(spec)
    release_at = next(i for i, ln in enumerate(lines) if json.loads(ln).get("do") == "release")
    script = os.path.join(tmp, "p01-to-booking.jsonl")
    open(script, "w").write("\n".join(lines[:release_at]) + "\n")
    rest = os.path.join(tmp, "p01-rest.jsonl")
    open(rest, "w").write("\n".join(lines[release_at + 1:]) + "\n")
    unsigned, signed = os.path.join(tmp, "unsigned.jsonl"), os.path.join(tmp, "signed.jsonl")
    console("prepare", script, "--out", unsigned)
    r = subprocess.run([sys.executable, "-m", "dispatcher.signer_service", "sign-batch", "--dir", folder,
                        "--in", unsigned, "--out", signed, "--code", _code(secret)],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    console("session", script, "--config-dir", "synth/tuples/config", "--signed", signed)
    return {"folder": folder, "secret": secret, "state": state, "env": env, "rest": rest,
            "spec": spec, "console": console}


def test_a_session_without_its_signatures_is_refused_line_by_line(tmp_path):
    folder, out, _ = _signer(str(tmp_path))
    state = str(tmp_path / "state")
    env = {**os.environ, "LISTINGASSISTANTS_STATE_DIR": state}
    subprocess.run([sys.executable, "tools/console.py", "init", "--from-signer", out], cwd=ROOT, env=env,
                   check=True, capture_output=True)
    script = tmp_path / "s.jsonl"
    script.write_text(json.dumps({"do": "config", "to": "17", "ctx": "setup",
                                  "payload": {"brokerage_identification": "X"}}) + "\n")
    r = subprocess.run([sys.executable, "tools/console.py", "session", str(script)], cwd=ROOT, env=env,
                       capture_output=True, text=True)
    assert "needs your signature on the signer" in r.stdout
    log = [json.loads(ln) for ln in open(os.path.join(state, "console-audit.jsonl"))]
    assert not [e for e in log if e["kind"] == "envelope.persisted" and e.get("intent") == "config.update"]


def _browser_release(tmp, use_key):
    pw = pytest.importorskip("playwright.sync_api")
    from test_desk import free_port, start, stop
    office = _office(tmp)
    sport = free_port()
    old = {k: os.environ.get(k) for k in ("LISTINGASSISTANTS_SIGNER_URL",)}
    os.environ["LISTINGASSISTANTS_SIGNER_URL"] = f"http://localhost:{sport}"
    try:
        p, url, port = start([], office["state"])
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    signer = subprocess.Popen(
        [sys.executable, "-m", "dispatcher.signer_service", "serve", "--dir", office["folder"],
         "--port", str(sport)], cwd=ROOT,
        env={**os.environ, "LISTINGASSISTANTS_SIGNER_ORIGIN": f"http://localhost:{sport}",
             "LISTINGASSISTANTS_DESK_ORIGIN": f"http://127.0.0.1:{port}"},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    signer.stdout.readline()
    try:
        with pw.sync_playwright() as play:
            browser = play.chromium.launch()
            page = browser.new_page()
            page.goto(url)
            page.get_by_role("button", name="Send", exact=True).first.click()
            with page.expect_popup() as pop:
                page.get_by_role("button", name="Tap again to sign and send").click()
            popup = pop.value
            popup.wait_for_selector("text=Sign this?")
            assert popup.locator("text=Send a held message").count() == 1
            if use_key:
                cdp = popup.context.new_cdp_session(popup)
                cdp.send("WebAuthn.enable")
                cdp.send("WebAuthn.addVirtualAuthenticator", {"options": {
                    "protocol": "ctap2", "transport": "usb", "hasResidentKey": False,
                    "hasUserVerification": True, "isUserVerified": True}})
                # adding a key needs the code; then the key alone signs
                added = popup.evaluate("""async (code) => {
                  const b64u = b => btoa(String.fromCharCode(...new Uint8Array(b))).replace(/\\+/g,'-').replace(/\\//g,'_').replace(/=+$/,'');
                  const unb = s => Uint8Array.from(atob(s.replace(/-/g,'+').replace(/_/g,'/') + '==='.slice((s.length+3)%4)), c => c.charCodeAt(0));
                  const o = await (await fetch('/keys/options', {method:'POST', headers:{'Content-Type':'application/json'},
                     body: JSON.stringify({code, label: 'keyring'})})).json();
                  if (o.error) return o;
                  const p = o.options; p.challenge = unb(p.challenge); p.user.id = unb(p.user.id);
                  p.excludeCredentials = [];
                  const c = await navigator.credentials.create({publicKey: p});
                  const cred = {id: c.id, rawId: b64u(c.rawId), type: c.type, response: {
                    clientDataJSON: b64u(c.response.clientDataJSON), attestationObject: b64u(c.response.attestationObject)}};
                  return await (await fetch('/keys/register', {method:'POST', headers:{'Content-Type':'application/json'},
                     body: JSON.stringify({token: o.token, credential: cred})})).json();
                }""", _code(office["secret"], 1))
                assert added.get("ok") is True, added
                popup.get_by_role("button", name="Use my security key").click()
            else:
                popup.fill("input[name=code]", _code(office["secret"], 1))
                popup.get_by_role("button", name="Sign", exact=True).click()
            deadline = time.time() + 20
            while time.time() < deadline:
                s = json.load(urllib.request.urlopen(url + "api/state"))
                if not [i for i in s["needs_you"] if i["type"] == "held"]:
                    break
                time.sleep(0.5)
            browser.close()
        assert not [i for i in s["needs_you"] if i["type"] == "held"], s["needs_you"]
    finally:
        stop(p)
        signer.terminate()
        signer.wait(timeout=10)
    log = [json.loads(ln) for ln in open(os.path.join(office["state"], "console-audit.jsonl"))]
    released = [e for e in log if e["kind"] == "absolute_signal.released"]
    assert released and released[0]["intent"] == "vendor.schedule"
    signed = [e for e in SignerStore(office["folder"]).log.read() if e["kind"] == "signer.signed"]
    return office, signed, log


def test_release_on_the_desk_signed_with_the_authenticator_code(tmp_path):
    office, signed, _ = _browser_release(str(tmp_path), use_key=False)
    assert signed[-1]["intent"] == "disclosure.authority" and signed[-1]["factor"] == "authenticator code"
    # and the playbook finishes from there
    office["console"]("session", office["rest"], "--config-dir", "synth/tuples/config")
    import run_tuples
    log = [json.loads(ln) for ln in open(os.path.join(office["state"], "console-audit.jsonl"))]
    idx = run_tuples.ctx_index(log)
    assert [c for c in office["spec"]["expect"] if not run_tuples.check(log, idx, c)[0]] == []


def test_release_on_the_desk_signed_with_a_security_key(tmp_path):
    office, signed, _ = _browser_release(str(tmp_path), use_key=True)
    assert signed[-1]["intent"] == "disclosure.authority"
    assert signed[-1]["factor"].startswith("security key")
    kinds = [e["kind"] for e in SignerStore(office["folder"]).log.read()]
    assert "signer.key_added" in kinds
