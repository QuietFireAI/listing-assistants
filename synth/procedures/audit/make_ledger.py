#!/usr/bin/env python3
"""make_ledger - one line per statement in the Operating Procedures manual,
for the claim-by-claim audit (owner 2026-10-27: every statement checked
against its source, not from memory).

A statement in the page files is either plain text (not yet audited) or
{"t": text, "src": where it was checked}. src names a code line, a test, a
record entry, a signed decision or a cited web page. The ledger lists every
statement with its source; one with no source is "UNCHECKED".

    python synth/procedures/audit/make_ledger.py          # writes ledger.jsonl, prints counts
"""
import glob
import json
import os
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
PROC = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(PROC))


def resolve(src: str) -> tuple[str, list[str]]:
    """Checks every reference in a source string and pins anchors to lines.
    "path:12-30" must name lines that exist; "path::text" must find text on
    exactly one line of the file and becomes "path:N (text)". Anything else
    (a test id, a decision, a URL, "definition") passes as written.
    Returns (resolved source, problems)."""
    out, problems = [], []
    for ref in [r.strip() for r in src.split(";") if r.strip()]:
        if ref.startswith("run:"):
            # run:P01:05->09 vendor.request  - a step of a recorded playbook run
            _, pid, note = ref.split(":", 2)
            fl = _RUNS.get(pid, {}).get("flow") or []
            if not any(note.strip() == f"{m['from']}->{m['to']} {m['intent']}" for m in fl):
                problems.append(f"{pid}: no step {note.strip()!r} in its recorded run")
            out.append(ref); continue
        if ref.startswith("result:"):
            # result:01-01:VARIANCE - the recorded result of the procedure's run
            _, tid, res = ref.split(":", 2)
            if _EVT.get(tid, {}).get("result") != res.strip():
                problems.append(f"{tid}: recorded result is {_EVT.get(tid, {}).get('result')!r}, not {res.strip()!r}")
            out.append(ref); continue
        if ref.startswith("check:"):
            # check:03-01:escalation.raised - a passing check on the procedure's recorded run
            # check:ID:kind or check:ID:kind:intent (a note in brackets after it is ignored)
            _, tid, rest = ref.split(":", 2)
            rest = rest.split(" (", 1)[0].strip()
            kind, _, intent = rest.partition(":")
            cs = _TCHECKS.get(tid, [])
            if not any(c.get("kind") == kind and c.get("ok") and (not intent or c.get("intent") == intent)
                       for c in cs):
                problems.append(f"{tid}: no passing check {rest!r}")
            out.append(ref); continue
        if ref.startswith(("tuple:", "spec:")):
            # tuple:03-01 - the signed tuple text; spec:03-01 - the test's lines and note
            tid = ref.split(":", 1)[1].strip()
            if tid not in _SPECS:
                problems.append(f"no tuple {tid!r} in synth/tuples/specs")
            out.append(ref); continue
        if ref.startswith("flow:"):
            # flow:03-01:external->11 client.reply  - a message in a procedure's recorded run
            _, tid, note = ref.split(":", 2)
            fl = _TFLOW.get(tid, [])
            if not any(note.strip() == f"{m['from']}->{m['to']} {m['intent']}" for m in fl):
                problems.append(f"{tid}: no message {note.strip()!r} in its recorded run")
            out.append(ref); continue
        if "::" in ref:
            path, anchor = ref.split("::", 1)
            fp = os.path.join(ROOT, path.strip())
            if not os.path.isfile(fp):
                problems.append(f"no file {path}"); out.append(ref); continue
            hits = [i + 1 for i, l in enumerate(open(fp, encoding="utf-8")) if anchor in l]
            if len(hits) != 1:
                problems.append(f"{path}: anchor {anchor!r} found on {len(hits)} lines")
                out.append(ref); continue
            out.append(f"{path.strip()}:{hits[0]} ({anchor})")
            continue
        head = ref.split(" ", 1)[0]
        if ":" in head and head.split(":", 1)[0].endswith((".py", ".json", ".md", ".jsonl", ".html")):
            path, rng = head.split(":", 1)
            fp = os.path.join(ROOT, path)
            if not os.path.isfile(fp):
                problems.append(f"no file {path}")
            else:
                n = sum(1 for _ in open(fp, encoding="utf-8"))
                for part in rng.replace(",", " ").split():
                    try:
                        a, _, b = part.partition("-")
                        if not (1 <= int(a) <= n and (not b or int(a) <= int(b) <= n)):
                            problems.append(f"{path}: lines {part} outside 1-{n}")
                    except ValueError:
                        problems.append(f"{path}: bad line range {part!r}")
        out.append(ref)
    return "; ".join(out), problems
