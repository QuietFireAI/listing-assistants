"""Agent isolation V1 in real containers (owner decisions 2026-10-26).

The compose file is generated (tools/gen_compose.py); the first test checks
the committed one matches. The rest build the image and run the whole
setup with Docker: they run only when LA_DOCKER_TESTS=1 (the CI job
linux-containers sets it), because they need a Docker engine and take
minutes.

What they prove, each with the real containers:
  - playbook P01 runs start to end with every agent in its own container
  - an agent container has no network, no capabilities, a read-only disk
    and only its own line; the dispatcher has no internet
  - your browser reaches the Desk through the desk door on 127.0.0.1 only
  - a rogue program on agent 20's line is refused and stopped, and the
    alert goes to the alert door (which, with no Twilio details, says so
    on the record)
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
COMPOSE = os.path.join(ROOT, "docker", "compose.yml")
PROJECT = "la-ctest"
IMAGE = "listingassistants:local"


def test_the_compose_file_is_the_generated_one():
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "gen_compose.py"), "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def _blocks():
    """service name -> its lines in docker/compose.yml (the file is generated,
    so plain text is enough; no YAML library is needed)."""
    import re
    text = open(COMPOSE, encoding="utf-8").read()
    services = text.split("\nservices:\n", 1)[1].split("\nnetworks:\n", 1)[0]
    out, current = {}, None
    for ln in services.splitlines():
        m = re.match(r"^  ([a-z0-9-]+):$", ln)
        if m:
            current = out.setdefault(m.group(1), [])
        elif ln.startswith("    ") and current is not None:
            current.append(ln.strip())
    return out, text


def test_every_agent_is_locked_down_in_the_compose_file():
    blocks, text = _blocks()
    agents = {k: v for k, v in blocks.items() if k.startswith("agent-")}
    assert sorted(agents) == [f"agent-{i:02d}" for i in range(1, 21)]
    for name, lines in agents.items():
        aid = name.split("-")[1]
        for must in ("network_mode: none", "read_only: true", "cap_drop: [ALL]",
                     'security_opt: ["no-new-privileges:true"]', 'user: "10001:10001"',
                     f"- portal-{aid}:/line:ro"):
            assert must in lines, (name, must)
        assert [ln for ln in lines if ln.startswith("- ")] == [f"- portal-{aid}:/line:ro"]
    disp = blocks["dispatcher"]
    assert "networks: [inside]" in disp and not [ln for ln in disp if ln.startswith("ports")]
    assert "  inside:\n    internal: true" in text
    assert 'ports: ["127.0.0.1:8765:8765"]' in blocks["desk-door"]
    assert "networks: [outside]" in blocks["alert-door"]
    # the key's room: on its own closed network, never shared with the dispatcher
    assert "networks: [signing]" in blocks["signer"]
    assert "  signing:\n    internal: true" in text
    assert not [ln for ln in disp if "signer-state" in ln]
    assert "- signer-out:/signer-out:ro" in disp
    assert 'ports: ["127.0.0.1:8767:8767"]' in blocks["signer-door"]


needs_docker = pytest.mark.skipif(os.environ.get("LA_DOCKER_TESTS") != "1",
                                  reason="set LA_DOCKER_TESTS=1 to run the container tests")


def _run(*args, check=True, timeout=900, **kw):
    r = subprocess.run(list(args), capture_output=True, text=True, timeout=timeout, cwd=ROOT, **kw)
    if check and r.returncode != 0:
        raise AssertionError(f"{' '.join(args)} failed:\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}")
    return r


def _compose(*args, **kw):
    return _run("docker", "compose", "-p", PROJECT, "-f", COMPOSE, *args, **kw)


def _in(container, code):
    # an agent's container restarts when a dispatcher session ends (its line
    # closes); wait for it to be running again
    for _ in range(60):
        r = _run("docker", "exec", f"{PROJECT}-{container}-1", "python", "-c", code, check=False)
        if r.returncode == 0 or "is restarting" not in r.stderr:
            break
        time.sleep(1)
    if r.returncode != 0:
        raise AssertionError(r.stdout[-2000:] + r.stderr[-2000:])
    return r.stdout


def _record():
    out = _run("docker", "run", "--rm", "--user", "10001", "-v", f"{PROJECT}_state:/state:ro",
               IMAGE, "cat", "/state/console-audit.jsonl").stdout
    return [json.loads(ln) for ln in out.splitlines() if ln.strip()]


@pytest.fixture(scope="module")
def stack():
    build = ["docker", "build", "-f", "docker/Dockerfile", "-t", IMAGE]
    if os.environ.get("LA_DOCKER_BUILD_CA"):            # a proxy's certificate, build time only
        build += ["--secret", f"id=ca,src={os.environ['LA_DOCKER_BUILD_CA']}"]
    _run(*build, ".", timeout=1800)
    _compose("down", "-v", check=False)
    # the key is made in the signer and never leaves it; the dispatcher
    # gets the public key and the signed list of installed files
    _compose("run", "--rm", "signer", "python", "-m", "dispatcher.signer_service", "init",
             "--dir", "/signer", "--out", "/out", "--account", "broker@example.test")
    _compose("run", "--rm", "dispatcher", "python", "tools/console.py", "init",
             "--from-signer", "/signer-out")
    agents = [f"agent-{i:02d}" for i in range(1, 21)]
    _compose("up", "-d", *agents, "alert-door")
    _compose("run", "--rm", "dispatcher", "python", "tools/console.py", "onboard",
             "--name", "Container Broker", "--login", "broker@example.test")
    scripts = tempfile.mkdtemp(prefix="la-cscripts-")
    os.chmod(scripts, 0o777)        # the containers write the prepared and signed files here
    yield scripts
    _compose("down", "-v", check=False)


def _code():
    from dispatcher import totp
    secret = json.loads(_run("docker", "run", "--rm", "--user", "10001", "-v",
                             f"{PROJECT}_signer-state:/signer:ro", IMAGE, "cat",
                             "/signer/totp.json").stdout)["secret"]
    return totp.code_at(secret, totp.counter_now())


def _session(scripts, name, lines, sign=False):
    path = os.path.join(scripts, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(json.dumps(x) if not isinstance(x, str) else x for x in lines) + "\n")
    os.chmod(path, 0o644)
    signed = []
    if sign:
        # what the script asks you to sign, signed in a batch on the signer
        # with your code; the dispatcher never sees the key
        _compose("run", "--rm", "-v", f"{scripts}:/run-scripts", "dispatcher", "python",
                 "tools/console.py", "prepare", f"/run-scripts/{name}",
                 "--out", f"/run-scripts/{name}.unsigned")
        _compose("run", "--rm", "-v", f"{scripts}:/run-scripts", "signer", "python", "-m",
                 "dispatcher.signer_service", "sign-batch", "--dir", "/signer",
                 "--in", f"/run-scripts/{name}.unsigned", "--out", f"/run-scripts/{name}.signed",
                 "--code", _code())
        signed = ["--signed", f"/run-scripts/{name}.signed"]
    r = _compose("run", "--rm", "-v", f"{scripts}:/run-scripts:ro", "dispatcher", "python",
                 "tools/console.py", "session", f"/run-scripts/{name}",
                 "--config-dir", "synth/tuples/config", *signed)
    last = json.loads(r.stdout.strip().splitlines()[-1])
    assert last.get("session_complete"), r.stdout[-2000:]
    return r.stdout


@needs_docker
def test_a_playbook_runs_with_every_agent_in_its_own_container(stack):
    """P01 up to the photographer booking, which waits for your signed
    release (that release is signed on the Desk through the signer's page:
    tests_isolation/test_signer.py drives it in a browser)."""
    sys.path.insert(0, os.path.join(ROOT, "synth", "tuples"))
    sys.path.insert(0, ROOT)
    import run_tuples
    [spec] = run_tuples.load_specs(["P01"], spec_set="playbooks")
    lines = run_tuples.session_lines(spec)
    upto = next(i for i, ln in enumerate(lines) if json.loads(ln).get("do") == "release")
    _session(stack, "P01.jsonl", lines[:upto], sign=True)
    entries = _record()
    held = [e for e in entries if e["kind"] == "absolute_signal.hold"]
    assert held and held[0]["intent"] == "vendor.schedule", [e["kind"] for e in entries][-30:]
    assert len([e for e in entries if e["kind"] == "envelope.persisted"
                and e.get("from_agent") == "human"]) >= 1
    assert not [e for e in entries if e["kind"] == "reject"]
    assert [e for e in entries if e["kind"] == "portal.team"]
    assert not [e for e in entries if e["kind"] in ("portal.violation", "portal.agent_stopped")]


@needs_docker
def test_the_key_is_only_in_the_signer(stack):
    listing = _run("docker", "run", "--rm", "--user", "10001", "-v", f"{PROJECT}_state:/state:ro",
                   IMAGE, "ls", "/state").stdout.split()
    assert "operator-key.bin" not in listing and "operator-public.bin" in listing
    signer_files = _run("docker", "run", "--rm", "--user", "10001", "-v",
                        f"{PROJECT}_signer-state:/signer:ro", IMAGE, "ls", "/signer").stdout.split()
    assert "operator-key.bin" in signer_files and "totp.json" in signer_files
    _compose("up", "-d", "dispatcher", "signer", "signer-door")
    try:
        page = None
        for _ in range(60):
            try:
                req = urllib.request.Request("http://127.0.0.1:8767/", headers={"Host": "localhost:8767"})
                page = urllib.request.urlopen(req, timeout=3).read().decode()
                break
            except OSError:
                time.sleep(2)
        assert page and "Your signer" in page
        out = _in("dispatcher", """
