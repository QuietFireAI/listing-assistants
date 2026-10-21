"""The Broker Desk answers only its own page (2026-10-14, integration
snapshot finding 1).

Before: in local mode the desk had no check at all. Measured on main
9b45334: a request with Host: attacker.example got 200 on /api/state, and a
POST with a foreign Origin and Content-Type text/plain reached the action
handler - so a web page the broker visited could, by DNS rebinding, read the
desk and post actions the desk signs with the broker's key.

Now: local mode answers only a request addressed to this machine by name;
an action must come from the desk's own page (Origin) and be JSON; the LAN
desk needs its access code, compared in constant time.

And the state folder is private (finding 2): new files are created 0600 and
folders 0700 on Linux / macOS, and a folder an earlier version left readable
is tightened when a program opens it.
"""
import http.client
import http.server
import json
import os
import stat
import sys
import threading

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)

import desk as desk_mod  # noqa: E402
from dispatcher.private_file import tighten_tree  # noqa: E402

WINDOWS = os.name == "nt"


class FakeDesk:
    """Stands in for the swarm: records what reached it."""

    def __init__(self):
        self.acted = []
        self.reads = 0

    def state(self, day=None):
        self.reads += 1
        return {"ok": True}

    def act(self, body):
        self.acted.append(body)
        return {"ok": True}


@pytest.fixture
def served():
    started = []

    def start(token=None, lan=False):
        fake = FakeDesk()
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0),
                                              desk_mod.make_handler(fake, token, lan=lan))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        started.append(srv)
        return fake, srv.server_address[1]

    yield start
    for srv in started:
        srv.shutdown()
        srv.server_close()