OUT = os.path.join(HERE, "ledger.jsonl")
import sys as _sys
_sys.path.insert(0, os.path.join(ROOT, "synth", "tuples"))
import run_tuples as _rt
_SPECS = {sp["id"]: sp for sp in _rt.load_specs()}
_RUNS = json.load(open(os.path.join(PROC, "evidence_playbooks.json")))["tuples"]
_EVT = json.load(open(os.path.join(PROC, "evidence.json")))["tuples"]
_TCHECKS = {k: v.get("checks", []) for k, v in _EVT.items()}
_TFLOW = {k: v.get("flow", []) for k, v in json.load(open(os.path.join(PROC, "evidence.json")))["tuples"].items()}


def items():
    for a in json.load(open(os.path.join(PROC, "agents.json")))["agents"]:
        pg = "A" + a["id"]
        for f in ("job", "process"):
            yield pg, f, 0, a[f]
        for f in ("steps", "today", "compare", "user_part", "never", "not_built"):
            for i, x in enumerate(a[f]):
                yield pg, f, i, x
    for p in json.load(open(os.path.join(PROC, "playbook_pages.json"))):
        for f in ("purpose", "starts", "ends", "run_note"):
            yield p["id"], f, 0, p[f]
        for i, s in enumerate(p["steps"]):
            t = f"[{s['by']}] {s['text']}"
            yield p["id"], "steps", i, ({"t": t, "src": s["src"]} if s.get("src") else t)
        for f in ("user_decides", "never", "not_built"):
            for i, x in enumerate(p[f]):
                yield p["id"], f, i, x
    o = json.load(open(os.path.join(PROC, "overview.json")))
    for i, x in enumerate(o.get("story", [])):
        yield "W", "story", i, x
    for st in o["stages"]:
        for f in ("business", "system"):
            if f in st:
                yield "W:" + st["id"], f, 0, st[f]
        for i, x in enumerate(st["person"]):
            yield "W:" + st["id"], "person", i, x
    for i, x in enumerate(o["always_person"]):
        yield "W", "always_person", i, x
    for path in sorted(glob.glob(os.path.join(PROC, "pages", "*.json"))):
        for pg in json.load(open(path)):
            for f in ("title", "when", "why", "you_see", "test"):
                if pg.get(f):
                    yield pg["id"], f, 0, pg[f]
            for f in ("steps", "never"):
                for i, x in enumerate(pg.get(f) or []):
                    yield pg["id"], f, i, x
    # "How to read this manual" (guide.json): every statement, in page order
    g = json.load(open(os.path.join(PROC, "guide.json")))
    for si, sec in enumerate(g["sections"]):
        for bi, blk in enumerate(sec["blocks"]):
            for kind in ("p", "ul", "ol", "table", "roles"):
                if kind in blk:
                    items = blk[kind] if isinstance(blk[kind], list) else [blk[kind]]
                    for i, x in enumerate(items):
                        if isinstance(x, dict) and "k" in x:
                            x = {"t": f"{x['k']}: {x['t']}", "src": x.get("src", "")}
                        yield f"GUIDE-{si + 1}", f"{kind}{bi}", i, x


def main():
    n = Counter()
    bad = []
    with open(OUT + ".tmp", "w") as f:
        for page, field, i, v in items():
            t, src = (v["t"], v.get("src", "")) if isinstance(v, dict) else (v, "")
            if src:
                src, problems = resolve(src)
                for pr in problems:
                    bad.append(f"{page}/{field}/{i}: {pr}")
            r = {"id": f"{page}/{field}/{i}", "page": page, "field": field, "i": i,
                 "text": t, "source": src or "UNCHECKED"}
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            n["checked" if src else "unchecked"] += 1
    os.replace(OUT + ".tmp", OUT)
    print(json.dumps(dict(n)))
    for b in bad:
        print("BAD SOURCE", b)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
