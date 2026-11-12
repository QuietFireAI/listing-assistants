"""The demo script is the first thing the documents send a newcomer to.
It must go live, and it must say so honestly.

Found 2026-11-11: tools/run_demo.py printed False for the go-live and still
exited 0. Two causes: it never gave the broker's release for the photographer
booking, and it built Agents 12 and 17 without the brokerage identification
(owner decision 2026-10-14), so the campaign asked a human instead of
publishing. The operator guide's READY TO RECORD line trusts this exit code.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)


def test_demo_completes_every_stage_and_exits_zero():
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "run_demo.py")],
                       capture_output=True, text=True, timeout=300, cwd=ROOT)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    assert "DEMO COMPLETE: every stage above happened." in r.stdout
    assert "[FAILED]" not in r.stdout
    # the stages the old script reported as False
    for stage in ("photo deliverable verified present-and-opens",
                  "status.update(active) reached 11, 12 and 14",
                  "campaign published after the broker's key",
                  "seller told 'you're live'"):
        assert f"[ok    ] {stage}" in r.stdout, stage


def test_demo_exits_nonzero_when_a_stage_does_not_happen(monkeypatch, capsys):
    """Without the brokerage identification Agent 12 asks a human instead of
    publishing. The demo must then name the stages and return 1."""
    import run_demo
    monkeypatch.setattr(run_demo, "BROKERAGE_ID", None)
    assert run_demo.main() == 1
    out = capsys.readouterr().out
    assert "DEMO DID NOT COMPLETE" in out
    assert "[FAILED] campaign published after the broker's key" in out