def call(port, method, path, host=None, headers=None, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    h = {"Host": host or f"127.0.0.1:{port}"}
    h.update(headers or {})
    conn.request(method, path, body=body, headers=h)
    r = conn.getresponse()
    data = r.read()
    conn.close()
    return r.status, (json.loads(data) if data[:1] in (b"{", b"[") else data)


ACT = json.dumps({"action": "ack", "id": "x", "title": "t"})
JSON = {"Content-Type": "application/json"}


# ------------------------------------------------------------- local mode
def test_a_rebinding_host_name_cannot_read_the_desk(served):
    fake, port = served()
    for path in ("/", "/api/state"):
        code, body = call(port, "GET", path, host=f"attacker.example:{port}")
        assert code == 403, path
        assert "its own address" in body["error"]
    assert fake.reads == 0


def test_a_rebinding_host_name_cannot_act(served):
    fake, port = served()
    code, _ = call(port, "POST", "/api/act", host=f"attacker.example:{port}",
                   headers=JSON, body=ACT)
    assert code == 403 and fake.acted == []


def test_another_site_cannot_post_an_action(served):
    fake, port = served()
    # the exact request measured on 9b45334: a simple cross-site POST
    code, body = call(port, "POST", "/api/act",
                      headers={"Origin": "https://attacker.example", "Content-Type": "text/plain"},
                      body=ACT)
    assert code == 403 and "own page" in body["error"]
    # JSON with a foreign Origin is refused too
    code, _ = call(port, "POST", "/api/act",
                   headers={"Origin": "https://attacker.example", **JSON}, body=ACT)
    assert code == 403
    # a sandboxed page sends Origin: null
    code, _ = call(port, "POST", "/api/act", headers={"Origin": "null", **JSON}, body=ACT)
    assert code == 403
    assert fake.acted == []


def test_an_action_must_be_json(served):
    fake, port = served()
    for ctype in ("text/plain", "application/x-www-form-urlencoded", "multipart/form-data"):
        code, _ = call(port, "POST", "/api/act", headers={"Content-Type": ctype}, body=ACT)
        assert code == 415, ctype
    code, _ = call(port, "POST", "/api/act", body=ACT)      # no content type at all
    assert code == 415
    assert fake.acted == []


def test_the_desks_own_page_still_works(served):
    fake, port = served()
    code, page = call(port, "GET", "/")
    assert code == 200 and b"<html" in page.lower()
    assert call(port, "GET", "/api/state")[0] == 200
    for host in (f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}", f"LOCALHOST:{port}"):
        code, _ = call(port, "POST", "/api/act", host=host,
                       headers={"Origin": f"http://{host}", **JSON}, body=ACT)
        assert code == 200, host
    # a client that is not a browser page (no Origin) - curl, the console's tests
    assert call(port, "POST", "/api/act", headers=JSON, body=ACT)[0] == 200
    assert len(fake.acted) == 5


def test_a_malformed_host_header_is_refused_not_a_crash(served):
    fake, port = served()
    code, _ = call(port, "GET", "/api/state", host="[::1")
    assert code == 403 and fake.reads == 0


def test_the_font_needs_no_address_check(served):
    """The font carries no data; a tablet's browser asks for it without a code."""
    _, port = served()
    name = sorted(desk_mod.FONT_FILES)[0]
    assert call(port, "GET", f"/fonts/{name}", host="anything.example")[0] == 200


# ------------------------------------------------------------- network mode
def test_the_network_desk_needs_its_code(served):
    fake, port = served(token="s3cret-code", lan=True)
    lan_host = f"192.168.1.20:{port}"
    assert call(port, "GET", "/api/state", host=lan_host)[0] == 403
    assert call(port, "GET", "/api/state?t=wrong", host=lan_host)[0] == 403
    assert call(port, "GET", "/api/state", host=lan_host,
                headers={"X-Desk-Token": "s3cret-cod"})[0] == 403
    assert call(port, "GET", "/api/state?t=s3cret-code", host=lan_host)[0] == 200
    assert call(port, "GET", "/api/state", host=lan_host,
                headers={"X-Desk-Token": "s3cret-code"})[0] == 200
    # with the code, an action still has to come from the desk's own page
    code, _ = call(port, "POST", "/api/act", host=lan_host,
                   headers={"X-Desk-Token": "s3cret-code", "Origin": "http://evil.example", **JSON},
                   body=ACT)
    assert code == 403
    code, _ = call(port, "POST", "/api/act", host=lan_host,
                   headers={"X-Desk-Token": "s3cret-code", "Origin": f"http://{lan_host}", **JSON},
                   body=ACT)
    assert code == 200 and len(fake.acted) == 1


def test_the_network_desk_cannot_be_built_without_a_code():
    with pytest.raises(ValueError):
        desk_mod.make_handler(FakeDesk(), None, lan=True)


# ------------------------------------------------------------- private state
def test_tighten_tree_removes_group_and_other_access(tmp_path):
    root = tmp_path / "state"
    if WINDOWS:
        # Windows has no POSIX mode bits: tighten_tree changes nothing there
        root.mkdir()
        (root / "f").write_text("{}")
        assert tighten_tree(str(root)) == 0
        return
    (root / "drawers" / "ctx-1").mkdir(parents=True)
    f1 = root / "console-audit.jsonl"
    f2 = root / "drawers" / "ctx-1" / "drawer.json"
    for f in (f1, f2):
        f.write_text("{}")
        os.chmod(f, 0o644)
    for d in (root, root / "drawers", root / "drawers" / "ctx-1"):
        os.chmod(d, 0o755)
    os.symlink("/etc/passwd", root / "link")              # a link is not followed or changed
    before = stat.S_IMODE(os.stat("/etc/passwd").st_mode)
    assert tighten_tree(str(root)) == 5
    for p in (root, root / "drawers", root / "drawers" / "ctx-1"):
        assert stat.S_IMODE(os.stat(p).st_mode) == 0o700, p
    for p in (f1, f2):
        assert stat.S_IMODE(os.stat(p).st_mode) == 0o600, p
    assert stat.S_IMODE(os.stat("/etc/passwd").st_mode) == before
    assert tighten_tree(str(root)) == 0                    # nothing left to change
    assert tighten_tree(str(tmp_path / "missing")) == 0


@pytest.mark.skipif(WINDOWS, reason="POSIX modes; not measured on Windows")
def test_the_console_keeps_its_state_private(tmp_path):
    """End to end, in child processes with the common umask (0022):
    1. init, then a session: every file and folder in the state is private.
    2. a folder an earlier version left readable (0755 / 0644) is tightened
       when the console opens it."""
    import subprocess
    state = tmp_path / "state"
    env = dict(os.environ, LISTINGASSISTANTS_STATE_DIR=str(state))
    script = os.path.join(ROOT, "scenes", "scene03_speed_to_lead.jsonl")
    pre = "import os,runpy,sys; os.umask(0o022); sys.argv=sys.argv[1:]; " \
          "runpy.run_path(sys.argv[0], run_name='__main__')"
    console = os.path.join(ROOT, "tools", "console.py")
    r = subprocess.run([sys.executable, "-c", pre, console, "init"],
                       env=env, cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    r = subprocess.run([sys.executable, "-c", pre, console, "session", script,
                        "--config-dir", os.path.join(ROOT, "scenes", "config")],
                       env=env, cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    assert (state / "console-audit.jsonl").exists() and (state / "swarm-state.sqlite").exists()
    readable = []
    for dirpath, dirnames, filenames in os.walk(state):
        for name in [None, *dirnames, *filenames]:
            p = dirpath if name is None else os.path.join(dirpath, name)
            if stat.S_IMODE(os.lstat(p).st_mode) & 0o077:
                readable.append(os.path.relpath(p, state))
    assert readable == [], readable

    # 2. an older, readable folder
    old = state / "drawers" / "ctx-old"
    old.mkdir(parents=True)
    (old / "drawer.json").write_text("{}")
    for p in (state, state / "drawers", old):
        os.chmod(p, 0o755)
    os.chmod(old / "drawer.json", 0o644)
    env = dict(os.environ, LISTINGASSISTANTS_STATE_DIR=str(state))
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "console.py"), "verify"],
                   env=env, cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert stat.S_IMODE(os.stat(old / "drawer.json").st_mode) == 0o600
    assert stat.S_IMODE(os.stat(state).st_mode) == 0o700


# ------------------------------------------------------------- MCP boot probe
def test_the_mcp_boot_check_leaves_no_file_behind():
    """Every MCP boot wrote a conformance-*.jsonl probe log to the temp folder
    and never removed it (4,389 had piled up on one test machine)."""
    import glob
    import tempfile
    pytest.importorskip("mcp")
    from dispatcher import identity_mcp
    pattern = os.path.join(tempfile.gettempdir(), "conformance-*.jsonl*")
    before = set(glob.glob(pattern))
    identity_mcp._boot_conformance()
    assert set(glob.glob(pattern)) - before == set()
