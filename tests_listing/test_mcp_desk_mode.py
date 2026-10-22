"""The AI assistant inside the running Broker Desk (owner decision 2026-10-22).

Hermes (or any MCP host) mounts dispatcher/identity_mcp.py. By default the
server works inside the broker's RUNNING desk, on the broker's records,
through the desk's door (POST /api/mcp with the token in the private file
desk-mcp.json). One record: what the assistant brings in shows on the desk at
once. The assistant can read and bring in an inquiry; it cannot sign.

These tests run the real pieces: a live desk process, and the MCP server over
stdio through the MCP SDK, the way a host starts it.
"""
import asyncio
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests_listing"))

from test_desk import start, stop  # noqa: E402

mcp = pytest.importorskip("mcp")
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

LOGIN = "broker@example.test"


def _live(tmp_path):
    state = str(tmp_path / "state")
    env = {**os.environ, "LISTINGASSISTANTS_STATE_DIR": state}
    for args in (["init"], ["onboard", "--name", "Test Broker", "--login", LOGIN]):
        out = subprocess.run([sys.executable, "tools/console.py", *args], cwd=ROOT, env=env,
                             capture_output=True, text=True)
        assert out.returncode == 0, out.stdout + out.stderr
    return state


async def _calls(state, calls):
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "dispatcher.identity_mcp"],
        env={**os.environ, "PYTHONPATH": ROOT, "IDENTITY_ROOT": ROOT,
             "LISTINGASSISTANTS_STATE_DIR": state}, cwd=ROOT)
    out = {}
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            out["_tools"] = sorted(t.name for t in (await s.list_tools()).tools)
            for key, name, args in calls:
                res = await s.call_tool(name, args)
                out[key] = json.loads(res.content[0].text)
    return out


def _state(url):
    return json.load(urllib.request.urlopen(url + "api/state"))


def test_the_assistant_works_inside_the_running_desk_on_the_same_record(tmp_path):
    state = _live(tmp_path)
    p, url, port = start([], state)
    try:
        door = json.load(open(os.path.join(state, "desk-mcp.json"), encoding="utf-8"))
        assert door["port"] == port and door["token"]
        out = asyncio.run(_calls(state, [
            ("status", "identity.status", {}),
            ("lead", "identity.submit", {"intent": "lead.inbound", "context_id": "H-1",
                                         "payload": {"channel": "web_form", "name": "Pat Hermes",
                                                     "consent": {"email": "yes"},
                                                     "today": "2026-10-22"}}),
            ("sign", "identity.authority", {"intent": "listing.change.authorized",
                                            "payload": {"to": "05"}}),
            ("other", "identity.submit", {"intent": "listing.authorize", "payload": {}}),
            ("audit", "identity.audit", {}),
        ]))
        assert "identity.status" in out["_tools"]
        assert out["status"]["ok"] and out["status"]["mode"] == "live"
        assert out["lead"]["ok"] and out["lead"]["context_id"] == "H-1"
        assert not out["sign"]["ok"] and "cannot sign" in out["sign"]["reason"]
        assert not out["other"]["ok"] and "Broker Desk" in out["other"]["reason"]
        assert out["audit"]["chain_verified"] is True
        # the same record: the lead is on the desk the broker is looking at
        s = _state(url)
        assert [l["ctx"] for l in s["leads"]] == ["H-1"]
        log = [json.loads(x) for x in open(os.path.join(state, "console-audit.jsonl"), encoding="utf-8")]
        calls = [e for e in log if e.get("kind") == "mcp.call"]
        assert [c["tool"] for c in calls] == ["status", "submit", "submit", "audit"]
        sent = [e for e in log if e.get("kind") == "envelope.persisted" and e.get("intent") == "lead.inbound"]
        assert sent and sent[0]["provenance"]["via"] == "AI assistant (MCP host)"
        assert not [e for e in log if e.get("kind") == "authority.server_signed"]
    finally:
        stop(p)
    assert not os.path.exists(os.path.join(state, "desk-mcp.json")), "the door closes with the desk"


def test_with_no_desk_running_the_assistant_is_told_to_start_it(tmp_path):
    state = _live(tmp_path)
    out = asyncio.run(_calls(state, [("status", "identity.status", {})]))
    assert out["status"]["ok"] is False and "not running" in out["status"]["reason"]


def test_the_door_refuses_a_wrong_token_and_a_browser(tmp_path):
    state = _live(tmp_path)
    p, url, port = start([], state)
    try:
        def post(headers):
            req = urllib.request.Request(url + "api/mcp", method="POST",
                                         data=json.dumps({"tool": "status"}).encode(),
                                         headers={"Content-Type": "application/json", **headers})
            try:
                return urllib.request.urlopen(req).status
            except urllib.error.HTTPError as e:
                return e.code
        token = json.load(open(os.path.join(state, "desk-mcp.json"), encoding="utf-8"))["token"]
        assert post({"X-MCP-Token": "wrong"}) == 403
        assert post({}) == 403
        assert post({"X-MCP-Token": token, "Origin": url.rstrip("/")}) == 403
        assert post({"X-MCP-Token": token}) == 200
    finally:
        stop(p)
