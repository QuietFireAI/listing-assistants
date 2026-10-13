"""The day's work on the Broker Desk (added 2026-10-12): every count is a
count of audit-log entries for one local day, and each row carries the
entries behind it. Also: the desk's bundled font is served without the
access code, and only the font."""
import datetime
import json
import os
import sys
import urllib.error
import urllib.request

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)

import desk as desk_mod  # noqa: E402
from test_desk import press_through, start, stop  # noqa: E402


def ts_on(day, hour=12):
    return datetime.datetime.fromisoformat(f"{day}T{hour:02d}:00:00").timestamp()


def env(intent, frm, to, ctx="C1", payload=None, day="2026-10-12", n=0):
    return {"kind": "envelope.persisted", "intent": intent, "from_agent": frm, "to_agent": to,
            "client_context_id": ctx, "payload": payload or {}, "ts": ts_on(day) + n,
            "entry_hash": f"h{intent}{n}{day}"}


def rows(t):
    return {r["key"]: r for g in t["groups"] for r in g["rows"]}


def test_counts_one_day_only_and_lists_the_entries():
    log = [env("client.message.send", "11", "external", n=i) for i in range(3)]
    log += [env("client.message.send", "11", "external", day="2026-10-11", n=9)]
    log += [env("content.verdict", "17", "04", payload={"verdict": "flagged"}, n=1),
            env("content.verdict", "17", "04", payload={"verdict": "approved"}, n=2),
            {"kind": "disclosure.declined", "intent": "campaign.publish", "reason": "wrong photos",
             "client_context_id": "C2", "ts": ts_on("2026-10-12"), "entry_hash": "abc"},
            env("transaction.closed", "07", "14", ctx="S7", n=3),
            env("transaction.closed", "07", "16", ctx="S7", n=4),
            env("transaction.closed", "07", "14", ctx="S7", n=5)]      # the same sale, sent again
    t = desk_mod.day_tally(log, "2026-10-12")
    r = rows(t)
    assert t["days"] == ["2026-10-12", "2026-10-11"]
    assert r["client_messages"]["count"] == 3                     # not the 11th's
    assert r["copy"]["count"] == 2 and r["caught"]["count"] == 1
    assert r["declined"]["count"] == 1 and "wrong photos" in r["declined"]["items"][0]["text"]
    assert r["closed"]["count"] == 1                              # one sale: two agents told, sent twice
    assert r["leads"]["count"] == 0
    assert [i["ts"] for i in r["client_messages"]["items"]] == sorted(
        [i["ts"] for i in r["client_messages"]["items"]], reverse=True)     # newest first
    assert desk_mod.day_tally(log, "2026-10-11")["groups"][0]["rows"][2]["count"] == 1


def test_a_long_day_shows_thirty_entries_and_says_how_many_more():
    log = [env("lead.captured", "01", "02", ctx=f"L{i}", n=i) for i in range(45)]
    r = rows(desk_mod.day_tally(log, "2026-10-12"))["leads"]
    assert r["count"] == 45 and len(r["items"]) == 30 and r["more"] == 15


def test_a_day_with_nothing_still_answers():
    t = desk_mod.day_tally([], "2026-10-12")
    assert t["days"] == ["2026-10-12"]
    assert all(r["count"] == 0 for g in t["groups"] for r in g["rows"])


@pytest.fixture(scope="module")
def played(tmp_path_factory):
    d = desk_mod.Desk(str(tmp_path_factory.mktemp("day") / "show"), showcase=True)
    try:
        press_through(d)
        yield d
    finally:
        d.close()


def test_the_showcase_tally_matches_the_record(played):
    d = played
    s = d.state()
    r = rows(s["day"])
    log = d.sw.hub.audit.read()
    today = datetime.date.today().isoformat()
    todays = [e for e in log if desk_mod.local_day(e["ts"]) == today]
    assert s["day"]["day"] == today
    assert r["client_messages"]["count"] == s["proof"]["client_messages"]
    assert r["released"]["count"] == sum(1 for e in todays if e["kind"] == "disclosure.authorized") \
        == s["proof"]["gated_out_signed"]
    assert r["held"]["count"] == sum(1 for e in todays if e["kind"] == "absolute_signal.hold")
    assert r["files"]["count"] == sum(1 for e in todays if e["kind"] == "drawer.filed") > 0
    assert r["leads"]["count"] == 3 and r["caught"]["count"] == 1 and r["refused"]["count"] == 1
    hashes = {e["entry_hash"][:12] for e in log}
    assert all(i["entry"] in hashes for g in s["day"]["groups"] for row in g["rows"] for i in row["items"])


def test_font_served_without_the_code_and_nothing_else_is(tmp_path):
    p, url, port = start(["--showcase", "--lan"], str(tmp_path / "show"))
    try:
        base = f"http://127.0.0.1:{port}"
        r = urllib.request.urlopen(base + "/fonts/manrope-latin-wght-normal.woff2")
        body = r.read()
        assert r.headers["Content-Type"] == "font/woff2" and body[:4] == b"wOF2"
        assert body == open(os.path.join(ROOT, "tools", "fonts", "manrope-latin-wght-normal.woff2"), "rb").read()
        for bad in ("/fonts/OFL.txt", "/fonts/../desk.py", "/fonts/x.woff2"):
            with pytest.raises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(base + bad)
            assert e.value.code in (403, 404)
        token = url.split("?t=")[1]
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(f"{base}/api/state?t={token}&day=yesterday")
        assert e.value.code == 400
        s = json.load(urllib.request.urlopen(f"{base}/api/state?t={token}&day=2020-01-01"))
        assert s["day"]["day"] == "2020-01-01"
        assert all(r["count"] == 0 for g in s["day"]["groups"] for r in g["rows"])
    finally:
        stop(p)


def test_the_font_and_its_licence_ship_together():
    fonts = os.path.join(ROOT, "tools", "fonts")
    assert "SIL Open Font License" in open(os.path.join(fonts, "OFL.txt"), encoding="utf-8").read()
    page = open(os.path.join(ROOT, "tools", "desk.html"), encoding="utf-8").read()
    for f in desk_mod.FONT_FILES:
        assert os.path.isfile(os.path.join(fonts, f)) and f"fonts/{f}" in page
