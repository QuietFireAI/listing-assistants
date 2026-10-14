"""The core pin (owner decision D1, 2026-10-14): CORE_PIN.json names the exact
dispatcher-agents commit the 16 vendored files came from. tools/sync_core.py
writes it, refuses to write it from a core with uncommitted changes, and
checks against it; CI checks listing against its pin, not core main."""
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "tools", "sync_core.py")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import sync_core  # noqa: E402


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t",
                           *args], capture_output=True, text=True, check=True).stdout.strip()


def tool(*args):
    return subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True)


@pytest.fixture
def core_and_target(tmp_path):
    core, target = tmp_path / "core", tmp_path / "target"
    (core / "dispatcher").mkdir(parents=True)
    (target / "dispatcher").mkdir(parents=True)
    for name in sync_core.CORE_FILES:
        shutil.copy(os.path.join(ROOT, "dispatcher", name), core / "dispatcher" / name)
    git(core, "init", "-q")
    git(core, "add", "-A")
    git(core, "commit", "-q", "-m", "core")
    return core, target


def test_this_repos_pin_names_a_full_commit_and_the_sixteen_files():
    pin = json.load(open(os.path.join(ROOT, "CORE_PIN.json"), encoding="utf-8"))
    assert re.fullmatch(r"[0-9a-f]{40}", pin["commit"])
    assert pin["files"] == len(sync_core.CORE_FILES) == 16
    assert pin["repo"] == "https://github.com/QuietFireAI/dispatcher-agents"


def test_a_sync_writes_the_pin_and_a_check_holds_the_core_to_it(core_and_target):
    core, target = core_and_target
    r = tool("--core", str(core), "--target", str(target))
    assert r.returncode == 0, r.stderr
    head = git(core, "rev-parse", "HEAD")
    assert json.load(open(target / "CORE_PIN.json"))["commit"] == head
    assert tool("--print-pin", "--target", str(target)).stdout.strip() == head
    r = tool("--core", str(core), "--target", str(target), "--check", "--require-pin")
    assert r.returncode == 0 and "zero drift" in r.stdout
    # core moves on: the pin no longer matches until someone syncs on purpose
    (core / "dispatcher" / "kpi.py").write_text("# changed\n", encoding="utf-8")
    git(core, "commit", "-qam", "move")
    r = tool("--core", str(core), "--target", str(target), "--check", "--require-pin")
    assert r.returncode == 1 and "PIN MISMATCH" in r.stdout


def test_a_core_with_uncommitted_changes_is_refused_and_the_pin_left_alone(core_and_target):
    core, target = core_and_target
    assert tool("--core", str(core), "--target", str(target)).returncode == 0
    before = (target / "CORE_PIN.json").read_text()
    (core / "dispatcher" / "hub.py").write_text("# not committed\n", encoding="utf-8")
    r = tool("--core", str(core), "--target", str(target))
    assert r.returncode == 2 and "uncommitted changes" in r.stderr
    assert (target / "CORE_PIN.json").read_text() == before
    assert (target / "dispatcher" / "hub.py").read_text() != "# not committed\n"


def test_print_pin_without_a_pin_fails(tmp_path):
    r = tool("--print-pin", "--target", str(tmp_path))
    assert r.returncode == 2 and "no CORE_PIN.json" in r.stderr


def test_ci_checks_against_the_pin_not_core_main():
    ci = open(os.path.join(ROOT, ".github", "workflows", "ci.yml"), encoding="utf-8").read()
    # the core-parity job's own block, up to the next job (2026-10-14 cold
    # review: a search of the whole file could be satisfied by any job)
    job = re.search(r"^  core-parity:\n(.*?)(?=^  [a-z-]+:\n)", ci, re.M | re.S).group(1)
    steps = [l.strip() for l in job.splitlines()]
    checkout = next(i for i, l in enumerate(steps) if 'checkout --quiet "$PIN"' in l)
    check = next(i for i, l in enumerate(steps) if "sync_core.py --core /tmp/core --check --require-pin" in l)
    anc = next(i for i, l in enumerate(steps) if "merge-base --is-ancestor" in l)
    assert checkout < check < anc                       # pinned checkout, then the file check, then main
    cond = next(l for l in steps if "if: github.ref == 'refs/heads/main'" in l)
    assert "github.base_ref == 'main'" in cond          # also on pull requests into main
    assert "PIN=$(python tools/sync_core.py --print-pin)" in job


def test_drift_is_counted_in_changed_lines_without_the_diff_program(core_and_target, monkeypatch):
    core, target = core_and_target
    assert tool("--core", str(core), "--target", str(target)).returncode == 0
    with open(target / "dispatcher" / "kpi.py", "a", encoding="utf-8") as f:
        f.write("# local edit\n# another\n")
    r = tool("--core", str(core), "--target", str(target), "--check")
    assert r.returncode == 1 and "kpi.py: 2 diff lines" in r.stdout


def test_check_without_require_pin_says_when_the_commit_differs(core_and_target):
    # 2026-10-14 cold review: it passed a different commit silently
    core, target = core_and_target
    assert tool("--core", str(core), "--target", str(target)).returncode == 0
    (core / "README").write_text("moved\n", encoding="utf-8")
    git(core, "add", "README")
    git(core, "commit", "-qm", "move, dispatcher/ unchanged")
    r = tool("--core", str(core), "--target", str(target), "--check")
    assert r.returncode == 0 and "comparing files only" in r.stdout
    r = tool("--core", str(core), "--target", str(target), "--check", "--require-pin")
    assert r.returncode == 1 and "PIN MISMATCH" in r.stdout


def test_a_damaged_pin_is_a_message_not_a_traceback(tmp_path):
    (tmp_path / "CORE_PIN.json").write_text("{not json", encoding="utf-8")
    r = tool("--print-pin", "--target", str(tmp_path))
    assert r.returncode == 2 and "is not a valid pin" in r.stderr and "Traceback" not in r.stderr
    (tmp_path / "CORE_PIN.json").write_text('{"commit": ""}', encoding="utf-8")
    r = tool("--print-pin", "--target", str(tmp_path))
    assert r.returncode == 2 and "names no commit" in r.stderr


def test_a_sync_rewrites_a_damaged_pin(core_and_target):
    # 2026-10-14 second review: the sync copied the files, then failed on the pin
    core, target = core_and_target
    (target / "CORE_PIN.json").write_text("{not json", encoding="utf-8")
    r = tool("--core", str(core), "--target", str(target))
    assert r.returncode == 0 and "this sync rewrites it" in r.stdout, r.stderr
    assert json.load(open(target / "CORE_PIN.json"))["commit"] == git(core, "rev-parse", "HEAD")