import socket
for host in ("signer", "signer-door"):
    try:
        socket.create_connection((host, 8767), 4); print(host, "REACHED")
    except OSError as e: print(host, "unreachable")
""")
        assert "REACHED" not in out, out
    finally:
        _compose("stop", "dispatcher", "signer", "signer-door")


@needs_docker
def test_an_agent_container_reaches_nothing(stack):
    out = _in("agent-05", """
import os, socket
try:
    socket.create_connection(("1.1.1.1", 53), 3); print("NET")
except OSError: print("no-net")
print("ifaces", sorted(os.listdir("/sys/class/net")))
print("uid", os.getuid())
print([l.split()[1] for l in open("/proc/self/status") if l.startswith("CapEff")][0])
print("others", [d for d in os.listdir("/portal") if os.listdir("/portal/" + d)])
for p in ("/app/x", "/line/x"):
    try: open(p, "w"); print("WROTE", p)
    except OSError: print("ro", p)
""")
    assert "no-net" in out and "ifaces ['lo']" in out and "uid 10001" in out
    assert "0000000000000000" in out and "others []" in out
    assert "WROTE" not in out


@needs_docker
def test_the_desk_is_reached_through_the_desk_door_only(stack):
    _compose("up", "-d", "dispatcher", "desk-door")
    try:
        state = None
        for _ in range(90):
            try:
                state = json.load(urllib.request.urlopen("http://127.0.0.1:8765/api/state", timeout=3))
                break
            except OSError:
                time.sleep(2)
        assert state and state["mode"] == "live" and state["operator"]["login"] == "broker@example.test"
        out = _in("dispatcher", """
import socket
try:
    socket.create_connection(("1.1.1.1", 443), 4); print("REACHED")
except OSError: print("blocked")
""")
        assert "blocked" in out
    finally:
        _compose("stop", "dispatcher", "desk-door")


ROGUE = r'''
import sys
sys.path.insert(0, "/app")
from dispatcher.core import Envelope
from dispatcher.portal import DISPATCHER_TO_AGENT, Peer, PortalError
from dispatcher.portal_agent import connect
peer = Peer(connect("/line/portal.sock", float("inf")), {}, DISPATCHER_TO_AGENT, name="rogue 20")
def deliver(envelope):
    peer.call("send", {"envelope": Envelope(from_agent="13", to_agent="02", intent="lead.captured",
              client_context_id="X", payload={}, provenance={"source": "13", "captured_at": "runtime"})})
    return {"result": None, "tick_results": [], "state": None}
peer.handlers = {"init": lambda agent_id, kwargs: {"registered": ["20"], "resumers": [], "state": {}},
                 "deliver": deliver, "state": lambda: {},
                 "restore": lambda attrs: {"restored": [], "state": None}}
try:
    peer.serve_forever()
except PortalError:
    pass
'''


@needs_docker
def test_a_rogue_agent_container_is_stopped_and_the_alert_door_is_asked(stack):
    _compose("stop", "agent-20")
    with open(os.path.join(stack, "rogue.py"), "w", encoding="utf-8") as f:
        f.write(ROGUE)
    os.chmod(os.path.join(stack, "rogue.py"), 0o644)
    _run("docker", "rm", "-f", "la-ctest-rogue", check=False)
    _run("docker", "run", "-d", "--name", "la-ctest-rogue", "--network", "none", "--read-only",
         "--user", "10001:10001", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
         "--tmpfs", "/tmp", "-v", f"{PROJECT}_portal-20:/line:ro", "-v", f"{stack}:/rogue:ro",
         IMAGE, "python", "/rogue/rogue.py")
    try:
        mention = {"do": "send", "from": "external", "to": "20", "intent": "social.mention",
                   "payload": {"channel": "social", "text": "nice house"}}
        out = _session(stack, "rogue.jsonl", [{**mention, "ctx": "M-1"}, {**mention, "ctx": "M-2"}])
        assert '"portal.violation"' in out
        entries = _record()
        [v] = [e for e in entries if e["kind"] == "portal.violation"]
        assert v["agent"] == "20" and v["violation"] == "impersonation"
        pages = [e for e in entries if e["kind"] == "pager.failed" and e.get("via") == "alert door"]
        assert pages and pages[0]["error"] == "no pager set up in the alert door"
        dead = [e for e in entries if e["kind"] == "dead.letter" and "stopped" in str(e.get("reason"))]
        assert dead
    finally:
        _run("docker", "rm", "-f", "la-ctest-rogue", check=False)
